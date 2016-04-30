#!/bin/bash -e
cd "$(dirname $0)"
if [ "$UID" != "0" ]; then
    [ ! -f /usr/bin/sudo ] && echo "Run by root or install sudo!" && exit 1
    sudo cp -avf    ./ananicy.sh       /usr/lib/systemd/scripts/ananicy.sh
    sudo mkdir -p  /etc/ananicy.d/
    sudo rsync -a ./ananicy.d/ /etc/ananicy.d/
    sudo cp -avf    ./ananicy.service  /etc/systemd/system/ananicy.service
else
    cp -avf    ./ananicy.sh       /usr/lib/systemd/scripts/ananicy.sh
    mkdir -p  /etc/ananicy.d/
    rsync -a ./ananicy.d/ /etc/ananicy.d/
    cp -avf    ./ananicy.service  /etc/systemd/system/ananicy.service
fi
