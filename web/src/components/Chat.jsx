import { useRef, useState } from "react";
import { chat } from "../api";
import VoiceControl from "./VoiceControl";

export default function Chat({ onState, onModToggle }) {
  const [message, setMessage] = useState("");
  const [provider, setProvider] = useState("gemini");
  const utteranceRef = useRef(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Nipo boss 😎. Sema kazi."
    }
  ]);

  function handleModCommand(text) {
    if (text.toLowerCase().includes("mod on") || text.toLowerCase().includes("washa mod")) {
      onModToggle(true);
      return true;
    }
    if (text.toLowerCase().includes("mod off") || text.toLowerCase().includes("zima mod")) {
      onModToggle(false);
      return true;
    }
    return false;
  }

  async function send() {
    if (!message.trim()) return;
    const text = message.trim();

    // Check for MOD commands first
    if (handleModCommand(text)) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "MOD status updated 🔴" }
      ]);
      setMessage("");
      return;
    }

    setMessages(prev => [
      ...prev,
      { role: "user", content: text }
    ]);
    setMessage("");
    onState("THINKING");

    try {
      const result = await chat(text, provider);
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: result.response
        }
      ]);

      const speech = window.speechSynthesis;
      if (speech && "SpeechSynthesisUtterance" in window) {
        speech.cancel();
        const utterance = new SpeechSynthesisUtterance(result.response);
        utterance.lang = "sw-TZ";
        utterance.rate = 1;
        utterance.pitch = 1;
        utterance.onstart = () => onState("SPEAKING");
        utterance.onend = () => onState("IDLE");
        utterance.onerror = () => onState("ERROR");
        utteranceRef.current = utterance;
        speech.speak(utterance);
      } else {
        onState("IDLE");
      }
    } catch (error) {
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: `Kuna tatizo boss: ${error.message}`
        }
      ]);
      onState("ERROR");
    }
  }

  return (
    <section className="chat-panel">
      <div className="chat-header">
        <div>
          <strong>MR AI CORE</strong>
          <span>SECURE COMMAND CHANNEL</span>
        </div>
        <select
          value={provider}
          onChange={e => setProvider(e.target.value)}
        >
          <option value="gemini">GEMINI</option>
          <option value="kimi">KIMI</option>
        </select>
      </div>
      <div className="messages">
        {messages.map((item, index) => (
          <div
            key={index}
            className={`message ${item.role}`}
          >
            <span>
              {item.role === "assistant" ? "MR AI" : "BOSS"}
            </span>
            <p>{item.content}</p>
          </div>
        ))}
      </div>
      <div className="chat-input">
        <input
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter") send();
          }}
          placeholder="Mwambie MR AI kazi... (au sema 'mod on')"
        />
        <VoiceControl onTranscript={(text) => setMessage(text)} />
        <button onClick={send}>
          SEND
        </button>
      </div>
    </section>
  );
}
