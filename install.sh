#!/bin/bash
# Copywright Andre Madureira 2018
# Install dependencies to make Ananicy work inside Debian 9

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

[ "$(whoami)" != "root" ] && echo -e "\n\tRUN this script as ROOT. Exiting...\n" && exit 1

apt-get update &&
apt-get -y install schedtool git make gcc autoconf automake python3 &&
make -j4 install &&
systemctl daemon-reload &&
systemctl enable ananicy &&
systemctl start ananicy &&
echo -e '\n\tAll went fine, Ananicy Installed with SUCCESS\n' || (
  echo -e '\n\tAnanicy Installation - ERROR\n'
  exit 1
)

