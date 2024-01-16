#!/bin/bash

./generate_flows.sh -addresses "10.0.0.2 10.0.0.3 10.0.0.6" -name "10.0.0.9" -number 100 -port 8000 # sea -> mci, hou, den
./generate_flows.sh -addresses "10.0.0.2 10.0.0.3 10.0.0.6" -name "10.0.0.10" -number 100 -port 10000 # sjc -> mci, hou, den
./generate_flows.sh -addresses "10.0.0.2 10.0.0.3 10.0.0.6" -name "10.0.0.5" -number 100 -port 12000 # lax -> hou, mci, den
