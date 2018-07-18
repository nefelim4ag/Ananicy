#!/bin/bash
# Copywright Andre Madureira 2018
# Install dependencies to make Ananicy work inside Debian 9

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

[ "$(whoami)" != "root" ] && echo -e "\n\tRUN this script as ROOT. Exiting...\n" && exit 1

PWD=$(pwd) 
apt-get update &&
apt-get -y install schedtool git make gcc autoconf automake python3 &&
cd "$SCRIPT_DIR"/ananicy &&
make -j4 install &&
systemctl daemon-reload &&
systemctl enable ananicy &&
systemctl start ananicy 
STATUS=$?
cd "$PWD"
if [ $STATUS -eq 0 ]; then
  echo -e '\n\tAll went fine, Ananicy Installed with SUCCESS\n'
else
  echo -e '\n\tAnanicy Installation - ERROR\n'
  exit $STATUS
fi

