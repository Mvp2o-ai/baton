# Next: GitHub OSS / CI leftovers

Package is `@batoncli/cli`. Binary stays `baton`.

## Still open

- [ ] Set `NPM_TOKEN` on `Mvp2o-ai/baton` (granular token, `@batoncli` scope, bypass 2FA) so `.github/workflows/npm-publish.yml` can publish on GitHub Release
- [ ] Protect `main`: require the CI workflow, no force-push, require a PR (forks included)
- [ ] Add `CODEOWNERS` (and optionally a `MAINTAINERS` note) so review requests go to `wiltshirek` / `kenainative`
- [ ] Issue + PR templates; turn on GitHub security advisories to match `SECURITY.md`
- [ ] Enable “delete head branch on merge”
