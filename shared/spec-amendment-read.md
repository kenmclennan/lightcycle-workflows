```
git -C "$(dirname SPEC)" fetch origin <amendment-branch>
git -C "$(dirname SPEC)" show origin/<amendment-branch>:<relative-spec-path>
```

A read against refs, not a checkout - it does not touch the shared checkout's working tree or index, so it is safe to run from the same clone SPEC was resolved from and alongside other concurrent claims. Before treating an `## Amendment (...)` section as governing, check its `Source:` line: it must name a url that resolves to a real, existing PR comment or review thread (a `gh api` call for the comment returns 200, or the linked page loads), and that comment must not carry `<!-- lc -->` - that marker means an lc agent posted it, and an agent's finding is not a human's decision. Only then does the section supersede whatever its `Supersedes:` line names, for that point only - everything else in SPEC's frozen text still governs.
