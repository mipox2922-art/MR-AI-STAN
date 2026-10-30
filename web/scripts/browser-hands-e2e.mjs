import assert from "node:assert/strict";
import { chromium } from "playwright";
import { createServer } from "node:http";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";

const BASE_URL = process.env.BROWSER_E2E_WEB_URL || "http://127.0.0.1:5173";
const API_URL = (process.env.BROWSER_E2E_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const EXTENSION_DIR = resolve(process.env.BROWSER_E2E_EXTENSION_DIR || "../extension");
const FIXTURE_PATH = resolve(process.env.BROWSER_E2E_FIXTURE_PATH || "fixtures/browser-hands-e2e.html");
const FIXTURE_PORT = Number(process.env.BROWSER_E2E_FIXTURE_PORT || 4173);
const MARKER = "Browser Hands end-to-end marker";

async function jsonRequest(url, { token, method = "GET", body } = {}) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const raw = await response.text();
  let data;
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    data = { detail: raw.slice(0, 500) };
  }
  if (!response.ok) {
    throw new Error("HTTP " + response.status + " " + url + ": " + String(data.detail || raw).slice(0, 500));
  }
  return data;
}

async function waitUntil(check, { timeoutMs = 30000, intervalMs = 250, description = "condition" } = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await new Promise(resolvePromise => setTimeout(resolvePromise, intervalMs));
  }
  throw new Error("Timed out waiting for " + description + (lastError ? ": " + lastError.message : ""));
}

const fixtureHtml = await readFile(FIXTURE_PATH, "utf8");
const fixtureServer = createServer((req, res) => {
  if (req.method !== "GET" || !["/", "/index.html"].includes(new URL(req.url || "/", "http://127.0.0.1").pathname)) {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("not found");
    return;
  }
  res.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  res.end(fixtureHtml);
});

let context;
let profileDir;
await new Promise((resolvePromise, reject) => {
  fixtureServer.once("error", reject);
  fixtureServer.listen(FIXTURE_PORT, "127.0.0.1", resolvePromise);
});

try {
  await waitUntil(async () => {
    const response = await fetch(API_URL + "/health");
    const data = await response.json().catch(() => ({}));
    return response.ok && data.status === "healthy" && data.database === "reachable";
  }, { timeoutMs: 60000, description: "local FastAPI and its database" });

  await waitUntil(async () => {
    const response = await fetch(BASE_URL + "/");
    const body = await response.text();
    return response.ok && body.includes('id="root"');
  }, { timeoutMs: 60000, description: "local MR AI web application" });

  const username = "browser-e2e-" + Date.now();
  const credentials = await jsonRequest(API_URL + "/auth/register", {
    method: "POST",
    body: { username, password: "mr-ai-browser-e2e-password-2026" },
  });
  const token = credentials.access_token;
  assert.ok(token, "Test owner registration must issue a real backend JWT.");

  profileDir = await mkdtemp(join(tmpdir(), "mr-ai-browser-hands-e2e-"));
  context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    viewport: { width: 1440, height: 1000 },
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-extensions-except=" + EXTENSION_DIR,
      "--load-extension=" + EXTENSION_DIR,
    ],
  });

  let worker = context.serviceWorkers()[0];
  if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 20000 });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/, "Chromium must load the actual unpacked MV3 extension.");

  // Playwright exposes MV3 service workers through a generic Worker handle,
  // where extension-only chrome.* bindings may be absent in the evaluation
  // context. Configure the extension through its real popup page instead.
  const extensionSettingsPage = await context.newPage();
  await extensionSettingsPage.goto("chrome-extension://" + extensionId + "/popup.html", {
    waitUntil: "domcontentloaded",
  });
  await extensionSettingsPage.waitForFunction(
    () => Boolean(globalThis.chrome?.storage?.local),
    null,
    { timeout: 10000 }
  );
  await extensionSettingsPage.evaluate(async ({ accessToken, apiUrl }) => {
    await chrome.storage.local.set({
      mr_ai_token: accessToken,
      mr_ai_api_url: apiUrl,
      mr_ai_browser_allowlist: ["127.0.0.1"],
    });
  }, { accessToken: token, apiUrl: API_URL });
  await extensionSettingsPage.close();

  const dashboard = context.pages()[0] || await context.newPage();
  await dashboard.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await dashboard.evaluate(accessToken => localStorage.setItem("mr_ai_token", accessToken), token);
  await dashboard.reload({ waitUntil: "domcontentloaded" });
  await dashboard.waitForFunction(
    () => Boolean(document.documentElement?.dataset?.mrAiExtensionId),
    null,
    { timeout: 20000 }
  );
  // Mission Planner lives in the existing Agents view, not the dashboard home.
  await dashboard.locator(".sidebar nav button").filter({ hasText: "Agents" }).click();
  await dashboard.locator(".agent-planner-form input").waitFor({ state: "visible", timeout: 30000 });

  // Create an actual local web page in the same Chromium session. It is the
  // only non-dashboard domain added to Browser Hands' extension-local allowlist.
  const fixture = await context.newPage();
  await fixture.goto("http://127.0.0.1:" + FIXTURE_PORT + "/", { waitUntil: "domcontentloaded" });
  await fixture.getByText(MARKER, { exact: true }).waitFor({ state: "visible" });
  await dashboard.bringToFront();

  await dashboard.locator(".agent-planner-form input").fill("soma ukurasa");
  await dashboard.locator(".agent-planner-form").getByRole("button", { name: "ANZA KAZI" }).click();

  let lastObserved = null;
  const persisted = await waitUntil(async () => {
    const rows = await jsonRequest(API_URL + "/tasks", { token });
    const mission = rows.find(task => task.agent === "orchestrator" && task.title === "soma ukurasa");
    const command = rows.find(task =>
      task.agent === "browser" && task.source === "browser_hands" &&
      String(task.requested_by || "") === "mission:" + mission?.id
    );
    if (!mission || !command) return null;
    let commandPacket = {};
    try {
      commandPacket = typeof command.result === "string" ? JSON.parse(command.result || "{}") : (command.result || {});
    } catch {
      commandPacket = {};
    }
    lastObserved = {
      mission: { id: mission.id, status: mission.status, progress: mission.progress, error: mission.error },
      command: { id: command.id, status: command.status, error: command.error },
      commandResult: commandPacket,
    };
    if (["FAILED", "BLOCKED", "WAITING_FOR_VERIFICATION"].includes(String(mission.status).toUpperCase()) ||
        ["FAILED", "BLOCKED", "WAITING_FOR_VERIFICATION"].includes(String(command.status).toUpperCase())) {
      throw new Error("Browser result returned but was not accepted as independently verified: " + JSON.stringify(lastObserved));
    }
    if (mission.status !== "COMPLETED" || command.status !== "COMPLETED") return null;
    return { mission, command };
  }, { timeoutMs: 35000, intervalMs: 300, description: "real extension result persisted and verified by the backend" }).catch(error => {
    throw new Error(String(error.message || error) + (lastObserved ? "; last stored state=" + JSON.stringify(lastObserved) : ""));
  });

  const commandResult = typeof persisted.command.result === "string"
    ? JSON.parse(persisted.command.result)
    : persisted.command.result;
  const browserOutput = commandResult?.result;
  assert.equal(commandResult.status, "COMPLETED");
  assert.equal(commandResult.verified, true);
  assert.equal(browserOutput.action, "GET_PAGE_DATA");
  assert.equal(browserOutput.targetHost, "127.0.0.1");
  assert.match(browserOutput.targetUrl, new RegExp("127\\.0\\.0\\.1:" + FIXTURE_PORT));
  assert.equal(browserOutput.page.title, "MR AI Browser Fixture");
  assert.ok(browserOutput.page.text.includes(MARKER), "Backend must persist genuine text read by the content script.");

  const missionResult = typeof persisted.mission.result === "string"
    ? JSON.parse(persisted.mission.result)
    : persisted.mission.result;
  assert.equal(persisted.mission.progress, 100);
  assert.equal(missionResult.verified_steps, 1);
  assert.equal(missionResult.total_steps, 1);
  assert.equal(missionResult.steps[0].command_task_id, persisted.command.id);
  assert.equal(missionResult.steps[0].verified, true);

  // The normal React Mission Planner must render the status returned from the
  // persisted backend task, not from a mocked API response.
  await dashboard.waitForFunction(() => {
    const text = document.querySelector(".agent-result-run")?.innerText || "";
    return text.includes("IMEKAMILIKA") && text.includes("100%");
  }, null, { timeout: 15000 });

  const uiResult = await dashboard.locator(".agent-result-run").innerText();
  assert.match(uiResult, /IMEKAMILIKA/);
  assert.match(uiResult, /100%/);

  // Prove a duplicate receipt is idempotent and does not create a second step.
  const storedSteps = await jsonRequest(API_URL + "/tasks", { token });
  const parent = storedSteps.find(task => task.id === persisted.mission.id);
  assert.equal(parent.status, "COMPLETED");
  assert.equal(parent.verified_steps, 1);
  assert.equal(parent.step_count, 1);

  console.log("PASS real Browser Hands E2E");
  console.log("PASS mission task #" + persisted.mission.id + " delegated to Browser Agent");
  console.log("PASS extension executed GET_PAGE_DATA against http://127.0.0.1:" + FIXTURE_PORT);
  console.log("PASS backend validated and persisted the genuine fixture page text");
  console.log("PASS React Mission Planner rendered IMEKAMILIKA at 100%");
  console.log("PASS no mocked browser result or mock API endpoint was used");
} catch (error) {
  console.error("FAIL real Browser Hands E2E:", error?.stack || String(error));
  throw error;
} finally {
  if (context) await context.close().catch(() => {});
  await new Promise(resolvePromise => fixtureServer.close(() => resolvePromise()));
  if (profileDir) await rm(profileDir, { recursive: true, force: true }).catch(() => {});
}
