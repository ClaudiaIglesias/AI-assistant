
import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Pencil, Trash2 } from "lucide-react";
import './App.css';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [openMenuId, setOpenMenuId] = useState(null);

  const inputRef = useRef(null); // To re-activate it after sending a mesage
  const messagesEndRef = useRef(null); // To be able to autoscroll
  const chatMenuRef = useRef(null); // The chat options menu

  // Autoscroll
  useEffect(() => { 
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth"
    });
  }, [messages]);

  // The chat history in the side panel
  useEffect(() => {
    loadConversations();
  }, []);

  // Clicking outside the options menu closes it
  useEffect(() => {
    function handleClickOutside(event) {
      if (
        chatMenuRef.current &&
        !chatMenuRef.current.contains(event.target)
      ) {
        setOpenMenuId(null);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Loads the list of recent chats
  async function loadConversations() {
    try {
      const response = await fetch(
        "http://localhost:8000/conversations"
      );

      if (!response.ok) {
        throw new Error("Could not load conversations.");
      }

      const data = await response.json();

      setConversations(data.conversations);

    } catch (err) {
      console.error("Error loading conversations:", err);
    }
  }

  // Loads the messages of a specific chat
  async function loadConversation(conversation) {
    try {
      const response = await fetch(
        `http://localhost:8000/conversations/${conversation.id}/messages`
      );

      if (!response.ok) {
        throw new Error("Could not load conversation.");
      }

      const data = await response.json();

      // Load the messages into React
      setMessages(
        data.messages.map(message => ({
          role: message.role,
          content: message.content
        }))
      );

      // Set this as the active conversation
      setConversationId(conversation.id);

      // Clear any previous errors
      setError("");

    } catch (err) {
      console.error("Error loading conversation:", err);
      setError("Could not load this conversation.");
    }
  }

  // Create a new chat
  function newChat() {
    // No conversation exists in the database yet
    setConversationId(null);

    // Clear the chat window
    setMessages([]);

    // Clear previous errors
    setError("");

    // Return focus to the input
    inputRef.current?.focus();
  }


  // Sends a new message to the current conversation
  async function sendMessage() {
    const text = input.trim();

    if (!text || loading) return;

    // Add the user's message
    const updatedMessages = [
      ...messages,
      { role: "user", content: text }
    ];

    setMessages(updatedMessages);
    setInput("");
    setLoading(true);
    setError("");

    // Return focus to the input
    inputRef.current?.focus();

    try {
      // Create a conversation if one doesn't exist yet
      let activeConversationId = conversationId;

      if (activeConversationId === null) {
        const conversationResponse = await fetch(
          "http://localhost:8000/conversations",
          {
            method: "POST"
          }
        );

        if (!conversationResponse.ok) {
          throw new Error("Could not create conversation.");
        }

        const data = await conversationResponse.json();

        activeConversationId = data.conversation_id;
        setConversationId(activeConversationId);
      }

      // Send the conversation to our Python API
      const response = await fetch(
        "http://localhost:8000/chat",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            conversation_id: activeConversationId,
            messages: updatedMessages
          })
        }
      );

      if (!response.ok) {
        throw new Error("The server returned an error.");
      }


      // Create an empty assistant message (to fill it later with the response as it generates)
      setMessages([
        ...updatedMessages,
        { role: "assistant", content: "" }
      ]);

      // Response reader
      const reader = response.body.getReader();
      const decoder = new TextDecoder(); // Convert incoming bytes into text

      let buffer = "";

      function processLine(line) {
        // Ignore empty lines
        if (!line.trim()) return;

        // Convert the JSON string into a JavaScript object
        const data = JSON.parse(line);

        if (data.type === "chunk") {
          // Add the text to the assistant message
          setMessages(currentMessages => {
            const lastIndex = currentMessages.length - 1;

            return currentMessages.map((message, index) =>
              index === lastIndex
                ? { ...message, content: message.content + data.content }
                : message
            );
          });

        } else if (data.type === "error") {
          setError(data.content);

        } else if (data.type === "done") {
          // The response has finished
          console.log("Generation completed");
        }
      }

      // Read the stream until it finishes
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        // Convert incoming bytes into text and add them to the buffer
        buffer += decoder.decode(value, { stream: true });
        console.log("BUFFER:", JSON.stringify(buffer));

        // Split the buffer into lines
        const lines = buffer.split("\n");

        // Keep the last part because it may be incomplete
        buffer = lines.pop();

        // Process all complete lines
        for (const line of lines) {
          processLine(line);
        }
      }

      // Flush any remaining decoded bytes
      buffer += decoder.decode();

      // Process the last line if there is anything left
      if (buffer.trim()) {
        processLine(buffer);
      }

      // Reload chat history to add this new one
      await loadConversations();

    } catch (err) {
      console.error(err);
      setError("Could not connect to the AI assistant.");

    } finally {
      setLoading(false);

    }
  }

  return (
    <div className="app">

      <aside className="sidebar">
        <h2>AI Assistant</h2>

        <button className="new-chat" onClick={newChat} disabled={loading} >
          + New chat
        </button>

        <div className="chat-list">
          <h3>Chats</h3>

          {conversations.map((conversation) => (
            <div key={conversation.id} className={`chat-item-row ${
                conversationId === conversation.id ? "selected" : ""
              }`}>
              <button className="chat-item" type="button"
                onClick={() => {
                  setOpenMenuId(null);
                  loadConversation(conversation);
                }}
                disabled={loading}
              >
                {conversation.title}
              </button>

              <div className="chat-menu-container" ref={chatMenuRef}>
                <button
                  className="chat-menu-button"
                  type="button"
                  onClick={() =>
                    setOpenMenuId(
                      openMenuId === conversation.id ? null : conversation.id
                    )
                  }
                  aria-label="Open chat menu"
                >
                  ⋯
                </button>

                {openMenuId === conversation.id && (
                  <div className="chat-menu">
                    <button className="chat-menu-option" type="button"
                      onClick={() => {
                        setOpenMenuId(null);
                        console.log("Editar chat:", conversation.id);
                      }} >
                      <Pencil size={12} /> Rename
                    </button>

                    <button className="chat-menu-option delete-option" type="button"
                      onClick={() => {
                        setOpenMenuId(null);
                        console.log("Eliminar chat:", conversation.id);
                      }} >
                      <Trash2 size={12} /> Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          Local AI Assistant
        </div>
      </aside>

      <main className="chat">

        <section className="messages">
          <div className="messages-content">
            {messages.length === 0 && (
              <div className="welcome">
                <h1>How can I help you?</h1>
                <p>
                  Your personal AI assistant, running locally.
                </p>
              </div>
            )}

            {messages.map((message, index) => (
              <div key={index} className={`message ${message.role}`} >
                <ReactMarkdown>
                  {message.content}
                </ReactMarkdown>
              </div>
            ))}

            {loading && (
              <div className="message assistant">
                ...
              </div>
            )}

            {error && (
              <p className="error">{error}</p>
            )}

            <div ref={messagesEndRef} />
          </div>
        </section>

        <footer className="input-area">

          <div className="input-container">

            <input
              ref={inputRef}
              type="text"
              placeholder="Message your assistant..."
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  sendMessage();
                }
              }}
            />

            <button onClick={sendMessage} disabled={loading || !input.trim()} >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="4"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 21V7" />
                <path d="M5 12l7-7 7 7" />
              </svg>
            </button>
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;
