import os
import signal
import subprocess
import time

LOCAL_LIMIT = 60
NETWORK_LIMIT = 120
PUSH_LIMIT = 600
GH_LIMIT = 60
RETRY_PAUSE = 2

NETWORK_GIT = ("fetch", "push", "ls-remote", "clone", "pull")
LOW_SPEED = ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=30"]
TRANSIENT = (
    "Could not resolve host",
    "Connection reset",
    "Connection timed out",
    "TLS",
    "SSL",
    "early EOF",
    "RPC failed",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
    "i/o timeout",
)

sleep = time.sleep


class GitTimeout(Exception):
    def __init__(self, cmd, limit, attempts):
        self.cmd = cmd
        self.limit = limit
        self.attempts = attempts
        super().__init__(f"{cmd} timed out after {limit}s ({attempts} attempt{'s' if attempts != 1 else ''})")


def git_subcommand(args):
    i = 1
    while i < len(args):
        if args[i] in ("-c", "-C"):
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i]
    return None


def is_network(args):
    if args[0] == "gh":
        return True
    return args[0] == "git" and git_subcommand(args) in NETWORK_GIT


def limit_for(args):
    if args[0] == "gh":
        return GH_LIMIT
    if args[0] != "git":
        return None
    sub = git_subcommand(args)
    if sub == "push":
        return PUSH_LIMIT
    if sub in NETWORK_GIT:
        return NETWORK_LIMIT
    return LOCAL_LIMIT


def _attempt(args, limit):
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return None
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


def run(args, *, timeout=None, retry=True):
    args = list(args)
    network = is_network(args)
    limit = timeout if timeout is not None else limit_for(args)
    if network and args[0] == "git":
        args = [args[0], *LOW_SPEED, *args[1:]]
    attempts_allowed = 2 if network and retry else 1
    attempt = 0
    while True:
        attempt += 1
        result = _attempt(args, limit)
        if result is not None and result.returncode == 0:
            return result
        transient = result is None or any(t in (result.stderr or "") for t in TRANSIENT)
        if attempt < attempts_allowed and transient:
            sleep(RETRY_PAUSE)
            continue
        if result is None:
            raise GitTimeout(" ".join(args), limit, attempt)
        return result
