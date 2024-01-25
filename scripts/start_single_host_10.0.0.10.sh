#!/bin/bash
# Script starts sending traffic from host 10.0.0.10 to 10.0.0.6 (3600 flows at the same time).

root="/home/mnadmin"
base_command="$root/D-ITG-2.8.1-r1023/bin/ITGSend"

# Loop to execute the command with different filenames
for ((i = 1; i <= 1; i++)); do
  filename="10.0.0.10-single-$i"
  $base_command "$root/D-ITG-2.8.1-r1023/bin/generated/$filename" &
done

wait

