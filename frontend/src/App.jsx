
import { useState } from 'react';
import './App.css';

function App() {

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

    try {

      // Send the conversation to our Python API
      const response = await fetch(
        "http://localhost:8000/chat",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            messages: updatedMessages
          })
        }
      );

      if (!response.ok) {
        throw new Error("The server returned an error.");
      }

      const data = await response.json();

      // Add the assistant's response
      setMessages([
        ...updatedMessages,
        { role: "assistant", content: data.response }
      ]);

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

        <button className="new-chat">
          + New chat
        </button>

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
              <div
                key={index}
                className={`message ${message.role}`}
              >
                {message.content}
              </div>
            ))}

            {loading && (
              <div className="message assistant">
                <strong>AI</strong>
                <p>Thinking...</p>
              </div>
            )}

            {error && (
              <p className="error">{error}</p>
            )}

          </div>
        </section>

        <footer className="input-area">

          <div className="input-container">

            <input
              type="text"
              placeholder="Message your assistant..."
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  sendMessage();
                }
              }}
              disabled={loading}
            />

            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
            >
              ↑
            </button>

          </div>

        </footer>

      </main>

    </div>
  );
}

export default App;
