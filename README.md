# Ananicy

## Description
Ananicy (ANother Auto NICe daemon) — is a shell daemon created to manage processes' [IO](http://linux.die.net/man/1/ionice) and [CPU](http://linux.die.net/man/1/nice) priorities, with community-driven set of rules for popular applications (anyone may add his own rule via github's [pull request](https://help.github.com/articles/using-pull-requests/) mechanism).

I think it's only for desktop usage.

I just wanted a tool for auto set programs nice in my system, i.e.:
* Why do I have a lags, while compiling kernel and playing a game?
* Why does dropbox client eat all my IO?
* Why does torrent/dc client make my laptop run slower?
* ...

Use ananicy to fix this problems!

## Versions
```
X.Y.Z where
X - Major version,
Y - Script version - reset on each major update
Z - Rules version - reset on each script update
```
Read more about semantic versioning [here](http://semver.org/)

## Installation
To use ananicy you must have systemd installed.

You can install ananicy manualy by:
```
$ git clone https://github.com/Nefelim4ag/Ananicy.git /tmp/ananicy
# /tmp/ananicy/install.sh
```
* ![logo](http://www.monitorix.org/imgs/archlinux.png "arch logo") Arch: [AUR/ananicy-git](https://aur.archlinux.org/packages/ananicy-git).
* Debian/Ubuntu: use [package.sh](https://raw.githubusercontent.com/Nefelim4ag/Ananicy/master/package.sh) in repo
```
$ git clone https://github.com/Nefelim4ag/Ananicy.git
$ ./Ananicy/package.sh debian
$ sudo dpkg -i ./Ananicy/ananicy-*.deb
```

Enable
```
$ sudo systemctl enable ananicy
$ sudo systemctl start ananicy
```
## Configuration
Rules files should be placed under /etc/ananicy.d/ directory and have *.rules extension.
Inside .rules file every process is described on a separate line, general syntax is described below:

```
NAME=<process_name> NICE=cpu_nice SCHED=cpu_sched IOCLASS=io_class IONICE=io_nice_value
```

All fields except NAME are optional.

NAME used for pgrep -w, so you can test your rules manually.

Example configurations:
```
NAME=cron NICE=-1
NAME=xz   NICE=19 IOCLASS=idle IONICE=4
NAME=pulseaudio IOCLASS=realtime
```

Ananicy load all rules in ram while starting, so to apply rules, you must restart service.

Available ionice values:
```
$ man ionice
```

## Simple rules for writing rules
CFQ IO Scheduller also use 'nice' for internal scheduling, so it's mean processes with same IO class and IO priority, but with different nicceness will take advantages of 'nice' also for IO.

1. Try don't chage 'nice' of system wide process like initrd.
2. Please try use full process name (or name with ^$ symbols like NAME=^full_name$)
3. When writing rule - try use only 'nice', it must be enough in most cases.
4. Don't try set to high priority! Niceness can fix some performance problems, but can't give you more.
Example: pulseaudio uses 'nice' -11 by default, if you set other cpu hungry task, with 'nice' {-20..-12} you can catch a sound glitches.
5. For CPU hungry backround task like compiling, just use NICE=19.

About IO priority:

1. It's usefull use IOCLASS=idle for IO hungry background tasks like: file indexers, Cloud Clients, Backups and etc.
2. It's not cool set realtime to all tasks. The  RT  scheduling  class is given first access to the disk, regardless of what else is going on in the system.  Thus the RT class needs to be used with some care, as it can starve other processes. So try use ioclass first.

## Debugging
Get ananicy output with journalctl:
```
$ journalctl -efu ananicy.service
```

### Missing `schedtool`
If you see this error in the output
```
Jan 24 09:44:18 tony-dev ananicy[13783]: ERRO: Missing schedtool! Abort!
```
Fix it in Ubuntu with
```
sudo apt install schedtool
```

### Submitting new rules

Please use pull request, thanks
