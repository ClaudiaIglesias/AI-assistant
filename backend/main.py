
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal
from ollama import chat
import json
import logging

# Import database functions
from database import (
    init_db,
    create_conversation,
    save_message,
    get_conversations,
    update_conversation_title,
    get_messages
)


# --- LLM ---

MODEL = "gemma3:1b"

SYSTEM_PROMPT = """
You are a helpful AI assistant.
Always answer in Spanish unless the user asks otherwise.
Be clear, friendly and honest.
Never invent information.
"""

logger = logging.getLogger(__name__)


# --- API ---

app = FastAPI(title="AI Assistant API")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- DATA MODELS ---

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: int
    messages: list[Message]


# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"status": "AI Assistant API is running"}


@app.post("/conversations")
def create_conversation_endpoint():
    conversation_id = create_conversation()

    return {"conversation_id": conversation_id}


@app.get("/conversations")
def get_conversations_endpoint():
    conversations = get_conversations()

    return {"conversations": conversations}


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages_endpoint(conversation_id: int):
    messages = get_messages(conversation_id)

    return {"messages": messages}


@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    # Build the conversation history for Ollama
    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    conversation.extend(
        message.model_dump()
        for message in request.messages
    )

    # Find and save only the latest user message
    latest_user_message = next((
            message
            for message in reversed(request.messages)
            if message.role == "user"
        ),
        None
    )

    # Generate a title for the first message
    is_first_message = sum(1 for message in request.messages if message.role == "user") == 1

    if is_first_message and latest_user_message is not None:
        title = generate_conversation_title(latest_user_message.content)
        update_conversation_title(request.conversation_id, title)


    # Save the message in the DB
    if latest_user_message is not None:
        save_message(
            request.conversation_id,
            latest_user_message.role,
            latest_user_message.content
        )

    # Generate and stream the response
    def generate_response():
        try:
            response = chat(
                model=MODEL,
                messages=conversation,
                options={"temperature": 0.2},
                stream=True
            )

            assistant_response = ""

            for chunk in response:
                content = chunk.message.content

                assistant_response += content

                data = {
                    "type": "chunk",
                    "content": content
                }

                yield json.dumps(data, ensure_ascii=False) + "\n"

            # Save the complete assistant response
            if assistant_response:
                save_message(
                    request.conversation_id,
                    "assistant",
                    assistant_response
                )

            # Tell the frontend that generation is complete
            yield json.dumps({"type": "done"}) + "\n"

        except Exception:
            logger.exception("Error while generating the response")

            data = {
                "type": "error",
                "content": "Ha ocurrido un error al generar la respuesta."
            }

            yield json.dumps(data, ensure_ascii=False) + "\n"


    return StreamingResponse(
        generate_response(),
        media_type="application/x-ndjson"
    )


# --------- Helpers ------

def generate_conversation_title(user_message: str) -> str:
    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate a very short title for a conversation. "
                    "Use 3 to 6 words, in Spanish. "
                    "Describe the main topic of the conversation. "
                    "Return only the title, without quotes or explanations."
                )
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        options={"temperature": 0.2},
        stream=False
    )

    title = response.message.content.strip()

    # Remove unnecessary whitespace and line breaks
    title = " ".join(title.split())

    # Remove surrounding quotation marks, if any
    title = title.strip('"\'`')

    return title[:60] if title else "New conversation"
