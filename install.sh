#!/bin/bash
# Copywright - Andre L. R. Madureira - 2018
# Install dependencies to make Ananicy work inside a Linux Distribution
#
# To add a new distro, just add it below the declare -A
# and type in the command to update and install 
# dependencies. If you want to specify different 
# dependencies based on the ARCH of the system, just 
# type in SUPPORTED_DISTROS[distroname_arch]. Ex:
# SUPPORTED_DISTROS[debian_x86_64]="apt-get ..."
declare -A SUPPORTED_DISTROS

SUPPORTED_DISTROS[debian]="
apt-get update &&
apt-get install coreutils schedtool make python3"

SUPPORTED_DISTROS[ubuntu]="
apt-get update &&
apt-get install coreutils schedtool make python3"

# check if the distro supports systemctl
SERVICE_NAME=ananicy 
SYSTEMCTL=$(whereis systemctl | cut -d':' -f2 | tr -s ' ' | xargs | cut -d\  -f1) 

DISTRO=""
ARCH=""

[ "$(whoami)" != "root" ] && echo -e "\n\tRUN this script as ROOT. Exiting...\n" && exit 1

check_distro(){
  # find the distro running
  local SUPP_DIST=$(echo ${!SUPPORTED_DISTROS[@]} | tr ' ' '|')
  DISTRO=$( 
  (lsb_release -a ; cat /etc/issue* /etc/*release /proc/version) 2> /dev/null |
  tr '[:upper:]' '[:lower:]' |
  grep -o -P "($SUPP_DIST)" |
  head -n 1
  ) 
  # check distro architecture 
  if uname -a | grep -i -P '(amd64|x86_64)' &> /dev/null; then
    ARCH=x86_64
  else
    ARCH=i386
  fi  
}

install_deps(){      
  local PKT_TOOLS=${SUPPORTED_DISTROS[${DISTRO}_${ARCH}]}
  if [ -z "$PKT_TOOLS" ]; then
    PKT_TOOLS=${SUPPORTED_DISTROS[${DISTRO}]}
  fi  
  eval $PKT_TOOLS
}

set_autostart(){
  local LOCAL_STATUS=0
  if [ -n "$SYSTEMCTL" ]; then
    # use systemctl to autostart ananicy
    systemctl daemon-reload &&
    systemctl enable "$SERVICE_NAME" &&
    systemctl start "$SERVICE_NAME" 
    LOCAL_STATUS=$(($LOCAL_STATUS+$?))
  else
    # TODO, create SYS V INIT script and remove the 
    # LOCAL_STATUS=1 below
    LOCAL_STATUS=1
  fi  
  return $LOCAL_STATUS
}

check_distro
install_deps &&
make -j4 install &&
set_autostart &&
echo -e '\n\tAll went fine, Ananicy Installed with SUCCESS\n' || (
  echo -e '\n\tAnanicy Installation - ERROR\n'
  exit 1
)

