# Remote Mininet Instance

## Logging in

> host: <given privately>
> user: mnadmin
> pass: ********

You can log only using ssh-key you have given to the box administrator. Password login is disabled.

## Usage

### running mininet remotely

You can always use 2 terminals to spin up the controller and then the mininet process in separate SSH sessions.

You can also use `tmux` which is installed.
Tmux cheatsheet for beginners is here: https://tmuxcheatsheet.com/

Project is situated in `${HOME}/sdn_project`. Do not make changes on `main` branch.
If you want to test out PR, just log with your ssh-agent forwarded with `ssh -A` and add your fork to remotes.

This will be:
```bash
git remote add $your_chosen_remote_name https://github.com/$gh_username/Hierarchical-SDN-Controllers.git
git fetch $your_chosen_remote_name $branch_for_pr
```

Runnning the project should be the same as on [main readme](../README.md).

### attaching to hosts and switches

#### use x11 forwarding

Either install XQuartz if you are on MacOS or CygWin with XLaunch if you are on Windows. On Linux you are good to go.

To allow X11-forwarding on Linux and MacOS:
```
ssh -X $user@$remote_host
```

To do it in Windows use PuTTY with X11 Forwarding or the same as above through Powershell.

#### use mn-attach script

You can use `mn-attach` script to attach to hosts and switches. It attaches directly to hosts' namespace.
You can find it `./scripts/`

### remote packet capture

```bash
sudo wireshark '-oextcap.sshdump.remotehost:172.233.49.146' '-oextcap.sshdump.remoteuser:mnadmin' -i sshdump -k
```

### generating traffic

Use `ITGSend` and `ITGRecv` with appropriate parameters in order to generate traffic between hosts. Captured logs can be decoded using `ITGDec`. Please refer to the official documentation: https://traffic.comics.unina.it/software/ITG/manual/. The application is located in the home directory, in the `D-ITG-2.8.1-r1023` directory. To execute the commands on the hosts, make sure to be inside `D-ITG-2.8.1-r1023/bin` directory.
