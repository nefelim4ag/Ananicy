#!/usr/bin/env python3

import os
import re
import sys
import subprocess
import json
import _thread

from collections import namedtuple
from time import sleep


class Failure(Exception):
    pass


class Ananicy:
    RULE = namedtuple('RULE', ['nice', 'ioclass', 'ionice', 'sched', 'oom_score_adj'])

    config_dir = None
    types = {}
    rules = {}

    proc = {}

    def __init__(self, config_dir="/etc/ananicy.d/"):
        self.dir_must_exits(config_dir)
        self.config_dir = config_dir
        self.load_types()
        self.load_rules()

    def __strip_line(self, line):
        line = line.rstrip()
        # Remove comments from input
        line = line.split('#')
        return line[0]

    def __get_val(self, col):
        tmp = col.split('=')
        if len(tmp) < 1:
            return ""
        return tmp[1]

    def __check_nice(self, nice):
        if nice > 19 or nice < -20:
            raise Failure("Nice must be in range -20..19")

    def __check_ionice(self, ionice):
        if ionice > 7 or ionice < 0:
            raise Failure("IOnice/IOprio allowed only in range 0-7")

    def __check_oom_score_adj(self, adj):
        if adj < -1000 or adj > 1000:
            raise Failure("OOM_SCORE_ADJ must be in range -1000..1000")

    def get_type_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        name = ""
        nice = ""
        ioclass = ""
        ionice = ""
        sched = ""
        oom_score_adj = ""

        line = line.split()
        for col in line:
            if "TYPE=" in col:
                name = self.__get_val(col)
            if "NICE=" in col:
                nice = int(self.__get_val(col))
                self.__check_nice(nice)
            if "IOCLASS=" in col:
                ioclass = self.__get_val(col)
            if "IONICE=" in col:
                ionice = int(self.__get_val(col))
                self.__check_ionice(ionice)
            if "SCHED=" in col:
                sched = self.__get_val(col)
            if "OOM_SCORE_ADJ=" in col:
                oom_score_adj = int(self.__get_val(col))
                self.__check_oom_score_adj(oom_score_adj)

        if name == "":
            raise Failure("Missing TYPE=")

        self.types[name] = self.RULE(nice, ioclass, ionice, sched, oom_score_adj)

    def load_types(self):
        type_files = self.find_files(self.config_dir, '.*\\.types')
        for file in type_files:
            with open(file) as fd:
                for line in fd.readlines():
                    try:
                        self.get_type_info(line)
                    except Failure as e:
                        print(file, e.msg)

    def get_rule_info(self, line):
        line = self.__strip_line(line)
        if len(line) < 2:
            return

        name = ""
        nice = ""
        ioclass = ""
        ionice = ""
        sched = ""
        oom_score_adj = ""

        line = line.split()
        for col in line:
            if "NAME=" in col:
                name = self.__get_val(col)
            if "TYPE=" in col:
                type = self.__get_val(col)
                type = self.types[type]
                nice = type.nice
                ioclass = type.ioclass
                ionice = type.ionice
                sched = type.sched
                oom_score_adj = type.oom_score_adj
            if "NICE=" in col:
                nice = int(self.__get_val(col))
                self.__check_nice(nice)
            if "IOCLASS=" in col:
                ioclass = self.__get_val(col)
            if "IONICE=" in col:
                ionice = int(self.__get_val(col))
                self.__check_ionice(ionice)
            if "SCHED=" in col:
                sched = self.__get_val(col)
            if "OOM_SCORE_ADJ=" in col:
                oom_score_adj = int(self.__get_val(col))
                self.__check_oom_score_adj(oom_score_adj)

        if name == "":
            raise Failure("Missing NAME=")

        self.rules[name] = self.RULE(nice, ioclass, ionice, sched, oom_score_adj)

    def load_rules(self):
        rule_files = self.find_files(self.config_dir, '.*\\.rules')
        for file in rule_files:
            with open(file) as fd:
                for line in fd.readlines():
                    try:
                        self.get_rule_info(line)
                    except Failure as e:
                        print(file, e.msg)

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

    def update_proc_map(self, pause=1):
        while True:
            proc = {}
            for proc_dir in os.listdir("/proc"):
                try:
                    pid = int(proc_dir)
                    task_dirs = os.listdir("/proc/" + str(pid) + "/task/")
                except ValueError:
                    continue
                except FileNotFoundError:
                    continue

                try:
                    exe = os.path.realpath("/proc/" + str(pid) + "/exe")
                except FileNotFoundError:
                    continue
                _exe = exe.split('/')
                cmd = _exe[-1]
                for task_dir in task_dirs:
                    try:
                        tpid = int(task_dir)
                    except ValueError:
                        continue
                    cmd = ""
                    stat = ""
                    cmdline = ""
                    nice = ""
                    with open("/proc/" + str(pid) + "/task/" + str(tpid) + "/stat") as fd:
                        stat = fd.readlines()
                        stat = stat[0].rstrip()
                        _stat = stat.rsplit()
                        nice = _stat[18]

                    with open("/proc/" + str(pid) + "/task/" + str(tpid) + "/cmdline") as fd:
                        cmdline = fd.readlines()
                        cmdline = stat[0].rstrip()

                    proc[tpid] = {
                        'exe': exe,
                        'cmd': cmd,
                        'stat': stat,
                        'cmdline': cmdline,
                        'nice': nice
                    }
            self.proc = proc
            sleep(pause)

    def run(self):
        _thread.start_new_thread(self.update_proc_map, (1,))
        sleep(1)
        print(json.dumps(self.proc, indent=4))
        sleep(1000)

        pass

    def dump_types(self):
        print(json.dumps(self.types, indent=4))

    def dump_rules(self):
        print(json.dumps(self.rules, indent=4))


def help():
    print("Usage: ananicy [options]\n",
          "  start         Run script\n",
          "  stop          Stop script\n",
          "  reload        Recompile rule cache\n",
          "  dump rules    Generate and print rules cache to stdout\n",
          "  dump types    Generate and print types cache to stdout")
    exit(0)


def main(argv):

    if len(argv) < 2:
        help()

    if argv[1] == "start":
        daemon = Ananicy()
        daemon.run()

    if argv[1] == "dump":
        daemon = Ananicy()
        if argv[2] == "rules":
            daemon.dump_rules()
        if argv[2] == "types":
            daemon.dump_types()


if __name__ == '__main__':
    main(sys.argv)
