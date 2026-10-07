function detectApiUrl() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  const { hostname, protocol } = window.location;
  if (hostname.endsWith(".app.github.dev")) {
    return `${protocol}//${hostname.replace(/-\d+\.app\.github\.dev$/, "-8000.app.github.dev")}`;
  }
  return "http://localhost:8000";
}
const API_URL = detectApiUrl();

export function getToken() {
  return localStorage.getItem("mr_ai_token");
}

export function setToken(token) {
  localStorage.setItem("mr_ai_token", token);
}

export function clearToken() {
  localStorage.removeItem("mr_ai_token");
}

async function request(path, options = {}) {
  const token = getToken();

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers
  });

  const data = await response.json();

  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
    }

    throw new Error(data.detail || "Request failed");
  }

  return data;
}

export async function register(username, password, email) {
  const data = await request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, email: email || username + "@mrai.local" })
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

export function chat(message, provider = "gemini", toolContext = null) {
  return request("/ai/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      provider,
      tool_context: toolContext
    })
  });
}

export function getStatus() {
  return request("/system/status");
}

export function getActivity() {
  return request("/activity");
}

export function getTasks() {
  return request("/tasks");
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

  const response = await fetch(`${DEVICE_BRIDGE_URL}${path}`, {
    ...options,
    headers
  });

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



function getBrowserExtensionId() {
  const configured = import.meta.env.VITE_MR_AI_EXTENSION_ID;
  if (configured) return configured;

  const discovered = document.documentElement?.dataset?.mrAiExtensionId;
  return discovered || "";
}

export async function getBrowserHandsStatus() {
  const extensionId = getBrowserExtensionId();
  return {
    installed: Boolean(extensionId),
    extensionId: extensionId || null,
    targetTab: extensionId ? "controlled_non_mr_ai_tab" : "unknown"
  };
}

export function browserAction(action, payload = {}) {
  const extensionId = getBrowserExtensionId();

  if (!extensionId) {
    return Promise.reject(
      new Error(
        "MR AI Browser Hands extension not detected. Reload the MR AI page after installing/reloading the extension."
      )
    );
  }

  const requestId = `mr-ai-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  return Promise.race([
    globalThis.chrome.runtime.sendMessage(extensionId, {
      type: "MR_AI_BROWSER_ACTION",
      requestId,
      action,
      ...payload
    }),
    new Promise((_, reject) => {
      window.setTimeout(() => {
        reject(new Error("MR AI Browser Hands did not respond within 15 seconds."));
      }, 15000);
    })
  ]).then(message => {
    if (!message?.ok) {
      throw new Error(message?.error || "Browser action failed");
    }
    return message.result;
  });
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


export function getAgents() {
  return request("/agents");
}

export function planAgentWork(requestText) {
  return request("/agents/plan", {
    method: "POST",
    body: JSON.stringify({ request: requestText })
  });
}


export function executeMission(requestText) {
  return request("/agents/mission", {
    method: "POST",
    body: JSON.stringify({ request: requestText }),
  });
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
  });
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
  });
}


export function dispatchTool(command) {
  return request("/tools/dispatch", {
    method: "POST",
    body: JSON.stringify({ command }),
  });
}


export function getExecutiveBriefing() {
  return request("/agents/briefing");
}


export function runOrchestrator(message) {
  return request("/orchestrator/run", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
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
