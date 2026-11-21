# 🤖🌎 ULTRON — Desktop AI Assistant

**Your laptop. Your AI. Your control.**

ULTRON is a local-first desktop AI assistant designed to bring an intelligent, interactive AI experience directly to your computer. It combines a locally hosted AI model, laptop automation, a futuristic 3D HUD interface, and optional external integrations.

ULTRON is designed to operate locally, giving users control over their AI assistant, system interactions, and optional integrations.

## ✨ Key Features

- **Local AI Intelligence:** Powered by Ollama and locally hosted language models.
- **Laptop Authority:** Control laptop functions such as Wi-Fi, volume, brightness, application launching, and more.
- **3D HUD Interface:** An interactive browser-based interface with a futuristic design.
- **Smart Coding Assistant:** Automatically routes programming-related tasks to a dedicated coding model.
- **Voice Transcriber:** Converts speech into text using browser speech recognition.
- **Optional Connectors:** Gmail, WhatsApp, and external news integrations.
- **Creative Studio:** Optional AI-powered image and video generation through Agnes AI, alongside local PowerPoint generation.
- **Privacy-Focused Architecture:** Local services communicate through `127.0.0.1`.

By default, ULTRON keeps its AI processing and laptop-control services local. External services are used only when explicitly configured and enabled.

---

# 📋 System Requirements

Before installing ULTRON, ensure your computer meets the following requirements.

| Component | Requirement |
|---|---|
| Operating System | Windows 10/11 |
| Python | Python 3.10 or later |
| AI Runtime | Ollama |
| Browser | Google Chrome or Microsoft Edge |
| RAM | Depends on the AI model selected |
| Internet | Required for initial installation and model downloads |
| Agnes AI API | Optional, for cloud image/video generation |

**Note:** Windows is recommended for full Laptop Authority functionality.

---

# 🚀 Installation Guide

Follow these steps in sequence to install and launch ULTRON.

## Step 1. Extract the ULTRON Package

1. Download the ULTRON ZIP package.
2. Right-click the ZIP file.
3. Select **Extract All**.
4. Choose a suitable location on your computer.

For example:

```text
C:\Users\YourName\Desktop\ULTRON
```

After extraction, you should see files and folders similar to:

```text
ULTRON/
│
├── ultron.html
├── ultron_agent.py
├── ultron_hud_server.py
├── ultron_media_service.py
│
├── start_ultron_agent.bat
├── start_hud.bat
├── start_ultron_media.bat
│
├── selftest.py
├── install.py
│
├── requirements-agent.txt
├── requirements-media.txt
├── requirements-optional.txt
│
├── .env.example
├── .gitignore
├── README.md
│
└── src/
```

Your exact folder structure may vary depending on the release.

## Step 2. Install Python

1. Download Python from the official website.
2. Run the installer.
3. Make sure to select **Add Python to PATH**.
4. Complete the installation.

Verify the installation by opening PowerShell and running:

```powershell
python --version
```

## Step 3. Install Ollama

Ollama provides the local AI runtime used by ULTRON.

1. Visit the official Ollama website:
   https://ollama.com/download
2. Download the Windows installer.
3. Install Ollama.
4. Allow it to start automatically.
5. Make sure Ollama is running in the Windows system tray.

ULTRON uses Ollama to run language models locally without requiring an external AI API for normal chat.

## Step 4. Download the AI Models

Open Command Prompt and download the default general-purpose model:

```bash
ollama pull gemma4:12b
```

For programming, debugging, and coding assistance, download:

```bash
ollama pull qwen2.5-coder:1.5b
```

### Alternative Models for Lower-Specification Computers

For laptops with approximately 8 GB RAM, consider lighter models:

```bash
ollama pull gemma4:e2b
ollama pull qwen2.5-coder:1.5b
```

**Important:**
- Model downloads can require several gigabytes of storage.
- The required RAM depends on the model and its configuration.
- Keep Ollama running while using ULTRON.
- Model selection can be changed according to your hardware capabilities.

---

# 🔐 Security Configuration

ULTRON uses a unique security token to authenticate communication between the browser interface and the local Laptop Authority agent.

Every installation should have its own security token.

## Step 5. Generate a Unique Security Token

1. Open PowerShell.
2. Copy and execute the following commands:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[Convert]::ToBase64String($bytes)
$rng.Dispose()
```

3. A long random string will appear.
4. Copy this string and keep it private.

This token acts as the shared authentication secret between the browser and the local agent.

## Step 6. Configure the Environment File

1. Open your extracted ULTRON folder.
2. Find `.env.example`.
3. Make a copy of it.
4. Rename the copied file to `.env`.
5. Open `.env` using Notepad or VS Code.

Add or configure the following variables:

```properties
ULTRON_AGENT_TOKEN=paste_your_generated_token_here
AGNES_API_KEY=
```

Replace the placeholder with your generated security token.

Leave `AGNES_API_KEY` empty unless you have an Agnes AI API key and want to use cloud-based image and video generation.

Save the file.

**Security warning:** Never upload your `.env` file or personal credentials to GitHub.

---

# ⚙️ Starting ULTRON

Once Python, Ollama, the AI models, and the security configuration are ready, you can launch ULTRON.

## Step 7. Start the Three Local Services

ULTRON uses separate services for laptop automation, the HUD interface, and Creative Studio.

Open the following three `.bat` files in the specified order.

### 1. Start ULTRON Agent

Double-click:

```text
start_ultron_agent.bat
```

This starts the local Python agent responsible for laptop-control operations.

On the first launch:
- ULTRON may create a virtual environment.
- Required Python packages will be installed.
- Initial setup may take approximately one minute or longer.

When running successfully, you should see an address similar to:

```text
ULTRON AGENT - ws://127.0.0.1:8765
```

**Keep this terminal window open.**

### 2. Start the HUD Interface

Double-click:

```text
start_hud.bat
```

This starts the local web server and should automatically open the ULTRON interface in your browser.

### 3. Start Creative Studio Service (Optional)

Double-click:

```text
start_ultron_media.bat
```

This service is required for Creative Studio functionality, including media generation and local PowerPoint creation.

If you don't intend to use Creative Studio, this service is optional.

---

# 🖥️ Accessing the ULTRON Interface

## Step 8. Open ULTRON in Your Browser

After starting the HUD service, your browser should automatically open the interface.

If it doesn't, manually enter:

```text
http://127.0.0.1:8000/ultron.html
```

ULTRON is designed to run through its local web server rather than directly from the filesystem.

## Step 9. Authenticate Your Agent

1. Open ULTRON.
2. Locate the **Settings** (gear) icon.
3. Find the **Agent Security Token** field.
4. Paste the exact token you generated earlier.
5. Save your settings.
6. Wait for the agent connection status to show **Online**.

Make sure the token in your browser matches the token stored in `.env`.

Once the connection is established, ULTRON is ready to use.

---

# 🎨 Creative Studio

Creative Studio is ULTRON's optional media-generation environment.

It provides access to:

- AI image generation through Agnes AI.
- AI video generation through Agnes AI.
- Local PowerPoint presentation generation.

## How to Open Creative Studio

**IMPORTANT: Always open Creative Studio through the Creative Studio button inside the ULTRON GUI.**

Follow these instructions:

1. Start `start_ultron_media.bat`.
2. Open the main ULTRON interface in your browser.
3. Locate the **CREATIVE STUDIO** button in the HUD.
4. Click the button.
5. Creative Studio will open in its designated popup/window.

### ⚠️ Important: Do Not Open studio.html Directly

**Do not double-click `studio.html` or open it directly through Windows File Explorer.**

Creative Studio must be launched through the **CREATIVE STUDIO button in the main ULTRON GUI**.

This ensures it is opened through the correct local origin and can communicate with the required services.

Opening `studio.html` directly from File Explorer may cause functionality and connection issues.

### API Requirements

| Feature | API Required? |
|---|---|
| AI Image Generation | Agnes AI API key |
| AI Video Generation | Agnes AI API key |
| PowerPoint Generation | No API required |

To enable image and video generation, configure a valid `AGNES_API_KEY` inside your `.env` file.

Local PowerPoint generation works without an external API key.

---

# 🤖 Main Features Explained

## 1. Local AI Assistant

ULTRON uses Ollama to run AI models directly on your computer.

Its capabilities include:

- General conversations.
- Explanations and research assistance.
- Translation.
- Coding assistance.
- Debugging.
- Programming-related tasks.
- Text generation.
- Streaming responses.

### Smart Coding Model Routing

ULTRON supports automatic model switching for coding-related requests.

For example:

| Task | Model |
|---|---|
| General conversation | Gemma 4 12B |
| Translation | Gemma 4 12B |
| Explanations | Gemma 4 12B |
| Programming | Qwen Coder |
| Debugging | Qwen Coder |
| Code generation | Qwen Coder |

The coding model and automatic routing settings can be changed through HUD Settings.

ULTRON's assistant personality is configured through its system prompt. This does not fine-tune or train the underlying model weights.

## 2. Laptop Authority

Laptop Authority allows ULTRON to perform supported actions on your Windows computer.

### Supported Examples

| Command | Action |
|---|---|
| `WiFi Off` | Turn Wi-Fi off |
| `WiFi On` | Turn Wi-Fi on |
| `Bluetooth On` | Enable Bluetooth |
| `Bluetooth Off` | Disable Bluetooth |
| `Open VS Code` | Launch Visual Studio Code |
| `Set volume to 35%` | Adjust system volume |
| `Brightness 70%` | Adjust screen brightness |
| `Lock my PC` | Lock the computer |
| `Find invoice PDF` | Search for an invoice PDF |

### Security Architecture

The Laptop Authority agent:

- Runs exclusively on `127.0.0.1`.
- Uses token-based authentication.
- Checks browser origin.
- Reports failed or unsupported actions instead of pretending they succeeded.

Some Windows Bluetooth operations may require administrator permissions.

Airplane-mode switching is deliberately reported as unsupported by the safe adapter.

## 3. Voice Transcriber

ULTRON includes a browser-based speech transcription feature.

Capabilities include:

- Capturing spoken input.
- Displaying final speech segments.
- Returning the actual transcript when recording is stopped.

Requirements:
- Google Chrome or Microsoft Edge.
- Microphone permission enabled.
- Browser SpeechRecognition support.

**Privacy note:** Browser speech recognition may process audio according to the browser or speech-recognition provider's privacy policy. Avoid confidential recordings unless that processing is approved.

## 4. Optional Connectors

ULTRON supports optional integrations for external services.

Available integrations include:

- Gmail.
- WhatsApp.
- External news feeds.

All connectors are disabled by default.

ULTRON does not automatically have access to your Gmail, contacts, messages, or other accounts.

Users must explicitly enable and configure the relevant connectors through Settings.

### Connector Permissions

| Connector | Function |
|---|---|
| Gmail | Uses configured IMAP/SMTP access through an account App Password |
| WhatsApp | May open and control WhatsApp Web |
| News | Allows outbound requests to configured news-feed hosts |

Additional security considerations:

- Keep connectors disabled unless required.
- Review permissions before enabling them.
- Test integrations before relying on them.
- Email sending requires a staged draft and explicit confirmation.

Never upload a filled `connectors.json` file to a public repository.

---

# 🧪 Testing and Diagnostics

ULTRON includes a self-test utility to help identify missing dependencies and configuration issues.

## Run the Self-Test

Open PowerShell inside your ULTRON directory and execute:

```bash
python selftest.py
```

The diagnostic utility checks for issues involving:

- Python installation.
- Ollama availability.
- Installed AI models.
- Agent configuration.
- Required dependencies.

## Quick Test Commands

Once ULTRON is online, try the following commands in the HUD:

```text
hello
```

```text
Set volume to 30%
```

```text
Open VS Code
```

```text
Brightness 70%
```

```text
Lock my PC
```

```text
Translate this sentence into French.
```

```text
Explain how artificial intelligence works.
```

---

# 🛠️ Troubleshooting

| Problem | Possible Solution |
|---|---|
| Agent stays offline | Ensure `start_ultron_agent.bat` is running and the security tokens match. |
| Python not found | Reinstall Python and enable Add Python to PATH. |
| Ollama not responding | Check the Windows system tray and restart Ollama if necessary. |
| Models missing | Run the appropriate `ollama pull` commands again. |
| Creative Studio not opening | Start the media service and open Creative Studio using the button in the main ULTRON GUI. |
| Creative Studio connection issues | Do not open `studio.html` directly through File Explorer. |
| Image/video generation unavailable | Check your Agnes AI API key in `.env`. |
| PowerPoint generation unavailable | Check that the media service is running and the required Python packages are installed. |
| Microphone not working | Use Chrome or Edge and allow microphone permissions. |
| Laptop Authority actions failing | Check agent status, permissions, and the requested action's support. |

---

# 🔒 Privacy and Security

ULTRON follows a local-first architecture.

Its main AI processing and laptop-control services operate locally.

### Default Privacy Settings

- Gmail connector: OFF.
- WhatsApp connector: OFF.
- External news feeds: OFF.
- Local agent: Bound to `127.0.0.1`.
- Agent authentication: Unique security token required.

### Files You Should Never Upload to GitHub

Never commit:

```text
.env
connectors.json
.venv/
__pycache__/
```

Also avoid uploading:

- API keys.
- Passwords.
- Personal credentials.
- Private account information.
- Generated files containing sensitive information.

If you accidentally expose a real security token or API key, generate a replacement and update your local configuration.

**Important:** Keep the agent and media service bound to loopback. Do not expose their ports to your LAN or the public internet.

---

# 🔧 Advanced: Build and Diagnostics

For users interested in running the local development build, ULTRON provides an installation script.

Run:

```bash
python install.py --out build
```

After installation, execute:

```bash
python selftest.py
```

This provides a local development build and diagnostic workflow.

Test system actions, connectors, and cloud-dependent functionality on your own computer before relying on them.

---

# 📌 Important Notes

1. Keep Ollama running while using ULTRON.
2. Keep the agent terminal open while using Laptop Authority.
3. Start the HUD using `start_hud.bat`.
4. Start the media service if you intend to use Creative Studio.
5. Always open Creative Studio through the **CREATIVE STUDIO button in the main ULTRON GUI**.
6. Never open `studio.html` directly through File Explorer.
7. Never share your `.env` file or security token.
8. Keep optional connectors disabled unless you explicitly need them.

---

# 🔴 ULTRON

**An intelligent local-first AI assistant designed to bring AI, automation, and creativity together in one desktop experience.**

Built to give users greater control over their computers through local AI intelligence, system automation, and an interactive interface.

**Your laptop. Your AI. Your control.**

THE FUTURE IS BUILT, NOT WAITED FOR.

Inspired by the vision of Tony Stark and the technological imagination of Marvel.

ULTRON — Intelligence. Automation. Innovation.

"Every great invention begins with an idea. Every revolution begins with someone willing to build it"

Built by Namit😊.
