#!/usr/bin/env python3

import os
import re
import sys
import time
import subprocess
import json
import _thread

from time import sleep


class Failure(Exception):
    pass


class TPID():
    pid = 0
    tpid = 0
    exe = None
    _stat = None
    __cmd = None
    __ionice = None
    __ioclass = None
    __oom_score_adj = None

    def __init__(self, pid: int, tpid: int):
        self.pid = pid
        self.tpid = tpid
        self.prefix = "/proc/{}/task/{}/".format(pid, tpid)
        self.exe = os.path.realpath("/proc/{}/exe".format(pid))
        self.__oom_score_adj = self.prefix + "/oom_score_adj"

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
            return _status_file.readline().split()[1]

    @property
    def nice(self):
        if not self._stat:
            m = re.search('\\) . .*', self.stat)
            self._stat = m.group(0).rsplit()
        return int(self._stat[17])

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
        ret = subprocess.run(["ionice", "-p", str(tpid)], check=True,
                             stdout=subprocess.PIPE,
                             universal_newlines=True
                             )
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

    _scheds = {
        0: "normal", "normal": 0,
        1: "fifo", "fifo": 1,
        2: "rr", "rr": 2,
        3: "batch", "batch": 3,
        4: "iso", "iso": 4,
        5: "idle", "idle": 5
    }

    @property
    def sched(self):
        if not self._stat:
            m = re.search('\\) . .*', self.stat)
            self._stat = m.group(0).rsplit()
        _sched = int(self._stat[39])
        return self._scheds.get(_sched)


class CgroupController:
    cgroup_fs = "/sys/fs/cgroup/"
    type = "cpu"
    name = ""
    work_path = ""

    ncpu = 1

    period_us = 100000
    quota_us = 100000

    files = {}
    files_mtime = {}
    tasks = {}

    def __init__(self, name, cpuquota):
        self.ncpu = os.cpu_count()
        self.name = name
        self.work_path = self.cgroup_fs + self.type + "/" + self.name

        if not os.path.exists(self.cgroup_fs):
            raise Failure("cgroup fs not mounted")

        if not os.path.exists(self.cgroup_fs + self.type):
            raise Failure("cgroup fs: {} missing".format(self.type))

        if not os.path.exists(self.work_path):
            os.makedirs(self.work_path)

        self.quota_us = self.period_us * self.ncpu * cpuquota / 100
        self.quota_us = int(self.quota_us)
        self.files = {
            'tasks': self.work_path + "/tasks"
        }

        try:
            with open(self.work_path + "/cpu.cfs_period_us", 'w') as fd:
                fd.write(str(self.period_us))
            with open(self.work_path + "/cpu.cfs_quota_us", 'w') as fd:
                fd.write(str(self.quota_us))
        except PermissionError as e:
            raise Failure(e)

        self.files_mtime[self.files["tasks"]] = 0

        _thread.start_new_thread(self.__tread_update_tasks, ())

    def __tread_update_tasks(self):
        tasks_path = self.files["tasks"]
        while True:
            while self.files_mtime[tasks_path] == os.path.getmtime(tasks_path):
                sleep(1)

            self.files_mtime[self.files["tasks"]] = os.path.getmtime(tasks_path)

            tasks = {}
            with open(self.files["tasks"], 'r') as fd:
                for pid in fd.readlines():
                    pid = int(pid.rstrip())
                    tasks[pid] = True
            self.tasks = tasks

    def pid_in_cgroup(self, pid):
        tasks = self.tasks
        if tasks.get(int(pid)):
            return True
        return False

    def add_pid(self, pid):
        try:
            with open(self.files["tasks"], 'w') as _tasks_file:
                _tasks_file.write(str(pid))
        except OSError:
            pass


class Ananicy:
    config_dir = None
    cgroups = {}
    types = {}
    rules = {}

    proc = {}

    check_freq = 5

    verbose = {
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

    def __init__(self, config_dir="/etc/ananicy.d/", daemon=True):
        if daemon:
            self.__check_disks_schedulers()
        self.dir_must_exits(config_dir)
        self.config_dir = config_dir
        self.load_config()
        if not daemon:
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
        if len(tmp) < 1:
            return ""
        return tmp[1].rstrip('"')

    def __check_nice(self, nice):
        if nice:
            if nice > 19 or nice < -20:
                raise Failure("Nice must be in range -20..19")
        return nice

    def __check_ionice(self, ionice):
        if ionice:
            if ionice > 7 or ionice < 0:
                raise Failure("IOnice/IOprio allowed only in range 0-7")
        return ionice

    def __check_oom_score_adj(self, adj):
        if adj:
            if adj < -1000 or adj > 1000:
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
            print("Disk {} not use cfq/bfq scheduler IOCLASS/IONICE will not work on it".format(disk), flush=True)

    def __YN(self, val):
        if val.lower() in ("true", "yes", "1"):
            return True
        else:
            return False

    def load_config(self):
        with open(self.config_dir + "ananicy.conf") as _config_file:
            for line in _config_file:
                line = self.__strip_line(line)
                for col in line.rsplit():
                    if "check_freq=" in col:
                        check_freq = self.__get_val(col)
                        self.check_freq = float(check_freq)
                    if "cgroup_load=" in col:
                        self.verbose["cgroup_load"] = self.__YN(self.__get_val(col))
                    if "type_load=" in col:
                        self.verbose["type_load"] = self.__YN(self.__get_val(col))
                    if "rule_load=" in col:
                        self.verbose["rule_load"] = self.__YN(self.__get_val(col))
                    if "apply_nice=" in col:
                        self.verbose["apply_nice"] = self.__YN(self.__get_val(col))
                    if "apply_ioclass=" in col:
                        self.verbose["apply_ioclass"] = self.__YN(self.__get_val(col))
                    if "apply_ionice=" in col:
                        self.verbose["apply_ionice"] = self.__YN(self.__get_val(col))
                    if "apply_sched=" in col:
                        self.verbose["apply_sched"] = self.__YN(self.__get_val(col))
                    if "apply_oom_score_adj=" in col:
                        self.verbose["apply_oom_score_adj"] = self.__YN(self.__get_val(col))
                    if "apply_cgroup=" in col:
                        self.verbose["apply_cgroup"] = self.__YN(self.__get_val(col))

    def load_cgroups(self):
        files = self.find_files(self.config_dir, '.*\\.cgroups')
        for file in files:
            if self.verbose["cgroup_load"]:
                print("Load cgroup:", file)
            line_number = 1
            with open(file) as _cgroups_file:
                for line in _cgroups_file:
                    try:
                        self.get_cgroup_info(line)
                    except Failure as e:
                        str = "File: {}, Line: {}, Error: {}".format(file, line_number, e)
                        print(str, flush=True)
                    except json.decoder.JSONDecodeError as e:
                        str = "File: {}, Line: {}, Error: {}".format(file, line_number, e)
                        print(str, flush=True)
                    line_number += 1

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
        type = line.get("type")
        if type == "":
            raise Failure('Missing "type": ')

        self.types[type] = {
            "nice": self.__check_nice(line.get("nice")),
            "ioclass": line.get("ioclass"),
            "ionice": self.__check_ionice(line.get("ionice")),
            "sched": line.get("sched"),
            "oom_score_adj": self.__check_oom_score_adj(line.get("oom_score_adj")),
            "cgroup": line.get("cgroup")
        }

    def load_types(self):
        type_files = self.find_files(self.config_dir, '.*\\.types')
        for file in type_files:
            if self.verbose["type_load"]:
                print("Load types:", file)
            line_number = 1
            with open(file) as _types_file:
                for line in _types_file:
                    try:
                        self.get_type_info(line)
                    except Failure as e:
                        str = "File: {}, Line: {}, Error: {}".format(file, line_number, e)
                        print(str, flush=True)
                    except json.decoder.JSONDecodeError as e:
                        str = "File: {}, Line: {}, Error: {}".format(file, line_number, e)
                        print(str, flush=True)
                    line_number += 1

    def get_rule_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        line = json.loads(line, parse_int=int)
        name = line.get("name")
        if name == "":
            raise Failure('Missing "name": ')

        type = line.get("type")
        if type:
            if not self.types.get(type):
                raise Failure('"type": "{}" not defined'.format(type))
            type = self.types[type]
            for attr in ("nice", "ioclass", "ionice", "sched", "oom_score_adj", "cgroup"):
                tmp = type.get(attr)
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
            "oom_score_adj": self.__check_oom_score_adj(line.get("oom_score_adj")),
            "type": line.get("type"),
            "cgroup": cgroup
        }

    def load_rules(self):
        rule_files = self.find_files(self.config_dir, '.*\\.rules')
        for file in rule_files:
            if self.verbose["rule_load"]:
                print("Load rules:", file)
            line_number = 1
            with open(file) as _rules_file:
                for line in _rules_file:
                    try:
                        self.get_rule_info(line)
                    except Failure as e:
                        str = "File: {}, Line: {}, Error: {}".format(file, line_number, e)
                        print(str, flush=True)
                    except json.decoder.JSONDecodeError as e:
                        str = "File: {}, Line: {}, Error: {}".format(file, line_number, e)
                        print(str, flush=True)
                    line_number += 1

        if len(self.rules) == 0:
            raise Failure("No rules loaded")

    def dir_must_exits(self, path):
        if not os.path.exists(path):
            raise Failure("Missing dir: " + path)

    def find_files(self, path, name_mask):
        files = []
        entryes = os.listdir(path)
        if len(entryes) == 0:
            return files
        for entry_name in entryes:
            entry_path = path + "/" + entry_name
            if os.path.isdir(entry_path):
                files += self.find_files(entry_path, name_mask)
            if os.path.isfile(entry_path):
                if re.search(name_mask, entry_name):
                    realpath = os.path.realpath(entry_path)
                    files += [realpath]
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
            pids += [pid]
        return pids

    __kthreads = {}

    def kthreads_update(self):
        __kthreads = {}
        for pid in self.__proc_get_pids():
            try:
                if not os.path.realpath("/proc/{}/exe".format(pid)):
                    __kthreads[pid] = True
            except FileNotFoundError:
                continue
        self.__kthreads = __kthreads

    def thread_kthreads_update(self):
        while False:
            self.kthreads_update()
            sleep(60)

    def proc_get_pids(self):
        pids = []
        for pid in self.__proc_get_pids():
            if self.__kthreads.get(pid):
                continue
            try:
                if not os.path.realpath("/proc/{}/exe".format(pid)):
                    continue
                mtime = os.path.getmtime("/proc/{}".format(pid)) + self.check_freq
                if mtime > time.time():
                    continue
            except FileNotFoundError:
                continue
            pids += [pid]
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

            tpids += [tpid]
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
        subprocess.run(["renice", "-n", str(nice), "-p", str(pid)], stdout=subprocess.DEVNULL)

    def renice(self, tpid: int, nice: int, name: str):
        p_tpid = self.proc[tpid]
        c_nice = p_tpid.nice
        if not name:
            name = p_tpid.cmd
        if c_nice == nice:
            return
        self.renice_cmd(tpid, nice)
        msg = "renice: {}[{}/{}] {} -> {}".format(name, p_tpid.pid, tpid, c_nice, nice)
        if self.verbose["apply_nice"]:
            print(msg, flush=True)

    def ioclass_cmd(self, pid: int, ioclass: str):
        subprocess.run(["ionice", "-p", str(pid), "-c", ioclass], stdout=subprocess.DEVNULL)

    def ioclass(self, tpid: int, ioclass: str, name: str):
        p_tpid = self.proc[tpid]
        c_ioclass = p_tpid.ioclass
        if not name:
            name = p_tpid.cmd
        if ioclass != c_ioclass:
            self.ioclass_cmd(tpid, ioclass)
            msg = "ioclass: {}[{}/{}] {} -> {}".format(p_tpid.cmd, p_tpid.pid, tpid, c_ioclass, ioclass)
            if self.verbose["apply_ioclass"]:
                print(msg, flush=True)

    def ionice_cmd(self, pid: int, ionice: int):
        subprocess.run(["ionice", "-p", str(pid), "-n", str(ionice)], stdout=subprocess.DEVNULL)

    def ionice(self, tpid, ionice, name: str):
        p_tpid = self.proc[tpid]
        c_ionice = p_tpid.ionice
        if c_ionice is None:
            return
        if not name:
            name = p_tpid.cmd
        if str(ionice) != c_ionice:
            self.ionice_cmd(tpid, ionice)
            msg = "ionice: {}[{}/{}] {} -> {}".format(p_tpid.cmd, p_tpid.pid, tpid, c_ionice, ionice)
            if self.verbose["apply_ionice"]:
                print(msg, flush=True)

    def oom_score_adj(self, tpid, oom_score_adj, name: str):
        p_tpid = self.proc[tpid]
        c_oom_score_adj = p_tpid.oom_score_adj
        if not name:
            name = p_tpid.cmd
        if c_oom_score_adj != oom_score_adj:
            p_tpid.oom_score_adj = oom_score_adj
            msg = "oom_score_adj: {}[{}/{}] {} -> {}".format(p_tpid.cmd, p_tpid.pid, tpid,
                                                             c_oom_score_adj, oom_score_adj)
            if self.verbose["apply_oom_score_adj"]:
                print(msg, flush=True)

    def sched_cmd(self, pid: int, sched: str, l_prio: int = None):
        arg_map = {
            'other': '-N', 'normal': '-N',
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

    def sched(self, tpid, sched, name):
        p_tpid = self.proc[tpid]
        l_prio = None
        c_sched = p_tpid.sched
        if not name:
            name = p_tpid.cmd
        if not c_sched or c_sched == sched:
            return
        if sched == "other" and c_sched == "normal":
            return
        if sched == "rr" or sched == "fifo":
            l_prio = 1
        self.sched_cmd(p_tpid.tpid, sched, l_prio)
        msg = "sched: {}[{}/{}] {} -> {}".format(p_tpid.cmd, p_tpid.pid, tpid, c_sched, sched)
        if self.verbose["apply_sched"]:
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
            if rule.get("nice"):
                self.renice(tpid, rule["nice"], rule_name)
            if rule.get("ioclass"):
                self.ioclass(tpid, rule["ioclass"], rule_name)
            if rule.get("ionice"):
                self.ionice(tpid, rule["ionice"], rule_name)
            if rule.get("sched"):
                self.sched(tpid, rule["sched"], rule_name)
            if rule.get("oom_score_adj"):
                self.oom_score_adj(tpid, rule["oom_score_adj"], rule_name)
        except subprocess.CalledProcessError:
            return
        except FileNotFoundError:
            return

        cgroup = rule.get("cgroup")
        if cgroup:
            cgroup_ctrl = self.cgroups[cgroup]
            if not cgroup_ctrl.pid_in_cgroup(tpid):
                cgroup_ctrl.add_pid(tpid)
                msg = "Cgroup: {}[{}] added to {}".format(rule_name, tpid, cgroup_ctrl.name)
                if self.verbose["apply_cgroup"]:
                    print(msg)

    def run(self):
        _thread.start_new_thread(self.thread_kthreads_update, ())
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
        cgroups_dict = {}
        for cgroup in self.cgroups:
            cgroups_dict[cgroup] = self.cgroups[cgroup].__dict__

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
                    "sched": TPID_l.sched,
                    "ionice": [TPID_l.ioclass, TPID_l.ionice],
                    "oom_score_adj": TPID_l.oom_score_adj,
                    "cmdline": TPID_l.cmdline,
                }
            except FileNotFoundError:
                continue

        print(json.dumps(proc_dict, indent=4), flush=True)


def help():
    print("Usage: ananicy [options]\n",
          "  start         Run script\n",
          "  dump rules    Generate and print rules cache to stdout\n",
          "  dump types    Generate and print types cache to stdout\n",
          "  dump cgroups  Generate and print cgroups cache to stdout\n",
          "  dump proc     Generate and print proc map cache to stdout", flush=True)
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
    except PermissionError as e:
        print("You are root?: {}".format(e))


if __name__ == '__main__':
    main(sys.argv)
