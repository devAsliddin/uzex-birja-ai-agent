"""Minimal paramiko helper. Reads VPS_HOST / VPS_USER / VPS_PASSWORD from env (never hardcoded)."""
import os
import sys

import paramiko


def connect() -> paramiko.SSHClient:
    host = os.environ["VPS_HOST"]
    user = os.environ.get("VPS_USER", "root")
    password = os.environ["VPS_PASSWORD"]
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # no known_hosts writes
    c.connect(host, username=user, password=password, look_for_keys=False, allow_agent=False, timeout=30)
    return c


def run(c: paramiko.SSHClient, cmd: str, check: bool = True, timeout: int = 1800) -> str:
    _, out, err = c.exec_command(cmd, timeout=timeout, get_pty=False)
    o = out.read().decode(errors="replace")
    e = err.read().decode(errors="replace")
    rc = out.channel.recv_exit_status()
    sys.stdout.write(o)
    if e.strip():
        sys.stdout.write("[stderr] " + e[-4000:] + "\n")
    if check and rc != 0:
        raise SystemExit(f"remote command failed rc={rc}: {cmd[:200]}")
    return o


def put(c: paramiko.SSHClient, local: str, remote: str) -> None:
    sftp = c.open_sftp()
    try:
        sftp.put(local, remote)
    finally:
        sftp.close()


if __name__ == "__main__":
    cl = connect()
    run(cl, sys.argv[1], check=False)
    cl.close()
