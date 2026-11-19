# AI-Assistant

**A locally hosted AI assistant powered by Ollama, Python and React.**

AI-Assistant is a personal project focused on building an AI assistant that runs locally on your computer and can be accessed through a web interface.

The goal is to explore local LLMs, full-stack development, and agentic AI systems.

## Features

- [x] React-based chat interface
- [x] Python backend with FastAPI
- [x] Integration with Ollama
- [x] SQLite database for persistent conversations and messages
- [x] Automatic conversation titles
- [x] Markdown rendering in assistant responses
- [x] Edit conversation titles
- [x] Delete conversations
- [ ] Tool calling
  - [x] Date and Time
  - [x] Calculator
  - [x] Get the weather
  - [ ] Search in Internet
  - [ ] Notes and Reminders
  - [ ] Control the PC
- [ ] Agent loop and autonomous tasks
- [ ] Reminders and task management

## Tech Stack

| Technology | Purpose |
|---|---|
| React | Frontend user interface |
| JavaScript | Frontend development |
| Vite | Frontend tooling and development server |
| React Markdown | Rendering Markdown responses |
| Lucide React | Interface icons |
| Python | Backend and assistant logic |
| FastAPI | Backend API |
| Uvicorn | ASGI server |
| SQLite | Persistent conversation storage |
| Ollama | Local LLM runtime |
| Gemma 3 1B | Initial language model |

## Project Structure

```text
AI-Assistant/
├── backend/
│   ├── main.py
│   ├── database.py
│   └── assistant.db
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── App.css
│   ├── package.json
│   └── ...
│
└── README.md
```

The backend handles API requests, communicates with Ollama, streams responses, and manages conversation storage.

The frontend provides the chat interface and communicates with the backend through HTTP requests.

SQLite stores conversations and their messages locally.

## Architecture

The application follows this communication flow:

```text
React Frontend
      |
      | HTTP requests
      v
FastAPI Backend
      |
      | Ollama Python library
      v
Ollama
      |
      v
Qwen 3.5 2b

FastAPI Backend
      |
      v
SQLite Database
```

Assistant responses are streamed from the backend to the frontend using newline-delimited JSON (NDJSON).

## Prerequisites

- Windows 10/11
- Python 3.10+
- Node.js 22+ and npm
- Git
- Ollama

## Installation

### 1. Clone the repository

```powershell
git clone https://github.com/YOUR-USERNAME/ai-assistant.git
cd ai-assistant
```

### 2. Install Ollama

Open PowerShell and run:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Check the installation:

```powershell
ollama --version
```

### 3. Download the language model

```powershell
ollama pull qwen3.5:4b
```

Verify that the model is available:

```powershell
ollama list
```

Make sure Ollama is running before starting the application.

### 4. Set up the Python backend

Create and activate a virtual environment from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```powershell
pip install fastapi uvicorn ollama requests
```

### 5. Set up the React frontend

From the project root:

```powershell
cd frontend
npm install
npm install react-markdown lucide-react
npm install remark-math rehype-katex katex
```

## Running the Application

The frontend and backend must run simultaneously. Ollama must also be running.

### 1. Start the backend

Open a PowerShell terminal in the project root.

Activate the virtual environment if necessary:

```powershell
.\.venv\Scripts\Activate.ps1
```

Navigate to the backend folder:

```powershell
cd backend
```

Start FastAPI:

```powershell
uvicorn main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

FastAPI interactive API documentation:

```text
http://localhost:8000/docs
```

### 2. Start the frontend

Open a second PowerShell terminal:

```powershell
cd frontend
npm run dev
```

Vite will display the local URL where the application can be accessed, usually:

```text
http://localhost:5173
```

## Database

The project uses SQLite to persist conversations and messages.

The database is automatically initialized when the backend starts.

Two main tables are used:

- `conversations`: stores conversation IDs, titles and timestamps.
- `messages`: stores conversation messages, roles and timestamps.

The database file is located at:

```text
backend/database.db
```

New conversations are created when the user sends their first message, avoiding empty conversations in the database.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Backend status |
| POST | `/conversations` | Create a new conversation |
| GET | `/conversations` | Retrieve conversation history |
| GET | `/conversations/{id}/messages` | Retrieve messages from a conversation |
| POST | `/chat` | Send messages and receive a streamed assistant response |

## Status

**Work in progress.**

This project is being developed incrementally as a learning experience.

New features, technical decisions and implementation details will be documented as the project evolves.