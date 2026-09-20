# PIN — Flock Yeah DVR HLS (fix or retire)

**Pinned:** 2026-09-20  
**Do by:** end of week (~2026-09-26)  
**Status:** deferred — product cams work via `/api/cam/*`

## Symptom (fixed for viewers)
- `/cam-dvr/{nest-a|run-b}/index.m3u8` → **200**
- `/cam-dvr/.../seg_*.ts` → **404**
- Player stuck on “starting delayed…” while retrying HLS
- Legacy `/cam-stream` + `/cam-snap` path routes also **404**

## Working path (current default)
- Snap: `https://solforge.lonetreeacres.com/api/cam/snap?src=nest-a|run-b`
- Live MP4: `.../api/cam/live?src=nest-a|run-b`
- Client: `flock-yeah` `cam-config.js` `mode: "mp4"` + cache-bust `?v=mp4api1`
- Deployed under webhost `~/solforge/public/flock/`

## Decide later this week
1. **Fix DVR** — repair `flock-dvr-nest-a` / `flock-dvr-run-b` on webhost so playlist segments exist; then optionally re-enable `mode: "hls"` behind a segment health gate.  
2. **Retire DVR** — remove `/cam-dvr` from Caddy + stop DVR containers; keep only go2rtc + `/api/cam/*`.

## Hosts / containers (webhost `192.168.68.113`)
- `go2rtc` on **:1985** (also hosts X2D)
- Docker: `go2rtc-nest`, `flock-dvr-nest-a`, `flock-dvr-run-b` (were Up ~7d when broken)
- Scripts: `~/solforge/scripts/flock-cam-dvr.sh`, `deploy/go2rtc/`

## Check
```bat
forge check cams
```
- FAIL on `snap_*` / `live_*` = real outage  
- WARN on `dvr_*` = expected until this PIN is closed  

## Close criteria
- Either DVR segs return 200 for both cams, **or** DVR routes/containers removed and docs updated.
