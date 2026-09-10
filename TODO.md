# Next: GitHub OSS / CI leftovers

Package is `@batoncli/cli`. Binary stays `baton`.

## Still open

- [ ] Set `NPM_TOKEN` on `Mvp2o-ai/baton` (granular token, `@batoncli` scope, bypass 2FA) so a `vMAJOR.MINOR.PATCH` GitHub Release can publish `@batoncli/cli`
- [x] Protect `main`: require a PR + the `CI` check, no force-push; zero required approvals so the solo maintainer can merge their own PRs
- [x] `CODEOWNERS` → `@wiltshirek` (requests, not blocking)
- [ ] Issue + PR templates; turn on GitHub security advisories to match `SECURITY.md`
- [ ] Enable “delete head branch on merge”
