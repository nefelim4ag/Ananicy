#!/bin/bash -e
cd "$(dirname $0)"
################################################################################
# echo wrappers
INFO(){ echo -n "INFO: "; echo "$@" ;}
WARN(){ echo -n "WARN: "; echo "$@" ;}
ERRO(){ echo -n "ERRO: "; echo -n "$@" ; echo " Abort!"; exit 1;}

PREFIX="/"
case $1 in
    PREFIX=*) PREFIX=$(echo $1 | cut -d'=' -f2);;
esac

cd "$(dirname $0)"
if [ "$PREFIX" == "/" ]; then
    if [ "$UID" != "0" ]; then
        [ ! -f /usr/bin/sudo ] && ERRO "Run by root or install sudo!" || :
        SUDO=sudo
    else
        unset SUDO
    fi
fi

$SUDO mkdir -p $PREFIX/etc/ananicy.d/
$SUDO rsync -a       ./ananicy.d/      $PREFIX/etc/ananicy.d/
$SUDO install -Dm755 ./ananicy.sh      $PREFIX/usr/lib/systemd/scripts/ananicy.sh
$SUDO install -Dm644 ./ananicy.service $PREFIX/usr/lib/systemd/system/ananicy.service
