const CONTROLLER_PATTERNS = [
  /^http:\/\/localhost:5173\//,
  /^http:\/\/127\.0\.0\.1:5173\//,
  /^https:\/\/[^/]+\.app\.github\.dev\//,
  /^https:\/\/mr-ai-stan\.pages\.dev\//
];

let controlledTabId = null;

function isControllerPage(url = "") {
  return CONTROLLER_PATTERNS.some(pattern => pattern.test(url));
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

    const payload = {
      type: "MR_AI_BROWSER_ACTION",
      requestId: message.requestId,
      action: message.action,
      ...message
    };

    const result = await chrome.tabs.sendMessage(tabId, payload);
    return result;
  })()
    .then(result => sendResponse(result || { ok: false, error: "Empty extension response." }))
    .catch(error => sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    }));

  return true;
});
