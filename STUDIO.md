# ComfyStudio fork

This is `nohat/ComfyUI`, a fork of [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI)
used as the bundled, app-private server of [ComfyStudio](https://github.com/nohat/ComfyStudio).
It is pinned there as a git submodule at `Server/ComfyUI`, tracking the `comfystudio` branch.

- `master` tracks upstream and carries no changes. Do not commit to it.
- `comfystudio` is an upstream commit plus a short patch series. This is the branch ComfyStudio uses.

## The rule

- Keep the series small. Every commit is prefixed `studio:` and does one thing.
- Explain why in the commit body. Each commit should apply and pass its tests on its own.
- Upstream whatever can be upstreamed, then drop the commit at the next rebase.
- Anything that does not need to touch ComfyUI's code belongs in ComfyStudio's
  `Server/custom_nodes/` instead, not here.
- Prefer new files and small hooks over edits in hot code. Every touched line is a future conflict.
- Add tests under `tests-unit/` for new behavior.

## Upgrade procedure

Replace `<old-base>` with the upstream commit the series currently sits on (the parent of the
first `studio:` commit: `git log --oneline master..comfystudio` lists the series, and
`git merge-base comfystudio upstream/master` finds the base when it is still on upstream history).
Replace `<new-upstream-commit>` with an upstream tag or commit, for example `v0.43.1`.

```sh
git fetch upstream --tags
git checkout comfystudio
git rebase --onto <new-upstream-commit> <old-base> comfystudio
# resolve conflicts commit by commit; keep each commit's single concern
python -m pytest tests-unit/server_test tests-unit/prompt_server_test   # plus any area a commit touches
git push --force-with-lease origin comfystudio
git checkout master && git merge --ff-only <new-upstream-commit> && git push origin master
```

Then bump the submodule in ComfyStudio:

```sh
cd <ComfyStudio>/Server/ComfyUI
git fetch origin && git checkout origin/comfystudio
cd ../.. && git add Server/ComfyUI
git commit -m "Update server to ComfyUI <version>" -- Server/ComfyUI
```

Finally, update the "Base" line below to name the new base (amend the `studio: document the patch
series` commit, then push again with `--force-with-lease`).

## Current series

Base: upstream `19ae172b` (ComfyUI 0.42.0, "Add a Branch node (#16383)").

1. `studio: allow --lowvram/--novram on MPS`: `comfy/model_management.py`. On Apple silicon
   upstream forces the shared VRAM state and ignores both flags. This keeps them on MPS.
   Candidate to upstream.
2. `studio: require a bearer token when COMFYSTUDIO_API_TOKEN is set`: `server.py`,
   `tests-unit/server_test/test_bearer_token.py`. When the environment variable is non-empty, a
   middleware that runs before every other middleware answers 401 (empty body) to every HTTP
   request and the `/ws` upgrade unless `Authorization: Bearer <token>` matches (constant-time
   compare, header only, no exemptions). Unset or empty: no change in behavior. Not a candidate
   for upstream as written.
3. `studio: document the patch series`: this file.
