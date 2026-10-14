This only applies when either (a) `lc show STEP`'s note contains a `SPEC CHANGE:` line, or (b) mid-implementation you find the change you are building contradicts, rather than extends, a stated spec Design/Acceptance decision - narrower than the ordinary "spec can be stale" posture, which covers a factual claim only: this applies only when a human's own comment or review thread on the code PR (not your own inference) already asked for the contradicting change. Neither path is your own judgement that the spec is wrong - both terminate in a real, findable PR comment or review thread that asked for the change:

- Path (a): `handle-feedback` wrote the `SPEC CHANGE:` line from a specific comment/review it read - locate it on the code PR (`gh api repos/{OWNER}/{REPO}/pulls/{NUM}/comments` for an inline review comment, or `gh api repos/{OWNER}/{REPO}/issues/{NUM}/comments` for a top-level one - both already REST - matched by timing/content to the note) and its `html_url` is `Source:` below.
- Path (b): search the PR's comments/reviews for the authorizing thread yourself; if found, its `html_url` is `Source:`.

**If neither path turns up a real, resolvable authorizing url - or the comment it names carries `<!-- lc -->`, which means an lc agent posted it and a finding is not a human's decision - do not amend.** Block instead, naming the comment and, when it carries the marker, that it is lc's own: `lc set STEP --state waiting --needs "<what human decision this needs>" --reason "<what happened that led here>"`, then EXIT. Only once a genuine authorizing comment/thread is in hand does this pass amend the spec, before finishing:

1. Resolve the specs repo's root from the already-synced checkout: `git -C "$(dirname SPEC)" rev-parse --show-toplevel` (SPECS_ROOT), and its remote: `git -C SPECS_ROOT remote get-url origin` (SPECS_REMOTE). Do not edit or commit inside SPECS_ROOT itself - it is the shared checkout every concurrent claim's `sync_specs()` reads and fast-forwards; writing there risks another worker's claim hitting a dirty or diverged checkout.
2. **Idempotency check first**: `lc show ITEM` for an existing `spec-amendment` artifact. If one exists, its value is this item's amendment PR url - reuse it (skip to sub-step 4 below) rather than opening a second one.
3. In a fresh scratch clone (`git clone SPECS_REMOTE <tmpdir>`, not SPECS_ROOT), check out the amendment branch: if sub-step 2 found an existing PR, fetch and check out its branch; otherwise branch from the specs repo's current default branch, named e.g. `spec-amend/<ITEM>-<short-slug>`. Edit the spec file at the same repo-relative path as SPEC by **appending**, never editing existing prose in place, a new section:

   **Binding:**

   ```
   ## Amendment (<STEP>, <YYYY-MM-DD>)

   Supersedes: <what it overrides, matching the SPEC CHANGE: note's first line>

   Source: <PR comment/thread url that authorized this>

   <the new decision, in the detail a coder or reviewer needs to build/check it>
   ```

   `Source:` must be the real, resolvable url located above - never a placeholder, never your own paraphrase of "a human asked for this" with no url behind it. Keep the blank line between `Supersedes:` and `Source:`: a formatter that unwraps prose merges consecutive non-blank lines into one paragraph, and the review stage checks for a standalone `Source:` line, so without it a genuine amendment reads as unauthorized. Format it as the specs repo's `CLAUDE.md` requires. Commit (a subject naming the item and the short reason, per the specs repo's `CLAUDE.md`), push the branch, and (first time only) open the PR via REST - `gh api repos/{SPECS_OWNER}/{SPECS_REPO}/pulls -f title="Amend <ITEM>: <short reason>" -f body="<body>" -f head=<branch> -f base=<specs repo's default branch> --jq .html_url` (`SPECS_OWNER`/`SPECS_REPO` parsed from SPECS_REMOTE, matching `https://github.com/{SPECS_OWNER}/{SPECS_REPO}.git`; POST is the default once fields are present, per `gh help api`), body explaining this records a decision already made in the code PR's comment thread and linking it. **Never merge it** - same rule as every other PR this pipeline opens. Inline the body with `-f` exactly as written above, or write it to a file first to sidestep shell quoting on a long or multi-line body. Use `-F body=@file`, never `-f body=@file`.

4. `lc attach ITEM spec-amendment <pr-url> --replace` (first time), or leave the existing artifact as-is (rework of an already-open amendment - the url doesn't change).
5. Proceed to build to match the amended design, as if SPEC already read that way.
6. Carry the amendment PR url forward to the `--note` on your final `lc done`.

If the push in sub-step 3 above is rejected (a concurrent amendment landed), fetch, re-apply the appended section against the new tip, and retry once; if it still conflicts, `lc set STEP --state waiting --needs "<...>" --reason "<what happened that led here>"`.
