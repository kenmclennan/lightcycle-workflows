import json
import os
import subprocess
import unittest

from tests.harness import ScriptCase, sh


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
