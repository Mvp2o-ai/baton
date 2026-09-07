# Next: publish `@baton-cli/cli` to npm

Open this file first. Color chrome is already committed. GitHub is [Mvp2o-ai/baton](https://github.com/Mvp2o-ai/baton). The package is **not** on the public registry yet.

Until publish succeeds, people install with:

```sh
npm install -g github:Mvp2o-ai/baton
# or from a clone:
npm install -g .
```

The user-facing command after publish is `npm install -g @baton-cli/cli` (unscoped `baton` is taken). Binary name stays `baton`.

## Already in the repo

- `package.json` name `@baton-cli/cli`, version `0.1.0`, `publishConfig.access: public`
- `.npmignore` keeps `__pycache__`, tests, `.venv`, `.github` out of the tarball
- `.github/workflows/npm-publish.yml` publishes on GitHub Release or `workflow_dispatch`, using `secrets.NPM_TOKEN` and `--provenance`
- Local global install works (`/opt/homebrew/bin/baton` → `@baton-cli/cli`)

## Blockers from last session

1. This machine is **not logged in** to npm (`npm whoami` → `ENEEDAUTH`).
2. First publish may need to **create the `@baton-cli` org** on npmjs.com and add this npm user.
3. CI publish needs **`NPM_TOKEN`** on the `Mvp2o-ai/baton` repo (or an org-level secret). Provenance also needs the workflow’s `id-token: write` (already set).

## Do this

- [ ] `npm login` (or `npm adduser`) in a real terminal.
- [ ] Confirm `npm whoami` and that the user can publish under `@baton-cli`. Create the org if npm asks.
- [ ] Dry-run the tarball from the repo root: `npm pack --dry-run`. Confirm `baton/style.py` is included and `tests/` / `__pycache__` are not.
- [ ] Decide publish path (either is fine; CI is the repeatable one):
  - **Local:** `npm publish --access public`
  - **CI:** set `NPM_TOKEN`, then `gh release create v0.1.0` (or run the `npm publish` workflow).
- [ ] Verify: `npm view @baton-cli/cli` and a clean `npm install -g @baton-cli/cli`.
- [ ] Flip README install from “until the package is on the public registry” to the registry command as the default.
- [ ] Push this branch if the color commit is not on `origin/main` yet.

## Uncommitted leftover (not part of the color commit)

Working tree still has a Codex catalog fix: union `codex debug models --bundled` with the live catalog so entitlement-thinned live lists do not drop shipped models. Files:

- `baton/provider_models.py`
- `tests/test_baton.py` (the `merge_codex_catalogs` / hide-vs-none tests)
- `README.md` / `CHANGELOG.md` one-liners

Commit or drop that before tagging `0.1.0` if you want it in the first npm release.
