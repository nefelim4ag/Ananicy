# Ananicy
Ananicy - is Another auto nice daemon, with community rules support (Use pull request please)

Configs can be placed under: /etc/ananicy.d/
Config syntax, each process described as a line:
```
NAME=cron NICE=-1
NAME=xz   NICE=19 IOCLASS=idle IONICE=4
```

All fields except NAME are optional

* ![logo](http://www.monitorix.org/imgs/archlinux.png "arch logo") Arch: in the [AUR](https://aur.archlinux.org/packages/ananicy-git).
