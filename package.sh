#!/bin/bash -e
################################################################################
# echo wrappers
INFO(){ echo -n "INFO: "; echo "$@" ;}
WARN(){ echo -n "WARN: "; echo "$@" ;}
ERRO(){ echo -n "ERRO: "; echo -n "$@" ; echo " Abort!"; exit 1;}

debian_package(){
    cd "$(dirname $0)"
    VERSION=$(git tag | tail -n 1)
    [ -z "$VERSION" ] && ERRO "Can't get git tag, VERSION are empty!"
    DEB_NAME=ananicy-${VERSION}_any
    mkdir -p $DEB_NAME
    ./install.sh PREFIX=$DEB_NAME/
    mkdir -p $DEB_NAME/DEBIAN/
    echo "Package: ananicy"         >> $DEB_NAME/DEBIAN/control
    echo "Version: $VERSION"        >> $DEB_NAME/DEBIAN/control
    echo "Section: custom"          >> $DEB_NAME/DEBIAN/control
    echo "Priority: optional"       >> $DEB_NAME/DEBIAN/control
    echo "Architecture: all"        >> $DEB_NAME/DEBIAN/control
    echo "Essential: no"            >> $DEB_NAME/DEBIAN/control
    echo "Installed-Size: 16"       >> $DEB_NAME/DEBIAN/control
    echo "Maintainer: nefelim4ag@gmail.com" >> $DEB_NAME/DEBIAN/control
    echo "Description: Ananicy (ANother Auto NICe daemon) — is a shell daemon created to manage processes' IO and CPU priorities, with community-driven set of rules for popular applications (anyone may add his own rule via github's pull request mechanism)." >> $DEB_NAME/DEBIAN/control
    dpkg-deb --build $DEB_NAME
}

archlinux_package(){
    INFO "Use yaourt -S ananicy-git"
}

case $1 in
    debian) debian_package ;;
    archlinux) archlinux_package ;;
    *) echo "$0 <debian|archlinux>" ;;
esac
