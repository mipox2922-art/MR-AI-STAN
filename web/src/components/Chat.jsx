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


function sanitizeAssistantMessage(value) {
  const lines = String(value || "").replace(/\r\n/g, "\n").split("\n");
  const safeLines = lines.filter(line => {
    const trimmed = line.trim();
    if (!trimmed) return true;
    if (/user\s*safety\s*:|\bNO_TOOL_MATCH\b|\btool_call\b|\bsystem_telemetry\b/i.test(trimmed)) {
      return false;
    }
    // Hide standalone uppercase debug labels, not ordinary explanatory sentences.
    if (/^[A-Z][A-Z0-9_]*(?:\s+[A-Z][A-Z0-9_]*)?:\s*(?:[A-Z0-9_ -]+)?$/.test(trimmed)) {
      return false;
    }
    return true;
  });
  return safeLines.join("\n").trim();
}

function isGenericGreeting(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/[.!?]+$/g, "");
  return /^(?:habari(?: boss ferisi)?|habari boss|hello(?: boss)?|hi(?: boss)?|good morning(?: boss)?|good afternoon(?: boss)?|good evening(?: boss)?|sawa\. unahitaji nini leo)$/.test(normalized);
}

function getAcknowledgementReply(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/[.!?]+$/g, "").replace(/\s+/g, " ");
  if (!/^(?:sawa|sasa|upo sawa|uko sawa|poa|nimekupata|okay|ok|asante)$/.test(normalized)) return null;
  if (normalized === "sawa" || normalized === "okay" || normalized === "ok") {
    return "Nimekupata. Tuendelee na mada ya awali.";
  }
  if (normalized === "sasa") return "Nipo hapa. Tuendelee na mada ya awali, au una jambo jipya?";
  return "Nimekupata. Tuendelee na tulichokuwa tunazungumzia.";
}

function getUnsupportedCapabilityReply(value) {
  const text = String(value || "");
  if (/\b(logs?|log files?|rekodi za mfumo)\b|kagua\s+logs?|angalia\s+logs?/i.test(text)) {
    return "Ukaguzi wa logs haujaunganishwa kwa sasa. Naweza kukusaidia kwa kitu kingine? Kwa sasa ninaweza kutumia historia ya mazungumzo haya, orodha ya kazi na telemetry iliyopokelewa tu.";
  }
  if (/\b(?:kagua|angalia|chunguza|inspect|review)\b.{0,50}\b(?:repo(?:sitory)?|source code|msimbo wa mfumo|database|server errors?|makosa ya mfumo|bugs?)\b/i.test(text)) {
    return "Ukaguzi huo haujaunganishwa kwa sasa. Ninaweza kutumia historia ya mazungumzo haya, orodha ya kazi na telemetry iliyopokelewa tu.";
  }
  return null;
}

function finalizeAssistantReply(value, priorMessages, mode) {
  let content = sanitizeAssistantMessage(value);
  if (!content) {
    content = "Jibu lilikuwa na metadata ya ndani pekee, kwa hiyo halikuonyeshwa.";
  }

  const unsupportedClaim = /(?:nime(?:kagua|angalia|chunguza|pima)|i have (?:checked|reviewed|inspected)|i(?:'ve| have) (?:checked|reviewed|inspected)).{0,70}\b(?:logs?|log files?|makosa ya mfumo|system errors?|source code|repository|database|bugs?)\b/i;
  if (unsupportedClaim.test(content)) {
    return "Ukaguzi huo haujaunganishwa kwa sasa. Ninaweza kutumia historia ya mazungumzo haya, orodha ya kazi na telemetry iliyopokelewa tu.";
  }

  const previousAssistant = [...priorMessages].reverse().find(item => item.role === "assistant");
  if (previousAssistant && isGenericGreeting(content) && isGenericGreeting(previousAssistant.content)) {
    return "Nimekupata. Tuendelee na mada ya awali.";
  }

  const modeClaim = /(?:nina|nipo|niko|iko)\s+(?:katika|kwenye)\s+working mode|working mode\s+(?:iko online|is online)/i;
  if (mode !== "working" && modeClaim.test(content)) {
    return "Hali ya sasa ni " + (mode === "sleep" ? "SLEEP MODE" : "NORMAL MODE") + ".";
  }

  return content;
}

function readableRoutingStatus(value) {
  const raw = String(value || "").trim();
  const upper = raw.toUpperCase();
  if (!raw || upper === "AI_ONLY" || upper === "NO_TOOL_MATCH") return "MAZUNGUMZO YA AI";
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

export default function Chat({
  onState,
  onModToggle,
  onPowerCommand,
  mode = "normal",
  coreStatus = "IDLE",
  tasks = [],
  telemetry = null,
}) {
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
          content: item.role === "user" ? item.content : sanitizeAssistantMessage(item.content),
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

    const localCapabilityReply = getUnsupportedCapabilityReply(text);
    const acknowledgementReply = getAcknowledgementReply(text);
    if (localCapabilityReply || acknowledgementReply) {
      const content = localCapabilityReply || acknowledgementReply;
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: sanitizeAssistantMessage(content) }
      ]);
      setMessage("");
      return;
    }

    const conversationHistory = messages.slice(-10).map(item => ({
      role: item.role === "user" ? "user" : "assistant",
      content: item.role === "assistant" ? sanitizeAssistantMessage(item.content) : String(item.content || ""),
    }));

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

      const availableCapabilities = {
        read_conversation: true,
        read_task_list: Array.isArray(tasks),
        read_telemetry: Boolean(telemetry && typeof telemetry === "object"),
      };
      const requestContext = {
        ...(toolContext || {}),
        conversation_history: conversationHistory,
        operational_mode: mode,
        allowed_capabilities: availableCapabilities,
        available_task_list: tasks.map(task => ({
          id: task.id,
          title: task.title,
          status: task.status,
          agent: task.agent,
          progress: task.progress,
        })),
        available_telemetry: telemetry || null,
      };
      const result = await chat(text, provider, requestContext);
      const safeResponse = finalizeAssistantReply(result?.response, messages, mode);
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: safeResponse
        }
      ]);

      const speech = window.speechSynthesis;
      if (speech && "SpeechSynthesisUtterance" in window) {
        speech.cancel();
        const utterance = new SpeechSynthesisUtterance(safeResponse);
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
          content: sanitizeAssistantMessage("Kuna tatizo boss: " + (error.message || "Hitilafu haijafafanuliwa."))
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
        <span className="tool-routing-status" aria-live="polite" title={toolStatus}>{sending ? "NACHAMBUA OMBI..." : coreStatus}</span>
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
