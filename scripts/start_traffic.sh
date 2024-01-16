#!/bin/bash

# Run ifconfig command and extract IPv4 address
ipv4_address=$(ip addr show | awk '/inet / && $2 !~ /^127\./ {gsub(/\/.*/, "", $2); print $2}')

root="/home/mnadmin"

$root/D-ITG-2.8.1-r1023/bin/ITGSend $root/D-ITG-2.8.1-r1023/bin/generated/$ipv4_address
