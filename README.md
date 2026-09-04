# Proactive Virtual Facilitator

This repository contains an early-stage prototype of an interactive 3D AI virtual agent, developed as part of the research for the workshop paper:

> **[When and How Should the Agent Intervene? Designing an RL-Driven Multimodal Virtual Agent for Proactive Facilitation](./ASIMOV_2026%20%283%29.pdf)**

### Publication
This paper was accepted at **ASIMOV 2026** (Workshop on Adaptive Social Interaction based on user's Mental mOdels and behaVior in HRI), held in conjunction with **The 18th International Conference on Social Robotics + Art**, 1-4 July, 2026, London (UK).

---

## System Overview

![UI Screenshot](./image/Screenshot%202026-09-04%20225102.jpg)

![System Framework](./overall_pipeline.jpg)

The system is a web application split into two parts that run simultaneously:

| Part | Technology | Role |
|------|-----------|------|
| **Frontend** | React + Vite (JavaScript) | Renders the 3D avatar in the browser, captures audio/video from participants |
| **Backend** | FastAPI (Python) | Runs the AI brain — LLM facilitation logic, speech recognition, text-to-speech synthesis, and WebSocket communication |

The browser talks to the backend via HTTPS and WebSocket. Because microphone access in modern browsers **requires a secure (HTTPS) connection**, both sides must run with SSL certificates — even on localhost.

---

## Prerequisites

Install the following tools **before** starting. Each item links to its official download page.

| Tool | Purpose | How to check if installed |
|------|---------|--------------------------|
| [Node.js (LTS)](https://nodejs.org/) | Runs the frontend dev server | `node -v` |
| [Python 3.8+](https://www.python.org/downloads/) | Runs the backend | `python --version` |
| [mkcert](https://github.com/FiloSottile/mkcert/releases) | Generates trusted local SSL certificates | `mkcert --version` |
| [ngrok](https://ngrok.com/download) | Exposes your local server to the internet | `ngrok version` |
| [FFmpeg](https://ffmpeg.org/download.html) | Audio processing (already bundled in `ffmpeg-8.1/` if present) | `ffmpeg -version` |

> **OpenAI API Key** — The backend uses GPT models. You need a valid key from [platform.openai.com](https://platform.openai.com/api-keys).

---

## Installation & Setup

### Step 1 — Clone the Repository

```bash
git clone <your-repo-url>
cd Virtual-Agent-for-Proactive-Facilitation
```

---

### Step 2 — Run the Setup Script

The project includes an automated setup script that configures the Python virtual environment, installs Node modules, and generates the necessary SSL certificates.

Simply double-click the `setup.bat` file in the root directory, or run it from the terminal:
```bash
.\setup.bat
```
Follow the on-screen prompts. When asked for your local IP address, enter it if you want to access the app from other devices on your network. Otherwise, you can press Enter to skip.

> **Note:** Make sure you have installed all the prerequisites (Node.js, Python, mkcert) before running this script.

---

### Step 3 — Configure API Keys

After the setup script completes, it will create a `back\.env` file for you. Open this file in a text editor and add your OpenAI API key:
```
OPENAI_API_KEY=sk-...your-actual-key-here...
```

---

### Step 5 — Expose the App Online (for remote participants)

If you want other people to access the app from different devices or over the internet, use `ngrok` to create a public URL.

**Open Terminal Window #3** and run:

```bash
ngrok http https://localhost:5173
```

✅ ngrok will display a public URL like:
```
Forwarding   https://abc123.ngrok-free.app -> https://localhost:5173
```

Share that `https://abc123.ngrok-free.app` URL with participants — they can open it in any browser without any additional setup.

> **Note:** The ngrok URL changes every time you restart ngrok (unless you have a paid plan with a fixed domain). You need to share the new URL each session.

---

## Running the System

Instead of opening multiple terminals manually, you can simply run the startup script:

1. Double-click `start.bat` in the root directory, or run `.\start.bat` from a terminal.
2. This will automatically launch both the Backend and Frontend servers in separate windows.
3. Open your browser and visit **`https://localhost:5173`**.

*(Optional)* If you need remote access, open a separate terminal and run `ngrok http https://localhost:5173`.

---

## Two Modes: Full vs Lite

The system can operate in two distinct modes, which can be toggled directly from the UI:

- **Full Mode**: The main research mode. The agent uses complex proactive facilitation logic to decide *when* to intervene and *what* to say, analyzing transcripts continuously. It uses a fully animated 3D avatar.
- **Lite Mode**: A simplified, highly responsive conversational mode. It acts as a standard voice agent without the complex action-parsing logic, accompanied by a lightweight audio-reactive visualizer instead of the 3D avatar.

---

## User 2 Simulator

To easily test the proactive facilitation logic without needing a second person, the system includes a built-in **User 2 Simulator**.

The simulator acts as another participant in the room, allowing you to trigger pre-recorded audio responses (like greetings, agreements, or questions) to see how the virtual agent reacts to the conversation.

Simply click **Add Simulator** in the web UI to bring User 2 into the session and start testing!

---

## How the System Works (Brief Technical Overview)

1. **Participant opens the browser** → the frontend (React) renders a 3D virtual avatar using Three.js / React Three Fiber.
2. **Audio is captured** from the participant's microphone and streamed to the backend via WebSocket.
3. **Speech Recognition** (`faster-whisper`) transcribes the audio to text on the backend.
4. **Facilitation Logic** (GPT-4o via OpenAI API) analyses the conversation context and decides whether the virtual agent should intervene — and what to say.
5. **Text-to-Speech** (`edge-tts`) converts the agent's response to audio.
6. **Lip Sync** (`rhubarb.exe` in `back/bin/`) generates mouth animation data from the audio.
7. The backend sends the audio + animation data back to the frontend, where the **avatar speaks and animates** in real time.

---

## Project Structure

```
Virtual-Agent-for-Proactive-Facilitation/
├── back/                    # Python backend (FastAPI)
│   ├── app/
│   │   ├── main.py          # App entry point
│   │   ├── api/             # HTTP & WebSocket route handlers
│   │   ├── core/            # Room manager, config
│   │   ├── services/        # LLM service, audio/TTS service
│   │   ├── models/          # Pydantic data models
│   │   └── utils/           # Helper utilities
│   ├── bin/
│   │   └── rhubarb.exe      # Lip sync tool (pre-bundled)
│   ├── audios/              # Temporarily generated audio files (git-ignored)
│   ├── requirements.txt     # Python dependencies
│   └── .env                 # API keys (git-ignored, create from .env.example)
│
├── front/                   # React/Vite frontend
│   ├── src/
│   │   ├── App.jsx          # Main application component
│   │   └── components/      # 3D avatar and UI components
│   ├── certs/               # SSL certificates (git-ignored, generate locally)
│   ├── vite.config.js       # Vite dev server config (SSL, proxy, ports)
│   └── package.json         # JavaScript dependencies
│
├── setup.bat                # Automated setup script
├── start.bat                # Automated startup script
├── overall_pipeline.jpg     # System diagram
├── ASIMOV_2026 (3).pdf      # Research paper
└── README.md                # This file
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Browser says "Not Secure" or blocks microphone | SSL certificate not trusted | Run `mkcert -install` again and regenerate certs |
| `uvicorn` fails with SSL error | Wrong certificate filenames | Check filenames in `front/certs/` match lines 7–8 of `vite.config.js` |
| Backend starts but frontend can't connect | Proxy mismatch or backend not running | Make sure backend is running on port 3000 before starting frontend |
| `npm install` fails | Node.js version too old | Use Node.js LTS (v18 or v20 recommended) |
| `pip install` fails on `faster-whisper` | Missing C++ build tools on Windows | Install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |
| ngrok URL not working | Session expired | Restart ngrok and share the new URL |

---

## Version Control Notes

The following are intentionally **excluded from git** (see `.gitignore`):

- `.env` files — protect your API keys
- `front/certs/` — SSL certificates are machine-specific
- `back/audios/` — temporary generated audio files
- `node_modules/`, `venv/`, `__pycache__/` — dependency caches, re-installed locally
