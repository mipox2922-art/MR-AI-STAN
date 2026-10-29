import { useEffect, useRef, useState } from "react";
import { chat, routeTool, getExecutiveBriefing, getChatHistory, setAIState } from "../api";
import VoiceControl from "./VoiceControl";
import { sanitizeAssistantMessage } from "../utils/chatSafety";
import { getTanzaniaGreeting } from "../utils/localTime";


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


function isGenericGreeting(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/[.!?]+$/g, "");
  if (normalized.length > 180) return false;
  return /^(?:habari(?: boss(?: ferisi)?)?|hello(?: boss)?|hi(?: boss)?|good morning(?: boss)?|good afternoon(?: boss)?|good evening(?: boss)?|sawa\. unahitaji nini leo)(?:[,.!?\\s]|$)/.test(normalized);
}

function getModeStatusReply(value, mode) {
  const text = String(value || "").trim();
  const asksAboutMode = /(?:\b(?:uko|upo|niko|nipo)\b.{0,40}\b(?:working mode|normal mode|mode)\b|\b(?:what|which) mode\b|\bhali ya mode\b|\bmode ya sasa\b)/i.test(text);
  const isQuestion = /\?$/.test(text) || /^(?:uko|upo|niko|nipo|what|which|hali ya mode|mode ya sasa)\b/i.test(text);
  if (!asksAboutMode || !isQuestion) return null;
  const normalized = mode === "working" ? "WORKING MODE" : mode === "sleep" ? "SLEEP MODE" : "NORMAL MODE";
  return "Mode ya sasa ni " + normalized + ".";
}

function getTaskStatusReply(value, tasks, tasksAvailable) {
  const text = String(value || "").trim().toLowerCase();
  const asksStatus =
    /\bumefanya\s+kazi\s+gani/.test(text) ||
    /\bkazi\s+ngapi\b.{0,70}(?:zime.{0,20}(?:kamil|kamli|isha|fanyika)|completed|done|zinaendelea|zinafanyika)/.test(text) ||
    /\b(?:kazi|tasks?)\b.{0,70}\b(?:zimekamilika|completed|finished|done|status|progress|zinaendelea)\b/.test(text) ||
    /\b(?:what work have you done|what have you done so far|how many tasks|completed tasks|task status|task summary)\b/.test(text) ||
    /\bmuhtasari wa kazi\b|\bhali ya kazi\b|\bkazi zilizokamilika\b/.test(text);
  if (!asksStatus) return null;
  if (tasksAvailable !== true || !Array.isArray(tasks)) {
    return "Boss Ferisi, siwezi kuthibitisha idadi ya kazi kwa sababu orodha ya Tasks haijapakiwa kutoka backend. Sitachukulia mazungumzo au idadi ya rekodi kuwa ushahidi wa kazi zilizokamilika.";
  }

  const statusOf = task => String(task?.status || "").toUpperCase();
  const completed = tasks.filter(task => ["COMPLETED", "DONE", "VERIFIED"].includes(statusOf(task)));
  const active = tasks.filter(task => ["RUNNING", "IN_PROGRESS", "WORKING"].includes(statusOf(task)));
  const waiting = tasks.filter(task => ["PENDING", "WAITING", "BLOCKED", "WAITING_APPROVAL", "WAITING_FOR_HAND", "WAITING_FOR_PROFILE", "WAITING_FOR_VERIFICATION", "READY_FOR_REVIEW"].includes(statusOf(task)));
  const failed = tasks.filter(task => ["FAILED", "ERROR", "CANCELLED"].includes(statusOf(task)));
  const asksWhatDone = /umefanya\s+kazi\s+gani|what work have you done|what have you done so far|kazi zilizokamilika|completed tasks/i.test(text);

  const lines = [
    "Boss Ferisi, huu ndio muhtasari wa orodha ya Tasks iliyopakiwa, si madai kuhusu kazi ambazo hazina rekodi.",
    `Kazi zilizoorodheshwa: ${tasks.length} · Zilizokamilika: ${completed.length} · Zinaendelea: ${active.length} · Zinasubiri: ${waiting.length} · Zilizoshindwa/kusitishwa: ${failed.length}.`
  ];
  if (asksWhatDone) {
    if (completed.length) {
      lines.push("Kazi zilizowekwa COMPLETED:");
      completed.slice(0, 5).forEach((task, index) => {
        lines.push(`${index + 1}. ${String(task.title || task.name || "Kazi bila jina")} · Agent: ${String(task.agent || "haijatajwa")} · ID: ${task.id ?? "haipo"}`);
      });
    } else {
      lines.push("Hakuna kazi iliyo na status COMPLETED kwenye orodha hii. Kazi zilizorekodiwa pekee hazimaanishi zimekamilika.");
    }
  }
  return lines.join("\n");
}

function getAmbiguousDelegationReply(value) {
  const text = String(value || "").trim().toLowerCase();
  const asksDelegate = /\bwambie\b.{0,50}\b(?:vijana|mawakala|agents|crew)\b.{0,50}\b(?:kazi|pige|fanye|work|task)\b/.test(text) ||
    /\b(?:assign|tell)\b.{0,50}\b(?:agents|team|crew)\b.{0,50}\b(?:work|tasks?)\b/.test(text);
  if (!asksDelegate) return null;
  return "Nimeelewa Boss: unataka kazi zikabidhiwe kwa vijana/mawakala. Lakini agizo halijataja kazi mahsusi, kwa hiyo sijaunda Task wala kudai mawakala wameanza. Taja kazi yenyewe au fungua Mission Control uweke lengo, kisha nitapanga hatua na kuonyesha matokeo yaliyothibitishwa.";
}

function getProactiveTaskSummary(tasks, tasksAvailable) {
  if (tasksAvailable !== true || !Array.isArray(tasks)) {
    return "Ripoti ya kazi haijathibitishwa kwa sababu orodha ya Tasks haijapakiwa kutoka backend.";
  }
  const statusOf = task => String(task?.status || "").toUpperCase();
  const completed = tasks.filter(task => ["COMPLETED", "DONE", "VERIFIED"].includes(statusOf(task)));
  const active = tasks.filter(task => ["RUNNING", "IN_PROGRESS", "WORKING", "STARTED", "EXECUTING"].includes(statusOf(task)));
  const waiting = tasks.filter(task => ["PENDING", "WAITING", "BLOCKED", "WAITING_APPROVAL", "WAITING_FOR_HAND", "WAITING_FOR_VERIFICATION", "WAITING_FOR_PROFILE", "READY_FOR_REVIEW"].includes(statusOf(task)));
  const failed = tasks.filter(task => ["FAILED", "ERROR", "CANCELLED"].includes(statusOf(task)));
  const summary = `Ripoti ya kazi: ${tasks.length} zimeorodheshwa, ${completed.length} zimethibitishwa kukamilika, ${active.length} zinaendelea, ${waiting.length} zinasubiri, na ${failed.length} zimeshindwa.`;
  const current = active[0]
    ? `Kazi hai: ${active[0].title || "Kazi bila jina"} · Wakala: ${active[0].agent || "Haijathibitishwa"}.`
    : "Hakuna kazi hai iliyothibitishwa kwa sasa.";
  const blocker = failed[0]
    ? ` Kazi inayohitaji ukaguzi: ${failed[0].title || "Kazi bila jina"} · ${failed[0].error || "Sababu haijawekwa kwenye rekodi"}.`
    : "";
  return `${summary} ${current}${blocker}`;
}

function getAcknowledgementReply(value, tasks, tasksAvailable) {
  const text = String(value || "").trim().toLowerCase().replace(/[.!?]+$/g, "").replace(/\s+/g, " ");
  const taskSummary = getProactiveTaskSummary(tasks, tasksAvailable);
  if (/^(sasa|mambo|vipi|niaje|habari|upo|uko hapo|mr ai|hello|hi|good morning|good afternoon|good evening)$/.test(text)) {
    return `${getTanzaniaGreeting()}. Nipo hapa Boss Ferisi. ${taskSummary}`;
  }
  if (/^(kazi|tuanze kazi|endelea|endelea kazi)$/.test(text)) {
    return `Nimekupata Boss. ${taskSummary} Kizuizi chochote cha provider au zana kitaonyeshwa kama hitilafu iliyorekodiwa, si kama kazi iliyokamilika.`;
  }
  if (/^(sawa|saw|sawasawa|sawa boss|upo sawa|uko sawa|poa|nimekupata|okay|ok|asante)$/.test(text)) {
    return `Nimekupata Boss. ${taskSummary}`;
  }
  return null;
}

function getUnsupportedCapabilityReply(value) {
  const text = String(value || "");
  if (/\b(logs?|log files?|rekodi za mfumo)\b|kagua\s+logs?|angalia\s+logs?/i.test(text)) {
    return "Ukaguzi wa logs haujaunganishwa kwa sasa. Naweza kukusaidia kwa kitu kingine? Kwa sasa ninaweza kutumia historia ya mazungumzo haya, orodha ya kazi na telemetry iliyopokelewa tu.";
  }
  if (/\b(?:kagua|angalia|chunguza|inspect|review)\b.{0,50}\b(?:repo(?:sitory)?|source code|msimbo wa mfumo|database|server errors?|makosa(?:\s+ya\s+mfumo)?|bugs?)\b/i.test(text)) {
    return "Ukaguzi huo haujaunganishwa kwa sasa. Ninaweza kutumia historia ya mazungumzo haya, orodha ya kazi na telemetry iliyopokelewa tu.";
  }
  return null;
}

function finalizeAssistantReply(value, priorMessages, mode) {
  let content = sanitizeAssistantMessage(value);
  if (!content) {
    content = "Jibu lilikuwa na metadata ya ndani pekee, kwa hiyo halikuonyeshwa.";
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

function explainChatFailure(rawMessage) {
  const message = String(rawMessage || "").trim();
  const lower = message.toLowerCase();

  if (/\b429\b|quota|rate.?limit|too many requests/.test(lower)) {
    return "Provider imezuia ombi kwa sababu ya quota au rate limit. Jaribu tena baadaye, au chagua provider nyingine iliyoidhinishwa kwenye Chat. TEST AI PROVIDER huthibitisha probe fupi tu, si quota ya kila chat.";
  }
  if (/\b401\b|invalid api key|unauthorized|api key.*(missing|not configured|haipo)/.test(lower)) {
    return "Provider imekataa au haijapokea API key sahihi. Hakiki jina na thamani ya key kwenye Render Environment bila kuiweka kwenye chat.";
  }
  if (/\b403\b|forbidden|model.*(access|permission)|access denied/.test(lower)) {
    return "Provider imekataa ufikiaji wa model iliyochaguliwa. Hakiki model/route inayopatikana kwa akaunti hiyo, kisha ujaribu provider nyingine.";
  }
  if (/\b404\b|model.*(not found|unavailable)|no endpoints|no eligible provider|no available provider/.test(lower)) {
    return "Model au endpoint ya provider haipatikani kwa ombi hili. Chagua model/route nyingine ya bure inayopatikana, kisha ujaribu tena.";
  }
  if (/empty content|empty or invalid response|invalid response|provider returned empty|model refused/.test(lower)) {
    return "Provider ilijibu jaribio la afya, lakini haikutoa jibu linaloweza kutumika kwa chat hii. Hali ya provider kuwa LIVE haithibitishi kuwa kila ombi la chat litafaulu. Kagua quota/model route au ujaribu provider nyingine.";
  }
  if (/timed out|timeout|request aborted|aborterror/.test(lower)) {
    return "Ombi la chat limezidi muda wa kusubiri. Jaribu tena; fallback itatumia muda wake wa pamoja, si sekunde za ziada kwa kila provider.";
  }
  if (/cannot reach mr ai backend|connection failed|failed to fetch|networkerror/.test(lower)) {
    return "Dashboard haiwezi kufikia backend ya MR AI. Angalia muunganisho wa mtandao na hali ya https://mr-ai-stan.onrender.com/health.";
  }
  if (/unknown provider/.test(lower)) {
    return "Provider iliyochaguliwa haitambuliki na backend hii. Chagua OpenRouter, Gemini, Kimi, Mistral au Grok kwenye menyu ya Chat.";
  }
  if (!message) {
    return "Ombi halijakamilika kwa sababu isiyojulikana. Angalia Hitilafu Zilizorekodiwa kwenye Executive Briefing.";
  }
  return "Ombi halijakamilika. " + sanitizeAssistantMessage(message).slice(0, 180)
    + " Kagua Hitilafu Zilizorekodiwa kwenye Executive Briefing.";
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
  provider = "openrouter",
  onProviderChange,
  tasks = [],
  tasksAvailable = false,
  telemetry = null,
}) {
  const [sessionId] = useState(() => {
    try {
      const key = "mr_ai_chat_session_id";
      const existing = window.sessionStorage.getItem(key);
      if (existing) return existing;
      const created = window.crypto?.randomUUID
        ? window.crypto.randomUUID()
        : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      window.sessionStorage.setItem(key, created);
      return created;
    } catch {
      return `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
  });
  const [message, setMessage] = useState("");
  const utteranceRef = useRef(null);
  const messageListRef = useRef(null);
  const [toolStatus, setToolStatus] = useState("AI_ONLY");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Karibu Boss Ferisi. Nitaonyesha hali iliyohifadhiwa kwenye mfumo, na nitasema wazi pale data inapokosekana au haijathibitishwa."
    }
  ]);

  useEffect(() => {
    let active = true;
    getChatHistory(sessionId)
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
  }, [sessionId]);

  function reportRuntimeState(nextState) {
    onState?.(nextState);
    if (["IDLE", "THINKING", "SPEAKING", "ERROR"].includes(nextState)) {
      setAIState(nextState).catch(() => {
        // The chat UI remains usable if the persisted-state route is unavailable.
      });
    }
  }

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

    const modeStatusReply = getModeStatusReply(text, mode);
    if (modeStatusReply) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: modeStatusReply }
      ]);
      setMessage("");
      return;
    }

    // Handle short acknowledgements locally. These do not need an AI-provider
    // round trip, which previously caused ordinary messages like "sasa" to fail.
    const taskStatusReply = getTaskStatusReply(text, tasks, tasksAvailable);
    if (taskStatusReply) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: taskStatusReply }
      ]);
      setMessage("");
      reportRuntimeState("IDLE");
      return;
    }

    const delegationReply = getAmbiguousDelegationReply(text);
    if (delegationReply) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: delegationReply }
      ]);
      setMessage("");
      reportRuntimeState("IDLE");
      return;
    }

    const acknowledgementReply = getAcknowledgementReply(text, tasks, tasksAvailable);
    if (acknowledgementReply) {
      setMessages(prev => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: acknowledgementReply }
      ]);
      setMessage("");
      reportRuntimeState("IDLE");
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
    reportRuntimeState("THINKING");

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
        read_task_list: tasksAvailable === true,
        read_telemetry: Boolean(telemetry && typeof telemetry === "object"),
      };
      const requestContext = {
        ...(toolContext || {}),
        conversation_history: conversationHistory,
        operational_mode: mode,
        allowed_capabilities: availableCapabilities,
        available_task_list: tasksAvailable
          ? tasks.map(task => ({
              id: task.id,
              title: task.title,
              status: task.status,
              agent: task.agent,
              progress: task.progress,
            }))
          : null,
        available_telemetry: telemetry || null,
      };
      const result = await chat(text, provider, requestContext, sessionId);
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
        utterance.onstart = () => reportRuntimeState("SPEAKING");
        utterance.onend = () => reportRuntimeState("IDLE");
        utterance.onerror = () => reportRuntimeState("ERROR");
        utteranceRef.current = utterance;
        speech.speak(utterance);
      } else {
        reportRuntimeState("IDLE");
      }
    } catch (error) {
      // Keep provider internals out of the conversation. If a tool/briefing
      // already returned data, tell the Boss what failed without pretending the
      // requested operation succeeded.
      const rawError = String(error?.message || "");
      const readableError = "Samahani Boss. " + explainChatFailure(rawError);
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: sanitizeAssistantMessage(readableError)
        }
      ]);
      reportRuntimeState("ERROR");
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
          onChange={e => onProviderChange?.(e.target.value)}
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
