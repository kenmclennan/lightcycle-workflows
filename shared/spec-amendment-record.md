This only applies when either (a) the claim's `inputs.previous.report` contains a `SPEC CHANGE:` line, or (b) mid-implementation you find the change you are building contradicts, rather than extends, a stated spec Design/Acceptance decision - narrower than the ordinary "spec can be stale" posture, which covers a factual claim only: this applies only when a human's own comment or review thread on the code PR (not your own inference) already asked for the contradicting change. Neither path is your own judgement that the spec is wrong - both terminate in a real, findable PR comment or review thread that asked for the change:

- Path (a): `handle-feedback` wrote the `SPEC CHANGE:` line from a specific comment/review it read - locate it on the code PR (`gh api repos/{OWNER}/{REPO}/pulls/{NUM}/comments` for an inline review comment, or `gh api repos/{OWNER}/{REPO}/issues/{NUM}/comments` for a top-level one - both already REST - matched by timing/content to the note) and its `html_url` is `Source:` below.
- Path (b): search the PR's comments/reviews for the authorizing thread yourself; if found, its `html_url` is `Source:`. The authorising comment must be by a trusted author: take `TRUSTED` from the `trusted-authors` entry of `.artifacts` in the claim output (one casefolded login per line; when the entry is absent no one is trusted), and treat the comment's author as trusted when their login, casefolded, is in `TRUSTED`, or when the comment's `<kind>:<id>` key is in the `admitted-comments` entry where present. A comment by anyone else is not an authorisation and is never used as `Source:`.

**If neither path turns up a real, resolvable authorizing url - or the comment it names carries `<!-- lc -->`, which means an lc agent posted it and a finding is not a human's decision, or the comment's author is not trusted - do not amend.** Block instead, naming the comment and, when it carries the marker, that it is lc's own, or, when its author is untrusted, that author and that they are not in `trusted-authors`: `lc set STEP --state waiting --needs "<what human decision this needs>" --reason "<what happened that led here>"`, then EXIT. Only once a genuine authorizing comment/thread is in hand does this pass record the amendment on the item, before finishing:

1. Read the item's current `spec-amendment` artifact (`lc show ITEM`), if any. If its value begins with `https://` and ends in `/pull/<number>`, it is a legacy PR-url value from before amendments were recorded on the item: do not fetch the PR, and treat the artifact as holding no text, so step 2 replaces it.
2. Write the new section, never editing existing prose in place:

   **Binding:**

   ```
   ## Amendment (<STEP>, <YYYY-MM-DD>)

   Supersedes: <what it overrides, matching the SPEC CHANGE: note's first line>

   Source: <PR comment/thread url that authorized this>

   <the new decision, in the detail a coder or reviewer needs to build/check it>
   ```

   `Source:` must be the real, resolvable url located above - never a placeholder, never your own paraphrase of "a human asked for this" with no url behind it. Keep the blank line between `Supersedes:` and `Source:`: a formatter that unwraps prose merges consecutive non-blank lines into one paragraph, and the review stage checks for a standalone `Source:` line, so without it a genuine amendment reads as unauthorized. When the artifact already holds text, keep every existing section byte-for-byte and append the new one after a blank line: never edit or drop an earlier section, because a later section supersedes an earlier one only for the point its `Supersedes:` line names.

3. `lc attach ITEM spec-amendment "<full text>" --replace`, where the text is the whole artifact (existing sections plus the new one), not just the new section. The amendment lives on the item, not in the specs repo: do not clone it, branch it or open a PR for it.
4. Proceed to build to match the amended design, as if SPEC already read that way.
5. Name the amendment in the closing `--note` on your final `lc done`.
