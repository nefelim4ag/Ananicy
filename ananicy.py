#!/usr/bin/env python3

import os
import re
import sys
import subprocess
import json
import _thread

from time import sleep


class Failure(Exception):
    pass


class Ananicy:
    config_dir = None
    types = {}
    rules = {}

    proc = {}

    check_freq = 5

    verbose = {
        "type_load": True,
        "rule_load": True,
        "apply_nice": True,
        "apply_ioclass": True,
        "apply_ionice": True,
        "apply_sched": True,
        "apply_oom_score_adj": True
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
        if nice > 19 or nice < -20:
            raise Failure("Nice must be in range -20..19")

    def __check_ionice(self, ionice):
        if ionice > 7 or ionice < 0:
            raise Failure("IOnice/IOprio allowed only in range 0-7")

    def __check_oom_score_adj(self, adj):
        if adj < -1000 or adj > 1000:
            raise Failure("OOM_SCORE_ADJ must be in range -1000..1000")

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

    def get_type_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        line = json.loads(line)
        type = line.get("type")
        if type == "":
            raise Failure('Missing "type": ')

        self.types[type] = {
            "nice": line.get("nice"),
            "ioclass": line.get("ioclass"),
            "ionice": line.get("ionice"),
            "sched": line.get("sched"),
            "oom_score_adj": line.get("oom_score_adj")
        }

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

        #
        line = json.loads(line)
        name = line.get("name")
        if name == "":
            raise Failure('Missing "name": ')

        type = line.get("type")
        if type:
            if not self.types.get(type):
                raise Failure('"type": "{}" not defined'.format(type))
            type = self.types[type]
            for attr in ("nice", "ioclass", "ionice", "sched", "oom_score_adj"):
                tmp = type.get(attr)
                if tmp:
                    line[attr] = tmp

        self.rules[name] = {
            "nice": line.get("nice"),
            "ioclass": line.get("ioclass"),
            "ionice": line.get("ionice"),
            "sched": line.get("sched"),
            "oom_score_adj": line.get("oom_score_adj"),
            "type": line.get("type")
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
                    files += [entry_path]
        return files

    def update_proc_map(self):
        proc = {}
        for proc_dir in os.listdir("/proc"):
            try:
                pid = int(proc_dir)
                task_dirs = os.listdir("/proc/" + str(pid) + "/task/")
                exe = os.path.realpath("/proc/" + str(pid) + "/exe")
                _oom_score_adj = open("/proc/" + str(pid) + "/oom_score_adj").readline()
                oom_score_adj = int(_oom_score_adj.rstrip())
            except ValueError:
                continue
            except FileNotFoundError:
                continue
            _exe = exe.split('/')
            cmd = _exe[-1]
            for task_dir in task_dirs:
                try:
                    tpid = int(task_dir)
                except ValueError:
                    continue
                stat = ""
                cmdline = ""
                nice = ""
                try:
                    stat = open("/proc/" + str(pid) + "/task/" + str(tpid) + "/stat").readline().rstrip()
                    m = re.search('\\) . .*', stat)
                    m = m.group(0)
                    m = m.rsplit()
                    nice = int(m[17])

                    cmdline = open("/proc/" + str(pid) + "/task/" + str(tpid) + "/cmdline").readline().rstrip('\x00')
                    cmdline = cmdline.replace('\u0000', ' ')
                except FileNotFoundError:
                    continue

                proc[tpid] = {
                    'tpid': tpid,
                    'exe': exe,
                    'cmd': cmd,
                    'nice': nice,
                    'oom_score_adj': oom_score_adj,
                    'stat': stat,
                    'cmdline': cmdline,
                }
        self.proc = proc

    def thread_update_proc_map(self, pause=1):
        while True:
            self.update_proc_map()
            sleep(pause)

    def renice(self, proc, pid, nice):
        try:
            self.run_cmd(["renice", "-n", str(nice), "-p", str(pid)])
        except subprocess.CalledProcessError:
            return
        msg = "renice: {}[{}] {} -> {}".format(proc[pid]["cmd"], pid, proc[pid]["nice"], nice)
        if self.verbose["apply_nice"]:
            print(msg, flush=True)

    def get_ioclass(self, pid):
        ret = self.run_cmd(["ionice", "-p", str(pid)])
        stdout = ret.stdout.rsplit(': prio ')
        return stdout[0].rstrip()

    def get_ionice(self, pid):
        ret = self.run_cmd(["ionice", "-p", str(pid)])
        stdout = ret.stdout.rsplit(': prio ')
        # can return only ioclass, if process class are idle
        if len(stdout) == 2:
            return stdout[1].rstrip()
        else:
            return None

    def ioclass(self, proc, pid, ioclass):
        try:
            c_ioclass = self.get_ioclass(pid)
            if ioclass != c_ioclass:
                self.run_cmd(["ionice", "-p", str(pid), "-c", ioclass])
                msg = "ioclass: {}[{}] {} -> {}".format(proc[pid]["cmd"], pid, c_ioclass, ioclass)
                if self.verbose["apply_ioclass"]:
                    print(msg, flush=True)
        except subprocess.CalledProcessError:
            return

    def ionice(self, proc, pid, ionice):
        try:
            c_ionice = self.get_ionice(pid)
            if c_ionice is None:
                return
            if str(ionice) != c_ionice:
                self.run_cmd(["ionice", "-p", str(pid), "-n", str(ionice)])
                msg = "ionice: {}[{}] {} -> {}".format(proc[pid]["cmd"], pid, c_ionice, ionice)
                if self.verbose["apply_ionice"]:
                    print(msg, flush=True)
        except subprocess.CalledProcessError:
            return

    def get_oom_score_adj(self, pid):
        _oom_score_adj = open("/proc/" + str(pid) + "/oom_score_adj").readline().rstrip()
        return int(_oom_score_adj)

    def oom_score_adj(self, proc, pid, oom_score_adj):
        try:
            c_oom_score_adj = self.get_oom_score_adj(pid)
            if c_oom_score_adj != oom_score_adj:
                file = open("/proc/" + str(pid) + "/oom_score_adj")
                file.write(str(oom_score_adj))
                msg = "oom_score_adj: {}[{}] {} -> {}".format(proc[pid]["cmd"], pid, c_oom_score_adj, oom_score_adj)
                if self.verbose["apply_oom_score_adj"]:
                    print(msg, flush=True)
        except FileNotFoundError:
            return

    def get_sched(self, pid):
        try:
            ret = self.run_cmd(["schedtool", str(pid)])
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

    def sched(self, proc, pid, sched):
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
        c_sched = self.get_sched(pid)
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
        try:
            self.run_cmd(["schedtool", sched_arg, "-p", str(l_prio), str(pid)])
        except subprocess.CalledProcessError:
            return
        msg = "sched: {}[{}] {} -> {}".format(proc[pid]["cmd"], pid, c_sched, sched)
        if self.verbose["apply_sched"]:
            print(msg)

    def process_pid(self, proc, pid):
        proc_entry = proc[pid]
        cmd = proc_entry["cmd"]
        rule = self.rules.get(cmd)
        if not rule:
            return
        current_nice = proc_entry["nice"]
        if rule.get("nice"):
            if current_nice != rule["nice"]:
                self.renice(proc, pid, rule["nice"])
        if rule.get("ioclass"):
            self.ioclass(proc, pid, rule["ioclass"])
        if rule.get("ionice"):
            self.ionice(proc, pid, rule["ionice"])
        if rule.get("sched"):
            self.sched(proc, pid, rule["sched"])
        if rule.get("oom_score_adj"):
            self.oom_score_adj(proc, pid, rule["oom_score_adj"])

    def processing_rules(self):
        proc = self.proc
        for pid in proc:
            self.process_pid(proc, pid)

    def run(self):
        _thread.start_new_thread(self.thread_update_proc_map, (self.check_freq,))
        while True:
            self.processing_rules()
            sleep(self.check_freq)

    def dump_types(self):
        print(json.dumps(self.types, indent=4), flush=True)

    def dump_rules(self):
        print(json.dumps(self.rules, indent=4), flush=True)

    def dump_proc(self):
        self.update_proc_map()
        print(json.dumps(self.proc, indent=4), flush=True)


def help():
    print("Usage: ananicy [options]\n",
          "  start         Run script\n",
          "  dump rules    Generate and print rules cache to stdout\n",
          "  dump types    Generate and print types cache to stdout\n",
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
        if argv[2] == "rules":
            daemon.dump_rules()
        if argv[2] == "types":
            daemon.dump_types()
        if argv[2] == "proc":
            daemon.dump_proc()


if __name__ == '__main__':
    main(sys.argv)
