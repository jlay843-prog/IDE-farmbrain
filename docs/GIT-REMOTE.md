# Git remote (not configured)

This tree has **no remotes**. Forge does not invent or add `origin`.

## Jeff: add origin when ready

1. Create an **empty** repository on GitHub (or your host). Do not initialize with a README if this tree already has history.
2. Copy the clone URL (HTTPS or SSH).
3. From this repo:

```powershell
cd C:\Users\jlay\Grok\forge
git remote add origin <paste-url-here>
git remote -v
```

4. First push (when you choose): `git push -u origin <branch>`.

Until step 3, `git remote -v` should stay empty. Local commits only; no push from agent runs.
