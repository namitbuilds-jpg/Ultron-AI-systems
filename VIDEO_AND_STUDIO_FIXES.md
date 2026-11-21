# ULTRON Studio and Agnes Video Fixes

## HUD / Studio launch
- The HUD has a dedicated CREATIVE STUDIO button that opens Studio in a separate popup window.
- `start_hud.bat` now launches `ultron_hud_server.py` rather than Python's unrestricted static file server.
- The HUD server serves only `ultron.html`, `studio.html`, and safe-named files in `generated/`. It does not serve `.env`, Python source, repository docs, or other project files.
- Do not open `studio.html` with `file://`; start the HUD with `start_hud.bat` and use its button.

## Agnes Video 2.5 integration
- Creates jobs with `POST /v1/videos`, explicitly sending `mode: text`, `seconds` as a string, `size`, and `aspect_ratio`.
- Uses the returned `video_id` (with `id` / `task_id` compatibility fallback) and polls `/agnesapi?video_id=...&model_name=...`.
- Reads completed URLs from `url`, `video_url`, `metadata.url`, or `data.url`.
- Recognises `completed`, `succeeded`, `success`, and `done`; terminal failures include `failed`, `error`, and `cancelled`.
- Preserves upstream HTTP status codes such as 401, 429, and 503 so Studio can show the provider's actual error instead of flattening every provider response to HTTP 502.

## Validation performed
- Python compile check: passed for `ultron_media_service.py` and `ultron_hud_server.py`.
- Studio JavaScript syntax check: passed.
- HUD JavaScript syntax check: passed (excluding the importmap JSON block).
- Safe HUD server allowlist test: HUD and Studio returned HTTP 200; `.env`, Python source, README, and unapproved generated paths returned HTTP 404.
- Mocked Agnes video create + poll test: passed, including `mode=text`, `seconds="5"`, `size="720P"`, `video_id` polling, and `metadata.url` result extraction.

A real cloud video generation was not run as part of this package build because the user's private Agnes API key and live account quota are not available in this environment. Agnes Video 2.5 Flash can also have a congested promotional queue; retry later if Agnes returns a queue-full or rate-limit response.
