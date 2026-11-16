# AI-Assistant

**A locally hosted AI assistant powered by Ollama, Python and React.**

This AI-assistant is a personal project focused on building an AI assistant that runs locally on your computer and can be accessed through a web interface.

The goal is to explore local LLMs, full-stack development, and agentic AI systems while learning and documenting the development process.

## Planned Features

- [x] Local LLM setup with Ollama
- [x] React-based chat interface
- [x] Python backend with FastAPI
- [x] Integration with Ollama
- [ ] Streaming responses
- [ ] Mobile-friendly interface
- [ ] Conversation history
- [ ] Tool calling
- [ ] Agent loop and autonomous tasks
- [ ] Reminders and task management

## Tech Stack

| Technology | Purpose |
|---|---|
| React | Frontend user interface |
| JavaScript | Frontend development |
| Vite | Frontend tooling |
| Python | Backend and assistant logic |
| FastAPI | Backend API |
| Ollama | Local LLM runtime |
| Gemma 3 1B | Initial language model |

## Prerequisites

- Windows 10/11
- Python 3.10+
- Node.js 22+ and npm
- Git
- Ollama

## Installation

### 1. Install Ollama

Open PowerShell and run:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Check the installation:

```powershell
ollama --version
```

### 2. Download the language model

```powershell
ollama pull gemma3:1b
```

Verify that the model is available:

```powershell
ollama list
```

### 3. Install Node.js and npm

If they are not already installed:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

Restart PowerShell and verify:

```powershell
node -v
npm -v
```

npm is included with Node.js.

### 4. Set up the Python environment

Clone the repository:

```powershell
git clone https://github.com/YOUR-USERNAME/localmind.git
cd localmind
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the initial backend dependencies:

```powershell
pip install fastapi uvicorn ollama
```

### 5. Set up the React frontend

Once the frontend project has been created:

```powershell
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm run dev
```

Vite will display a local URL where the frontend can be accessed.


## Status

**Work in progress.**

New features, technical decisions and implementation details will be documented as the project evolves.