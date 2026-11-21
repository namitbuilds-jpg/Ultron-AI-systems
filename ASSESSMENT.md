# ULTRON — Updated Development Build Assessment

Date: 2026-11-18

## Scope

This build was updated from the supplied `ultron-run-fixed (3).zip`. The existing
3D HUD was retained; a small Creative Studio launcher was added. The runnable
frontend, local WebSocket agent, install script, and optional media service were
inspected and modified.

## Implemented in this package

### Authority and OS actions
- Added direct command parsing for `WiFi Off`, `Bluetooth On`, and `Open VS Code`.
- Corrected Windows Wi-Fi `netsh` argument syntax.
- Added Windows Bluetooth Plug-and-Play enable/disable handling. Windows may
  require an elevated agent; failures are returned rather than reported as success.
- Removed the unsupported Windows registry-based airplane-mode toggle and return
  a clear unsupported message instead.
- VS Code launch checks PATH and common Windows install locations.
- HUD state for radio/app actions is updated only after a successful agent result.
- Added localhost-only WebSocket origin validation and removed the known default
  agent secret. The agent requires a user-generated token in `.env`.

### Email and transcription
- Email Briefing no longer displays hard-coded sample messages as if they were live.
  It requires a connected and configured Gmail connector.
- Email send no longer reports success when the agent is offline.
- Transcriber now starts browser speech recognition, displays captured final
  segments, and returns the actual transcript. A visible stop control is provided.
- Browser speech-recognition providers may process audio according to their own
  privacy policies; do not use this for confidential meetings unless approved.

### Speed and assistant personality
- Kept streaming responses.
- Reduced the default generation cap to 512 tokens.
- Reduced default context to 4K on small device profiles.
- Kept the core model warm for 15 minutes.
- Made coder-model routing opt-in by default to avoid frequent model switching.
- Automatic selection now favours smaller installed models for laptop responsiveness.
- Default model selection is `gemma4:12b`; optional lightweight coder is
  `qwen2.5-coder:1.5b`.
- Updated the system prompt to a composed, strategic, futuristic assistant persona.

These are speed-oriented defaults, not a measured performance guarantee. The
underlying model weights have not been trained or fine-tuned. The persona is
prompt-level configuration.

### Creative Studio
- Added Agnes Image 2.5 Flash text-to-image integration.
- Added Agnes Video 2.5 Flash asynchronous video generation and video_id-based status polling, with optional Agnes Video 2.5 selection.
- Added local PowerPoint creation with `python-pptx`.
- API credentials are read by the Python service from `.env`; no API key is
  included in the repository or sent to browser JavaScript.
- Added a separate `studio.html` page and a launcher link in the original HUD.

The image and video integrations use the user's own Agnes AI API key.
The package does not contain a developer-owned key. Image/video requests may
consume paid credits or account quota.

## Verification performed

- Python syntax compilation passed for `ultron_agent.py`, `ultron_media_service.py`,
  `install.py`, and `selftest.py`.
- JavaScript syntax check passed for the main module and Creative Studio script.
- Local Creative Services `/health` endpoint returned successfully without an API key.
- Local presentation endpoint created a two-slide `.pptx` file.
- `install.py --out build_test` completed and copied the new Studio/service files.
- The original 3D HUD source was preserved except for the small Creative Studio link
  and the described functional changes.

## Not verified on the target laptop

The following require a real Windows device, account, permissions, and/or API key:
- Wi-Fi adapter switching.
- Bluetooth adapter switching (may require administrator rights).
- VS Code launching on the user's installation.
- Gmail IMAP/SMTP with the user's account.
- Browser microphone permission and speech recognition behavior.
- Agnes AI image and video API calls, account entitlements, and billing.
- Actual Ollama response latency, memory use, and GPU/CPU offload.

## Release status

This is an updated development build, not a certified release-ready application.
Before public GitHub release, test the unverified items above on a clean Windows
installation, review all remaining OS commands and connector permissions, and
run a full security review. Do not commit `.env`, API keys, personal connector
configuration, or generated private content.


## Model routing defaults (updated)

- Default core model: `gemma4:12b`.
- Automatic coder routing: enabled on a fresh install unless the user explicitly sets it to `off` in local browser settings.
- Default coding model: `qwen2.5-coder:1.5b`; install it with `ollama pull qwen2.5-coder:1.5b` or select another installed coder model in Settings.
- Routing is heuristic request classification, not model training.
