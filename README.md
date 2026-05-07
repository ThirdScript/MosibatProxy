# MOSIBAT PROXY

## The Problem

Since the horrifying internet blockage in Iran, the government has issued special SIM cards to company owners and verified individuals — SIM cards that have internet access, but still require an additional proxy or VPN to reach the global internet.

This left every sysadmin, developer, and DevOps engineer dealing with the same headache: how do you install packages, pull images, or do anything on your server that requires the open internet?

## What This Script Does

It chains your traffic like this:

```
Your Server
    → Your Laptop (connected to the whitelisted hotspot)
        → A proxy or VPN running on your laptop (SOCKS5 on some port)
            → Global Internet
```

It does this by opening a reverse SSH tunnel from your laptop to your server, then configuring `proxychains4` on the server so you can prefix any command with `proxychains4` and have its traffic routed through your laptop and out through your VPN.

## Requirements

- Python 3 on your laptop
- SSH access to your server
- A SOCKS5 proxy or VPN running on your laptop (e.g. on port 3067)

## Usage

```bash
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
python3 lsproxy.py
```

The script will ask you for:
- Your server's SSH host or alias
- The local SOCKS5 port on your laptop
- The port to open on the server for the tunnel
- The SSH port of your server

Once running, go to your server and test it:

```bash
proxychains4 curl https://ifconfig.me
# should return your VPN's IP, not your server's IP
```

Then use it for whatever you need:

```bash
proxychains4 apt install <package>
proxychains4 curl ...
proxychains4 wget ...
```

Press `Ctrl+C` on your laptop when done — the script will tear everything down and restore your server to its original state.

## If the Script Was Force-Killed

If the script was killed before it could clean up, run reset mode to restore the server manually:

```bash
python3 lsproxy.py --reset <ssh-host>

# if your server uses a non-standard SSH port:
python3 lsproxy.py --reset <ssh-host> --ssh-port 2222
```

## Important Warning

This script **installs `proxychains4`** on your server automatically, and **removes it again** when you exit cleanly.

If you are already using `proxychains4` on your server for other purposes — **do not use this script**. It will overwrite your existing config and uninstall the package on exit, which will break your existing setup.


## Contribution

if you wanted to make any improvements to the script
please keep everything in a single file `mosibat.py` for simplicity.
