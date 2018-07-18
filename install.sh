#!/bin/bash
# Copywright - Andre L. R. Madureira - 2018
# Install dependencies to make Ananicy work inside a Linux Distribution
#
# Currently supported distros: Debian, ... others go here ...

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

# check if the distro supports systemctl
SYSTEMCTL=$(whereis systemctl | cut -d':' -f2 | tr -s ' ' | xargs | cut -d\  -f1) 
DISTRO=""
ARCH=""

[ "$(whoami)" != "root" ] && echo -e "\n\tRUN this script as ROOT. Exiting...\n" && exit 1

check_distro(){
  # find the distro running
  DISTRO=$( (lsb_release -a ; cat /etc/issue* /etc/*release /proc/version) 2> /dev/null ) 
  if echo "$DISTRO" | grep -i -P 'debian' &> /dev/null; then
    DISTRO=debian
  fi
  # check distro architecture 
  if uname -a | grep -i -P '(amd64|x86_64)' &> /dev/null; then
    ARCH=x86_64
  else
    ARCH=i386
  fi  
}

install_deps(){    
  local LOCAL_STATUS=0
  case "${DISTRO}_${ARCH}" in
  debian*|ubuntu*)
    apt-get update &&
    apt-get -y install coreutils schedtool make python3
    LOCAL_STATUS=$(($LOCAL_STATUS+$?))
    ;;
  *)
    # add other distros here as needed
    ;;
  esac
  return $LOCAL_STATUS
}

set_autostart(){
  local SERVICE_NAME=ananicy   
  if [ -n "$SYSTEMCTL" ]; then
    # use systemctl to autostart ananicy
    systemctl daemon-reload &&
    systemctl enable "$SERVICE_NAME" &&
    systemctl start "$SERVICE_NAME" 
  else
    # TODO, create SYS V INIT script
  fi  
}

check_distro
install_deps &&
make -j4 install &&
set_autostart &&
echo -e '\n\tAll went fine, Ananicy Installed with SUCCESS\n' || (
  echo -e '\n\tAnanicy Installation - ERROR\n'
  exit 1
)

