#!/bin/bash -e

#=================================================
# CHECK ROOT
#=================================================

if [[ $(id -u) -ne 0 ]] ; then echo "Please run as root" ; exit 1 ; fi

################################################################################
# echo wrappers
INFO(){ echo "INFO: $*";}
WARN(){ echo "WARN: $*";}
ERRO(){ echo "ERRO: $*"; exit 1;}

debian_package(){
    cd "$(dirname "$0")"
    VERSION=$(git tag --sort version:refname | tail -n 1)
    [ -z "$VERSION" ] && ERRO "Can't get git tag, VERSION are empty!"
    DEB_NAME="ananicy-${VERSION}_any"
    
    # cleanup after previous installation
    rm "./${DEB_NAME}.deb" && rm -rf "${DEB_NAME}"
    
    mkdir -p "${DEB_NAME}"
    make install PREFIX="${DEB_NAME}"
    mkdir -p "${DEB_NAME}/DEBIAN/"
    {
        echo "Package: ananicy"
        echo "Version: $VERSION"
        echo "Section: custom"
        echo "Priority: optional"
        echo "Architecture: all"
        echo "Depends: coreutils, schedtool"
        echo "Essential: no"
        echo "Installed-Size: 16"
        echo "Maintainer: nefelim4ag@gmail.com"
        echo "Description: Ananicy (ANother Auto NICe daemon) — is a shell daemon created to manage processes' IO and CPU priorities, with community-driven set of rules for popular applications (anyone may add his own rule via github's pull request mechanism)."
    } > "${DEB_NAME}/DEBIAN/control"

    POSTINST="${DEB_NAME}/DEBIAN/postinst"
    touch "${POSTINST}" && chmod +x "${POSTINST}"
    {
        echo "#!/bin/sh"
        echo "chown -R root:root /etc/ananicy.d"
        echo "chown root:root /lib/systemd/system/ananicy.service"
        echo "chown root:root /usr/bin/ananicy"
    } > "${POSTINST}"
    dpkg-deb --build "${DEB_NAME}"
}

archlinux_package(){
    INFO "Use yaourt -S ananicy-git"
}

case $1 in
    debian) debian_package ;;
    archlinux) archlinux_package ;;
    *) echo "$0 <debian|archlinux>" ;;
esac
