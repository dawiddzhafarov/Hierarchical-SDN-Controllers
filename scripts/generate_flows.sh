#!/bin/bash

# Initialize variables with default values
addresses=""
filename=""
number=""
port=""

# Function to print usage information
print_usage() {
  echo "Usage: $0 -addresses <ip_addresses> -name <string> -number <integer> -port <integer>"
  exit 1
}

# Parse command-line arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    -addresses)
      shift
      addresses="$1"
      ;;
    -name)
      shift
      filename="$1"
      ;;
    -number)
      shift
      number="$1"
      ;;
    -port)
      shift
      port="$1"
      ;;
    *)
      # Unknown option
      print_usage
      ;;
  esac
  shift
done

# Check if all required flags are provided
if [ -z "$addresses" ] || [ -z "$filename" ] || [ -z "$number" ] || [ -z "$port" ]; then
  echo "Error: All flags (-addresses, -name, -number) must be provided."
  print_usage
fi

# Split addresses into an array
IFS=' ' read -r -a address_array <<< "$addresses"

# Generate lines with the specified format and redirect to the output file
for address in "${address_array[@]}"; do
  for ((i = 0; i < number; i++)); do
    echo "-a $address -C 1 -c 1 -t 10000 -rp $port -T UDP"
    port=$((port+1))
  done
  port=$((port+300))
done > "$HOME/D-ITG-2.8.1-r1023/bin/generated/$filename"

echo "SUCCESS"
