# Supporting skills

Not installed by `npm` / `baton init`. Symlink into each user skill home:

```sh
ln -sfn "$PWD/skills/catch-up-on-previous-thread" ~/.cursor/skills/catch-up-on-previous-thread
ln -sfn "$PWD/skills/catch-up-on-previous-thread" ~/.claude/skills/catch-up-on-previous-thread
ln -sfn "$PWD/skills/catch-up-on-previous-thread" ~/.agents/skills/catch-up-on-previous-thread
```

Then any CLI can take “catch up on previous thread.” A hop still *continues*
a session; this skill *reads* it. See the root README, **Catch up without hopping**.
