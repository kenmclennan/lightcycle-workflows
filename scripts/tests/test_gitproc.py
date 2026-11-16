import os
import signal
import subprocess
import sys
import time
import unittest

from tests.harness import SCRIPTS, HangCase

sys.path.insert(0, str(SCRIPTS))
import gitproc  # noqa: E402


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class ConstantsTest(unittest.TestCase):
    def test_default_limits(self):
        self.assertEqual(gitproc.LOCAL_LIMIT, 60)
        self.assertEqual(gitproc.NETWORK_LIMIT, 120)
        self.assertEqual(gitproc.PUSH_LIMIT, 600)
        self.assertEqual(gitproc.GH_LIMIT, 60)

    def test_push_is_pinned_apart_from_the_other_network_commands(self):
        self.assertEqual(gitproc.limit_for(["git", "push", "origin", "x"]), 600)
        for sub in ("fetch", "ls-remote", "clone", "pull"):
            self.assertEqual(gitproc.limit_for(["git", sub]), 120, sub)
        self.assertEqual(gitproc.limit_for(["git", "status"]), 60)
        self.assertEqual(gitproc.limit_for(["gh", "api", "x"]), 60)
        self.assertIsNone(gitproc.limit_for(["lc", "show", "x"]))

    def test_subcommand_is_found_past_global_options(self):
        self.assertEqual(gitproc.git_subcommand(["git", "-C", "/x", "-c", "a=b", "fetch"]), "fetch")


class RecordingPopen:
    calls = []

    def __init__(self, args, **kwargs):
        self.pid = 0
        self.args = args
        self.returncode = 0
        RecordingPopen.calls.append({"args": args, "kwargs": kwargs, "timeout": None})

    def communicate(self, timeout=None):
        RecordingPopen.calls[-1]["timeout"] = timeout
        return "", ""


class PassedLimitTest(unittest.TestCase):
    def setUp(self):
        RecordingPopen.calls = []
        self.real = subprocess.Popen
        subprocess.Popen = RecordingPopen
        self.addCleanup(setattr, subprocess, "Popen", self.real)

    def test_push_gets_the_push_limit_and_fetch_the_shorter_one(self):
        gitproc.run(["git", "push", "origin", "x"])
        gitproc.run(["git", "fetch", "origin"])

        self.assertEqual([c["timeout"] for c in RecordingPopen.calls], [600, 120])

    def test_explicit_timeout_overrides_the_default(self):
        gitproc.run(["git", "fetch"], timeout=5)

        self.assertEqual(RecordingPopen.calls[0]["timeout"], 5)

    def test_network_git_carries_the_low_speed_settings_and_local_does_not(self):
        gitproc.run(["git", "fetch", "origin"])
        gitproc.run(["git", "status"])

        fetch, status = (c["args"] for c in RecordingPopen.calls)
        self.assertEqual(
            fetch[:5], ["git", "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=30"]
        )
        self.assertNotIn("http.lowSpeedLimit=1000", status)

    def test_child_runs_in_its_own_session(self):
        gitproc.run(["git", "status"])

        self.assertTrue(RecordingPopen.calls[0]["kwargs"]["start_new_session"])


class RetryTest(HangCase):
    def write_stub(self, name, body):
        path = self.bin / name
        path.write_text("#!%s\n%s" % (sys.executable, body))
        path.chmod(0o755)

    def run_helper(self, args, **kwargs):
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{old}"
        self.addCleanup(os.environ.__setitem__, "PATH", old)
        os.environ["STUB_DIR"] = str(self.root)
        gitproc.RETRY_PAUSE = 0
        self.addCleanup(setattr, gitproc, "RETRY_PAUSE", 2)
        return gitproc.run(args, **kwargs)

    FLAKY = (
        "import os, sys\n"
        "p = os.environ['STUB_DIR'] + '/n'\n"
        "n = int(open(p).read()) if os.path.exists(p) else 0\n"
        "open(p, 'w').write(str(n + 1))\n"
        "if n == 0:\n"
        "    sys.stderr.write(%r); sys.exit(128)\n"
    )

    def attempts(self):
        return int((self.root / "n").read_text())

    def test_transient_stderr_is_retried_once_and_succeeds(self):
        self.write_stub("git", self.FLAKY % "fatal: Could not resolve host: github.com\n")

        result = self.run_helper(["git", "fetch"])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.attempts(), 2)

    def test_non_transient_failure_is_not_retried(self):
        self.write_stub("git", self.FLAKY % "! [rejected] (non-fast-forward)\n")

        result = self.run_helper(["git", "push"])

        self.assertEqual(result.returncode, 128)
        self.assertEqual(self.attempts(), 1)

    def test_transient_failure_on_a_local_command_is_not_retried(self):
        self.write_stub("git", self.FLAKY % "Connection reset\n")

        result = self.run_helper(["git", "status"])

        self.assertEqual(result.returncode, 128)
        self.assertEqual(self.attempts(), 1)

    def test_retry_false_runs_a_network_call_once(self):
        self.write_stub("gh", self.FLAKY % "HTTP 502\n")

        result = self.run_helper(["gh", "api", "x"], retry=False)

        self.assertEqual(result.returncode, 128)
        self.assertEqual(self.attempts(), 1)

    def test_a_transient_failure_twice_returns_the_second_result(self):
        self.write_stub("gh", "import sys\nsys.stderr.write('HTTP 503\\n'); sys.exit(1)\n")

        result = self.run_helper(["gh", "api", "x"])

        self.assertEqual(result.returncode, 1)
        self.assertIn("HTTP 503", result.stderr)


class TimeoutTest(HangCase):
    def run_helper(self, args, limit=2):
        code = (
            "import sys; sys.path.insert(0, %r); import gitproc\n"
            "gitproc.RETRY_PAUSE = 0\n"
            "try:\n    gitproc.run(%r, timeout=%d)\n"
            "except gitproc.GitTimeout as e:\n    print(e); sys.exit(3)\n"
        ) % (str(SCRIPTS), args, limit)
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env["STUB_DIR"] = str(self.stub)
        if self.grandchild:
            env["STUB_GRANDCHILD"] = "1"
        return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)

    def test_network_command_times_out_after_two_attempts(self):
        self.hang("git")

        started = time.monotonic()
        result = self.run_helper(["git", "fetch"])

        self.assertEqual(result.returncode, 3)
        self.assertIn("timed out", result.stdout)
        self.assertIn("2 attempts", result.stdout)
        self.assertEqual(len(self.calls("git")), 2)
        self.assertLess(time.monotonic() - started, 15)

    def test_local_command_times_out_after_one_attempt(self):
        self.hang("git")

        result = self.run_helper(["git", "status"])

        self.assertEqual(result.returncode, 3)
        self.assertEqual(len(self.calls("git")), 1)

    def test_grandchild_is_killed_with_its_parent(self):
        self.hang("git", grandchild=True)

        result = self.run_helper(["git", "fetch"])

        self.assertEqual(result.returncode, 3)
        pid = int((self.stub / "grandchild.pid").read_text())
        deadline = time.monotonic() + 3
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if alive(pid):
            os.kill(pid, signal.SIGKILL)
            self.fail("grandchild outlived the timed-out command")


class NoRawGitCallsTest(unittest.TestCase):
    def test_no_script_calls_git_or_gh_outside_gitproc(self):
        for path in SCRIPTS.glob("*.py"):
            if path.name == "gitproc.py":
                continue
            text = path.read_text()
            for needle in ("subprocess.run", "subprocess.Popen", "subprocess.check_output", "subprocess.call"):
                self.assertNotIn(needle, text, f"{path.name} calls {needle}")


if __name__ == "__main__":
    unittest.main()
