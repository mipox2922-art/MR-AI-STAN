import { useEffect, useRef, useState } from "react";
import { chat, routeTool, getExecutiveBriefing, getChatHistory } from "../api";
import VoiceControl from "./VoiceControl";


function renderInlineMessage(text) {
  return String(text || "").split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function ChatMessageContent({ content }) {
  const lines = String(content || "").split(/\r?\n/);
  return (
    <div className="chat-message-body">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return <div className="chat-message-spacer" key={index} />;
        const heading = trimmed.match(/^#{1,4}\s+(.+)$/);
        if (heading) return <strong className="chat-message-heading" key={index}>{renderInlineMessage(heading[1])}</strong>;
        const listItem = trimmed.match(/^(?:([-*•])|(\d+[.)]))\s+(.+)$/);
        if (listItem) {
          return (
            <div className="chat-message-list-item" key={index}>
              <span>{listItem[1] || listItem[2]}</span>
              <div>{renderInlineMessage(listItem[3])}</div>
            </div>
          );
        }
        return <p className="chat-message-paragraph" key={index}>{renderInlineMessage(trimmed)}</p>;
      })}
    </div>
  );
}

function readableRoutingStatus(value) {
  const raw = String(value || "").trim();
  const upper = raw.toUpperCase();
  if (!raw || upper === "AI_ONLY") return "MAZUNGUMZO YA AI";
  if (upper === "ROUTING") return "NACHAMBUA OMBI...";
  if (upper.includes("EXECUTIVE BRIEFING")) return "MUHTASARI WA MFUMO";
  if (upper.includes("TOOL ROUTER ERROR") || upper.includes("BRIEFING ERROR")) return "ZANA HAIPATIKANI · AI INAENDELEA";
  if (upper.includes("AGENT:")) {
    const agent = raw.match(/AGENT:\s*([^/]+)/i)?.[1]?.trim();
    const tool = raw.match(/TOOL:\s*([^/]+)/i)?.[1]?.trim();
    return "WAKALA: " + (agent || "MR AI") + (tool ? " · ZANA: " + tool : "");
  }
  if (upper.includes("TOOL:")) return "ZANA: " + (raw.match(/TOOL:\s*([^/]+)/i)?.[1]?.trim() || "IMECHAGULIWA");
  if (upper.includes("READY")) return "IKO TAYARI";
  return raw.replaceAll("_", " ");
}

export default function Chat({ onState, onModToggle, onPowerCommand }) {
  const [message, setMessage] = useState("");
  const [provider, setProvider] = useState("openrouter");
  const utteranceRef = useRef(null);
  const messageListRef = useRef(null);
  const [toolStatus, setToolStatus] = useState("AI_ONLY");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Habari Boss Ferisi. Niambie unachotaka nifanye. Nitakujibu kwa Kiswahili na nitaeleza wazi kazi iliyokamilika, inayosubiri muunganisho, au iliyoshindikana."
    }
  ]);

  useEffect(() => {
    let active = true;
    getChatHistory()
      .then(data => {
        if (!active || !Array.isArray(data?.messages) || data.messages.length === 0) return;
        setMessages(data.messages.map(item => ({
          role: item.role === "user" ? "user" : "assistant",
          content: item.content,
        })));
      })
      .catch(() => {
        // Keep the local welcome message when history is unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

  // Keep the embedded dashboard chat pinned to the newest exchange.
  useEffect(() => {
    const container = messageListRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages]);

  function getModeCommand(text) {
    const value = String(text || "")
      .trim()
      .toLowerCase()
      .replace(/[.!?]+$/g, "")
      .replace(/\s+/g, " ");

    if ([
      "vip", "vip mode", "vip kaka", "vip on", "washa vip",
      "mod on", "washa mod", "working mode", "washa working mode"
    ].includes(value)) return true;

    if ([
      "vip off", "mod off", "zima mod", "normal", "normal mode",
      "washa normal mode"
    ].includes(value)) return false;

    return null;
  }

  function getPowerCommand(text) {
    const value = text.trim().toLowerCase();
    if (/^(zima|lala|sleep|sleep mode)$/.test(value)) return "sleep";
    if (/^(amka|wake|wake up|amka mr ai)$/.test(value)) return "wake";
    return null;
  }

  function handlePowerCommand(text) {
    const command = getPowerCommand(text);
    if (!command) return false;
    onPowerCommand?.(command);
    return true;
  }

  function isGreeting(value) {
    return /^(mr\s*ai|mr ai[,! ]*(habari|mambo|vipi|hello|hi|niaje)?|habari( mr ai)?|mambo( mr ai)?|vipi( mr ai)?|niaje( mr ai)?|good morning( mr ai)?|good evening( mr ai)?)\W*$/i.test(value.trim());
  }

  async function send(overrideText = null) {
    const text = String(overrideText ?? message).trim();
    if (!text) return;

    // Power commands control the local MR AI mode and are not sent to the model.
    if (handlePowerCommand(text)) {
      const sleeping = /^(zima|lala|sleep|sleep mode)$/i.test(text.trim());
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: sleeping ? "Naingia SLEEP MODE. Wake path imebaki tayari." : "Sawa boss, narudi ONLINE." }
      ]);
      setMessage("");
      return;
    }

    // Operational mode aliases are handled locally so "VIP" never gets
    // misrouted as a question about paid membership.
    const modeCommand = getModeCommand(text);
    if (modeCommand !== null) {
      onModToggle?.(modeCommand);
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        {
          role: "assistant",
          content: modeCommand
            ? "VIP MODE ACTIVATED, boss. WORKING MODE iko ONLINE. Nipo tayari kwa kazi."
            : "NORMAL MODE imerejeshwa, boss."
        }
      ]);
      setMessage("");
      return;
    }

    if (sending) return;

    setMessages(prev => [
      ...prev,
      { role: "user", content: text }
    ]);
    setMessage("");
    setSending(true);
    onState("THINKING");

    try {
      setToolStatus("ROUTING");
      let dispatch = null;

      if (isGreeting(text)) {
        try {
          dispatch = await getExecutiveBriefing();
          setToolStatus(`EXECUTIVE BRIEFING / ${dispatch.status || "READY"}`);
        } catch (briefingError) {
          setToolStatus(`BRIEFING ERROR / ${briefingError.message}`);
        }
      } else {
        try {
          dispatch = await routeTool(text);
          const selected = dispatch?.route?.tool || dispatch?.tool;
          const agent = dispatch?.route?.agent;
          setToolStatus(
            selected
              ? `${agent ? "AGENT: " + agent + " / " : ""}TOOL: ${selected} / ${dispatch.status || "ROUTED"}`
              : "AI_ONLY"
          );
        } catch (toolError) {
          setToolStatus(`TOOL ROUTER ERROR / ${toolError.message}`);
        }
      }

      const greeting = isGreeting(text);
      const toolContext = dispatch
        ? {
            status: dispatch.status,
            route: dispatch.route,
            result: greeting
              ? dispatch
              : dispatch.result?.results
                ? {
                    ...dispatch.result,
                    results: dispatch.result.results.slice(0, 5),
                  }
                : dispatch.result,
            message: dispatch.message,
            briefing: greeting,
          }
        : null;

      const result = await chat(text, provider, toolContext);
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
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="chat-panel">
      <div className="chat-header">
        <div>
          <strong>MR AI CORE</strong>
          <span>MAZUNGUMZO NA MR AI</span>
        </div>
        <span className="tool-routing-status" aria-live="polite" title={toolStatus}>{sending ? "NACHAMBUA OMBI..." : readableRoutingStatus(toolStatus)}</span>
        <select
          value={provider}
          onChange={e => setProvider(e.target.value)}
        >
          <option value="openrouter">OPENROUTER (FREE ROUTER)</option>
          <option value="mistral">MISTRAL</option>
          <option value="grok">GROK / xAI</option>
          <option value="gemini">GEMINI</option>
          <option value="kimi">KIMI</option>
        </select>
      </div>
      <div className="messages" ref={messageListRef}>
        {messages.map((item, index) => (
          <div
            key={index}
            className={`message ${item.role}`}
          >
            <span>
              {item.role === "assistant" ? "MR AI" : "BOSS"}
            </span>
            <ChatMessageContent content={item.content} />
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
          placeholder="Andika hapa unachotaka MR AI ikusaidie..."
        />
        <VoiceControl
          onTranscript={(text) => {
            setMessage(text);
            if (getPowerCommand(text) || getModeCommand(text) !== null) send(text);
          }}
        />
        <button onClick={() => send()} disabled={sending}>
          {sending ? "..." : "TUMA"}
        </button>
      </div>
    </section>
  );
}
