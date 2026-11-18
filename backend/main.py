
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from typing import Literal
from ollama import chat
import json
import logging
import time

from database import (
    init_db,
    create_conversation,
    save_message,
    get_conversations,
    update_conversation_title,
    get_messages,
    delete_conversation
)
from tools import get_available_tools, execute_tool


# --- LLM ---

MODEL = "qwen3.5:2b"

SYSTEM_PROMPT = """
You are a helpful AI assistant.
Always respond in the same language as the user's latest message.
Be clear, friendly and honest.
Never invent information.

When a tool returns a result containing an "error" field:
- Never pretend the tool succeeded.
- Do not invent the missing information.
- Explain the problem to the user clearly.
- If possible, answer the rest of the request without that tool.

When a tool provides date or time information, use its values exactly.
Never guess or recalculate information already provided by a tool.
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

class RenameConversationRequest(BaseModel):
    title: str

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

    # If it's the first message, we will generate a title
    is_first_message = sum(1 for message in request.messages if message.role == "user") == 1


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
            max_tool_rounds = 5
            assistant_response = ""
            execution_context = {"count": 0, "seen": set()}

            for round_number in range(max_tool_rounds + 1):
                response_stream = chat(
                    model=MODEL,
                    messages=conversation,
                    tools=get_available_tools(),
                    options={"temperature": 0.2},
                    think=False,
                    stream=True
                )

                round_content = ""
                tool_calls = []

                for chunk in response_stream:
                    message = chunk.message

                    # Acumular los fragmentos de texto
                    if message.content:
                        round_content += message.content
                        yield json.dumps({"type": "chunk", "content": message.content}, ensure_ascii=False) + "\n"

                    # Acumular las solicitudes de herramientas
                    if message.tool_calls:
                        tool_calls.extend(message.tool_calls)

                assistant_response += round_content

                # Si no hay herramientas, hemos terminado
                if not tool_calls:
                    break

                if round_number == max_tool_rounds:
                    raise RuntimeError("Maximum number of tool calls exceeded.")

                # Guardar el mensaje del asistente que contiene las llamadas
                conversation.append({
                    "role": "assistant",
                    "content": round_content,
                    "tool_calls": tool_calls
                })

                # Ejecutar las herramientas solicitadas
                for tool_call in tool_calls:
                    tool_result = execute_tool(tool_call, execution_context)

                    conversation.append({
                        "role": "tool",
                        "name": tool_call.function.name,
                        "content": tool_result
                    })

            else:
                raise RuntimeError("Maximum number of tool calls exceeded.")

            # Guardar la respuesta completa en la base de datos
            if assistant_response:
                save_message(
                    request.conversation_id,
                    "assistant",
                    assistant_response
                )
            yield json.dumps({"type": "done"}) + "\n"

        except Exception:
            logger.exception("Error while generating the response")

            yield json.dumps({"type": "error", "content": "Ha ocurrido un error al generar la respuesta."}, ensure_ascii=False) + "\n"

    background_task = None

    # Generate title is its the first message
    if is_first_message:
        background_task = BackgroundTask(
            generate_and_save_title,
            request.conversation_id,
            latest_user_message.content
        )

    return StreamingResponse( generate_response(), media_type="application/x-ndjson", background=background_task)


@app.put("/conversations/{conversation_id}/title")
def rename_conversation(conversation_id: int, request: RenameConversationRequest):
    new_title = request.title.strip()

    if not new_title:
        raise HTTPException(status_code=400, detail="Conversation title cannot be empty.")

    conversations = get_conversations()

    if not any(c["id"] == conversation_id for c in conversations):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    update_conversation_title(conversation_id, new_title)

    return {
        "success": True,
        "title": new_title
    }


@app.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: int):
    conversations = get_conversations()

    if not any(c["id"] == conversation_id for c in conversations):
        raise HTTPException(status_code=404, detail="Conversation not found")

    delete_conversation(conversation_id)

    return {"success": True}

# --------- Helpers ---------
def generate_conversation_title(user_message: str) -> str:
    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate a very short title for a conversation. "
                    "Use 3 to 6 words, in the same language as the user. "
                    "Describe the main topic of the conversation. "
                    "Return only the title, without quotes or explanations."
                )
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        options={"temperature": 0.2, "num_predict": 30},
        think=False,
        stream=False
    )

    title = response.message.content.strip()

    # Remove unnecessary whitespace and line breaks
    title = " ".join(title.split())

    # Remove surrounding quotation marks, if any
    title = title.strip('"\'`')

    return title[:60] if title else "New conversation"

def generate_and_save_title(conversation_id: int, user_message: str):
    """Generates and saves a conversation title in the background."""

    try:
        title = generate_conversation_title(user_message)
        update_conversation_title(conversation_id, title)

    except Exception:
        logger.exception("Error while generating conversation title")
