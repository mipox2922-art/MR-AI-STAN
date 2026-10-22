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
        // Fall through and search for an allowed tab.
      }
    }

    // If the remembered target is stale or outside the allowlist, select the
    // most recently used open tab whose exact host (or subdomain) is approved.
    if (!target) {
      target = await findAllowedTarget(allowlist);
      if (target) rememberTarget(target);
    }

    if (!target || !Number.isInteger(target.id)) {
      const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
      const activeTab = tabs.find(tab => tab.active && !isControllerPage(tab.url || ""));
      const activeHost = hostnameFromUrl(activeTab?.url || "");
      const allowlistText = allowlist.length ? allowlist.join(", ") : "(tupu)";
      throw new Error(
        `BLOCKED_BY_ALLOWLIST: Hakuna tab iliyo wazi inayolingana na Allowlist [${allowlistText}]. Tab ya sasa: ${activeHost || "haijatambuliwa"}. Fungua tovuti iliyoidhinishwa, mfano remoteok.com, kisha jaribu tena.`
      );
    }

    const tabId = target.id;
    const currentHost = hostnameFromUrl(target.url || "");
    if (message.action === "NAVIGATE") {
      const destinationHost = hostnameFromUrl(String(message.url || ""));
      if (!hostIsAllowed(destinationHost, allowlist)) {
        throw new Error(
          `BLOCKED_BY_ALLOWLIST: Destination ${destinationHost || "isiyotambuliwa"} haipo kwenye Allowlist [${allowlist.join(", ") || "(tupu)"}].`
        );
      }
    }

    const payload = { type: "MR_AI_BROWSER_ACTION", requestId: message.requestId, action: message.action, ...message };
    const response = await chrome.tabs.sendMessage(tabId, payload);
    if (!response?.ok) throw new Error(response?.error || "Browser action failed.");
    // Unwrap content-script response; don't let a nested {ok,result} look like verified success.
    return { ...response.result, targetHost: currentHost, targetUrl: target.url || null, targetTitle: target.title || null };
  })()
    .then(result => sendResponse(result || { ok: false, error: "Empty extension response." }))
    .catch(error => sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    }));

  return true;
});
