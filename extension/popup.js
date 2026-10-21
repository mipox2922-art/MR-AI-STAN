const DEFAULT_API_URL = "https://mr-ai-stan.onrender.com";

async function getApiUrl() {
  const stored = await chrome.storage.local.get("mr_ai_api_url");
  const candidate = String(stored.mr_ai_api_url || DEFAULT_API_URL).trim();
  let url;
  try {
    url = new URL(candidate);
  } catch {
    throw new Error("Invalid MR AI API URL. Configure mr_ai_api_url in extension storage.");
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("MR AI API URL must use HTTP or HTTPS.");
  }
  return url.toString().replace(/\/+$/, "");
}

const prompt = document.getElementById("prompt");
const result = document.getElementById("result");

async function getPage() {
  const tabs = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  const tab = tabs[0];
  if (!tab?.id || !tab.url) throw new Error("No active web page is available.");

  const stored = await chrome.storage.local.get("mr_ai_browser_allowlist");
  const allowlist = Array.isArray(stored.mr_ai_browser_allowlist) ? stored.mr_ai_browser_allowlist : [];
  let host;
  try {
    const parsed = new URL(tab.url);
    if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("unsupported protocol");
    host = parsed.hostname.toLowerCase();
  } catch {
    throw new Error("This page cannot be read by Browser Hands.");
  }
  const allowed = allowlist.some(entry => {
    const domain = String(entry || "").trim().toLowerCase();
    return domain && (host === domain || host.endsWith("." + domain));
  });
  if (!allowed) throw new Error("BLOCKED_BY_ALLOWLIST: Add " + host + " in Browser Hands allowlist before reading or sending page content to MR AI.");

  const response = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_DATA" });
  if (response?.ok === false) throw new Error(response.error || "The page is not approved.");
  return {
    title: response?.title || tab.title || "",
    url: response?.url || tab.url || "",
    text: response?.text || ""
  };
}

async function askMR(promptText) {
  const token = await chrome.storage.local.get("mr_ai_token");

  const apiUrl = await getApiUrl();
  const response = await fetch(
    `${apiUrl}/ai/chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token.mr_ai_token || ""}`
      },
      body: JSON.stringify({
        message: promptText,
        provider: "gemini"
      })
    }
  );

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Backend error");
  }

  return data.response;
}

document.getElementById("analyze").onclick =
  async () => {
    try {
      result.textContent = "Scanning page...";

      const page = await getPage();

      const answer = await askMR(
        `Analyze this web page.

Title:
${page.title}

URL:
${page.url}

Visible content:
${page.text.slice(0, 12000)}`
      );

      result.textContent = answer;

    } catch (error) {
      result.textContent =
        `ERROR: ${error.message}`;
    }
  };

document.getElementById("summarize").onclick =
  async () => {
    try {
      result.textContent = "Summarizing...";

      const page = await getPage();

      const answer = await askMR(
        `Summarize this page in concise natural Swahili.

${page.text.slice(0, 12000)}`
      );

      result.textContent = answer;

    } catch (error) {
      result.textContent =
        `ERROR: ${error.message}`;
    }
  };

document.getElementById("task").onclick =
  async () => {
    try {
      const title =
        prompt.value.trim() ||
        "Review current web page";

      const token = await chrome.storage.local.get(
        "mr_ai_token"
      );

      const apiUrl = await getApiUrl();
      const response = await fetch(
        `${apiUrl}/tasks`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization:
              `Bearer ${token.mr_ai_token || ""}`
          },
          body: JSON.stringify({
            title
          })
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Task creation failed"
        );
      }

      result.textContent =
        `Task #${data.id} imeundwa.`;

    } catch (error) {
      result.textContent =
        `ERROR: ${error.message}`;
    }
  };


// Boss-managed Browser Hands allowlist. Render domain text safely (never innerHTML).
const allowHostInput = document.getElementById("allow-host");
const allowAddButton = document.getElementById("allow-add");
const allowListElement = document.getElementById("allow-list");

function normalizeAllowedHost(raw) {
  const value = String(raw || "").trim();
  if (!value || value.includes("/") || value.includes("@") || value.includes(":") || /\s/.test(value)) {
    throw new Error("Weka domain tu, mfano example.com. Usitumie URL, path, port au credentials.");
  }
  let host;
  try {
    host = new URL("https://" + value).hostname.toLowerCase();
  } catch {
    throw new Error("Domain si sahihi.");
  }
  if (!host || host !== value.toLowerCase() || host.includes("..") || host.startsWith(".") || host.endsWith(".")) {
    throw new Error("Domain si sahihi. Mfano: example.com");
  }
  return host;
}

async function renderAllowlist() {
  const stored = await chrome.storage.local.get("mr_ai_browser_allowlist");
  const items = Array.isArray(stored.mr_ai_browser_allowlist) ? stored.mr_ai_browser_allowlist : [];
  allowListElement.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "Allowlist tupu. Browser automation imefungwa mpaka Boss aongeze domain.";
    allowListElement.appendChild(empty);
    return;
  }
  for (const host of items) {
    const row = document.createElement("div");
    row.className = "allow-item";
    row.setAttribute("role", "listitem");
    const label = document.createElement("span");
    label.textContent = host;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "REMOVE";
    remove.setAttribute("aria-label", "Ondoa " + host);
    remove.addEventListener("click", async () => {
      const latest = await chrome.storage.local.get("mr_ai_browser_allowlist");
      const current = Array.isArray(latest.mr_ai_browser_allowlist) ? latest.mr_ai_browser_allowlist : [];
      await chrome.storage.local.set({ mr_ai_browser_allowlist: current.filter(value => value !== host) });
      await renderAllowlist();
      result.textContent = "Allowlist updated: domain removed. Browser actions to this domain are now blocked.";
    });
    row.append(label, remove);
    allowListElement.appendChild(row);
  }
}

allowAddButton?.addEventListener("click", async () => {
  try {
    const host = normalizeAllowedHost(allowHostInput.value);
    const stored = await chrome.storage.local.get("mr_ai_browser_allowlist");
    const current = Array.isArray(stored.mr_ai_browser_allowlist) ? stored.mr_ai_browser_allowlist : [];
    const next = [...new Set([...current, host])].slice(0, 100);
    await chrome.storage.local.set({ mr_ai_browser_allowlist: next });
    allowHostInput.value = "";
    await renderAllowlist();
    result.textContent = "Domain allowed: " + host + ". Payments, form submissions and downloads still need Boss confirmation.";
  } catch (error) {
    result.textContent = "ALLOWLIST ERROR: " + error.message;
  }
});

renderAllowlist().catch(error => {
  allowListElement.textContent = "Allowlist could not be loaded: " + error.message;
});
