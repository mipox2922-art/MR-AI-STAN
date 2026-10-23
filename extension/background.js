const CONTROLLER_PATTERNS = [
  /^http:\/\/localhost:5173\//,
  /^http:\/\/127\.0\.0\.1:5173\//,
  /^https:\/\/[^/]+\.app\.github\.dev\//,
  /^https:\/\/mr-ai-stan-web\.onrender\.com\//
];

let controlledTabId = null;

function isControllerPage(url = "") {
  return CONTROLLER_PATTERNS.some(pattern => pattern.test(url));
}

async function getAllowedHosts() {
  const stored = await chrome.storage.local.get("mr_ai_browser_allowlist");
  const rows = Array.isArray(stored.mr_ai_browser_allowlist) ? stored.mr_ai_browser_allowlist : [];
  return rows.filter(value => typeof value === "string").map(value => value.trim().toLowerCase()).filter(Boolean);
}

function hostnameFromUrl(raw) {
  try {
    const parsed = new URL(raw);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) return null;
    return parsed.hostname.toLowerCase();
  } catch {
    return null;
  }
}

function hostIsAllowed(hostname, allowlist) {
  if (!hostname) return false;
  return allowlist.some(entry => hostname === entry || hostname.endsWith("." + entry));
}

async function findAllowedTarget(allowlist, preferredTabId = null) {
  const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
  const candidates = tabs.filter(tab => {
    if (!Number.isInteger(tab.id) || isControllerPage(tab.url || "")) return false;
    return hostIsAllowed(hostnameFromUrl(tab.url || ""), allowlist);
  });

  const preferred = candidates.find(tab => tab.id === preferredTabId);
  if (preferred) return preferred;

  candidates.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
  return candidates[0] || null;
}

function rememberTarget(tab) {
  if (!tab || !Number.isInteger(tab.id) || isControllerPage(tab.url || "")) return;
  controlledTabId = tab.id;
  chrome.storage.session.set({ mrAiControlledTabId: tab.id }).catch(() => {});
}

async function restoreTarget() {
  if (Number.isInteger(controlledTabId)) return controlledTabId;

  try {
    const saved = await chrome.storage.session.get("mrAiControlledTabId");
    if (Number.isInteger(saved.mrAiControlledTabId)) {
      controlledTabId = saved.mrAiControlledTabId;
      const tab = await chrome.tabs.get(controlledTabId);
      if (!isControllerPage(tab.url || "")) return controlledTabId;
    }
  } catch {
    // Fall through to active-tab discovery.
  }

  const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
  const candidates = tabs
    .filter(tab => Number.isInteger(tab.id) && !isControllerPage(tab.url || ""))
    .sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));

  const target = candidates[0];
  if (target) rememberTarget(target);
  return target?.id ?? null;
}

chrome.runtime.onInstalled.addListener(() => {
  console.log("MR AI Browser Hands installed.");
});

chrome.runtime.onStartup.addListener(() => {
  restoreTarget().catch(() => {});
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    rememberTarget(tab);
  } catch {
    // Ignore tabs that disappear during activation.
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId !== controlledTabId) return;
  controlledTabId = null;
  chrome.storage.session.remove("mrAiControlledTabId").catch(() => {});
});

async function executeBrowserAction(message) {
  const allowlist = await getAllowedHosts();
  const rememberedTabId = await restoreTarget();
  let target = null;

  if (Number.isInteger(rememberedTabId)) {
    try {
      const remembered = await chrome.tabs.get(rememberedTabId);
      const rememberedHost = hostnameFromUrl(remembered.url || "");
      if (!isControllerPage(remembered.url || "") && hostIsAllowed(rememberedHost, allowlist)) {
        target = remembered;
      }
    } catch {
      // Discover another explicitly approved tab below.
    }
  }

  if (!target) {
    target = await findAllowedTarget(allowlist);
    if (target) rememberTarget(target);
  }

  if (!target || !Number.isInteger(target.id)) {
    const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
    const activeTab = tabs.find(tab => tab.active && !isControllerPage(tab.url || ""));
    const activeHost = hostnameFromUrl(activeTab?.url || "");
    const allowlistText = allowlist.length ? allowlist.join(", ") : "(tupu)";
    throw new Error("BLOCKED_BY_ALLOWLIST: Hakuna tab inayolingana na allowlist [" + allowlistText + "]. Tab ya sasa: " + (activeHost || "haijatambuliwa") + ".");
  }

  const tabId = target.id;
  const currentHost = hostnameFromUrl(target.url || "");
  if (message.action === "NAVIGATE") {
    const destinationHost = hostnameFromUrl(String(message.url || ""));
    if (!hostIsAllowed(destinationHost, allowlist)) {
      throw new Error("BLOCKED_BY_ALLOWLIST: Destination " + (destinationHost || "isiyotambuliwa") + " haipo kwenye allowlist.");
    }
  }

  const payload = {
    type: "MR_AI_BROWSER_ACTION",
    requestId: message.requestId,
    action: message.action,
    ...message
  };
  let response;
  try {
    response = await chrome.tabs.sendMessage(tabId, payload);
  } catch (firstError) {
    const detail = firstError instanceof Error ? firstError.message : String(firstError);
    const noReceiver = /receiving end does not exist|could not establish connection|message port closed/i.test(detail);
    if (!noReceiver) throw firstError;

    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
      response = await chrome.tabs.sendMessage(tabId, payload);
    } catch (retryError) {
      const retryDetail = retryError instanceof Error ? retryError.message : String(retryError);
      throw new Error("Browser Hands haikuweza kuwasiliana na tab " + currentHost + ". Refresh ukurasa huo. Maelezo: " + retryDetail.slice(0, 240));
    }
  }

  if (!response?.ok) throw new Error(response?.error || "Content script imerudisha hitilafu bila maelezo.");
  return {
    ...response.result,
    targetHost: currentHost,
    targetUrl: target.url || null,
    targetTitle: target.title || null
  };
}

async function browserApiBase() {
  const stored = await chrome.storage.local.get("mr_ai_api_url");
  const candidate = String(stored.mr_ai_api_url || "https://mr-ai-stan.onrender.com").trim();
  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error("MR AI API URL is invalid.");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error("MR AI API URL must use HTTP(S) and cannot contain credentials.");
  }
  if (parsed.protocol === "http:" && !["localhost", "127.0.0.1", "::1"].includes(parsed.hostname)) {
    throw new Error("HTTP is permitted only for local loopback development; use HTTPS remotely.");
  }
  return parsed.toString().replace(/\/+$/, "");
}

async function authenticatedBrowserFetch(path, options = {}) {
  const stored = await chrome.storage.local.get("mr_ai_token");
  const token = String(stored.mr_ai_token || "").trim();
  if (!token) throw new Error("MR AI session is not connected. Sign in to the dashboard first.");

  const baseUrl = await browserApiBase();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(baseUrl + path, {
      ...options,
      signal: controller.signal,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
        Authorization: "Bearer " + token
      }
    });
    const raw = await response.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { detail: "Backend returned an invalid JSON response." };
    }
    if (!response.ok) throw new Error(String(data.detail || ("HTTP " + response.status)).slice(0, 500));
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("MR AI browser queue request timed out.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function reportBrowserResult(command, report) {
  const key = "mr_ai_browser_pending_results";
  const existing = await chrome.storage.session.get(key);
  const queue = Array.isArray(existing[key]) ? existing[key].slice(-9) : [];
  queue.push({
    command_id: command.task_id,
    request_id: command.request_id,
    claim_token: command.claim_token,
    report,
    created_at: Date.now()
  });
  await chrome.storage.session.set({ [key]: queue });

  // Bounded retries are safe because the backend accepts an identical result
  // receipt idempotently and will not execute the command a second time.
  for (const delayMs of [0, 350, 900]) {
    if (delayMs) await new Promise(resolve => setTimeout(resolve, delayMs));
    try {
      const stored = await chrome.storage.session.get(key);
      const pending = Array.isArray(stored[key]) ? stored[key] : [];
      const receipt = pending.find(item => item.command_id === command.task_id && item.request_id === command.request_id);
      if (!receipt) return true;
      const response = await authenticatedBrowserFetch("/agents/browser/" + encodeURIComponent(command.task_id) + "/result", {
        method: "POST",
        body: JSON.stringify({
          request_id: receipt.request_id,
          claim_token: receipt.claim_token,
          ...receipt.report
        })
      });
      if (response.status === "ALREADY_RECORDED" || response.command_task_id === command.task_id || response.status) {
        const latest = await chrome.storage.session.get(key);
        const remaining = (Array.isArray(latest[key]) ? latest[key] : [])
          .filter(item => !(item.command_id === command.task_id && item.request_id === command.request_id));
        await chrome.storage.session.set({ [key]: remaining });
        return true;
      }
    } catch {
      // Keep only in session storage; do not persist page text to durable local storage.
    }
  }
  return false;
}

let browserPollInProgress = false;

async function drainPendingBrowserResults() {
  const stored = await chrome.storage.session.get("mr_ai_browser_pending_results");
  const rows = Array.isArray(stored.mr_ai_browser_pending_results) ? stored.mr_ai_browser_pending_results : [];
  for (const row of rows) {
    const command = {
      task_id: row.command_id,
      request_id: row.request_id,
      claim_token: row.claim_token
    };
    if (!await reportBrowserResult(command, row.report)) return false;
  }
  return true;
}

async function pollBrowserCommands() {
  if (browserPollInProgress) return;
  browserPollInProgress = true;
  try {
    const stored = await chrome.storage.local.get("mr_ai_token");
    if (!String(stored.mr_ai_token || "").trim()) return;
    if (!await drainPendingBrowserResults()) return;

    const response = await authenticatedBrowserFetch("/agents/browser/next");
    if (response.status !== "RUNNING" || !response.command) return;
    const command = response.command;

    let report;
    try {
      const result = await executeBrowserAction({
        requestId: command.request_id,
        action: command.action,
        ...(command.payload || {}),
        ...(command.boss_approved === true ? { boss_approved: true } : {})
      });
      report = { result };
    } catch (error) {
      report = { error: error instanceof Error ? error.message : String(error) };
    }
    await reportBrowserResult(command, report);
  } catch (error) {
    // Do not include auth tokens, page contents or session data in console logs.
    console.warn("MR AI Browser Hands queue unavailable:", error instanceof Error ? error.message : "unknown error");
  } finally {
    browserPollInProgress = false;
  }
}

function startBrowserPolling() {
  chrome.alarms.create("mr-ai-browser-command-poll", { periodInMinutes: 0.5 });
  pollBrowserCommands().catch(() => {});
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "mr-ai-browser-command-poll") pollBrowserCommands().catch(() => {});
});

chrome.runtime.onInstalled.addListener(() => {
  startBrowserPolling();
});
chrome.runtime.onStartup.addListener(() => {
  startBrowserPolling();
});

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (!isControllerPage(sender.url || "")) {
    sendResponse({ ok: false, error: "MR AI controller origin is not authorized." });
    return false;
  }

  if (message?.type === "MR_AI_PING") {
    sendResponse({ ok: true, type: "MR_AI_PONG", version: chrome.runtime.getManifest().version });
    pollBrowserCommands().catch(() => {});
    return false;
  }

  if (message?.type === "MR_AI_AUTH_TOKEN") {
    const token = typeof message.token === "string" ? message.token.trim() : "";
    if (token.length > 8192) {
      sendResponse({ ok: false, error: "Authentication token is too long." });
      return false;
    }
    const operation = token
      ? chrome.storage.local.set({ mr_ai_token: token })
      : chrome.storage.local.remove("mr_ai_token");
    operation
      .then(() => {
        sendResponse({ ok: true });
        if (token) pollBrowserCommands().catch(() => {});
      })
      .catch(() => sendResponse({ ok: false, error: "Could not sync MR AI authentication." }));
    return true;
  }

  if (message?.type === "MR_AI_POLL_NOW") {
    pollBrowserCommands().catch(() => {});
    sendResponse({ ok: true, scheduled: true });
    return false;
  }

  if (message?.type !== "MR_AI_BROWSER_ACTION") {
    sendResponse({ ok: false, error: "Unsupported external message." });
    return false;
  }

  executeBrowserAction(message)
    .then(result => sendResponse({ ok: true, result }))
    .catch(error => sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    }));
  return true;
});
