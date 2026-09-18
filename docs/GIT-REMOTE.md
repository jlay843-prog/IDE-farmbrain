# Git remote

Forge does **not** invent remotes in code or smoke tests. Jeff adds `origin` manually when ready.

## Configured on this PC

```text
origin  https://github.com/jlay843-prog/IDE-farmbrain.git (fetch)
origin  https://github.com/jlay843-prog/IDE-farmbrain.git (push)
```

Verify:

```powershell
cd C:\Users\jlay\Grok\forge
git remote -v
```

Push a branch (Jeff or agent when asked):

```powershell
git push -u origin <branch>
```

## Add origin on a fresh clone

1. Create an **empty** repository on GitHub. Do not initialize with a README if this tree already has history.
2. From the repo:

```powershell
git remote add origin https://github.com/jlay843-prog/IDE-farmbrain.git
git remote -v
```

3. First push: `git push -u origin <branch>`.
