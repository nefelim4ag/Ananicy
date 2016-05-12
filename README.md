# Ananicy

## Description
Ananicy (ANother Auto NICe daemon) - is a shell daemon created to manage processes' [IO](http://linux.die.net/man/1/ionice) and [CPU](http://linux.die.net/man/1/nice) priorities, with community rules support (anyone may add his own rule via github's [pull request](https://help.github.com/articles/using-pull-requests/) mechanism)

I think it's only for desktop usage

I just wanted a tool for auto set programs nice in my system, i.e.:
* Why i must have a lags, while i'm compiling kernel and playing a game?
* Why dropbox client eat all my IO?
* Why torrent/dc client make my book run slower?
* ...

For fix this problem - use ananicy.

## Versions
```
X.x.x - Major version,
x.X.x - Script version - Reset on each major update
x.x.X - Rules version - Reset on each script update
```

## Installation
For install ananicy you must have a system with systemd

You can install ananicy manualy by:
```
$ git clone https://github.com/Nefelim4ag/Ananicy.git /tmp/ananicy
# /tmp/ananicy/install.sh
```
* ![logo](http://www.monitorix.org/imgs/archlinux.png "arch logo") Arch: in the [AUR](https://aur.archlinux.org/packages/ananicy-git).
* Debian/Ubuntu: use [package.sh](https://raw.githubusercontent.com/Nefelim4ag/Ananicy/master/package.sh) in repo
```
$ git clone https://github.com/Nefelim4ag/Ananicy.git
$ ./Ananicy/package.sh debian
$ dpkg -i ./Ananicy/ananicy-*.deb
```

## Configuration
Rules files should be placed under /etc/ananicy.d/ directory.

File extension for rules: .rules

In rule each process is described on a separate line, general syntax is described below

```
NAME=<process_name> NICE=cpu_nice IOCLASS=io_class IONICE=io_nice_value
```

All fields except NAME are optional

NAME used for pgrep -w, so you can test your rules

Example configurations
```
NAME=cron NICE=-1
NAME=xz   NICE=19 IOCLASS=idle IONICE=4
NAME=pulseaudio IOCLASS=realtime
```

## Debugging
You can use journalctl for check output:
journalctl -f -u ananicy.service
