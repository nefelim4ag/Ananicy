#!/usr/bin/env python3

import os
import sys
import subprocess

from collections import namedtuple


class Failure(Exception):
    pass


class Ananicy:
    RULE = namedtuple('RULE', ['nice', 'ioclass', 'ionice', 'sched', 'oom_score_adj'])

    config_dir = None
    types = {}
    rules = {}

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
                nice = self.__get_val(col)
            if "IOCLASS=" in col:
                ioclass = self.__get_val(col)
            if "IONICE=" in col:
                ionice = self.__get_val(col)
            if "SCHED=" in col:
                sched = self.__get_val(col)
            if "OOM_SCORE_ADJ=" in col:
                oom_score_adj = self.__get_val(col)

        self.types[name] = self.RULE(nice, ioclass, ionice, sched, oom_score_adj)

    def load_types(self):
        ret = self.find_files(self.config_dir, "*.types")
        type_files = ret.stdout.splitlines()
        for file in type_files:
            with open(file) as file:
                for line in file.readlines():
                    self.get_type_info(line)

        print(self.types)

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
                nice = self.__get_val(col)
            if "IOCLASS=" in col:
                ioclass = self.__get_val(col)
            if "IONICE=" in col:
                ionice = self.__get_val(col)
            if "SCHED=" in col:
                sched = self.__get_val(col)
            if "OOM_SCORE_ADJ=" in col:
                oom_score_adj = self.__get_val(col)

        self.rules[name] = self.RULE(nice, ioclass, ionice, sched, oom_score_adj)

    def load_rules(self):
        ret = self.find_files(self.config_dir, "*.rules")
        rule_files = ret.stdout.splitlines()
        for file in rule_files:
            with open(file) as file:
                for line in file.readlines():
                    self.get_rule_info(line)

        print(self.rules)

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
        return self.run_cmd(["find", "-P", path, "-type", "f", "-name", name_mask])

    def run(self):
        pass


def help():
    exit(0)


def main(argv):

    if len(argv) < 2:
        help()

    if argv[1] == "start":
        daemon = Ananicy()
        daemon.run()


if __name__ == '__main__':
    main(sys.argv)
