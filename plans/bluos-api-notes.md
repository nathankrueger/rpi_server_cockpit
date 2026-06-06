# BluOS Control API — Handoff Notes

Research notes for controlling a BluOS / Bluesound player (play/pause, track, volume, album art) from Python or plain REST. Move this file into the correct project workspace to continue.

## TL;DR
- BluOS devices serve a **REST API on port 11000**. HTTP GET requests, URL-encoded params, **XML responses, no auth required**.
- Bluesound publishes an official **Custom Integration API spec (v1.7)** — the sanctioned subset. The full underlying protocol is broader but undocumented.
- For Python, use **[pyblu](https://github.com/LouisChrist/pyblu)** (async, maintained, basis for the Home Assistant integration). Or hit the raw endpoints with `requests` — zero deps.

## Raw endpoints (player at `192.168.1.100`)
| Action | Request |
|---|---|
| Status (state, track, volume, art) | `GET :11000/Status` |
| Sync status (long-poll for changes) | `GET :11000/SyncStatus` |
| Set volume (0–100) | `GET :11000/Volume?level=15` |
| Relative volume | `GET :11000/Volume?db=2` |
| Play / Pause / Stop | `GET :11000/Play` · `/Pause` · `/Stop` |
| Next / previous track | `GET :11000/Skip` · `/Back` |

Long-poll `/SyncStatus` to track volume/state changes (incl. secondary players in a group).

## Album artwork
`/Status` returns an `<image>` element = URL of current artwork (album, station, input...).
- **Absolute URL** → service-hosted (TIDAL/Qobuz/etc.), fetch directly.
- **Relative path** (often starts with `/Artwork`) → prefix with player address: `http://192.168.1.100:11000<image>`.
- Relative `/Artwork` URLs may 302 redirect — add **`followRedirects=1`** to get image bytes directly.
- Separate `<icon>` field = the *service* logo, distinct from album art.

## Python libraries
- **[pyblu](https://github.com/LouisChrist/pyblu)** ([PyPI](https://pypi.org/project/pyblu/), [docs](https://louischrist.github.io/pyblu/api.html)) — async, current. Covers status, volume, play/pause, skip/back, presets, inputs, play-from-URL. Status object exposes `image: str | None` ("URL of the album art").
- **[venjum/bluesound](https://github.com/venjum/bluesound)** — older synchronous Python 3 wrapper.
- **[fontikos/bluos-scrobbler](https://github.com/fontikos/bluos-scrobbler)** — Last.fm scrobbler; good `/Status` polling reference.
- **[albertony/blushell](https://github.com/albertony/blushell)** — PowerShell wrapper; documents many raw endpoints.
- **[buzink/BluOS-from-across-the-room-display](https://github.com/buzink/BluOS-from-across-the-room-display)** — now-playing display; reference for title/artist/album-art handling.

## pyblu example
```python
from pyblu import Player

async with Player("192.168.1.100") as player:
    status = await player.status()
    print(status.state, status.volume)

    art_url = status.image                       # may be relative or absolute
    if art_url and art_url.startswith("/"):
        art_url = f"http://192.168.1.100:11000{art_url}"

    await player.volume(level=20)
    await player.skip()                          # next track
    await player.pause(toggle=True)              # play/pause toggle
```
> pyblu hands back the artwork URL as-is — it does NOT normalize relative paths or fetch bytes. Prefix + `requests.get(...)` yourself.

## Sources
- [BluOS Custom Integration API v1.7 (PDF)](https://bluos.io/wp-content/uploads/2025/06/BluOS-Custom-Integration-API_v1.7.pdf)
- [pyblu — GitHub](https://github.com/LouisChrist/pyblu) · [docs](https://louischrist.github.io/pyblu/api.html) · [PyPI](https://pypi.org/project/pyblu/)
- [venjum/bluesound](https://github.com/venjum/bluesound)
- [blushell (PowerShell wrapper)](https://github.com/albertony/blushell)
- [buzink/BluOS-from-across-the-room-display](https://github.com/buzink/BluOS-from-across-the-room-display)
