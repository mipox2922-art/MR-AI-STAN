const DEFAULT_API_URL = "https://mr-ai-stan.pages.dev/api";

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
  return url.toString().replace(/\\/+$/, "");
}

const prompt = document.getElementById("prompt");
const result = document.getElementById("result");

async function getPage() {
  const tabs = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  const tab = tabs[0];

  const response = await chrome.tabs.sendMessage(
    tab.id,
    { type: "GET_PAGE_DATA" }
  );

  return {
    title: tab.title || "",
    url: tab.url || "",
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
