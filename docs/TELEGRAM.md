# Telegram `/forge` (Legion only)

Forge is a Legion workspace tool on **Legion** via **@LTF47bot**. `/forge` shells `C:\Users\jlay\Grok\forge\forge.cmd`. Farm Brain keeps `/coder` — do not add `/forge` there unless Jeff asks.

**Do not add `/forge` to Farm Brain.** This alias lives in this repo only.

## One-time secrets

1. Create a **separate** Telegram bot (do not reuse the Farm Brain bot token — two pollers cannot share it).
2. Write the token to `C:\Users\jlay\secrets\forge_telegram_token.txt` or set `FORGE_TELEGRAM_TOKEN`.
3. Write your numeric user id to `C:\Users\jlay\secrets\forge_telegram_allow.txt` or set `FORGE_TELEGRAM_ALLOW`.

## Run on Legion

```bat
forge telegram --probe
forge telegram --text "/forge status"
scripts\forge-telegram.cmd
```

`forge telegram` refuses to poll unless `COMPUTERNAME` contains `Legion`.

Live polling needs `C:\Users\jlay\secrets\forge_telegram_token.txt` (or `FORGE_TELEGRAM_TOKEN`) **and** `forge_telegram_allow.txt`. Without the token file, skip polling and use the desk or CLI on Legion.

## Commands

```
/forge status  — probe EVO CUDA/AMD + tower + Farm Brain
/forge which
/forge models
/forge use code|chat
/forge ask <prompt>
/forge git     — local status only
```

Burst/5090, edit, apply, open, and launch are refused here. Never port-forward Ollama. The model still has no shell tool.
