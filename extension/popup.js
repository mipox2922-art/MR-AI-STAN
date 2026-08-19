const API_URL = "http://localhost:8000";

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

  const response = await fetch(
    `${API_URL}/ai/chat`,
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

      const response = await fetch(
        `${API_URL}/tasks`,
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
