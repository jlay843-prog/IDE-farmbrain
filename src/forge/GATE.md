# Forge gate

This applies to every Edit, in every workspace. It is not a checklist of Lone Tree Acres apps.

## While writing the diff

Change only the behavior the prompt names. Leave every other line alone.

An auth or access check you add must do nothing when its env var is unset. The program's existing health route, and a request from 127.0.0.1, stay open.

Do not invent signature checks, cryptography, or a verifier. A function that returns true, or a comment that a header is proof, is not a control.

When the prompt contains a block marked NEW, the diff is that block and no other hunk. Copy it. Do not rename, wrap, or repeat it.

One change, one hunk. Do not paste the same hunk again.

Do not deploy, restart a service, or bind a new public address. Return only a unified diff.

## After the diff

Assure reads added lines only. It fails a stub verifier, a comment that a header is proof, the same added line repeated, a secret, dynamic eval, or a path that leaves the workspace.

After Accept, smoke the program's existing health URL and record the status code. The coder does not call the network and does not deploy.
