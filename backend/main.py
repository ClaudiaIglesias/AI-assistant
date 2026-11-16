
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal
from ollama import chat

# Configuration
MODEL = "gemma3:1b"

SYSTEM_PROMPT = """
You are a helpful AI assistant.
Always answer in Spanish unless the user asks otherwise.
Be clear, friendly and honest.
Never invent information.
"""

# npm run dev 
# uvicorn main:app --reload --port 8000

# Create the API
app = FastAPI(title="AI Assistant API")

# Allow our React frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Data models
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    messages: list[Message]


# Endpoints
@app.get("/")
def home():
    return {"status": "AI Assistant API is running"}


@app.post("/chat")
def chat_endpoint(request: ChatRequest):

    # Add the system instructions
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Add conversation history
    conversation.extend(
        message.model_dump()
        for message in request.messages
    )

    try:
        # Ask Ollama for a response
        response = chat(
            model=MODEL,
            messages=conversation,
            options={"temperature": 0.2}
        )

        return {
            "response": response.message.content
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Error communicating with Ollama: {error}"
        )
