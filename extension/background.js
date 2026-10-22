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

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  const senderUrl = sender.url || "";
  if (!isControllerPage(senderUrl)) {
    sendResponse({ ok: false, error: "MR AI controller origin is not authorized." });
    return false;
  }

  if (message?.type === "MR_AI_PING") {
    sendResponse({
      ok: true,
      type: "MR_AI_PONG",
      version: chrome.runtime.getManifest().version
    });
    return false;
  }

  if (message?.type === "MR_AI_AUTH_TOKEN") {
    const token = typeof message.token === "string" ? message.token.trim() : "";
    if (token.length > 8192) {
      sendResponse({ ok: false, error: "Authentication token is too long." });
      return false;
    }

    const storageOperation = token
      ? chrome.storage.local.set({ mr_ai_token: token })
      : chrome.storage.local.remove("mr_ai_token");
    storageOperation
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false, error: "Could not sync MR AI authentication." }));
    return true;
  }

  if (message?.type !== "MR_AI_BROWSER_ACTION") {
    sendResponse({ ok: false, error: "Unsupported external message." });
    return false;
  }

  (async () => {
    const tabId = await restoreTarget();
    if (!Number.isInteger(tabId)) {
      throw new Error("No controlled browser tab is available. Open a target web page first.");
    }

    const target = await chrome.tabs.get(tabId);
    if (isControllerPage(target.url || "")) {
      throw new Error("The controlled tab points to the MR AI dashboard; open a target web page first.");
    }

    const allowlist = await getAllowedHosts();
    const currentHost = hostnameFromUrl(target.url || "");
    if (!hostIsAllowed(currentHost, allowlist)) {
      throw new Error("BLOCKED_BY_ALLOWLIST: Boss Ferisi lazima aongeze domain hii kwenye Browser Hands allowlist ya extension kwanza.");
    }
    if (message.action === "NAVIGATE") {
      const destinationHost = hostnameFromUrl(String(message.url || ""));
      if (!hostIsAllowed(destinationHost, allowlist)) {
        throw new Error("BLOCKED_BY_ALLOWLIST: Destination domain haipo kwenye Browser Hands allowlist.");
      }
    }

    const payload = { type: "MR_AI_BROWSER_ACTION", requestId: message.requestId, action: message.action, ...message };
    const response = await chrome.tabs.sendMessage(tabId, payload);
    if (!response?.ok) throw new Error(response?.error || "Browser action failed.");
    // Unwrap content-script response; don't let a nested {ok,result} look like verified success.
    return { ...response.result, targetHost: currentHost };
  })()
    .then(result => sendResponse(result || { ok: false, error: "Empty extension response." }))
    .catch(error => sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    }));

  return true;
});
