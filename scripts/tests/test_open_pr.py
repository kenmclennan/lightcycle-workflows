import json
import os
import importlib.util
import subprocess
import unittest
from unittest import mock

from tests.harness import SCRIPTS, ScriptCase, sh


class OpenPrTest(ScriptCase):
    def test_first_push_creates_the_pr_and_attaches_it(self):
        self.feature_branch()
        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(len(creates), 1)
        fields = creates[0]["fields"]
        self.assertEqual(fields["title"], "feat(x): add the thing")
        self.assertEqual(fields["base"], "main")
        self.assertEqual(fields["head"], "feat/x")
        self.assertTrue(fields["body"].startswith(f"<!-- lc:item={self.item} -->\n<!-- lc:body -->"))
        self.assertIn("body line", fields["body"])
        self.assertIn("## Closing note from write-code\n\nbuilt the thing", fields["body"])
        self.assertTrue(fields["body"].endswith("<!-- /lc:body -->"))
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])
        remote = sh("git", "ls-remote", "--heads", "origin", "feat/x", cwd=self.work).stdout
        self.assertIn("refs/heads/feat/x", remote)

    def test_rework_resync_replaces_only_the_marked_block(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        state = self.read_gh_state()
        pull = state["pulls"][0]
        pull["body"] = "human above\n" + pull["body"] + "\nhuman below"
        self.gh_state = state
        self.write_gh_state()
        self.lc_show["inputs"]["previous"]["report"] = "second round note"
        self.lc_show["runs"][0]["pr"] = pull["html_url"]
        self.write_lc_show()
        (self.work / "feature.txt").write_text("two\n")
        sh("git", "add", "feature.txt", cwd=self.work)
        sh("git", "commit", "--amend", "-m", "feat(x): redesigned thing\n\nnew body", cwd=self.work)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.read_gh_state()["pulls"][0]
        self.assertTrue(after["body"].startswith("human above\n"))
        self.assertTrue(after["body"].endswith("\nhuman below"))
        self.assertIn("new body", after["body"])
        self.assertIn("second round note", after["body"])
        self.assertNotIn("body line", after["body"])
        self.assertNotIn("built the thing", after["body"])
        self.assertEqual(after["title"], "feat(x): redesigned thing")
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(len(creates), 1)

    def test_resync_leaves_a_body_without_markers_alone(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        state = self.read_gh_state()
        state["pulls"][0]["body"] = "written by a human"
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        patches = [c for c in self.gh_calls() if c["method"] == "PATCH"]
        self.assertFalse([p for p in patches if "body" in p["fields"]])
        self.assertEqual(self.read_gh_state()["pulls"][0]["body"], "written by a human")

    def test_resync_adds_the_item_marker_when_absent(self):
        self.feature_branch()
        state = self.read_gh_state()
        state["pulls"].append({
            "number": 1,
            "html_url": "https://github.com/o/r/pull/1",
            "title": "feat(x): add the thing",
            "body": "<!-- lc:body -->\nold\n<!-- /lc:body -->",
        })
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.read_gh_state()["pulls"][0]["body"]
        self.assertTrue(body.startswith(f"<!-- lc:item={self.item} -->\n<!-- lc:body -->"))

    def test_failed_push_is_a_failure_with_no_outcome(self):
        self.feature_branch()
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho rejected by test >&2\nexit 1\n")
        hook.chmod(0o755)

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("rejected by test", result.stderr)
        self.assertFalse([c for c in self.gh_calls() if c["method"] == "POST"])
        self.assertEqual(self.lc_calls(), [])

    def test_rebase_conflict_prints_conflicted_when_declared(self):
        self.commit("clash.txt", "main side\n", "chore: main change")
        sh("git", "push", "origin", "main", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "conflicted")
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.work).stdout, "")

    def test_rebase_conflict_fails_when_no_conflicted_outcome(self):
        self.lc_show["valid_outcomes"] = ["done"]
        self.write_lc_show()
        self.commit("clash.txt", "main side\n", "chore: main change")
        sh("git", "push", "origin", "main", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("clash.txt", result.stderr)

    def test_rebase_failure_without_conflicts_fails_with_its_output(self):
        self.commit("later.txt", "later\n", "chore: main moves")
        sh("git", "push", "origin", "main", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("feature.txt", "one\n", "feat(x): add the thing")
        hook = self.work / ".git" / "hooks" / "pre-rebase"
        hook.write_text("#!/bin/sh\necho refused by test >&2\nexit 1\n")
        hook.chmod(0o755)

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("conflicted", result.stdout)
        self.assertIn("no conflicted paths", result.stderr)
        self.assertIn("origin/main", result.stderr)
        self.assertIn("refused by test", result.stderr)

    def test_origin_default_moved_after_clone_is_followed(self):
        self.feature_branch()
        sh("git", "branch", "-m", "main", "trunk", cwd=self.origin)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(creates[0]["fields"]["base"], "trunk")
        head = sh("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=self.work).stdout.strip()
        self.assertEqual(head, "origin/trunk")

    def test_existing_pr_not_recorded_on_the_run_is_attached(self):
        self.feature_branch()
        state = self.read_gh_state()
        state["pulls"].append({
            "number": 1,
            "html_url": "https://github.com/o/r/pull/1",
            "title": "feat(x): add the thing",
            "body": "<!-- lc:body -->\nold\n<!-- /lc:body -->",
        })
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_existing_pr_already_recorded_is_not_attached_again(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/1"
        self.write_lc_show()
        (self.stub / "lc-calls.jsonl").unlink()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [])

    def test_rebase_in_progress_is_aborted_and_the_run_completes(self):
        self.feature_branch()
        sh("git", "fetch", "origin", cwd=self.work)
        env = {**os.environ, "GIT_SEQUENCE_EDITOR": "perl -pi -e 's/^pick/edit/'"}
        subprocess.run(
            ["git", "rebase", "-i", "origin/main"], cwd=self.work, env=env, check=True, capture_output=True
        )
        self.assertEqual(sh("git", "branch", "--show-current", cwd=self.work).stdout.strip(), "")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        self.assertEqual(sh("git", "branch", "--show-current", cwd=self.work).stdout.strip(), "feat/x")
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_recorded_pr_without_a_branch_pr_is_a_divergence(self):
        self.feature_branch()
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/9"
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("pull/9", result.stderr)
        self.assertFalse([c for c in self.gh_calls() if c["method"] == "POST"])

    def test_newest_run_of_the_pass_and_phase_decides_the_recorded_pr(self):
        self.feature_branch()
        older = dict(self.lc_show["runs"][0], id="older", pr="https://github.com/o/r/pull/9")
        newer = dict(self.lc_show["runs"][0], id="newer", pr=None)
        self.lc_show["runs"] = [older, newer]
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_create_error_that_succeeded_server_side_is_used(self):
        self.feature_branch()
        self.gh_state.update(create_error=True, create_server_side=True)
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_create_error_with_no_pr_fails(self):
        self.feature_branch()
        self.gh_state.update(create_error=True)
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.lc_calls(), [])

    def test_stale_local_branch_is_reset_to_the_remote_head(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        local = sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip()
        other = self.root / "other"
        sh("git", "clone", "-b", "feat/x", str(self.origin), str(other))
        sh("git", "config", "user.name", "T", cwd=other)
        sh("git", "config", "user.email", "t@example.com", cwd=other)
        (other / "more.txt").write_text("more\n")
        sh("git", "add", "more.txt", cwd=other)
        sh("git", "commit", "-m", "feat(x): remote advance", cwd=other)
        sh("git", "push", "origin", "feat/x", cwd=other)
        remote = sh("git", "rev-parse", "HEAD", cwd=other).stdout.strip()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        note = json.loads(result.stdout)["note"]
        self.assertIn(local, note)
        self.assertIn(remote, note)
        self.assertEqual(sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip(), remote)

    def test_stale_local_branch_with_dirty_tree_fails(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        other = self.root / "other"
        sh("git", "clone", "-b", "feat/x", str(self.origin), str(other))
        sh("git", "config", "user.name", "T", cwd=other)
        sh("git", "config", "user.email", "t@example.com", cwd=other)
        (other / "more.txt").write_text("more\n")
        sh("git", "add", "more.txt", cwd=other)
        sh("git", "commit", "-m", "feat(x): remote advance", cwd=other)
        sh("git", "push", "origin", "feat/x", cwd=other)
        (self.work / "scratch.txt").write_text("dirty\n")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("scratch.txt", result.stderr)

    def test_untracked_file_refuses_to_open_a_pr(self):
        self.feature_branch()
        (self.work / "digest.md").write_text("late\n")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("digest.md", result.stderr)
        self.assertIn("uncommitted changes", result.stderr)
        self.assertEqual(self.gh_calls(), [])
        self.assertEqual(self.lc_calls(), [])

    def test_uncommitted_edit_refuses_to_update_an_open_pr(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        (self.work / "feature.txt").write_text("edited\n")
        (self.stub / "gh-calls.jsonl").unlink()

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("feature.txt", result.stderr)
        self.assertEqual(self.gh_calls(), [])


class OpenPrNonMainBaseTest(ScriptCase):
    base_branch = "master"

    def test_pr_base_and_rebase_use_the_default_branch(self):
        self.commit("later.txt", "later\n", "chore: base moves")
        sh("git", "push", "origin", "master", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("feature.txt", "one\n", "feat(x): add the thing")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(creates[0]["fields"]["base"], "master")
        base = sh("git", "merge-base", "origin/master", "HEAD", cwd=self.work).stdout.strip()
        self.assertEqual(base, sh("git", "rev-parse", "origin/master", cwd=self.work).stdout.strip())

    def test_rebase_conflict_names_the_default_branch(self):
        self.lc_show["valid_outcomes"] = ["done"]
        self.write_lc_show()
        self.commit("clash.txt", "base side\n", "chore: base change")
        sh("git", "push", "origin", "master", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("origin/master", result.stderr)
        self.assertIn("clash.txt", result.stderr)

    def test_rebase_conflict_prints_conflicted_when_declared(self):
        self.commit("clash.txt", "base side\n", "chore: base change")
        sh("git", "push", "origin", "master", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "conflicted")


DELIVERY = (
    "Decision: stack\n"
    "Reasons: the change has two seams a reviewer reads apart\n"
    "Layer 1: the data model, cut here because nothing else depends on it yet\n"
    "Layer 2: the caller, cut here because it needs the model"
)


class StackedOpenPrTest(ScriptCase):
    def stacked(self, **cfg):
        sh("git", "checkout", "-b", "feat/x-1", cwd=self.work)
        self.commit("model.txt", "m\n", "feat(model): add the model\n\nmodel body")
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        self.commit("caller.txt", "c\n", "feat(caller): use the model\n\ncaller body")
        self.gh_state["stack"] = dict({"branches": ["feat/x-1", "feat/x"]}, **cfg)
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = [{"name": "delivery", "value": DELIVERY}]
        self.write_lc_show()

    def pulls(self):
        return self.read_gh_state()["pulls"]

    def push_stack(self):
        self.stacked()
        sh("git", "push", "origin", "feat/x-1", "feat/x", cwd=self.work)

    def other_clone(self):
        other = self.root / "other"
        sh("git", "clone", str(self.origin), str(other))
        sh("git", "config", "user.name", "Tester", cwd=other)
        sh("git", "config", "user.email", "t@example.com", cwd=other)
        sh("git", "checkout", "feat/x-1", cwd=other)
        return other

    def rev(self, ref):
        return sh("git", "rev-parse", ref, cwd=self.work).stdout.strip()

    def test_stale_lower_layer_is_reset_to_the_rewritten_remote(self):
        self.push_stack()
        stale = self.rev("feat/x-1")
        other = self.other_clone()
        (other / "model.txt").write_text("m2\n")
        sh("git", "add", "model.txt", cwd=other)
        sh("git", "commit", "--amend", "-m", "feat(model): rewrite the model", cwd=other)
        sh("git", "push", "--force", "origin", "feat/x-1", cwd=other)
        sh("git", "fetch", "origin", cwd=self.work)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        note = json.loads(result.stdout)["note"]
        self.assertEqual(self.rev("feat/x-1"), self.rev("origin/feat/x-1"))
        self.assertNotEqual(self.rev("feat/x-1"), stale)
        self.assertIn(f"reset layer feat/x-1 {stale}", note)

    def two_commit_layer(self):
        self.stacked()
        sh("git", "checkout", "feat/x-1", cwd=self.work)
        self.commit("more.txt", "more\n", "feat(model): extend the model")
        sh("git", "checkout", "feat/x", cwd=self.work)
        sh("git", "push", "origin", "feat/x-1", "feat/x", cwd=self.work)

    def test_two_commit_lower_layer_rewritten_on_the_remote_is_reset(self):
        self.two_commit_layer()
        stale = self.rev("feat/x-1")
        other = self.other_clone()
        sh("git", "reset", "--hard", "HEAD~2", cwd=other)
        for name in ("a.txt", "b.txt"):
            (other / name).write_text(name)
            sh("git", "add", name, cwd=other)
            sh("git", "commit", "-m", f"feat(model): rewrite {name}", cwd=other)
        sh("git", "push", "--force", "origin", "feat/x-1", cwd=other)
        sh("git", "fetch", "origin", cwd=self.work)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rev("feat/x-1"), self.rev("origin/feat/x-1"))
        self.assertIn(f"reset layer feat/x-1 {stale}", json.loads(result.stdout)["note"])

    def test_local_only_commit_on_a_two_commit_layer_is_held_back(self):
        self.two_commit_layer()
        sh("git", "checkout", "feat/x-1", cwd=self.work)
        self.commit("local.txt", "l\n", "feat(model): local only")
        sh("git", "checkout", "feat/x", cwd=self.work)
        local = self.rev("feat/x-1")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rev("feat/x-1"), local)
        self.assertIn("held back layer feat/x-1", json.loads(result.stdout)["note"])

    def test_remote_ahead_lower_layer_is_fast_forwarded(self):
        self.push_stack()
        other = self.other_clone()
        (other / "more.txt").write_text("more\n")
        sh("git", "add", "more.txt", cwd=other)
        sh("git", "commit", "-m", "feat(model): extend the model", cwd=other)
        sh("git", "push", "origin", "feat/x-1", cwd=other)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rev("feat/x-1"), self.rev("origin/feat/x-1"))
        self.assertIn("reset layer feat/x-1", json.loads(result.stdout)["note"])

    def test_local_only_layer_commit_is_never_reset(self):
        self.push_stack()
        sh("git", "checkout", "feat/x-1", cwd=self.work)
        self.commit("local.txt", "l\n", "feat(model): local only")
        sh("git", "checkout", "feat/x", cwd=self.work)
        local = self.rev("feat/x-1")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rev("feat/x-1"), local)
        self.assertNotEqual(self.rev("origin/feat/x-1"), local)
        self.assertIn("held back layer feat/x-1", json.loads(result.stdout)["note"])

    def test_layer_checked_out_in_another_worktree_is_skipped(self):
        self.push_stack()
        other = self.other_clone()
        (other / "more.txt").write_text("more\n")
        sh("git", "add", "more.txt", cwd=other)
        sh("git", "commit", "-m", "feat(model): extend the model", cwd=other)
        sh("git", "push", "origin", "feat/x-1", cwd=other)
        held = self.rev("feat/x-1")
        sh("git", "worktree", "add", str(self.root / "held"), "feat/x-1", cwd=self.work)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rev("feat/x-1"), held)
        self.assertIn("checked out in another worktree", json.loads(result.stdout)["note"])

    def test_stack_submits_and_attaches_the_stack_and_the_top_pr(self):
        self.stacked()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        stack_calls = [c["path"] for c in self.gh_calls() if c["method"] == "STACK"]
        self.assertIn("rebase", stack_calls)
        self.assertIn("submit --auto --open", stack_calls)
        self.assertEqual(
            self.lc_calls(),
            [
                ["attach", self.item, "stack", "https://github.com/o/r/stack/7"],
                ["attach", self.item, "pr", "https://github.com/o/r/pull/2"],
            ],
        )
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(creates, [])

    def test_each_layer_body_quotes_its_own_layer_line(self):
        self.stacked()

        self.assertEqual(self.run_script("open-pr.py").returncode, 0)

        lower, top = self.pulls()
        self.assertEqual(lower["title"], "feat(model): add the model")
        self.assertTrue(lower["body"].startswith(f"<!-- lc:item={self.item} -->\n<!-- lc:body -->"))
        self.assertIn("model body", lower["body"])
        self.assertIn("## Delivery\n\nLayer 1: the data model", lower["body"])
        self.assertNotIn("Layer 2", lower["body"])
        self.assertNotIn("Decision:", lower["body"])
        self.assertNotIn("Closing note", lower["body"])
        self.assertEqual(top["title"], "feat(caller): use the model")
        self.assertIn("Decision: stack\nReasons: the change has two seams", top["body"])
        self.assertIn("Layer 2: the caller", top["body"])
        self.assertNotIn("Layer 1", top["body"])
        self.assertIn("## Closing note from write-code\n\nbuilt the thing", top["body"])

    def test_exit_nine_lands_as_one_pr_with_the_fallback_noted(self):
        self.stacked(submit_rc=9)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        (pull,) = self.pulls()
        self.assertEqual(pull["head"], "feat/x")
        self.assertIn("Stacks are not enabled for this repo", pull["body"])
        self.assertIn("Decision: stack", pull["body"])
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_other_stack_failure_fails_the_stage(self):
        self.stacked(submit_rc=3)

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("gh stack submit --auto --open failed (3)", result.stderr)
        self.assertEqual(self.lc_calls(), [])

    def test_rerun_updates_the_same_layers_without_duplicates(self):
        self.stacked()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/2"
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.pulls()), 2)
        self.assertIn("Layer 1: the data model", self.pulls()[0]["body"])

    def seed_github_stack(self, heads, **cfg):
        for index, head in enumerate(heads, start=1):
            self.gh_state["pulls"].append({
                "number": index, "html_url": f"https://github.com/o/r/pull/{index}",
                "title": head, "body": "old", "head": head, "state": "open",
            })
        self.gh_state["stack"]["github"] = {"heads": heads}
        self.gh_state["stack"].update(cfg)
        self.write_gh_state()
        self.lc_show["runs"][0]["stack"] = "https://github.com/o/r/stack/7"
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/3"
        self.write_lc_show()

    def stack_calls(self):
        return [c["path"] for c in self.gh_calls() if c["method"] == "STACK"]

    def test_recut_that_drops_a_layer_closes_it_and_replaces_the_stack(self):
        self.stacked(unstack_clears_local=True)
        self.seed_github_stack(["feat/x-1", "feat/x-mid", "feat/x"], submit_stack=8)
        self.gh_state["pulls"][2]["head"] = "feat/x"
        self.gh_state["pulls"][1]["head"] = "feat/x-mid"
        self.gh_state["pulls"][0]["head"] = "feat/x-1"
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.stack_calls()
        self.assertLess(calls.index("unstack 7"), calls.index("init feat/x-1 feat/x"))
        self.assertLess(calls.index("init feat/x-1 feat/x"), calls.index("submit --auto --open"))
        mid = self.pulls()[1]
        self.assertEqual(mid["state"], "closed")
        comments = [c for c in self.gh_calls() if c["path"].endswith("/issues/2/comments") and c["method"] == "POST"]
        self.assertEqual(comments[0]["fields"]["body"], "Layer dropped by a re-cut; see https://github.com/o/r/pull/3")
        self.assertTrue(any(c["method"] == "DELETE" and c["path"].endswith("heads/feat/x-mid") for c in self.gh_calls()))
        self.assertEqual(
            self.lc_calls(),
            [
                ["attach", self.item, "stack", "https://github.com/o/r/stack/8", "--replace"],
                ["attach", self.item, "pr", "https://github.com/o/r/pull/3", "--replace"],
            ],
        )
        open_heads = [p["head"] for p in self.pulls() if p.get("state", "open") == "open"]
        self.assertEqual(sorted(open_heads), ["feat/x", "feat/x-1"])

    def test_recut_skips_init_when_the_local_stack_already_matches(self):
        self.stacked()
        self.seed_github_stack(["feat/x-1", "feat/x-mid", "feat/x"], submit_stack=8)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.stack_calls()
        self.assertIn("unstack 7", calls)
        self.assertFalse([c for c in calls if c.startswith("init")])
        self.assertIn("submit --auto --open", calls)
        self.assertEqual(self.pulls()[1]["state"], "closed")
        self.assertEqual(self.lc_calls()[0], ["attach", self.item, "stack", "https://github.com/o/r/stack/8", "--replace"])

    def test_unchanged_layer_set_does_not_unstack(self):
        self.stacked()
        self.seed_github_stack(["feat/x-1", "feat/x"])
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/2"
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.stack_calls()
        self.assertNotIn("unstack 7", calls)
        self.assertFalse([c for c in calls if c.startswith("init")])
        self.assertEqual(self.lc_calls(), [["attach", self.item, "stack", "https://github.com/o/r/stack/7"]])

    def test_dissolved_recorded_stack_submits_as_a_first_open(self):
        self.stacked()
        self.lc_show["runs"][0]["stack"] = "https://github.com/o/r/stack/7"
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse([c for c in self.stack_calls() if c.startswith(("unstack", "init"))])

    def test_no_stack_takes_todays_path_and_attaches_no_stack(self):
        self.feature_branch()
        self.lc_show["inputs"]["item"] = [
            {"name": "delivery", "value": "Decision: one-pr\nReasons: one seam"}
        ]
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])
        self.assertNotIn("Delivery", self.pulls()[0]["body"])
        self.assertEqual([c for c in self.gh_calls() if c["method"] == "STACK"], [
            c for c in self.gh_calls() if c["method"] == "STACK" and c["path"] == "view --json"
        ])


class CompletionRepliesTest(ScriptCase):
    def ack(self, cid, stamp, extra=""):
        return {"id": cid, "created_at": stamp, "body": f"<!-- lc -->\n<!-- lc:decision=rework -->\n{extra}ack"}

    def open_pr_then_seed(self, **lists):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        state = self.read_gh_state()
        state.update(lists)
        self.gh_state = state
        self.write_gh_state()
        (self.stub / "gh-calls.jsonl").unlink()

    def replies(self):
        return [
            c for c in self.gh_calls()
            if c["method"] == "POST" and ("/replies" in c["path"] or c["path"].endswith("/issues/1/comments"))
        ]

    def test_mixed_case_answers_only_the_eligible_acknowledgement(self):
        old, future = "2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z"
        self.open_pr_then_seed(
            issue_comments=[
                self.ack(11, old),
                {"id": 12, "created_at": old, "body": "<!-- lc -->\n<!-- lc:completes=11 -->\ndone"},
            ],
            review_comments=[self.ack(21, old), self.ack(22, future)],
            reviews=[],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        posted = self.replies()
        self.assertEqual(len(posted), 1)
        self.assertTrue(posted[0]["path"].endswith("/pulls/1/comments/21/replies"))
        body = posted[0]["fields"]["body"]
        self.assertTrue(body.startswith("<!-- lc -->\n<!-- lc:completes=21 -->"))
        self.assertIn(sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip(), body)
        self.assertIn("feat(x): add the thing", body)

    def test_top_level_acknowledgement_gets_a_top_level_reply(self):
        self.open_pr_then_seed(
            issue_comments=[self.ack(31, "2000-01-01T00:00:00Z")],
            review_comments=[],
            reviews=[],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        posted = self.replies()
        self.assertEqual(len(posted), 1)
        self.assertTrue(posted[0]["path"].endswith("/issues/1/comments"))

    def test_review_body_acknowledgement_is_answered(self):
        review = {"id": 41, "submitted_at": "2000-01-01T00:00:00Z", "body": "<!-- lc:decision=rework -->"}
        self.open_pr_then_seed(issue_comments=[], review_comments=[], reviews=[review])

        self.run_script("open-pr.py")

        posted = self.replies()
        self.assertEqual(len(posted), 1)
        self.assertIn("lc:completes=41", posted[0]["fields"]["body"])

    def test_all_answered_posts_nothing(self):
        old = "2000-01-01T00:00:00Z"
        self.open_pr_then_seed(
            issue_comments=[self.ack(51, old), {"id": 52, "created_at": old, "body": "<!-- lc:completes=51 -->"}],
            review_comments=[],
            reviews=[],
        )

        self.run_script("open-pr.py")

        self.assertEqual(self.replies(), [])

    def test_none_answered_replies_to_every_eligible(self):
        old = "2000-01-01T00:00:00Z"
        self.open_pr_then_seed(
            issue_comments=[self.ack(61, old), self.ack(62, old)],
            review_comments=[self.ack(63, old)],
            reviews=[],
        )

        self.run_script("open-pr.py")

        self.assertEqual(len(self.replies()), 3)


if __name__ == "__main__":
    unittest.main()


IRREDUCIBLE_DELIVERY = (
    "Decision: stack\n"
    "Reasons: the change has two seams a reviewer reads apart\n"
    "Layer 1: the data model, irreducible - one schema that cannot be split\n"
    "Layer 2: the caller, cut here because it needs the model"
)


class SizeCheckTest(ScriptCase):
    def setUp(self):
        super().setUp()
        self.lc_show["valid_outcomes"] = ["done", "conflicted", "too-big"]
        self.write_lc_show()

    def stacked(self, lines, delivery=DELIVERY):
        sh("git", "checkout", "-b", "feat/x-1", cwd=self.work)
        self.commit("model.txt", "m\n" * lines, "feat(model): add the model\n\nmodel body")
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        self.commit("caller.txt", "c\n", "feat(caller): use the model\n\ncaller body")
        self.gh_state["stack"] = {"branches": ["feat/x-1", "feat/x"]}
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = [{"name": "delivery", "value": delivery}]
        self.write_lc_show()

    def one_pr(self, lines, delivery):
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        self.commit("big.txt", "b\n" * lines, "feat(x): big\n\nbody")
        self.lc_show["inputs"]["item"] = [{"name": "delivery", "value": delivery}]
        self.write_lc_show()

    def assert_nothing_pushed(self):
        writes = [c for c in self.gh_calls() if c["method"] not in ("GET",) and c["path"] != "view --json"]
        self.assertEqual(writes, [])
        self.assertEqual(self.lc_calls(), [])
        remote = sh("git", "ls-remote", "--heads", "origin", "feat/x", cwd=self.work).stdout
        self.assertEqual(remote, "")

    def test_oversized_layer_not_marked_irreducible_closes_too_big_and_pushes_nothing(self):
        self.stacked(500)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["outcome"], "too-big")
        self.assertEqual(
            out["note"],
            "Re-cut: layer 1 of 2 is 500 lines, over layer-lines-limit 400 and not marked irreducible",
        )
        self.assert_nothing_pushed()

    def test_the_same_layer_marked_irreducible_opens(self):
        self.stacked(500, IRREDUCIBLE_DELIVERY)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        self.assertEqual(len(self.read_gh_state()["pulls"]), 2)

    def test_layers_under_the_limit_open_as_today(self):
        self.stacked(399)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

    def test_a_set_key_overrides_the_limit(self):
        self.stacked(401)
        self.assertEqual(json.loads(self.run_script("open-pr.py").stdout)["outcome"], "too-big")

        result = self.run_script("open-pr.py", {"LC_WORKFLOW_CONFIG_LAYER_LINES_LIMIT": "500"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

    def test_an_unset_key_fails_naming_it(self):
        self.stacked(10)

        result = self.run_script("open-pr.py", {"LC_WORKFLOW_CONFIG_LAYER_LINES_LIMIT": None})

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("layer-lines-limit", result.stderr)

    def test_a_blank_key_fails_naming_it(self):
        self.stacked(10)

        result = self.run_script("open-pr.py", {"LC_WORKFLOW_CONFIG_LAYER_LINES_LIMIT": "  "})

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("layer-lines-limit", result.stderr)

    def test_a_malformed_key_fails_naming_it(self):
        self.stacked(10)

        result = self.run_script("open-pr.py", {"LC_WORKFLOW_CONFIG_LAYER_LINES_LIMIT": "lots"})

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("layer-lines-limit", result.stderr)

    def test_layer_two_is_measured_against_layer_one(self):
        sh("git", "checkout", "-b", "feat/x-1", cwd=self.work)
        self.commit("model.txt", "m\n" * 300, "feat(model): add the model")
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        self.commit("caller.txt", "c\n" * 300, "feat(caller): use the model")
        self.gh_state["stack"] = {"branches": ["feat/x-1", "feat/x"]}
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = [{"name": "delivery", "value": DELIVERY}]
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

    def test_a_lower_layer_lagging_its_remote_head_is_measured_after_the_sync(self):
        sh("git", "checkout", "-b", "feat/x-1", cwd=self.work)
        self.commit("model.txt", "m\n" * 10, "feat(model): add the model")
        stale = sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip()
        sh("git", "checkout", self.base_branch, cwd=self.work)
        self.commit("drift.txt", "d\n" * 500, "chore: trunk drift")
        sh("git", "push", "origin", self.base_branch, cwd=self.work)
        sh("git", "checkout", "-b", "restacked", "feat/x-1", cwd=self.work)
        sh("git", "rebase", self.base_branch, cwd=self.work)
        sh("git", "push", "origin", "restacked:feat/x-1", cwd=self.work)
        self.commit("caller.txt", "c\n", "feat(caller): use the model")
        sh("git", "branch", "-M", "feat/x", cwd=self.work)
        sh("git", "fetch", "origin", cwd=self.work)
        self.gh_state["stack"] = {"branches": ["feat/x-1", "feat/x"]}
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = [{"name": "delivery", "value": DELIVERY}]
        self.write_lc_show()
        self.assertEqual(sh("git", "rev-parse", "feat/x-1", cwd=self.work).stdout.strip(), stale)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

    def test_one_pr_over_the_limit_is_refused_unless_reasons_say_irreducible(self):
        self.one_pr(500, "Decision: one-pr\nReasons: one seam")

        result = self.run_script("open-pr.py")

        self.assertEqual(json.loads(result.stdout)["outcome"], "too-big")
        self.assertIn("the one PR is 500 lines", json.loads(result.stdout)["note"])
        self.assert_nothing_pushed()

    def test_one_pr_marked_irreducible_in_reasons_opens(self):
        self.one_pr(500, "Decision: one-pr\nReasons: irreducible - one generated schema")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

    def test_a_stage_without_a_too_big_outcome_is_never_measured(self):
        self.lc_show["valid_outcomes"] = ["done", "conflicted"]
        self.one_pr(900, "Decision: one-pr\nReasons: one seam")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")


class StackLockTest(ScriptCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("open_pr_under_test", SCRIPTS / "open-pr.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.clock = [0.0]
        self.sleeps = []

        def sleep(seconds):
            self.sleeps.append(seconds)
            self.clock[0] += seconds

        module.sleep = sleep
        module.monotonic = lambda: self.clock[0]
        return module

    def stacked(self, **cfg):
        sh("git", "checkout", "-b", "feat/x-1", cwd=self.work)
        self.commit("model.txt", "m\n", "feat(model): add the model")
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        self.gh_state["stack"] = dict({"branches": ["feat/x-1", "feat/x"]}, **cfg)
        self.write_gh_state()

    def call(self, function, *args):
        env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "STUB_DIR": str(self.stub)}
        module = self.load()
        previous = os.getcwd()
        os.chdir(self.work)
        try:
            with mock.patch.dict(os.environ, env):
                return module, getattr(module, function)(*args)
        finally:
            os.chdir(previous)

    def stack_calls(self):
        return [c["path"] for c in self.gh_calls() if c["method"] == "STACK"]

    def test_rebase_retries_a_lock_failure_without_aborting(self):
        self.stacked(lock_failures={"rebase": 1})

        _, result = self.call("rebase_stack", ["done", "conflicted"])

        self.assertIsNone(result)
        self.assertEqual(self.stack_calls(), ["rebase", "rebase"])
        self.assertEqual(self.sleeps, [5])

    def test_rebase_waits_longer_between_tries_up_to_a_cap(self):
        self.stacked(lock_failures={"rebase": 5})

        self.call("rebase_stack", ["done"])

        self.assertEqual(self.sleeps, [5, 10, 20, 20, 20])

    def test_rebase_whose_lock_never_clears_fails_naming_the_lock(self):
        self.stacked(lock_failures={"rebase": 1000})

        with self.assertRaises(Exception) as caught:
            self.call("rebase_stack", ["done", "conflicted"])

        message = str(caught.exception)
        self.assertIn("gh stack lock", message)
        self.assertIn("150 s", message)
        self.assertNotIn("--abort", self.stack_calls())
        self.assertLessEqual(sum(self.sleeps), 150)

    def test_submit_retries_a_lock_failure(self):
        self.stacked(lock_failures={"submit": 2})

        _, url = self.call("submit_stack", "feat/x")

        self.assertEqual(url, "https://github.com/o/r/stack/7")
        self.assertEqual(self.sleeps, [5, 10])

    def test_a_failure_that_is_not_the_lock_is_not_retried(self):
        self.stacked(submit_rc=3)

        with self.assertRaises(Exception) as caught:
            self.call("submit_stack", "feat/x")

        self.assertIn("failed (3)", str(caught.exception))
        self.assertEqual(self.sleeps, [])
