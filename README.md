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
$ dpkg -i ./Ananicy/ananicy-*.deb
```

## Configuration
Rules files should be placed under /etc/ananicy.d/ directory and have *.rules extension.
Inside .rules file every process is described on a separate line, general syntax is described below:

```
NAME=<process_name> NICE=cpu_nice IOCLASS=io_class IONICE=io_nice_value
```

All fields except NAME are optional.

NAME used for pgrep -w, so you can test your rules manually.

Example configurations:
```
NAME=cron NICE=-1
NAME=xz   NICE=19 IOCLASS=idle IONICE=4
NAME=pulseaudio IOCLASS=realtime
```

## Debugging
Get ananicy output with journalctl:
journalctl -f -u ananicy.service
