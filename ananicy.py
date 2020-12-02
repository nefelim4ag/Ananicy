#!/usr/bin/env python3

import os
import re
import sys
import time
import subprocess
import json
import _thread

from enum import Enum, unique
from time import sleep


class Failure(Exception):
    pass


@unique
class ProcSchedulerPolicy(Enum):
    NORMAL = 0
    FIFO = 1
    RR = 2
    BATCH = 3
    ISO = 4
    IDLE = 5
    DEADLINE = 6
    OTHER = 99

    @classmethod
    def _missing_(cls, value):
        return ProcSchedulerPolicy.OTHER


class TPID:

    def __init__(self, pid: int, tpid: int):
        self.pid = pid
        self.tpid = tpid
        self.prefix = "/proc/{}/task/{}/".format(pid, tpid)
        self.parent = "/proc/{}/".format(pid)
        self.exe = os.path.realpath("/proc/{}/exe".format(pid))
        self.__oom_score_adj = self.prefix + "/oom_score_adj"

        self._stat = None
        self.__cmd = None
        self.__ionice = None
        self.__ioclass = None

    @property
    def cmd(self):
        if not self.__cmd:
            _exe = self.exe.split('/')
            self.__cmd = _exe[-1]
        return self.__cmd

    @property
    def oom_score_adj(self):
        with open(self.__oom_score_adj, 'r') as _oom_score_adj_file:
            return int(_oom_score_adj_file.readline().rstrip())

    @oom_score_adj.setter
    def oom_score_adj(self, oom_score_adj):
        with open(self.__oom_score_adj, 'w') as _oom_score_adj_file:
            _oom_score_adj_file.write(str(oom_score_adj))

    @property
    def stat(self):
        with open(self.prefix + "/stat") as _stat_file:
            return _stat_file.readline().strip()

    @property
    def stat_name(self):
        with open(self.prefix + "/status") as _status_file:
            try:
                name_line = _status_file.readline()
                line_list = name_line.split()
                if line_list:
                    return line_list[1]
            except (UnicodeDecodeError, IndexError):
                pass
            return ""

    @property
    def nice(self):
        return os.getpriority(os.PRIO_PROCESS, self.tpid)

    @property
    def autogroup(self):
        try:
            with open(self.parent + "/autogroup", 'r') as _autogroup:
                autogroup = _autogroup.readline().strip('/\n').split(" nice ")
        except FileNotFoundError:
            return None
        group_num = int(autogroup[0].split('-')[1])
        nice = int(autogroup[1])
        return { "group": group_num, "nice": nice }

    @autogroup.setter
    def autogroup(self, autogroup_nice):
        try:
            with open(self.parent + "/autogroup", 'w') as _autogroup:
                _autogroup.write(str(autogroup_nice))
        except FileNotFoundError:
            pass

    @property
    def cmdline(self):
        # read command line
        with open(self.prefix + '/cmdline', mode='rb') as cmdline_file:
            _cmdline = cmdline_file.read()
        # remove null character from end
        if len(_cmdline) > 0 and _cmdline[-1] == 0:
            _cmdline = _cmdline[:-1]
        # split on null characters
        _cmdline = _cmdline.split(b'\x00')
        # convert arguments from bytes to strings
        return tuple(arg.decode() for arg in _cmdline)

    def __ionice_cmd(self, tpid):
        ret = subprocess.run(["ionice", "-p", str(tpid)],
                             check=True,
                             stdout=subprocess.PIPE,
                             universal_newlines=True)
        return ret

    def __get_ioprop(self):
        ret = self.__ionice_cmd(self.tpid)
        stdout = ret.stdout.rsplit(': prio ')
        self.__ioclass = stdout[0].rstrip()
        if self.__ioclass == "none":
            self.__ioclass = "best-effort"
        # can return only ioclass, if process class are idle
        if len(stdout) == 2:
            self.__ionice = stdout[1].rstrip()
        else:
            self.__ionice = None

    @property
    def ioclass(self):
        if not self.__ioclass:
            self.__get_ioprop()
        return self.__ioclass

    @property
    def ionice(self):
        if not self.__ionice:
            self.__get_ioprop()
        return self.__ionice

    @property
    def sched(self):
        if not self._stat:
            m = re.search('\\) . .*', self.stat)
            self._stat = m.group(0).rsplit()
        _sched = int(self._stat[39])
        return ProcSchedulerPolicy(_sched).name.lower()

    @property
    def rtprio(self):
        if not self._stat:
            m = re.search('\\) . .*', self.stat)
            self._stat = m.group(0).rsplit()
        return int(self._stat[38])


class CgroupController:
    PERIOD_US = 100000
    CGROUP_FS = "/sys/fs/cgroup/"
    TYPE = "cpu"

    def __init__(self, name, cpuquota):
        if not os.path.exists(self.CGROUP_FS):
            raise Failure("cgroup fs not mounted")

        if not os.path.exists(self.CGROUP_FS + self.TYPE):
            raise Failure("cgroup fs: {} missing".format(self.TYPE))

        self.name = name
        self.work_path = self.CGROUP_FS + self.TYPE + "/" + self.name
        if not os.path.exists(self.work_path):
            os.makedirs(self.work_path)

        self.ncpu = os.cpu_count()
        self.quota_us = self.PERIOD_US * self.ncpu * cpuquota // 100
        self.cpu_shares = 1024 * cpuquota // 100
        self.tasks = dict()
        self.files = {'tasks': self.work_path + "/tasks"}

        try:
            with open(self.work_path + "/cpu.cfs_period_us", 'w') as fd:
                fd.write(str(self.PERIOD_US))
            with open(self.work_path + "/cpu.cfs_quota_us", 'w') as fd:
                fd.write(str(self.quota_us))
            with open(self.work_path + "/cpu.shares", 'w') as fd:
                fd.write(str(self.cpu_shares))
        except PermissionError as e:
            raise Failure(e)

        self.files_mtime = {self.files["tasks"]: 0.0}

        _thread.start_new_thread(self.__tread_update_tasks, ())

    def __tread_update_tasks(self):
        tasks_path = self.files["tasks"]
        while True:
            while self.files_mtime[tasks_path] == os.path.getmtime(tasks_path):
                sleep(1)

            self.files_mtime[self.files["tasks"]] = os.path.getmtime(
                tasks_path)

            tasks = {}
            with open(self.files["tasks"], 'r') as fd:
                for pid in fd.readlines():
                    pid = int(pid.strip())
                    tasks[pid] = True
            self.tasks = tasks

    def pid_in_cgroup(self, pid):
        return bool(self.tasks.get(int(pid)))

    def add_pid(self, pid):
        try:
            with open(self.files["tasks"], 'w') as _tasks_file:
                _tasks_file.write(str(pid))
        except OSError:
            pass


class Ananicy:
    def __init__(self, config_dir="/etc/ananicy.d/", daemon=True):
        self.dir_must_exits(config_dir)
        self.config_dir = config_dir
        self.cgroups = {}
        self.types = {}
        self.rules = {}
        self.proc = {}
        self.check_freq = 5
        self.verbose = {
            "cgroup_load": True,
            "type_load": True,
            "rule_load": True,
            "apply_nice": True,
            "apply_ioclass": True,
            "apply_ionice": True,
            "apply_sched": True,
            "apply_oom_score_adj": True,
            "apply_cgroup": True
        }

        self.load_config()
        if daemon:
            self.__check_disks_schedulers()
        else:
            for i in self.verbose:
                self.verbose[i] = False

        self.load_cgroups()
        self.load_types()
        self.load_rules()
        if os.getenv("NOTIFY_SOCKET"):
            subprocess.run(["systemd-notify", "--ready"])

    def __strip_line(self, line):
        line = line.rstrip()
        # Remove comments from input
        line = line.split('#')
        return line[0]

    def __get_val(self, col):
        tmp = col.split('=')
        if not tmp:
            return ""
        return tmp[1].rstrip('"')

    def __check_nice(self, nice):
        if nice:
            if not -20 <= nice <= 19:
                raise Failure("Nice must be in range -20..19")
        return nice

    def __check_ionice(self, ionice):
        if ionice:
            if not 0 <= ionice <= 7:
                raise Failure("IOnice/IOprio allowed only in range 0-7")
        return ionice

    def __check_rtprio(self, rtprio):
        if rtprio:
            if not 1 <= rtprio <= 99:
                raise Failure("RTprio allowed only in range 1-99")
        return rtprio

    def __check_oom_score_adj(self, adj):
        if adj:
            if not -1000 <= adj <= 1000:
                raise Failure("OOM_SCORE_ADJ must be in range -1000..1000")
        return adj

    def __check_disks_schedulers(self):
        prefix = "/sys/class/block/"
        for disk in os.listdir(prefix):
            if re.search('loop', disk):
                continue
            if re.search('ram', disk):
                continue
            if re.search('sr', disk):
                continue
            scheduler = prefix + disk + "/queue/scheduler"
            if not os.path.exists(scheduler):
                continue
            with open(scheduler) as fd:
                c_sched = fd.readlines()
                c_sched = c_sched[0].rstrip()
                if re.search('\\[cfq\\]', c_sched):
                    continue
                if re.search('\\[bfq\\]', c_sched):
                    continue
                if re.search('\\[bfq-mq\\]', c_sched):
                    continue

            msg = "Disk {} not use cfq/bfq scheduler IOCLASS/IONICE will not work on it".format(
                disk)
            if self.verbose["check_disks_schedulers"]:
                print(msg, flush=True)

    def __YN(self, val):
        return val.lower() in ("true", "yes", "1")

    def load_config(self):
        with open(self.config_dir + "ananicy.conf") as _config_file:
            for line in _config_file:
                line = self.__strip_line(line)
                for col in line.rsplit():
                    if "check_freq=" in col:
                        check_freq = self.__get_val(col)
                        self.check_freq = float(check_freq)
                    if "cgroup_load=" in col:
                        self.verbose["cgroup_load"] = self.__YN(
                            self.__get_val(col))
                    if "type_load=" in col:
                        self.verbose["type_load"] = self.__YN(
                            self.__get_val(col))
                    if "rule_load=" in col:
                        self.verbose["rule_load"] = self.__YN(
                            self.__get_val(col))
                    if "apply_nice=" in col:
                        self.verbose["apply_nice"] = self.__YN(
                            self.__get_val(col))
                    if "apply_ioclass=" in col:
                        self.verbose["apply_ioclass"] = self.__YN(
                            self.__get_val(col))
                    if "apply_ionice=" in col:
                        self.verbose["apply_ionice"] = self.__YN(
                            self.__get_val(col))
                    if "apply_sched=" in col:
                        self.verbose["apply_sched"] = self.__YN(
                            self.__get_val(col))
                    if "apply_oom_score_adj=" in col:
                        self.verbose["apply_oom_score_adj"] = self.__YN(
                            self.__get_val(col))
                    if "apply_cgroup=" in col:
                        self.verbose["apply_cgroup"] = self.__YN(
                            self.__get_val(col))
                    if "check_disks_schedulers" in col:
                        self.verbose["check_disks_schedulers"] = self.__YN(
                            self.__get_val(col))

    def load_cgroups(self):
        files = self.find_files(self.config_dir, '.*\\.cgroups')
        for file in files:
            if self.verbose["cgroup_load"]:
                print("Load cgroup:", file)
            with open(file) as _cgroups_file:
                for line_number, line in enumerate(_cgroups_file, start=1):
                    try:
                        self.get_cgroup_info(line)
                    except Failure as e:
                        str = "File: {}, Line: {}, Error: {}".format(
                            file, line_number, e)
                        print(str, flush=True)
                    except json.decoder.JSONDecodeError as e:
                        str = "File: {}, Line: {}, Error: {}".format(
                            file, line_number, e)
                        print(str, flush=True)

    def get_cgroup_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        line = json.loads(line, parse_int=int)
        cgroup = line.get("cgroup")
        if not cgroup:
            raise Failure('Missing "cgroup": ')

        cpuquota = line.get("CPUQuota")
        if not cpuquota:
            raise Failure('Missing "CPUQuota": ')

        self.cgroups[cgroup] = CgroupController(cgroup, cpuquota)

    def get_type_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        line = json.loads(line, parse_int=int)
        _type = line.get("type")
        if not _type:
            raise Failure('Missing "type": ')

        self.types[_type] = {
            "nice": self.__check_nice(line.get("nice")),
            "ioclass": line.get("ioclass"),
            "ionice": self.__check_ionice(line.get("ionice")),
            "sched": line.get("sched"),
            "rtprio": self.__check_rtprio(line.get("rtprio")),
            "oom_score_adj": self.__check_oom_score_adj(
                line.get("oom_score_adj")),
            "cgroup": line.get("cgroup")
        }

    def load_types(self):
        type_files = self.find_files(self.config_dir, '.*\\.types')
        for file in type_files:
            if self.verbose["type_load"]:
                print("Load types:", file)
            with open(file) as _types_file:
                for line_number, line in enumerate(_types_file, start=1):
                    try:
                        self.get_type_info(line)
                    except Failure as e:
                        out = "File: {}, Line: {}, Error: {}".format(
                            file, line_number, e)
                        print(out, flush=True)
                    except json.decoder.JSONDecodeError as e:
                        out = "File: {}, Line: {}, Error: {}".format(
                            file, line_number, e)
                        print(out, flush=True)

    def get_rule_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        line = json.loads(line, parse_int=int)
        name = line.get("name")
        if name == "":
            raise Failure('Missing "name": ')

        _type = line.get("type")
        if _type:
            if not self.types.get(_type):
                raise Failure('"type": "{}" not defined'.format(_type))
            _type = self.types[_type]
            for attr in ("nice", "ioclass", "ionice", "sched", "rtprio",
                         "oom_score_adj", "cgroup"):
                tmp = _type.get(attr)
                if not tmp:
                    continue
                if not line.get(attr):
                    line[attr] = tmp

        cgroup = line.get("cgroup")
        if not self.cgroups.get(cgroup):
            cgroup = None

        self.rules[name] = {
            "nice": self.__check_nice(line.get("nice")),
            "ioclass": line.get("ioclass"),
            "ionice": self.__check_ionice(line.get("ionice")),
            "sched": line.get("sched"),
            "rtprio": self.__check_rtprio(line.get("rtprio")),
            "oom_score_adj": self.__check_oom_score_adj(
                line.get("oom_score_adj")),
            "type": line.get("type"),
            "cgroup": cgroup
        }

    def load_rules(self):
        rule_files = self.find_files(self.config_dir, '.*\\.rules')
        for file in rule_files:
            if self.verbose["rule_load"]:
                print("Load rules:", file)
            with open(file) as _rules_file:
                for line_number, line in enumerate(_rules_file, start=1):
                    try:
                        self.get_rule_info(line)
                    except Failure as e:
                        out = "File: {}, Line: {}, Error: {}".format(
                            file, line_number, e)
                        print(out, flush=True)
                    except json.decoder.JSONDecodeError as e:
                        out = "File: {}, Line: {}, Error: {}".format(
                            file, line_number, e)
                        print(out, flush=True)

        if not self.rules:
            raise Failure("No rules loaded")

    def dir_must_exits(self, path):
        if not os.path.exists(path):
            raise Failure("Missing dir: " + path)

    def find_files(self, path, name_mask):
        files = []
        entries = sorted(os.listdir(path))
        if not entries:
            return files
        for entry_name in entries:
            entry_path = path + "/" + entry_name
            if os.path.isdir(entry_path):
                files += self.find_files(entry_path, name_mask)
            if os.path.isfile(entry_path):
                if re.search(name_mask, entry_name):
                    realpath = os.path.realpath(entry_path)
                    files.append(realpath)
        return files

    def __proc_get_pids(self):
        pids = []
        for pid in os.listdir("/proc"):
            try:
                pid = int(pid)
            except ValueError:
                continue
            if not os.path.isdir("/proc/{}".format(pid)):
                continue
            pids.append(pid)
        return pids

    def proc_get_pids(self):
        pids = []
        for pid in self.__proc_get_pids():
            try:
                if not os.path.realpath("/proc/{}/exe".format(pid)):
                    continue
                mtime = os.path.getmtime(
                    "/proc/{}".format(pid)) + self.check_freq
                if mtime > time.time():
                    continue
            except (FileNotFoundError, ProcessLookupError):
                continue
            pids.append(pid)
        return pids

    def pid_get_tpid(self, pid):
        tpids = []
        path = "/proc/{}/task/".format(pid)
        for tpid in os.listdir(path):
            try:
                tpid = int(tpid)
            except ValueError:
                continue

            path = "/proc/{}/task/{}".format(pid, tpid)
            try:
                mtime = os.path.getmtime(path) + self.check_freq
            except FileNotFoundError:
                continue
            if mtime > time.time():
                continue

            tpids.append(tpid)
        return tpids

    def proc_map_update(self):
        proc = {}
        for pid in self.proc_get_pids():
            try:
                for tpid in self.pid_get_tpid(pid):
                    proc[tpid] = TPID(pid, tpid)
            except FileNotFoundError:
                continue
        self.proc = proc

    def renice_cmd(self, pid: int, nice: int):
        subprocess.run(
            ["renice", "-n", str(nice), "-p",
             str(pid)],
            stdout=subprocess.DEVNULL)

    def renice(self, tpid: int, nice: int, name: str):
        p_tpid = self.proc[tpid]
        c_nice = p_tpid.nice
        if not name:
            name = p_tpid.cmd
        if c_nice == nice:
            return
        os.setpriority(os.PRIO_PROCESS, tpid, nice)
        self.renice_cmd(tpid, nice)
        msg = "renice: {}[{}/{}] {} -> {}".format(name, p_tpid.pid, tpid,
                                                  c_nice, nice)
        if self.verbose["apply_nice"]:
            print(msg, flush=True)

    def ionice(self, tpid, ioclass, ionice, name: str):
        p_tpid = self.proc[tpid]
        if not name:
            name = p_tpid.cmd
        args = []
        msg_ioclass = False
        msg_ionice = False
        if ionice is not None:
            c_ionice = p_tpid.ionice
            if c_ionice is not None and str(ionice) != c_ionice:
                if ioclass is not None:
                    args.extend(("-c", str(ioclass)))
                    c_ioclass = p_tpid.ioclass
                    if c_ioclass is not None and str(ioclass) != c_ioclass:
                        msg_ioclass = True
                args.extend(("-n", str(ionice)))
                msg_ionice = True
        if not args and ioclass is not None:
            c_ioclass = p_tpid.ioclass
            if c_ioclass is not None and str(ioclass) != c_ioclass:
                args.extend(("-c", str(ioclass)))
                msg_ioclass = True
        if args:
            subprocess.run(
                ["ionice", "-p", str(tpid), *args],
                stdout=subprocess.DEVNULL)
        if msg_ioclass and self.verbose["apply_ioclass"]:
            msg = "ioclass: {}[{}/{}] {} -> {}".format(
                p_tpid.cmd, p_tpid.pid, tpid, c_ioclass, ioclass)
            print(msg, flush=True)
        if msg_ionice and self.verbose["apply_ionice"]:
            msg = "ionice: {}[{}/{}] {} -> {}".format(
                p_tpid.cmd, p_tpid.pid, tpid, c_ionice, ionice)
            print(msg, flush=True)

    def oom_score_adj(self, tpid, oom_score_adj, name: str):
        p_tpid = self.proc[tpid]
        c_oom_score_adj = p_tpid.oom_score_adj
        if not name:
            name = p_tpid.cmd
        if c_oom_score_adj != oom_score_adj:
            p_tpid.oom_score_adj = oom_score_adj
            msg = "oom_score_adj: {}[{}/{}] {} -> {}".format(
                p_tpid.cmd, p_tpid.pid, tpid, c_oom_score_adj, oom_score_adj)
            if self.verbose["apply_oom_score_adj"]:
                print(msg, flush=True)

    def sched_cmd(self, pid: int, sched: str, l_prio: int = None):
        arg_map = {
            'other': '-N',
            'normal': '-N',
            'rr': '-R',
            'fifo': '-F',
            'batch': '-B',
            'iso': '-I',
            'idle': '-D'
        }
        sched_arg = arg_map[sched]
        cmd = ["schedtool", sched_arg]
        if l_prio:
            cmd += ["-p", str(l_prio)]
        cmd += [str(pid)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL)

    def sched(self, tpid, sched, rtprio, name):
        p_tpid = self.proc[tpid]
        l_prio = None
        c_sched = p_tpid.sched
        c_rtprio = p_tpid.rtprio
        if not name:
            name = p_tpid.cmd
        if not c_sched or (c_sched == sched
                           and (rtprio is None or c_rtprio == rtprio)):
            return
        if sched == "other" and c_sched == "normal":
            return
        if sched == "rr" or sched == "fifo":
            l_prio = rtprio or 1
        self.sched_cmd(p_tpid.tpid, sched, l_prio)
        msg = "sched: {}[{}/{}] {} -> {}".format(p_tpid.cmd, p_tpid.pid, tpid,
                                                 c_sched, sched)
        if self.verbose["apply_sched"]:
            print(msg)

    def apply_rule(self, tpid, rule, rule_name):
        if rule.get("nice"):
            self.renice(tpid, rule["nice"], rule_name)
        if rule.get("ioclass") or rule.get("ionice"):
            self.ionice(tpid, rule.get("ioclass"), rule.get("ionice"),
                        rule_name)
        if rule.get("sched"):
            self.sched(tpid, rule["sched"], rule["rtprio"], rule_name)
        if rule.get("oom_score_adj"):
            self.oom_score_adj(tpid, rule["oom_score_adj"], rule_name)

        cgroup = rule.get("cgroup")
        if not cgroup:
            return

        cgroup_ctrl = self.cgroups[cgroup]
        if not cgroup_ctrl.pid_in_cgroup(tpid):
            cgroup_ctrl.add_pid(tpid)
            msg = "Cgroup: {}[{}] added to {}".format(
                rule_name, tpid, cgroup_ctrl.name)
            if self.verbose["apply_cgroup"]:
                print(msg)

    def process_tpid(self, tpid):
        # proc entry
        pe = self.proc.get(tpid)
        if not os.path.exists("/proc/{}/task/{}".format(pe.pid, pe.tpid)):
            return

        rule_name = pe.cmd
        rule = self.rules.get(rule_name)
        if not rule:
            rule_name = pe.stat_name
            rule = self.rules.get(rule_name)
        if not rule:
            return

        try:
            self.apply_rule(tpid, rule, rule_name)
        except subprocess.CalledProcessError:
            return
        except FileNotFoundError:
            return

    def run(self):
        while True:
            self.proc_map_update()
            for tpid in self.proc:
                try:
                    self.process_tpid(tpid)
                except ProcessLookupError:
                    pass
            sleep(self.check_freq)

    def dump_types(self):
        print(json.dumps(self.types, indent=4), flush=True)

    def dump_cgroups(self):
        cgroups_dict = {
            cgroup: self.cgroups[cgroup].__dict__ for cgroup in self.cgroups
        }
        print(json.dumps(cgroups_dict, indent=4), flush=True)

    def dump_rules(self):
        print(json.dumps(self.rules, indent=4), flush=True)

    def dump_proc(self):
        self.proc_map_update()
        proc_dict = {}
        for tpid in self.proc:
            try:
                TPID_l = self.proc[tpid]
                proc_dict[tpid] = {
                    "pid": TPID_l.pid,
                    "tpid": TPID_l.tpid,
                    "exe": TPID_l.exe,
                    "cmd": TPID_l.cmd,
                    "stat": TPID_l.stat,
                    "stat_name": TPID_l.stat_name,
                    "nice": TPID_l.nice,
                    "autogroup": TPID_l.autogroup,
                    "sched": TPID_l.sched,
                    "rtprio": TPID_l.rtprio,
                    "ionice": [TPID_l.ioclass, TPID_l.ionice],
                    "oom_score_adj": TPID_l.oom_score_adj,
                    "cmdline": TPID_l.cmdline,
                }
            except FileNotFoundError:
                continue

        print(json.dumps(proc_dict, indent=4), flush=True)

    def dump_autogroup(self):
        self.proc_map_update()
        proc_autogroup = {}
        for tpid in self.proc:
            try:
                TPID_l = self.proc[tpid]
                group_num = TPID_l.autogroup["group"]
                proc_autogroup[group_num] = {
                    "nice": TPID_l.autogroup["nice"],
                    "proc": {}
                }
            except FileNotFoundError:
                continue

        for tpid in self.proc:
            try:
                TPID_l = self.proc[tpid]
                group_num = TPID_l.autogroup["group"]
                proc_autogroup[group_num]["proc"][tpid] = {
                    "pid": TPID_l.pid,
                    "tpid": TPID_l.tpid,
                    "exe": TPID_l.exe,
                    "cmd": TPID_l.cmd,
                    "stat": TPID_l.stat,
                    "stat_name": TPID_l.stat_name,
                    "nice": TPID_l.nice,
                    "sched": TPID_l.sched,
                    "ionice": [TPID_l.ioclass, TPID_l.ionice],
                    "oom_score_adj": TPID_l.oom_score_adj,
                    "cmdline": TPID_l.cmdline,
                }
            except FileNotFoundError:
                continue

        print(json.dumps(proc_autogroup, indent=4), flush=True)


def help():
    print(
        "Usage: ananicy [options]\n",
        "  start          Run script\n",
        "  dump rules     Generate and print rules cache to stdout\n",
        "  dump types     Generate and print types cache to stdout\n",
        "  dump cgroups   Generate and print cgroups cache to stdout\n",
        "  dump proc      Generate and print proc map cache to stdout\n",
        "  dump autogroup Generate and print autogroup tree",
        flush=True)
    exit(0)


def main(argv):

    if len(argv) < 2:
        help()

    try:
        if argv[1] == "start":
            daemon = Ananicy()
            daemon.run()

        if argv[1] == "dump":
            daemon = Ananicy(daemon=False)
            if len(argv) < 3:
                help()
            if argv[2] == "rules":
                daemon.dump_rules()
            if argv[2] == "types":
                daemon.dump_types()
            if argv[2] == "cgroups":
                daemon.dump_cgroups()
            if argv[2] == "proc":
                daemon.dump_proc()
            if argv[2] == "autogroup":
                daemon.dump_autogroup()
    except PermissionError as e:
        print("You are root?: {}".format(e))


if __name__ == '__main__':
    main(sys.argv)
