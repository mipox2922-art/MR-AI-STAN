function detectApiUrl() {
  // Use the explicitly configured backend first.
  const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();
  if (configuredApiUrl) {
    let baseUrl = configuredApiUrl;
    while (baseUrl.endsWith("/")) {
      baseUrl = baseUrl.slice(0, -1);
    }
    return baseUrl;
  }
  if (typeof window !== "undefined") {
    // Render serves the UI and API as separate services. Keep production connected
    // even if the static-site build missed its VITE_API_URL environment setting.
    if (window.location.hostname === "mr-ai-stan-web.onrender.com") {
      return "https://mr-ai-stan.onrender.com";
    }
    // Local and same-origin proxy deployments can still use /api.
    return `${window.location.origin}/api`;
  }
  return "http://localhost:8000";
}
const API_URL = detectApiUrl();

export function getToken() {
  return localStorage.getItem("mr_ai_token");
}

function syncExtensionAuthToken(token) {
  const extensionId = getBrowserExtensionId();
  if (!extensionId) return;
  sendExtensionMessage(extensionId, {
    type: "MR_AI_AUTH_TOKEN",
    token: token || "",
  }).catch(() => {
    // The dashboard remains usable when the extension is absent or reloading.
  });
}

export function setToken(token) {
  localStorage.setItem("mr_ai_token", token);
  syncExtensionAuthToken(token);
}

export function clearToken() {
  localStorage.removeItem("mr_ai_token");
  syncExtensionAuthToken("");
}

const DEFAULT_API_TIMEOUT_MS = 60000;
const CHAT_API_TIMEOUT_MS = 98000;
const TOOL_API_TIMEOUT_MS = 45000;

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}, timeoutMs = DEFAULT_API_TIMEOUT_MS) {
  const token = getToken();

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  let response;
  let rawBody;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal
    });
    // Keep the timeout active until the entire response body is available,
    // not just until the server sends its headers.
    rawBody = await response.text();
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError(`MR AI backend timed out while requesting ${path}.`, 0);
    }
    if (!response && error instanceof TypeError) {
      throw new ApiError(`Cannot reach MR AI backend at ${API_URL}. Check backend availability and CORS.`, 0);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
  let data = {};
  if (rawBody) {
    try {
      data = JSON.parse(rawBody);
    } catch {
      data = { detail: rawBody.trim() };
    }
  }

  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
    }

    let message = typeof data.detail === "string"
      ? data.detail
      : `Request failed (${response.status})`;

    if (/^<!doctype html|<html[\\s>]/i.test(message)) {
      message = `Upstream authentication gateway returned HTTP ${response.status}.`;
    }

    if (message.length > 300) {
      message = message.slice(0, 300) + "…";
    }

    throw new ApiError(message || `Request failed (${response.status})`, response.status);
  }

  return data;
}

export function getAuthStatus() {
  return request("/auth/status");
}

export async function register(username, password) {
  const data = await request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });

  setToken(data.access_token);
  return data;
}

export async function login(username, password) {
  const data = await request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });

  setToken(data.access_token);
  return data;
}

export async function chat(message, provider = "gemini", toolContext = null, sessionId = null) {
  const result = await request("/ai/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      provider,
      session_id: sessionId,
      tool_context: toolContext
    })
  }, CHAT_API_TIMEOUT_MS);
  notifyExtensionBrowserPoll();
  return result;
}


export function getGmailStatus() {
  return request("/integrations/gmail/status");
}

export function startGmailConnect() {
  return request("/integrations/gmail/connect");
}

export function searchGmail(query = "", maxResults = 20) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  params.set("max_results", String(maxResults));
  return request("/integrations/gmail/messages?" + params.toString());
}

export function getGmailMessage(messageId) {
  return request(`/integrations/gmail/messages/${encodeURIComponent(messageId)}`);
}

export function sendGmailMessage({ to, subject, body }) {
  return request("/integrations/gmail/messages/send", {
    method: "POST",
    body: JSON.stringify({ to, subject, body }),
  });
}

export function replyToGmailMessage(messageId, body) {
  return request(`/integrations/gmail/messages/${encodeURIComponent(messageId)}/reply`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function disconnectGmail() {
  return request("/integrations/gmail", { method: "DELETE" });
}

export function getStatus() {
  return request("/system/status");
}

export function getChatHistory(sessionId = null) {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  const suffix = params.toString();
  return request("/ai/history" + (suffix ? "?" + suffix : ""));
}

export function getAIState() {
  return request("/ai/state");
}

export function setAIState(state) {
  return request("/ai/state", {
    method: "POST",
    body: JSON.stringify({ state }),
  });
}

export function getAIHealth(provider = "gemini") {
  const params = new URLSearchParams({ provider });
  return request("/ai/health?" + params.toString(), {}, TOOL_API_TIMEOUT_MS);
}

export function getActivity() {
  return request("/activity");
}

export function recordActivityEvent(event) {
  return request("/activity/events", {
    method: "POST",
    body: JSON.stringify(event),
  });
}

export function getTasks() {
  return request("/tasks");
}

export function getBrokerStatus() {
  return request("/broker/status");
}

export function getBrokerOpportunities(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) params.set(key, String(value));
  });
  const suffix = params.toString();
  return request("/broker/opportunities" + (suffix ? "?" + suffix : ""));
}

export function researchBrokerOpportunities(payload) {
  return request("/broker/research", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  }, TOOL_API_TIMEOUT_MS);
}

export function prepareBrokerOutreach(opportunityId, payload = {}) {
  return request("/broker/opportunities/" + encodeURIComponent(opportunityId) + "/prepare-outreach", {
    method: "POST",
    body: JSON.stringify(payload),
  }, TOOL_API_TIMEOUT_MS);
}

export function updateBrokerOpportunity(opportunityId, payload = {}) {
  return request("/broker/opportunities/" + encodeURIComponent(opportunityId), {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function approveTask(taskId) {
  return request(`/tasks/${encodeURIComponent(taskId)}/approve`, { method: "POST" });
}

export function startApprovedMission(taskId) {
  return request(`/agents/mission/${encodeURIComponent(taskId)}/start`, { method: "POST", body: JSON.stringify({}) }, TOOL_API_TIMEOUT_MS);
}

export function createTask(title) {
  return request("/tasks", {
    method: "POST",
    body: JSON.stringify({ title })
  });
}

export function getMemories() {
  return request("/memory");
}

export function createMemory(key, value) {
  return request("/memory", {
    method: "POST",
    body: JSON.stringify({ key, value })
  });
}

export function updateMemory(memoryId, value) {
  return request(`/memory/${encodeURIComponent(memoryId)}`, {
    method: "PUT",
    body: JSON.stringify({ value })
  });
}

export function deleteMemory(memoryId) {
  return request(`/memory/${encodeURIComponent(memoryId)}`, {
    method: "DELETE"
  });
}

const DEVICE_BRIDGE_URL =
  import.meta.env.VITE_DEVICE_BRIDGE_URL || "http://127.0.0.1:8765";

function getBridgeToken() {
  return localStorage.getItem("mr_ai_bridge_token") || "";
}

export function setBridgeToken(token) {
  localStorage.setItem("mr_ai_bridge_token", token);
}

export function clearBridgeToken() {
  localStorage.removeItem("mr_ai_bridge_token");
}

async function bridgeRequest(path, options = {}) {
  const token = getBridgeToken();
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {})
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${DEVICE_BRIDGE_URL}${path}`, {
      ...options,
      headers
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        `Cannot reach the local MR AI Device Bridge at ${DEVICE_BRIDGE_URL}. Start device-bridge on this same PC and keep it running. If Chrome asks to let MR AI access your local network, allow it; if previously blocked, change Local Network Access to Allow in this site's Chrome settings. For a custom web domain, add it to MR_AI_WEB_ORIGIN and restart the bridge. Browser detail: ${error.message || "network request blocked"}`
      );
    }
    throw error;
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || "Device bridge request failed");
  }

  return data;
}

export function getDeviceBridgeHealth() {
  return bridgeRequest("/health");
}

export function getAndroidDevices() {
  return bridgeRequest("/devices/android");
}

export function getFastbootDevices() {
  return bridgeRequest("/devices/fastboot");
}

export function getAndroidDeviceInfo(serial) {
  return bridgeRequest(`/devices/${encodeURIComponent(serial)}/info`);
}

export function getAndroidDiagnostics(serial) {
  return bridgeRequest(`/devices/${encodeURIComponent(serial)}/diagnostics`);
}

export function getAndroidLogs(serial) {
  return bridgeRequest(`/devices/${encodeURIComponent(serial)}/logs`);
}

export function rebootAndroid(serial, mode = "system") {
  return bridgeRequest(`/devices/${encodeURIComponent(serial)}/reboot`, {
    method: "POST",
    body: JSON.stringify({ mode })
  });
}

export function scanBluetooth() {
  return bridgeRequest("/bluetooth/scan");
}

export function flashFirmware({ serial, partition, image_path, sha256, confirm }) {
  return bridgeRequest("/devices/flash", {
    method: "POST",
    body: JSON.stringify({
      serial,
      partition,
      image_path,
      sha256,
      confirm
    })
  });
}



function notifyExtensionBrowserPoll() {
  const extensionId = getBrowserExtensionId();
  if (!extensionId) return;
  sendExtensionMessage(extensionId, { type: "MR_AI_POLL_NOW" }, 3000).catch(() => {
    // The periodic background alarm is the recovery path if the bridge is unavailable.
  });
}

function sendExtensionMessage(extensionId, message, timeoutMs = 15000) {
  if (typeof globalThis.chrome?.runtime?.sendMessage === "function") {
    return Promise.race([
      globalThis.chrome.runtime.sendMessage(extensionId, message),
      new Promise((_, reject) => window.setTimeout(() => reject(new Error("Browser Hands message timed out.")), timeoutMs)),
    ]);
  }

  if (typeof window === "undefined" || typeof window.postMessage !== "function") {
    return Promise.reject(new Error("Browser Hands messaging is unavailable in this environment."));
  }

  const bridgeRequestId = window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : "mr-ai-bridge-" + Date.now() + "-" + Math.random().toString(36).slice(2);

  return new Promise((resolve, reject) => {
    let finished = false;
    const cleanup = () => {
      window.clearTimeout(timer);
      window.removeEventListener("message", onMessage);
    };
    const finish = (callback, value) => {
      if (finished) return;
      finished = true;
      cleanup();
      callback(value);
    };
    const onMessage = event => {
      if (event.source !== window || event.origin !== window.location.origin) return;
      const data = event.data;
      if (data?.type !== "MR_AI_EXTENSION_RESPONSE" || data.requestId !== bridgeRequestId) return;
      finish(resolve, data.response || { ok: false, error: "Browser Hands returned an empty bridge response." });
    };
    const timer = window.setTimeout(() => {
      finish(reject, new Error("Browser Hands did not answer within " + timeoutMs + "ms. Check that the extension is installed, reloaded, and allowed on this site."));
    }, timeoutMs);

    window.addEventListener("message", onMessage);
    window.postMessage({
      type: "MR_AI_EXTENSION_REQUEST",
      source: "mr-ai-web",
      extensionId,
      requestId: bridgeRequestId,
      message
    }, window.location.origin);
  });
}

function getBrowserExtensionId() {
  const configured = import.meta.env.VITE_MR_AI_EXTENSION_ID;
  if (configured) return configured;

  const discovered = document.documentElement?.dataset?.mrAiExtensionId;
  return discovered || "";
}

export async function getBrowserHandsStatus() {
  const extensionId = getBrowserExtensionId();
  const token = getToken();
  if (token) syncExtensionAuthToken(token);
  if (!extensionId) {
    return { installed: false, connected: false, extensionId: null, targetTab: "unknown" };
  }

  try {
    const response = await Promise.race([
      sendExtensionMessage(extensionId, { type: "MR_AI_PING" }, 2500),
      new Promise((_, reject) => window.setTimeout(
        () => reject(new Error("Extension ping timed out.")),
        2500
      ))
    ]);
    const installed = response?.ok === true && response?.type === "MR_AI_PONG";
    return {
      installed,
      connected: installed,
      extensionId,
      targetTab: installed ? "controlled_non_mr_ai_tab" : "unknown",
      version: response?.version || null,
      error: installed ? null : (response?.error || "Extension did not answer the connection check.")
    };
  } catch (error) {
    return {
      installed: false,
      connected: false,
      extensionId,
      targetTab: "unknown",
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

export async function browserAction(action, payload = {}) {
  const extensionId = getBrowserExtensionId();
  if (!extensionId) {
    throw new Error("MR AI Browser Hands extension not detected. Reload the MR AI page after installing/reloading the extension.");
  }
  const requestId = `mr-ai-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  async function sendBrowserRequest(extra = {}) {
    const message = await Promise.race([
      sendExtensionMessage(extensionId, {
        type: "MR_AI_BROWSER_ACTION",
        requestId,
        action,
        ...payload,
        ...extra
      }),
      new Promise((_, reject) => {
        window.setTimeout(() => reject(new Error("MR AI Browser Hands did not respond within 15 seconds.")), 15000);
      })
    ]);
    if (message?.ok === false) {
      throw new Error(message?.error || "Browser Hands ilirudisha hitilafu bila maelezo.");
    }

    // Compatibility with older locally installed Browser Hands builds, which
    // returned the successful action payload directly instead of { ok, result }.
    if (message?.ok === true && message.result && typeof message.result === "object") {
      return message.result;
    }
    if (message && typeof message === "object" &&
        (typeof message.verified === "boolean" || message.page || message.dispatched)) {
      return message;
    }

    throw new Error("Browser Hands ilirudisha majibu yasiyotambulika. Reload extension na ujaribu tena.");
  }

  async function audit(outcome, result = {}, riskOverride = null) {
    const targetHost = String(result?.targetHost || result?.host || "").toLowerCase();
    const riskValue = String(riskOverride || result?.risk || "MEDIUM").toUpperCase();
    const risk = ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(riskValue) ? riskValue : "HIGH";
    try {
      await recordActivityEvent({
        component: "browser",
        action: String(action || "UNKNOWN").slice(0, 80),
        outcome,
        risk,
        target_host: targetHost || undefined,
        request_id: requestId,
      });
    } catch (error) {
      // Fail closed for high-risk steps if the audit cannot be persisted.
      throw new Error("AUDIT_LOG_FAILED: Kitendo hakijaendelea kwa sababu audit log haikuhifadhiwa. " + error.message);
    }
  }

  let result;
  try {
    result = await sendBrowserRequest();
  } catch (error) {
    await audit("FAILED", {}, "MEDIUM").catch(() => {});
    throw error;
  }
  if (!result?.approvalRequired) {
    await audit(result?.verified === true ? "VERIFIED" : result?.dispatched ? "DISPATCHED_UNVERIFIED" : "REQUESTED", result);
    return result;
  }

  await audit("APPROVAL_REQUIRED", result, result.risk || "HIGH");
  const host = result.host || result.targetHost || "domain isiyojulikana";
  const risk = result.risk || "HIGH_RISK_ACTION";
  const reason = result.reason || "Kitendo hiki kina athari nje ya dashboard.";
  const approved = typeof window !== "undefined" && typeof window.confirm === "function"
    && window.confirm(`BOSS FERISI: Idhini inahitajika.\\n\\nKitendo: ${action}\\nHatari: ${risk}\\nDomain: ${host}\\n\\n${reason}\\n\\nKuendelea mara hii tu?`);
  if (!approved) {
    await audit("REJECTED", result, result.risk || "HIGH");
    return { ...result, deniedByBoss: true, dispatched: false, note: "Boss hakuidhinisha; hakuna kitendo kilichotekelezwa." };
  }

  await audit("APPROVED", result, result.risk || "HIGH");
  try {
    const dispatched = await sendBrowserRequest({ boss_approved: true });
    await audit(dispatched?.verified === true ? "VERIFIED" : dispatched?.dispatched ? "DISPATCHED_UNVERIFIED" : "REQUESTED", dispatched, result.risk || "HIGH");
    return dispatched;
  } catch (error) {
    await audit("FAILED", result, result.risk || "HIGH").catch(() => {});
    throw error;
  }
}

export function getCurrentPage() {
  return browserAction("GET_PAGE_DATA");
}

export function browserClick(selector) {
  return browserAction("CLICK", { selector });
}

export function browserType(selector, value) {
  return browserAction("TYPE", { selector, value });
}

export function browserScroll(amount = 600) {
  return browserAction("SCROLL", { amount });
}

export function browserNavigate(url) {
  return browserAction("NAVIGATE", { url });
}



export function getSchedules() {
  return request("/scheduler");
}

export function createSchedule({ title, command, run_at, interval_minutes = null }) {
  return request("/scheduler", {
    method: "POST",
    body: JSON.stringify({ title, command, run_at, interval_minutes }),
  });
}

export function updateSchedule(scheduleId, payload) {
  return request(`/scheduler/${scheduleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSchedule(scheduleId) {
  return request(`/scheduler/${scheduleId}`, {
    method: "DELETE",
  });
}

export function runScheduleNow(scheduleId) {
  return request(`/scheduler/${scheduleId}/run-now`, {
    method: "POST",
  });
}

export function getNotifications(unreadOnly = false, limit = 50) {
  const params = new URLSearchParams({
    unread_only: String(unreadOnly),
    limit: String(limit),
  });
  return request("/notifications?" + params.toString());
}

export function markNotificationRead(notificationId) {
  return request(`/notifications/${notificationId}/read`, {
    method: "POST",
  });
}

export function markAllNotificationsRead() {
  return request("/notifications/read-all", {
    method: "POST",
  });
}

export function getAgents() {
  return request("/agents");
}

export function planAgentWork(requestText) {
  return request("/agents/plan", {
    method: "POST",
    body: JSON.stringify({ request: requestText })
  }, TOOL_API_TIMEOUT_MS);
}


export async function executeMission(requestText) {
  const result = await request("/agents/mission", {
    method: "POST",
    body: JSON.stringify({ request: requestText }),
  }, TOOL_API_TIMEOUT_MS);
  notifyExtensionBrowserPoll();
  return result;
}

export function reportMissionHandoff(missionId, status, evidence) {
  return request(`/agents/mission/${missionId}/handoff`, {
    method: "POST",
    body: JSON.stringify({ status, evidence }),
  });
}

export function executeAgentAction(action, payload = {}) {
  return request("/agents/execute", {
    method: "POST",
    body: JSON.stringify({ action, ...payload })
  }, TOOL_API_TIMEOUT_MS);
}

export function browserDrag(selector, dx, dy) {
  return browserAction("DRAG", { selector, dx, dy });
}

export function scanWifi() {
  return bridgeRequest("/wifi/scan");
}

export function scanRadar() {
  return bridgeRequest("/radar/scan");
}

export function getRadioStatus() {
  return bridgeRequest("/radio/status");
}

export function getBootState(serial) {
  return bridgeRequest(`/devices/${encodeURIComponent(serial)}/boot-state`);
}


export function getTools() {
  return request("/tools");
}

export function searchToolWeb(query) {
  return request("/tools/search", {
    method: "POST",
    body: JSON.stringify({ query }),
  }, TOOL_API_TIMEOUT_MS);
}


export function dispatchTool(command) {
  return request("/tools/dispatch", {
    method: "POST",
    body: JSON.stringify({ command }),
  }, TOOL_API_TIMEOUT_MS);
}

export function routeTool(command) {
  return request("/tools/route", {
    method: "POST",
    body: JSON.stringify({ command }),
  }, TOOL_API_TIMEOUT_MS);
}


export function getExecutiveBriefing() {
  return request("/agents/briefing", {}, TOOL_API_TIMEOUT_MS);
}


export async function runOrchestrator(message) {
  const result = await request("/orchestrator/run", {
    method: "POST",
    body: JSON.stringify({ message }),
  }, TOOL_API_TIMEOUT_MS);
  notifyExtensionBrowserPoll();
  return result;
}

export function getOrchestratorExecutions() {
  return request("/orchestrator/executions");
}

export function getPendingApprovals() {
  return request("/orchestrator/approvals");
}

export function resolveApproval(approvalId, decision) {
  return request(`/orchestrator/approvals/${approvalId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ decision }),
  });
}


export function researchJobs(query, limit = 25) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return request("/jobs/research?" + params.toString(), {}, TOOL_API_TIMEOUT_MS);
}

export function getJobAutopilot() {
  return request("/jobs/autopilot", {}, TOOL_API_TIMEOUT_MS);
}

export function updateJobAutopilot(config) {
  return request("/jobs/autopilot", {
    method: "PUT",
    body: JSON.stringify(config),
  }, TOOL_API_TIMEOUT_MS);
}

export function saveJobApplicationProfile(profile) {
  return request("/jobs/autopilot/profile", {
    method: "PUT",
    body: JSON.stringify(profile),
  }, TOOL_API_TIMEOUT_MS);
}

export function runJobAutopilotNow() {
  return request("/jobs/autopilot/run-now", {
    method: "POST",
    body: JSON.stringify({}),
  }, TOOL_API_TIMEOUT_MS);
}

export function saveJob(job) {
  return request("/jobs/save", {
    method: "POST",
    body: JSON.stringify({
      title: job.title,
      company: job.company,
      url: job.url,
      description: job.description,
    }),
  });
}

export function updateJobTracking(taskId, tracking) {
  return request(`/jobs/${encodeURIComponent(taskId)}/tracking`, {
    method: "PATCH",
    body: JSON.stringify({
      status: tracking.status,
      evidence_url: tracking.evidence_url || "",
      owner_confirmed: tracking.owner_confirmed === true,
    }),
  });
}


export function getSystemDiagnostics() {
  return request("/system/diagnostics");
}
