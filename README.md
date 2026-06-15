# IAcine Virtual Avatar

This project contains an interactive 3D AI virtual avatar. It is divided into a React/Vite frontend and a FastAPI/Python backend.

## Prerequisites

- Node.js & npm (for the frontend)
- Python 3.8+ (for the backend)
- FFmpeg & Rhubarb Lip Sync (Ensure these are correctly configured or placed in the `back/bin` directory if required by your setup).

## Installation & Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd IAcine-Virtual-Avatar
```

### 2. Backend Setup

The backend handles the AI logic, text-to-speech, and audio processing using OpenAI.

```bash
# Navigate to the backend directory
cd back

# (Optional but recommended) Create and activate a virtual environment
python -m venv venv
# On Windows use: venv\Scripts\activate
# On Mac/Linux use: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Environment Variables
Create an `.env` file in the `back` directory. We have provided an example file for you:
```bash
cp .env.example .env
```
Edit the `.env` file and replace the placeholder with your actual `OPENAI_API_KEY`.

#### Run the Backend
```bash
# Ensure you are in the `back` folder
python main.py
```
The backend API and WebSockets will start (typically on port 3000).

### 3. Frontend Setup

The frontend provides the 3D environment for the Avatar using React and React Three Fiber.

Open a new terminal window:
```bash
# Navigate to the frontend directory
cd front

# Install dependencies
npm install

# Start the development server
npm run dev
```
The application will launch on your local dev server (usually `http://localhost:5173`).

## Project Structure & Git Notes
- **Environment Variables**: All `.env` files are ignored to protect your API keys.
- **Certificates**: Local SSL certificates (`front/certs/`) are ignored.
- **Generated Media**: Any temporary generated speech audio during chats (`back/audios/message_*`) is ignored.
- **Dependencies**: `node_modules`, `__pycache__`, and virtual environments (`venv`, `.venv`) are correctly excluded from version control.
