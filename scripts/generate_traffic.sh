#!/bin/bash

# "Magic" number of flows that can be sent per one line is 400. 
# It means, that if you send traffic from one to three hosts, 
# each host can generate 133 flows at most. If you send traffic
# from one to two hosts, each host might send 200 flows at most.

# Case 1: 3 hosts, each sends traffic to 3 more hosts -> 399 flows per host generated, 1197 flows in total
./generate_flows.sh -addresses "10.0.0.2 10.0.0.3 10.0.0.6" -name "10.0.0.9" -number 133 -port 8000 # sea -> mci, hou, den
./generate_flows.sh -addresses "10.0.0.2 10.0.0.3 10.0.0.6" -name "10.0.0.10" -number 133 -port 10000 # sjc -> mci, hou, den
./generate_flows.sh -addresses "10.0.0.2 10.0.0.3 10.0.0.6" -name "10.0.0.5" -number 133 -port 12000 # lax -> hou, mci, den

# Case 2: 1 host (SEA) generates 400*9=3600 flows to a single host (HOU). One more line causes receiver to error out.
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-1" -number 400 -port 14000
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-2" -number 400 -port 14500
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-3" -number 400 -port 15000
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-4" -number 400 -port 15500
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-5" -number 400 -port 16000
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-6" -number 400 -port 16500
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-7" -number 400 -port 17000
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-8" -number 400 -port 17500
./generate_flows.sh -addresses "10.0.0.3" -name "10.0.0.9-single-9" -number 400 -port 18000

# Case 2: 1 host (SJC) generates 3600 flows to a single host (MCI).
./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-1" -number 400 -port 14000
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-2" -number 400 -port 14500
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-3" -number 400 -port 15000
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-4" -number 400 -port 15500
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-5" -number 400 -port 16000
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-6" -number 400 -port 16500
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-7" -number 400 -port 17000
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-8" -number 400 -port 18500
#./generate_flows.sh -addresses "10.0.0.6" -name "10.0.0.10-single-9" -number 400 -port 18000


./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-1" -number 400 -port 14000
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-2" -number 400 -port 14500
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-3" -number 400 -port 15000
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-4" -number 400 -port 15500
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-5" -number 400 -port 16000
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-6" -number 400 -port 16500
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-7" -number 400 -port 17000
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-8" -number 400 -port 17500
./generate_flows.sh -addresses "10.0.0.2" -name "10.0.0.5-single-9" -number 400 -port 18000
