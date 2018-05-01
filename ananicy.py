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

    def run_cmd(self, run):
        ret = subprocess.run(run, timeout=30, check=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True
                             )
        return ret

    @property
    def cmd(self):
        if not self.__cmd:
            _exe = self.exe.split('/')
            self.__cmd = _exe[-1]
        return self.__cmd

    @property
    def oom_score_adj(self):
        _oom_score_adj = open(self.__oom_score_adj, 'r').readline()
        return int(_oom_score_adj.rstrip())

    def set_oom_score_adj(self, oom_score_adj):
        with open(self.__oom_score_adj, 'w') as fd:
            fd.write(str(oom_score_adj))

    @property
    def stat(self):
        return open(self.prefix + "/stat").readline().rstrip()

    @property
    def nice(self):
        stat = self.stat
        m = re.search('\\) . .*', stat)
        m = m.group(0)
        m = m.rsplit()
        return int(m[17])

    @property
    def cmdline(self):
        _cmdline = open(self.prefix + "/cmdline").readline()
        _cmdline = _cmdline.rstrip('\x00')
        _cmdline = _cmdline.replace('\u0000', ' ')
        return _cmdline.split()

    def __get_ioprop(self):
        ret = self.run_cmd(["ionice", "-p", str(self.tpid)])
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
        try:
            ret = self.run_cmd(["schedtool", str(self.tpid)])
            if "ERROR" in ret.stdout.rstrip():
                return
            sched = ret.stdout.rstrip()
            sched = sched.rsplit(',')
            sched = sched[1]
            sched = sched.rstrip(' ').rsplit(': ')[1]
            sched = sched.rsplit('_')[1]
            sched = sched.lower()
            return sched
        except subprocess.CalledProcessError:
            return


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
            open(self.files["tasks"], 'w').write(str(pid))
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
            self.run_cmd(["systemd-notify", "--ready"])

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
        lines = open(self.config_dir + "ananicy.conf").readlines()
        for line in lines:
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
            for line in open(file).readlines():
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
            for line in open(file).readlines():
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
                if tmp:
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
            for line in open(file).readlines():
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

    def run_cmd(self, run):
        ret = subprocess.run(run, timeout=30, check=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True
                             )
        return ret

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

    def update_proc_map(self):
        proc = {}
        for pid in os.listdir("/proc"):
            try:
                pid = int(pid)
                if not os.path.isdir("/proc/{}".format(pid)):
                    continue
                if not os.path.realpath("/proc/{}/exe".format(pid)):
                    continue

                mtime = os.path.getmtime("/proc/{}".format(pid)) + self.check_freq
                if mtime > time.time():
                    continue

                path = "/proc/{}/task/".format(pid)
                for tpid in os.listdir(path):
                    tpid = int(tpid)
                    path = "/proc/{}/task/{}".format(pid, tpid)

                    mtime = os.path.getmtime(path) + self.check_freq
                    if mtime > time.time():
                        continue

                    proc[tpid] = TPID(pid, tpid)
            except ValueError:
                continue
            except FileNotFoundError:
                continue
        self.proc = proc

    def renice(self, pid: int, nice: int):
        c_nice = self.proc[pid].nice
        if c_nice == nice:
            return
        self.run_cmd(["renice", "-n", str(nice), "-p", str(pid)])
        msg = "renice: {}[{}] {} -> {}".format(self.proc[pid].cmd, pid, c_nice, nice)
        if self.verbose["apply_nice"]:
            print(msg, flush=True)

    def ioclass(self, pid, ioclass):
        c_ioclass = self.proc[pid].ioclass
        if ioclass != c_ioclass:
            self.run_cmd(["ionice", "-p", str(pid), "-c", ioclass])
            msg = "ioclass: {}[{}] {} -> {}".format(self.proc[pid].cmd, pid, c_ioclass, ioclass)
            if self.verbose["apply_ioclass"]:
                print(msg, flush=True)

    def ionice(self, pid, ionice):
        c_ionice = self.proc[pid].ionice
        if c_ionice is None:
            return
        if str(ionice) != c_ionice:
            self.run_cmd(["ionice", "-p", str(pid), "-n", str(ionice)])
            msg = "ionice: {}[{}] {} -> {}".format(self.proc[pid].cmd, pid, c_ionice, ionice)
            if self.verbose["apply_ionice"]:
                print(msg, flush=True)

    def oom_score_adj(self, pid, oom_score_adj):
        c_oom_score_adj = self.proc[pid].oom_score_adj
        if c_oom_score_adj != oom_score_adj:
            self.set_oom_score_adj(pid, oom_score_adj)
            msg = "oom_score_adj: {}[{}] {} -> {}".format(self.proc[pid].cmd, pid, c_oom_score_adj, oom_score_adj)
            if self.verbose["apply_oom_score_adj"]:
                print(msg, flush=True)

    def sched(self, pid, sched):
        l_prio = 0
        arg_map = {
            'other': '-N',
            'normal': '-N',
            'rr': '-R',
            'fifo': '-F',
            'batch': '-B',
            'iso': '-I',
            'idle': '-D'
        }
        c_sched = self.proc[pid].sched
        if not c_sched:
            return
        if c_sched == sched:
            return
        if sched == "other" and c_sched == "normal":
            return
        if sched == "idle" and c_sched == "idleprio":
            return
        if sched == "rr" or sched == "fifo":
            l_prio = 1
        sched_arg = arg_map[sched]
        self.run_cmd(["schedtool", sched_arg, "-p", str(l_prio), str(pid)])
        msg = "sched: {}[{}] {} -> {}".format(self.proc[pid].cmd, pid, c_sched, sched)
        if self.verbose["apply_sched"]:
            print(msg)

    def process_tpid(self, tpid):
        pe = self.proc.get(tpid)
        if not os.path.exists("/proc/{}/task/{}".format(pe.pid, pe.tpid)):
            return
        rule = self.rules.get(pe.cmd)
        if not rule:
            return
        try:
            if rule.get("nice"):
                self.renice(tpid, rule["nice"])
            if rule.get("ioclass"):
                self.ioclass(tpid, rule["ioclass"])
            if rule.get("ionice"):
                self.ionice(tpid, rule["ionice"])
            if rule.get("sched"):
                self.sched(tpid, rule["sched"])
            if rule.get("oom_score_adj"):
                self.oom_score_adj(tpid, rule["oom_score_adj"])
        except subprocess.CalledProcessError:
            return
        except FileNotFoundError:
            return
        cgroup = rule.get("cgroup")
        if cgroup:
            cgroup_ctrl = self.cgroups[cgroup]
            if not cgroup_ctrl.pid_in_cgroup(tpid):
                cgroup_ctrl.add_pid(tpid)
                msg = "Cgroup: {}[{}] added to {}".format(self.proc[tpid].cmd, tpid, cgroup_ctrl.name)
                if self.verbose["apply_cgroup"]:
                    print(msg)

    def run(self):
        while True:
            self.update_proc_map()
            for tpid in self.proc:
                self.process_tpid(tpid)
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
        self.update_proc_map()
        proc_dict = {}
        for tpid in self.proc:
            try:
                TPID_l = self.proc[tpid]
                proc_dict[tpid] = {
                    "tpid": TPID_l.tpid,
                    "exe": TPID_l.exe,
                    "cmd": TPID_l.cmd,
                    "stat": TPID_l.stat,
                    "nice": TPID_l.nice,
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


if __name__ == '__main__':
    main(sys.argv)
