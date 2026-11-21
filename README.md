# ULTRON — Local-First Desktop AI Assistant

ULTRON combines a local Ollama chat model, a localhost-only Python authority agent,
a 3D HUD, optional communication connectors, and an optional Creative Studio.

The original 3D HUD is retained. This update adds more truthful OS-action results,
a working browser-based Transcriber, Agnes AI image/video integration, and local
PowerPoint generation.

## Requirements

- Windows 10/11 recommended for laptop-authority features.
- Python 3.10+.
- Ollama installed and running for local AI chat.
- A modern Chromium browser (Chrome/Edge) for the HUD and browser speech recognition.
- Optional: an Agnes AI API key for cloud image/video generation.
- Optional: `python-pptx` for PowerPoint creation (installed by the media launcher).

## First-time setup

1. Extract the package to a normal folder, e.g. `Desktop\\ULTRON`.
2. Copy `.env.example` to `.env`.
3. Generate a unique token in PowerShell:
   ```powershell
   $bytes = New-Object byte[] 32
   $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
   $rng.GetBytes($bytes)
   [Convert]::ToBase64String($bytes)
   $rng.Dispose()
   ```
4. Paste the generated token after `ULTRON_AGENT_TOKEN=` in `.env`.
5. If using Agnes AI image/video generation, paste your own key after `AGNES_API_KEY=`. Keep `AGNES_BASE_URL=https://apihub.agnes-ai.com/v1`. The image and video models are configurable with `AGNES_IMAGE_MODEL` and `AGNES_VIDEO_MODEL`.
6. Install Ollama and pull a default core model:
   ```bat
   ollama pull gemma4:12b
   ```
   Optional lightweight coding model:
   ```bat
   ollama pull qwen2.5-coder:1.5b
   ```
7. Start the three local services in separate windows:
   ```bat
   start_ultron_agent.bat
   start_hud.bat
   start_ultron_media.bat
   ```
8. Open `http://127.0.0.1:8000/ultron.html`.
9. In HUD Settings, paste the same `ULTRON_AGENT_TOKEN` from `.env`, save, and wait for
   the agent authentication status to turn online.

## Main features

### Local assistant
- Chat, explanations, translation, coding help, and general text tasks through Ollama.
- Streaming responses.
- Gemma 4 12B is the default general-purpose core model.
- Smart coder routing is enabled by default: programming, debugging, architecture, and code-generation requests are routed to the selected coding model (Qwen Coder by default).
- You can change the coding model or explicitly disable automatic routing in HUD Settings. The coding model must be installed locally with Ollama.
- The assistant persona is configured through a system prompt. This does not
  fine-tune or train the underlying model weights.

### Laptop Authority
Examples:
- `WiFi Off` / `WiFi On`
- `Bluetooth On` / `Bluetooth Off`
- `Open VS Code`
- `Set volume to 35%`
- `Brightness 70%`
- `Lock my PC`
- `Find invoice PDF`

The agent is bound to `127.0.0.1`, checks browser origin, requires a unique token,
and reports failed/unsupported actions instead of pretending they worked.
Windows Bluetooth control may require administrator permission. Airplane-mode
switching is deliberately reported as unsupported by this safe adapter.

### Privacy and optional connectors (default OFF)
- A fresh installation starts with Gmail, WhatsApp, and external news feeds disabled.
- ULTRON has no access to a user's Gmail, contacts, messages, or other accounts unless the user explicitly enables and configures the relevant connector in Settings.
- Do not add personal credentials to a public repository. `connectors.json` is local-only and ignored by Git; never commit it.
- Enabling Gmail grants the configured IMAP/SMTP access represented by that account's App Password. Enabling WhatsApp may open/control WhatsApp Web. Enabling news feeds permits outbound requests to the configured feed hosts.
- Keep each connector disabled unless it is needed. Review its permissions and test it before use. Disabling a connector prevents its connector functions from operating; it does not revoke credentials already issued to a third-party provider.
- Email sending requires a staged draft and explicit confirmation. No connector should be considered active until the user enables it and its real connection is tested.

### Transcriber
The Transcriber uses the browser's SpeechRecognition implementation, displays
captured final speech segments, and returns the actual transcript when stopped.
Chrome/Edge support and microphone permission are required. Browser recognition
may process audio according to the browser/provider privacy policy; do not use it
for confidential recordings unless that processing is approved.

### Creative Studio
Click the dedicated **CREATIVE STUDIO** button on the HUD to open `studio.html` in a separate popup window. If the browser blocks popups, the button falls back to opening Studio in the current tab.

The HUD launcher now uses `ultron_hud_server.py`, a loopback-only allowlist server. It serves only `ultron.html`, `studio.html`, and generated media; it does not expose `.env`, Python source, or project files through the static web server. Do not open `studio.html` directly from File Explorer; use `start_hud.bat` and the HUD button so the browser has the correct `http://localhost:8000` origin.

- **Image:** Agnes Image 2.5 Flash via `POST /v1/images/generations`.
- **Video:** Agnes Video 2.5 Flash by default (720P), with Agnes Video 2.5 as an optional higher-resolution model. Generation is asynchronous; ULTRON polls Agnes using the returned `video_id` and selected model name. The response parser accepts the documented `metadata.url` as well as compatible top-level URL fields, and recognises completed/success and failed/cancelled states. A busy Flash queue may still require waiting and retrying.
- **Presentations:** local `.pptx` creation with `python-pptx`; no AI key needed
  for the structured slide builder.

The same Agnes AI API key is used for image and video calls. No developer-owned
key is supplied. Image/video generation may consume account quota or paid credits;
check current model availability, quotas, and pricing in your Agnes AI account before generating.

## Speed tuning

The defaults are intentionally conservative for laptops:
- Core model default: `gemma4:12b`.
- Default context: 4K on small profiles.
- Default generation cap: 512 tokens.
- Core model keep-alive: 15 minutes.
- Coder-model routing: off until enabled in Settings.

Smaller models generally respond faster but may be less capable. The first request
after a model is unloaded can still take longer. Actual speed depends on RAM,
CPU/GPU offload, model quantization, context size, and background load. This
package does not promise a specific response time.

## Security and GitHub publishing

- Never commit `.env`, API keys, `connectors.json`, or private generated files.
- `.gitignore` excludes these files. If `connectors.json` was already tracked,
  run `git rm --cached connectors.json`.
- The shared token value in the uploaded baseline archive has been removed from
  this update. If it was a real credential used elsewhere, rotate it.
- Keep the agent and media service on loopback. Do not expose their ports to a LAN
  or the public internet.
- Review every new connector and OS command before enabling it.

## Build and diagnostics

Run:
```bat
python install.py --out build
python selftest.py
```

The installer copies the updated HUD, agent, Creative Studio, and launchers into
the selected output directory.

## Verification status

Static Python and JavaScript syntax checks passed. The local media service health
endpoint and local PowerPoint generation endpoint were tested. Actual Windows
radio switching, VS Code launching, Gmail/WhatsApp credentials, browser
microphone capture, and Agnes AI cloud generation still require testing on the
target laptop with its own permissions and account.

This is an updated development build, not a certified release-ready product.
