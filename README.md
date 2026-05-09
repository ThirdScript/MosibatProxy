# MOSIBAT PROXY
> [!WARNING]
> **This tool exists out of necessity, not endorsement.**
>
> Tiered internet access — where some people get a "whitelisted" SIM card with fuller connectivity while others don't — is a form of censorship and a violation of basic human rights. I do not support it, normalize it, or believe it should exist.
>
> MOSIBAT is a workaround for people trying to do their jobs in an increasingly dark environment. I hope the day comes when tools like this are no longer needed.

## The Problem

Since the horrifying internet blockage in Iran, the government has issued special SIM cards to company owners and verified individuals — SIM cards that have internet access, but still require an additional proxy or VPN to reach the global internet.

This left every sysadmin, developer, and DevOps engineer dealing with the same headache: how do you install packages, pull images, or do anything on your server that requires the open internet?

## What This Script Does

It chains your traffic like this:
<img width="936" height="421" alt="Screenshot 2026-05-08 at 9 06 21 PM" src="https://github.com/user-attachments/assets/84eb0dca-2088-4573-9df2-2fb893103347" />

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
python3 mosibat.py
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

## Emergency internet for a coworker (remote)

If a coworker is away and cannot use your laptop or phone, but they **have SSH access to the same server** and need emergency open-internet access, you can piggyback on your running tunnel.

**Prerequisites:**

- MOSIBAT is still running on your side (reverse tunnel active), with your laptop or phone still providing SOCKS over the hotspot path you chose when you ran the script.
- You tell your coworker the **tunnel port on the server** (the port you configured for “the tunnel on the server”; default example is `1080`).
- Their SSH user can log in and has TCP forwarding allowed by `sshd` (typical defaults allow this).

**Step 1 — on the coworker's machine**, they open a local forward so their traffic can reach `127.0.0.1:<tunnel_port>` on the server (where your tunnel is listening). Replace placeholders with real values:

```bash
ssh -N -L <local_port>:127.0.0.1:<tunnel_port> user@<server-host>
```

Use a spare `<local_port>` on their laptop (for example `19080`). `-N` keeps the session open only for forwarding; they leave this terminal running.

If the server SSH daemon listens on a non-default port:

```bash
ssh -p <ssh-port> -N -L <local_port>:127.0.0.1:<tunnel_port> user@<server-host>
```

**Step 2 — on the coworker's machine**, point their SOCKS5 client at **`127.0.0.1:<local_port>`** (same `<local_port>` as above). Traffic then flows: their app → SSH local forward → server loopback tunnel port → your reverse SSH → your SOCKS (laptop/VPN/hotlinked phone path) → the internet.

They can use v2rayNG, another SOCKS5-capable client, or any tool that accepts a SOCKS5 proxy pointing at `127.0.0.1:<local_port>`.

## If the Script Was Force-Killed

If the script was killed before it could clean up, run reset mode to restore the server manually:

```bash
python3 mosibat.py --reset <ssh-host>

# if your server uses a non-standard SSH port:
python3 mosibat.py --reset <ssh-host> --ssh-port 2222
```

## Important Warning

This script **installs `proxychains4`** on your server automatically, and **removes it again** when you exit cleanly.

If you are already using `proxychains4` on your server for other purposes — **do not use this script**. It will overwrite your existing config and uninstall the package on exit, which will break your existing setup.
