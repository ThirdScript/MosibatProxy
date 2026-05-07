#!/usr/bin/env python3

import argparse
import signal
import subprocess
import sys
import time

# ANSI colors
R = "\033[1;31m"
G = "\033[1;32m"
Y = "\033[1;33m"
B = "\033[1;34m"
C = "\033[1;36m"
W = "\033[1;37m"
DIM = "\033[2m"
RST = "\033[0m"

BANNER = "--- MOSIBAT PROXY ---"

# Globals
ssh_process = None
ssh_host = None
ssh_port = 22
server_port = None
laptop_port = None
proxychains_was_installed = False
original_proxychains_conf = None


# Print helpers
def info(msg):
    print(f"{G}[+]{RST} {msg}")


def warn(msg):
    print(f"{Y}[!]{RST} {msg}")


def error(msg):
    print(f"{R}[✗]{RST} {msg}")


def step(msg):
    print(f"{B}[→]{RST} {msg}")


# Run a command on the remote server over SSH
def run_remote(host, cmd, capture=True, check=True):
    full = ["ssh", "-p", str(ssh_port), host, cmd]
    if capture:
        result = subprocess.run(full, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result
    else:
        return subprocess.run(full, check=check)


# Run a sudo command on the remote server
def run_remote_sudo(host, cmd, capture=True, check=True):
    return run_remote(host, f"sudo {cmd}", capture=capture, check=check)


# Return True if proxychains4 is already installed on the server
def check_proxychains(host):
    result = run_remote(host, "which proxychains4 || which proxychains", check=False)
    return result.returncode == 0


# Install proxychains4 on the server via apt
def install_proxychains(host):
    global proxychains_was_installed
    step("Installing proxychains4 on server...")
    try:
        run_remote_sudo(
            host, "apt-get install -y proxychains4", capture=False, check=True
        )
        proxychains_was_installed = True
        info("proxychains4 installed successfully.")
    except Exception as e:
        error(f"Failed to install proxychains4: {e}")
        sys.exit(1)


# Save the current proxychains config so we can restore it on exit
def backup_proxychains_conf(host):
    global original_proxychains_conf
    step("Backing up current proxychains4 config...")
    result = run_remote(
        host,
        "cat /etc/proxychains4.conf 2>/dev/null || cat /etc/proxychains.conf 2>/dev/null",
        check=False,
    )
    original_proxychains_conf = result.stdout if result.returncode == 0 else None
    if original_proxychains_conf:
        info("Config backed up.")
    else:
        warn("No existing proxychains config found — will delete on cleanup.")


# Write a clean proxychains4 config pointing to our tunnel port
def configure_proxychains(host, tunnel_port):
    step(f"Configuring proxychains4 to use 127.0.0.1:{tunnel_port} ...")
    config = (
        "# Managed by tunnel_manager.py — do not edit manually\n"
        "dynamic_chain\n"
        "#strict_chain\n"
        "#random_chain\n"
        "proxy_dns\n"
        "tcp_read_time_out 15000\n"
        "tcp_connect_time_out 8000\n"
        "\n"
        "[ProxyList]\n"
        f"socks5  127.0.0.1  {tunnel_port}\n"
    )
    escaped = config.replace("'", "'\\''")
    run_remote(host, f"echo '{escaped}' | sudo tee /etc/proxychains4.conf > /dev/null")
    info("proxychains4 configured.")


# Restore the original proxychains config, or remove it if there wasn't one
def restore_proxychains_conf(host):
    step("Restoring proxychains4 config on server...")
    if original_proxychains_conf:
        escaped = original_proxychains_conf.replace("'", "'\\''")
        try:
            run_remote(
                host, f"echo '{escaped}' | sudo tee /etc/proxychains4.conf > /dev/null"
            )
            info("proxychains4 config restored.")
        except Exception as e:
            warn(f"Could not restore config: {e}")
    else:
        try:
            run_remote_sudo(host, "rm -f /etc/proxychains4.conf")
            info("proxychains4 config removed (there was none originally).")
        except Exception as e:
            warn(f"Could not remove config: {e}")


# Uninstall proxychains4 from the server
def uninstall_proxychains(host):
    step("Removing proxychains4 from server (we installed it)...")
    try:
        run_remote_sudo(
            host, "apt-get remove -y proxychains4", capture=False, check=True
        )
        info("proxychains4 removed.")
    except Exception as e:
        warn(f"Could not remove proxychains4: {e}")


# Open the reverse SSH tunnel from laptop to server
def start_tunnel(host, laptop_p, server_p):
    global ssh_process
    step(f"Opening reverse SSH tunnel: server:{server_p} → laptop:{laptop_p} ...")
    cmd = [
        "ssh",
        "-p",
        str(ssh_port),
        "-R",
        f"{server_p}:localhost:{laptop_p}",
        "-N",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ControlMaster=no",
        host,
    ]
    ssh_process = subprocess.Popen(cmd)
    time.sleep(2)
    if ssh_process.poll() is not None:
        error(
            "SSH tunnel failed to start. Check the port isn't already in use on the server."
        )
        sys.exit(1)
    info(f"Tunnel is UP  (server port {server_p} → laptop port {laptop_p})")


# Terminate the SSH tunnel process
def stop_tunnel():
    global ssh_process
    if ssh_process and ssh_process.poll() is None:
        step("Killing SSH tunnel...")
        ssh_process.terminate()
        try:
            ssh_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ssh_process.kill()
        ssh_process = None
        info("SSH tunnel closed.")


# Tear everything down and restore server state
def full_cleanup(host):
    print(f"\n{Y}--- Cleaning up ---{RST}")
    stop_tunnel()
    restore_proxychains_conf(host)
    if proxychains_was_installed:
        uninstall_proxychains(host)
    info("All done. Server is back to normal.")


# Reset mode: run this after a force-kill to clean the server manually
def reset_server(host):
    print(BANNER)
    warn(f"Reset mode — cleaning up {host} ...")

    step("Checking for leftover tunnel processes on server...")
    run_remote(host, "pkill -f 'ssh.*-R' 2>/dev/null; true", check=False)

    step("Removing proxychains4 config...")
    try:
        run_remote_sudo(host, "rm -f /etc/proxychains4.conf")
        info("proxychains4 config removed.")
    except Exception as e:
        warn(f"Could not remove config: {e}")

    answer = (
        input(f"\n{Y}Uninstall proxychains4 from server? [y/N]: {RST}").strip().lower()
    )
    if answer == "y":
        uninstall_proxychains(host)

    info("Reset complete.")


# Handle Ctrl+C and SIGTERM gracefully
def handle_signal(sig, frame):
    print(f"\n{Y}Caught signal {sig}, shutting down...{RST}")
    if ssh_host:
        full_cleanup(ssh_host)
    sys.exit(0)


def main():
    global ssh_host, ssh_port, server_port, laptop_port

    parser = argparse.ArgumentParser(
        description="SSH reverse tunnel + proxychains manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Normal mode:   python3 tunnel_manager.py
  Reset mode:    python3 tunnel_manager.py --reset myserver
  Reset w/ port: python3 tunnel_manager.py --reset myserver --ssh-port 2222
        """,
    )
    parser.add_argument(
        "--reset",
        metavar="SSH_HOST",
        help="Reset/clean server state after a force kill",
    )
    parser.add_argument(
        "--ssh-port",
        type=int,
        default=None,
        help="SSH port (used with --reset to skip the prompt)",
    )
    args = parser.parse_args()

    print(BANNER)

    # Reset mode
    if args.reset:
        if args.ssh_port:
            ssh_port = args.ssh_port
        else:
            p = input(f"{C}SSH port of your server{RST} [default: 22]: ").strip()
            ssh_port = int(p) if p else 22
        reset_server(args.reset)
        return

    # Interactive setup
    print(f"{W}Let's set up your proxy tunnel.{RST}\n")

    ssh_host = input(
        f"{C}SSH host/alias for your server{RST} (e.g. myserver or user@ip): "
    ).strip()
    if not ssh_host:
        error("SSH host cannot be empty.")
        sys.exit(1)

    lp = input(
        f"{C}Local SOCKS5 proxy port on your laptop{RST} [default: 3067]: "
    ).strip()
    laptop_port = int(lp) if lp else 3067

    sp = input(
        f"{C}Port to open on the server for the tunnel{RST} [default: 1080]: "
    ).strip()
    server_port = int(sp) if sp else 1080

    sshp = input(f"{C}SSH port of your server{RST} [default: 22]: ").strip()
    ssh_port = int(sshp) if sshp else 22

    print()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Check / install proxychains
    step("Checking if proxychains4 is installed on server...")
    if check_proxychains(ssh_host):
        info("proxychains4 is already installed.")
        backup_proxychains_conf(ssh_host)
    else:
        warn("proxychains4 not found on server.")
        install_proxychains(ssh_host)

    # Configure proxychains
    configure_proxychains(ssh_host, server_port)

    # Start tunnel
    start_tunnel(ssh_host, laptop_port, server_port)

    # Success hint
    print(f"""
{G}---{RST}
{W}  Tunnel is live! On your server, try:{RST}

    {C}proxychains4 curl https://ifconfig.me{RST}

  The IP shown should be your VPN's IP address.

{DIM}  Press Ctrl+C here to shut down the tunnel
  and restore your server to its original state.{RST}
{G}---{RST}
""")

    # Keep alive — watch for unexpected tunnel death
    try:
        while True:
            if ssh_process and ssh_process.poll() is not None:
                warn("SSH tunnel died unexpectedly. Cleaning up...")
                break
            time.sleep(5)
    finally:
        full_cleanup(ssh_host)


if __name__ == "__main__":
    main()
