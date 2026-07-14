# lightcycle-workflows

The built-in workflow source for [lightcycle](https://github.com/kenmclennan/lightcycle) - the `lightcycle` origin. `lc init` pulls this repo on first run; `lc workflow upgrade lightcycle` pulls updates.

It is an ordinary workflow source, following the structural convention any source uses:

```
source.toml            # manifest: name, contract, description
workflows/*.md         # the flow graphs (entry, edges, hooks, requires, workspace)
steps/*.md             # the steps the workflows reference (shared within this bundle)
```

- `source.toml`'s `contract` is the engine contract version these workflows target; the engine refuses to pull a source whose contract it does not support.
- Workflows and steps are discovered from the files - there is no explicit list to keep in sync.
- A pulled version is an immutable, self-contained bundle: its workflows reference only the steps in this same bundle.

This repo is decoupled from the engine's release cadence: `lc upgrade` updates the engine code; `lc workflow upgrade` updates these workflows. They share only the `contract` version.
