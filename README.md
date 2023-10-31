# Hierarchical-SDN-Controllers

## Topologies

### AbileneMod

![AbileneModTopology](docs/SDN_AbileneModTopo.png)

 * consists of 10 switches

### Abilene

![AbileneTopology](docs/SDN_AbileneTopo.png)

 * consists of 11 switches

## Running basic scenario

For simple test run - on Mininet VM please run:

> in one terminal
```
ryu-manager ryu.app.simple_switch_13 --log-file /tmp/ryu-logs.$$.log &>/dev/null
tail -f /tmp/ryu-logs.$$.log
```

> in second run
```
sudo mn -c &>/dev/null
sudo ./src/simple_run.py
```
