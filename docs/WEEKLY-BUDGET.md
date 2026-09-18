# Forge IDE — 30% weekly token schedule

Pro+ included usage resets on the **24th of each month** ([Spending](https://cursor.com/dashboard/spending)). Next reset: **24 Sep 2026**. Work backward from that cycle, not the calendar month.

## Stop numbers

| Knob | Value |
|---|---|
| Target | 30% of each week's fair share of the monthly pool |
| Band | 25–35% of that weekly fair share |
| Week as fraction of month | 1 / 4.345 |
| **Hard stop** | **~6.9% of the monthly included-usage bar** (band 5.8–8.1%), measured from the 24th |
| Other Models (avoid) | $70/mo → week fair share $16.11 → Forge cap **~$4.83** |

This cycle (through 24 Sep) already took W0. A small **CLI polish** (Phase I) is allowed while the bar is ~40% with 11 days left. After that polish, **stop Forge** until 24 Sep. No desk/IDE work this cycle.

Stay on **Cursor Grok / Composer**. Do not pin Claude or GPT for Forge.

Catch-up (2026-09-17, this tree): W14 terminal pane, W15 Legion `/forge` Telegram alias, W16 docs, Aether reads `forge-handoff.json`, PATH-less Python launch, leftover v1 project-row/smoke polish. Post-W16 next four (2026-09-18): Monaco vendored offline (`vendor:monaco`), health/smoke checks; Telegram live poll and code signing still blocked. Post-W16 batch two (2026-09-18): Phase I CLI polish (`forge health`, `forge log`), packaged smoke parity (`npm run smoke:packaged`); Telegram live poll and code signing still blocked. Post-W16 batch three (2026-09-18): shortcut `forge.ico`, `launch-forge.ps1` via `forge.cmd`, `npm run smoke:all`, smoke `/api/log` + `forge telegram --probe`; Telegram live poll and code signing still blocked. Token schedule below is unchanged.

## Sunday ritual (Plan, then one session)

1. Open `C:\Users\jlay\Grok\forge` in **Plan mode**.
2. Note Cursor Models % used on Spending (start of that cycle week).
3. Implement **only** this week's row.
4. Stop when the slice ships **or** the monthly bar moved ~7% since the 24th for that week.
5. Do not start a second Forge agent chat until next Sunday.

First kickoff after reset: **Sunday 27 Sep (W1)**. 24–26 Sep is a buffer — skip mid-week Forge unless the change is tiny.

## Cycle map

| Cycle (24th→24th) | Forge Sundays |
|---|---|
| Now → 24 Sep 2026 | W0 only — pause |
| 24 Sep → 24 Oct | W1–W4 |
| 24 Oct → 24 Nov | W5–W8 |
| 24 Nov → 24 Dec | W9–W12 |
| 24 Dec → 24 Jan | W13–W16 |

Four Forge Sundays per cycle ≈ 28% of that month's included bar. The other ~72% stays for farm, Lumen, Aether.

## Calendar

| Week | Dates | Phase | Ship then stop |
|---|---|---|---|
| W0 | Sep 13–24 2026 | Done | CLI + desk + mesh + Monaco/recipes — **pause until 24 Sep** |
| W1 | Sep 27–Oct 3 | Harden | Streaming ask/edit + session log |
| W2 | Oct 4–10 | Harden | Recursive file tree + path search |
| W3 | Oct 11–17 | Harden | Thin git status / diff / commit |
| W4 | Oct 18–24 | Coder | Multi-file change list from one edit |
| W5 | Oct 25–31 | Coder | Read/list/grep tools only (no shell) |
| W6 | Nov 1–7 | Coder | Per-hunk apply / reject |
| W7 | Nov 8–14 | Coder | farm-brain QC confirm in the desk UI |
| W8 | Nov 15–21 | Mesh | Live pulse + blocked-burst badge |
| W9 | Nov 22–28 | Mesh | Obsidian vault search + open note |
| W10 | Nov 29–Dec 5 | Mesh | Aether / Lumen last-URL handoff |
| W11 | Dec 6–12 | Deploy | electron-builder Windows `.exe` |
| W12 | Dec 13–19 | Deploy | Icon, uninstaller, first-run picker |
| W13 | Dec 20–26 | Deploy | Smoke + health + v1 cutover |
| W14 | Dec 27–Jan 2 | Stretch | Local terminal pane (optional) |
| W15 | Jan 3–9 | Stretch | Telegram `/forge` alias (optional) |
| W16 | Jan 10–16 | Stretch | Buffer / polish / docs |
