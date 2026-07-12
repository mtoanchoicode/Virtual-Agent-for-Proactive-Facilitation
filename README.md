# Proactive Virtual Facilitator

This repository contains an early-stage prototype of an interactive 3D AI virtual agent, developed as part of the research for the workshop paper:

> **[When and How Should the Agent Intervene? Designing an RL-Driven Multimodal Virtual Agent for Proactive Facilitation](./ASIMOV_2026%20%283%29.pdf)**

### Publication
This paper was accepted at **ASIMOV 2026** (Workshop on Adaptive Social Interaction based on user's Mental mOdels and behaVior in HRI), held in conjunction with **The 18th International Conference on Social Robotics + Art**, 1-4 July, 2026, London (UK).

---

## System Overview

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

> **Important:** You will need **three separate terminal windows** open at the same time to run the full system. The steps below guide you through each one.

---

### Step 1 — Clone the Repository

```bash
git clone <your-repo-url>
cd Virtual-Agent-for-Proactive-Facilitation
```

---

### Step 2 — Generate SSL Certificates (Do this once)

The browser requires HTTPS to access the microphone. We use `mkcert` to create a certificate that your computer trusts.

Open a terminal and run:

```bash
# 1. Install mkcert's root CA into your system's trust store (only needed once ever)
mkcert -install

# 2. Create the certs folder inside the frontend directory
mkdir front\certs

# 3. Move into that folder
cd front\certs

# 4. Generate the certificate — replace 192.168.1.20 with YOUR computer's local IP address
#    To find your local IP on Windows: run  ipconfig  and look for "IPv4 Address"
mkcert localhost 127.0.0.1 192.168.1.20
```

This creates two files inside `front/certs/`:
- `192.168.1.20+3.pem` — the certificate
- `192.168.1.20+3-key.pem` — the private key

> **Note:** The exact filenames depend on the IP you used. The `vite.config.js` and backend `main.py` are already configured to look for `192.168.1.20+3.pem` and `192.168.1.20+3-key.pem`. If your IP is different, you will need to update those filenames in both `front/vite.config.js` (lines 7–8) and `back/app/main.py` (lines 62–63).

---

### Step 3 — Backend Setup

**Open Terminal Window #1** and run:

```bash
# Navigate to the backend folder
cd back

# Create a Python virtual environment (keeps packages isolated)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
# source venv/bin/activate

# Install all required Python packages
pip install -r requirements.txt
```

#### Configure the API Key

```bash
# Copy the example environment file
copy .env.example .env
```

Now open `.env` in a text editor and replace the placeholder with your real OpenAI key:

```
OPENAI_API_KEY=sk-...your-actual-key-here...
```

#### Start the Backend Server

Still in **Terminal Window #1** (with the virtual environment active, inside the `back` folder):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3000 --ssl-keyfile ../front/certs/192.168.1.20+3-key.pem --ssl-certfile ../front/certs/192.168.1.20+3.pem
```

✅ You should see output like:
```
INFO:     Uvicorn running on https://0.0.0.0:3000 (Press CTRL+C to quit)
```

Leave this terminal open and running.

---

### Step 4 — Frontend Setup

**Open Terminal Window #2** and run:

```bash
# Navigate to the frontend folder
cd front

# Install JavaScript dependencies (only needed once, or after package.json changes)
npm install

# Start the development server
npm run dev
```

✅ You should see output like:
```
  VITE v4.x.x  ready in ...ms

  ➜  Local:   https://localhost:5173/
  ➜  Network: https://192.168.1.20:5173/
```

Open your browser and visit **`https://localhost:5173`**. If you see a certificate warning, click "Advanced" → "Proceed to localhost" — this is expected the first time with a local certificate.

Leave this terminal open and running.

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

## Running Order Summary

Every time you want to run the system, open three terminals and run these commands in order:

| Terminal | Directory | Command |
|----------|-----------|---------|
| **#1 — Backend** | `back/` | `venv\Scripts\activate` then `uvicorn app.main:app --host 0.0.0.0 --port 3000 --ssl-keyfile ../front/certs/192.168.1.20+3-key.pem --ssl-certfile ../front/certs/192.168.1.20+3.pem` |
| **#2 — Frontend** | `front/` | `npm run dev` |
| **#3 — ngrok** (optional) | anywhere | `ngrok http https://localhost:5173` |

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
