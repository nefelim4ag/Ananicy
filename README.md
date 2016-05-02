# Ananicy

## Description
Ananicy (ANother Auto NICe daemon) - is a shell daemon created to manage processes' [IO](http://linux.die.net/man/1/ionice) and [CPU](http://linux.die.net/man/1/nice) priorities, with community rules support (anyone may add his own rule via github's [pull request](https://help.github.com/articles/using-pull-requests/) mechanism)

## Installation
For install ananicy you must have a system with systemd

You can install ananicy manualy by:
```
git clone https://github.com/Nefelim4ag/Ananicy.git /tmp/ananicy
/tmp/ananicy/install.sh
```
* ![logo](http://www.monitorix.org/imgs/archlinux.png "arch logo") Arch: in the [AUR](https://aur.archlinux.org/packages/ananicy-git).

## Configuration
Config files should be placed under /etc/ananicy.d/ directory.

In config each process is described on a separate line, general syntax is described below

```
NAME=<process_name> NICE=cpu_nice IOCLASS=io_class IONICE=io_nice_value
```

All fields except NAME are optional

Example configurations
```
NAME=cron NICE=-1
NAME=xz   NICE=19 IOCLASS=idle IONICE=4
NAME=pulseaudio IOCLASS=realtime
```
