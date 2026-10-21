import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE_URL = process.env.UI_SMOKE_URL || "http://127.0.0.1:5173";
const API_ORIGIN = (process.env.VITE_API_URL || "https://mr-ai-stan.onrender.com").replace(/\/$/, "");
const browserErrors = [];
const unexpectedApi = [];
const completedChecks = [];
let mockTasks = [];
let mockMemories = [{ id: 1, key: "preferred_language", value: "Swahili" }];
let mockSchedules = [];
let nextTaskId = 1;
let nextMemoryId = 2;
let nextScheduleId = 1;
let rebootRequests = 0;
let radarScanRequests = 0;
let delayedChatRequests = 0;
let delayedChatRequestBodies = [];

const services = {
  ai_core: "CONFIGURED", database: "ONLINE", memory: "ONLINE", web_app: "ONLINE",
  agents: "REGISTERED", web_search: "CONFIGURED", security: "CONFIGURED", voice: "NOT_CONFIGURED", extension: "NOT_CONNECTED",
  gemini: "CONFIGURED", kimi: "NOT_CONFIGURED", openrouter: "CONFIGURED",
  mistral: "CONFIGURED", grok: "CONFIGURED", gmail: "NOT_CONFIGURED",
};
const telemetry = {
  cpu_percent: 23.1, memory_percent: 51.4, storage_percent: 42.0,
  network: { bytes_sent: 12000, bytes_received: 18000 },
  gpu: { status: "UNAVAILABLE", utilization_percent: null, memory_percent: null },
  uptime_seconds: 3600, source: "host_runtime",
};
const systemStatus = {
  organization: { owner: "Boss Ferisi", manager: "MR AI", workspace: "MOG343", crew: "Agent Team", model_role: "Digital Chief of Staff" },
  services, telemetry, security: { threats_detected: null, source: "no_security_engine" },
  ai: { provider: "openrouter", model: "openrouter/free", tier: "OPENROUTER_FREE", configured: true, ready: false },
  capabilities: { street_view: "AVAILABLE_VIA_MAPS_URL", device_tracking: "LOCAL_SENSOR_ONLY", gemini_tier: "FREE" },
};
const agents = [
  ["orchestrator", "MR AI Orchestrator"], ["research", "Research Agent"],
  ["browser", "Browser Agent"], ["gmail", "Gmail Agent"],
  ["jobs", "Job Research Agent"], ["coding", "Coding Agent"],
  ["creative", "Creative Studio Agent"], ["device", "Device Lab Agent"],
  ["security", "Security Agent"], ["memory", "Memory Agent"],
  ["scheduler", "Scheduler Agent"],
].map(([id, name]) => ({
  id, name, description: "UI smoke test agent", risk: "LOW",
  capabilities: ["test", "verification"], tools: ["test_tool"],
}));
const toolSummary = {
  total: 2, ready: 1, optional: 1, not_connected: 0,
  tools: [
    { id: "system_telemetry", name: "System Telemetry", category: "SYSTEM", status: "READY", description: "Verified runtime telemetry", mode: "LOCAL", free: true },
    { id: "searxng", name: "SearXNG", category: "RESEARCH", status: "NOT_CONNECTED", description: "Self-hosted web search", mode: "OPTIONAL", free: true },
  ],
};

function corsHeaders(origin = BASE_URL) {
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-headers": "authorization,content-type",
    "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    "access-control-max-age": "600",
  };
}

async function sendJson(route, payload, status = 200, origin = BASE_URL) {
  await route.fulfill({
    status,
    headers: { ...corsHeaders(origin), "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  });
}

function planFor(request) {
  const lower = request.toLowerCase();
  const systemOnly = ["system", "mfumo", "cpu", "ram", "storage", "disk", "network", "uptime", "hali ya pc"].some(term => lower.includes(term));
  const chosen = systemOnly ? [agents[0]] : [agents[0], agents[1]];
  return {
    request, status: "PLANNED", agents: chosen.map(agent => agent.name),
    steps: chosen.map((agent, index) => ({
      step: index + 1, agent: agent.id, name: agent.name, risk: agent.risk,
      capabilities: agent.capabilities, tools: agent.tools, status: "PLANNED",
    })),
    verification: ["Smoke test fixture only; no real external action was run."],
  };
}

async function apiMock(route) {
  const request = route.request();
  const method = request.method();
  const url = new URL(request.url());
  const path = url.pathname;
  if (method === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders(request.headers().origin || BASE_URL), body: "" });
    return;
  }

  let body = {};
  try { body = request.postDataJSON() || {}; } catch { body = {}; }

  if (method === "GET" && path === "/auth/status") return sendJson(route, { setup_required: false });
  if (method === "POST" && path === "/auth/login") return sendJson(route, { access_token: "smoke-login-token", token_type: "bearer" });
  if (method === "POST" && path === "/auth/register") return sendJson(route, { access_token: "smoke-register-token", token_type: "bearer" });
  if (method === "GET" && path === "/system/status") return sendJson(route, systemStatus);
  if (method === "GET" && path === "/system/diagnostics") return sendJson(route, { status: "CONFIGURATION_CHECKED", checks: [{ id: "database", label: "Persistent database", status: "PASS", detail: "Mock database check" }, { id: "ai_provider", label: "AI provider configuration", status: "CONFIGURED", detail: "Mock provider" }], truth_boundary: "Mock check only." });
  if (method === "GET" && path === "/agents") return sendJson(route, agents);
  if (method === "GET" && path === "/tasks") return sendJson(route, mockTasks);
  if (method === "POST" && path === "/tasks") {
    const task = { id: nextTaskId++, title: body.title, description: body.description || "", status: "PENDING", priority: body.priority || "NORMAL", agent: body.agent || "orchestrator", progress: 0 };
    mockTasks.unshift(task);
    return sendJson(route, task, 201);
  }
  if (method === "PATCH" && /^\/tasks\/\d+$/.test(path)) {
    const id = Number(path.split("/").pop());
    const task = mockTasks.find(item => item.id === id);
    if (!task) return sendJson(route, { detail: "Task not found" }, 404);
    Object.assign(task, body);
    return sendJson(route, task);
  }
  if (method === "GET" && path === "/memory") return sendJson(route, mockMemories);
  if (method === "POST" && path === "/memory") {
    const memory = { id: nextMemoryId++, key: body.key, value: body.value };
    mockMemories.unshift(memory);
    return sendJson(route, memory, 201);
  }
  if (method === "PUT" && /^\/memory\/\d+$/.test(path)) {
    const id = Number(path.split("/").pop());
    const memory = mockMemories.find(item => item.id === id);
    if (!memory) return sendJson(route, { detail: "Memory not found" }, 404);
    memory.value = body.value;
    return sendJson(route, memory);
  }
  if (method === "DELETE" && /^\/memory\/\d+$/.test(path)) {
    const id = Number(path.split("/").pop());
    mockMemories = mockMemories.filter(item => item.id !== id);
    return sendJson(route, { deleted: true });
  }
  if (method === "GET" && path === "/activity") return sendJson(route, []);
  if (method === "POST" && path === "/activity/events") {
    assert.ok(!("message" in body) && !("content" in body) && !("token" in body),
      "Audit API mock must not receive message content or credentials");
    return sendJson(route, { status: "RECORDED", event_id: 1, action: body.action, outcome: body.outcome });
  }
  if (method === "GET" && path === "/integrations/gmail/status") {
    return sendJson(route, { status: "NOT_CONFIGURED", configured: false, connected: false, scope: [] });
  }
  if (method === "GET" && path === "/ai/history") return sendJson(route, { messages: [], session_id: url.searchParams.get("session_id") });
  if (method === "GET" && path === "/ai/state") return sendJson(route, { state: "IDLE", verified: true, updated_at: new Date().toISOString() });
  if (method === "POST" && path === "/ai/state") return sendJson(route, { state: body.state, verified: true, updated_at: new Date().toISOString() });
  if (method === "GET" && path === "/ai/health") return sendJson(route, { status: "LIVE", provider: url.searchParams.get("provider") || "openrouter", latency_ms: 23, tested_at: new Date().toISOString(), reason: null });
  if (method === "POST" && path === "/ai/chat") {
    delayedChatRequestBodies.push({ message: body.message, at: Date.now() });
    if (body.message === "Timeout regression test") {
      delayedChatRequests += 1;
      await new Promise(resolve => setTimeout(resolve, 13000));
      return sendJson(route, { response: "Delayed chat response confirmed", provider: body.provider || "openrouter" });
    }
    return sendJson(route, { response: "E2E response from mocked API", provider: body.provider || "openrouter" });
  }
  if (method === "GET" && path === "/agents/briefing") return sendJson(route, { status: "READY", briefing: "Mock briefing only" });
  if (method === "POST" && path === "/agents/plan") return sendJson(route, planFor(String(body.request || "")));
  if (method === "POST" && path === "/agents/mission") {
    const plan = planFor(String(body.request || ""));
    const steps = plan.steps.map(step => ({ ...step, tool: step.tools[0], status: "COMPLETED", verified: true, evidence: { testFixture: true } }));
    return sendJson(route, { status: "COMPLETED", mission: { id: 999, title: body.request, status: "COMPLETED", progress: 100, agent: "orchestrator", result: "E2E test fixture" }, plan, steps, next_action: "UI smoke test only." });
  }
  if (method === "GET" && path === "/tools") return sendJson(route, toolSummary);
  if (method === "POST" && path === "/tools/search") {
    return sendJson(route, { status: "COMPLETED", query: body.query, results: [{ title: "Smoke Search Result", url: "https://example.com/", content: "Mocked search result for UI wiring", engine: "ui-smoke" }] });
  }
  if (method === "POST" && path === "/tools/route") return sendJson(route, { status: "ROUTED", route: { agent: "research", tool: "searxng" }, result: { status: "COMPLETED", results: [] }, message: "Mock tool routing only." });
  if (method === "POST" && path === "/tools/dispatch") return sendJson(route, { status: "COMPLETED", route: { agent: "orchestrator", tool: "system_telemetry" }, result: systemStatus });
  if (method === "GET" && path === "/jobs/research") return sendJson(route, { status: "COMPLETED", query: url.searchParams.get("query"), count: 1, sources: ["RemoteOK", "Remotive"], source_warnings: [], results: [{ id: "smoke-job-1", title: "Python Developer", company: "Example Remote", location: "Worldwide", url: "https://example.com/jobs/python", description: "Build Python APIs", tags: ["python", "api"], published_at: "2026-10-12", source: "RemoteOK" }] });
  if (method === "POST" && path === "/jobs/save") {
    const task = {
      id: nextTaskId++,
      title: `Job application: ${body.title}`,
      description: `Company: ${body.company || "Company not listed"}\nJob URL: ${body.url}\n\n${body.description || ""}`,
      status: "PENDING", priority: "NORMAL", agent: "jobs", result: null,
    };
    mockTasks.unshift(task);
    return sendJson(route, { status: "SAVED", task }, 201);
  }
  if (method === "PATCH" && /^\/jobs\/\d+\/tracking$/.test(path)) {
    const id = Number(path.split("/")[2]);
    const task = mockTasks.find(item => item.id === id && item.agent === "jobs");
    if (!task) return sendJson(route, { detail: "Saved job task not found" }, 404);
    let previous = {};
    try { previous = JSON.parse(task.result || "{}"); } catch { previous = {}; }
    const evidenceUrl = body.evidence_url || previous.evidence_url || null;
    const ownerConfirmed = body.owner_confirmed === true;
    const tracking = {
      status: body.status,
      evidence_url: evidenceUrl,
      updated_at: new Date().toISOString(),
      verified: false,
      owner_confirmed: ownerConfirmed,
      evidence_status: evidenceUrl ? "PROVIDED_NOT_CHECKED" : "NOT_PROVIDED",
      verification_method: evidenceUrl ? "evidence_link_provided_not_checked" : ownerConfirmed ? "owner_confirmation" : "unconfirmed",
      truth_note: "Status is user-reported; external evidence has not been independently checked.",
    };
    task.result = JSON.stringify(tracking);
    return sendJson(route, { status: "UPDATED", task_id: id, tracking });
  }
  if (method === "GET" && path === "/scheduler") return sendJson(route, mockSchedules);
  if (method === "POST" && path === "/scheduler") {
    const job = { id: nextScheduleId++, title: body.title, command: body.command, run_at: body.run_at, next_run_at: body.run_at, interval_minutes: body.interval_minutes || null, status: "ACTIVE" };
    mockSchedules.unshift(job);
    return sendJson(route, job, 201);
  }
  if (method === "PATCH" && /^\/scheduler\/\d+$/.test(path)) {
    const job = mockSchedules.find(item => item.id === Number(path.split("/").pop()));
    if (!job) return sendJson(route, { detail: "Schedule not found" }, 404);
    Object.assign(job, body);
    return sendJson(route, job);
  }
  if (method === "POST" && /^\/scheduler\/\d+\/run-now$/.test(path)) return sendJson(route, { status: "QUEUED" });
  if (method === "DELETE" && /^\/scheduler\/\d+$/.test(path)) {
    mockSchedules = mockSchedules.filter(item => item.id !== Number(path.split("/").pop()));
    return sendJson(route, { deleted: true });
  }

  unexpectedApi.push(`${method} ${path}`);
  return sendJson(route, { detail: `Unexpected mock API request: ${method} ${path}` }, 404);
}

async function bridgeMock(route) {
  const request = route.request();
  const method = request.method();
  const url = new URL(request.url());
  const path = url.pathname;
  if (method === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders(request.headers().origin || BASE_URL), body: "" });
    return;
  }
  if (method !== "GET" && method !== "POST") return sendJson(route, { detail: "Method not mocked" }, 405);

  if (path === "/health") return sendJson(route, { status: "healthy", service: "local_device_bridge", bind: "127.0.0.1:8765", adb: true, fastboot: true });
  if (path === "/devices/android") return sendJson(route, { devices: [{ serial: "E2E-ANDROID-001", state: "device", details: ["product:test"] }] });
  if (path === "/devices/fastboot") return sendJson(route, { devices: [] });
  if (path === "/wifi/scan") return sendJson(route, { platform: "windows", source: "ui-smoke", networks: [{ ssid: "Smoke Wi-Fi", signal_percent: 79 }] });
  if (path === "/bluetooth/scan") return sendJson(route, { devices: [{ name: "Smoke BLE", address: "00:11:22:33", rssi: -51, distance_estimate_m: 1.3, distance_confidence: 55, direction: "UNKNOWN" }] });
  if (path === "/radio/status") return sendJson(route, { status: "READY", receive_only: true, scan_status: "NOT_IMPLEMENTED", detected_signals: [], note: "Mock status only." });
  if (path === "/radar/scan") {
    radarScanRequests += 1;
    return sendJson(route, {
      status: "READY",
      findings: [{ type: "wifi", label: "Smoke Wi-Fi", signal: 79, source: "ui-smoke" }, { type: "bluetooth", label: "Smoke BLE", signal: -51, source: "ui-smoke", distance_estimate_m: 1.3, distance_confidence: 55, direction: "UNKNOWN" }],
      sensor_status: {
        wifi: { status: "SCANNED", count: 1 }, bluetooth: { status: "SCANNED", count: 1 },
        android: { status: "SCANNED", count: 1 }, fastboot: { status: "SCANNED", count: 0 },
        radio: { status: "READY", scan_status: "NOT_IMPLEMENTED" },
      },
      counts: { total: 2, wifi: 1, bluetooth: 1, android: 1, fastboot: 0 },
    });
  }
  if (/^\/devices\/[^/]+\/info$/.test(path)) return sendJson(route, { serial: "E2E-ANDROID-001", model: "Test Device", brand: "MR AI", android_version: "15", sdk: "35", security_patch: "2026-01-01" });
  if (/^\/devices\/[^/]+\/diagnostics$/.test(path)) return sendJson(route, { serial: "E2E-ANDROID-001", adb_state: "device", battery: "level: 99", storage: "mock storage" });
  if (/^\/devices\/[^/]+\/boot-state$/.test(path)) return sendJson(route, { serial: "E2E-ANDROID-001", state: { "ro.boot.verifiedbootstate": "green" } });
  if (method === "POST" && /^\/devices\/[^/]+\/reboot$/.test(path)) {
    rebootRequests += 1;
    return sendJson(route, { serial: "E2E-ANDROID-001", mode: "system", result: "mock reboot only" });
  }

  return sendJson(route, { detail: `Unexpected mock bridge request: ${method} ${path}` }, 404);
}

async function waitForText(locator, expected, label) {
  await locator.waitFor({ state: "visible" });
  await locator.page().waitForFunction(
    ({ selector, expectedText }) => document.querySelector(selector)?.textContent?.includes(expectedText),
    { selector: await locator.evaluate(el => {
      // Derive a stable selector from the locator's class names for a concise diagnostic.
      const classes = [...el.classList].filter(Boolean);
      return classes.length ? "." + classes.join(".") : el.tagName.toLowerCase();
    }), expectedText: expected },
    { timeout: 7000 },
  ).catch(async () => {
    const actual = await locator.textContent();
    throw new Error(`${label}: expected "${expected}" but saw "${actual}"`);
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  await context.grantPermissions(["geolocation"], { origin: BASE_URL });
  await context.setGeolocation({ latitude: -6.7924, longitude: 39.2083, accuracy: 12 });
  await context.addInitScript(() => {
    localStorage.setItem("mr_ai_token", "ui-smoke-token-not-valid-outside-this-mocked-test");
    localStorage.setItem("mr_ai_mode", "normal");
    // Deterministic browser voice fixture: exercises command wiring without
    // requiring a physical microphone or depending on CI host speech services.
    class MockSpeechRecognition {
      constructor() {
        this.lang = "sw-TZ";
        this.interimResults = false;
        this.continuous = false;
        this.onstart = null;
        this.onend = null;
        this.onerror = null;
        this.onresult = null;
      }
      start() {
        this.onstart?.();
        window.setTimeout(() => {
          this.onresult?.({ results: [[{ transcript: "vip" }]] });
          this.onend?.();
        }, 25);
      }
      stop() { this.onend?.(); }
      abort() { this.onend?.(); }
    }
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: MockSpeechRecognition,
    });
  });
  await context.route("https://myaccount.google.com/**", route => route.fulfill({ status: 200, contentType: "text/html", body: "<title>Google account link smoke fixture</title>" }));
  await context.route("https://www.openstreetmap.org/**", route => route.fulfill({ status: 200, contentType: "text/html", body: "<title>OpenStreetMap iframe smoke fixture</title>" }));

  const page = await context.newPage();
  const consoleErrors = [];
  const failedResponses = [];
  page.on("pageerror", error => browserErrors.push(error.message));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("requestfailed", request => failedResponses.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText || "failed"}`));
  page.on("response", response => { if (response.status() >= 400) failedResponses.push(`HTTP ${response.status()} ${response.url()}`); });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route(`${API_ORIGIN}/**`, apiMock);
  await page.route("http://127.0.0.1:8765/**", bridgeMock);
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  try {
    await page.waitForFunction(
      () => document.querySelector(".sidebar nav button") !== null || document.querySelector(".auth-card") !== null,
      undefined,
      { timeout: 10000 },
    );
  } catch (error) {
    const dom = await page.locator("#root").innerHTML().catch(() => "(root missing)");
    throw new Error(`App did not render dashboard or auth screen. URL=${page.url()} title=${await page.title()} root=${dom.slice(0, 1600)} pageErrors=${JSON.stringify(browserErrors)} consoleErrors=${JSON.stringify(consoleErrors)} failedRequests=${JSON.stringify(failedResponses)}; original=${error.message}`);
  }
  // A stored smoke token is a convenience, not a precondition. If the app
  // starts at the login screen, authenticate through the same mocked API flow.
  if (!(await page.locator(".sidebar nav button").count())) {
    await page.getByLabel("Username").fill("qa-owner");
    await page.getByLabel("Password").fill("qa-password-only-for-smoke");
    await page.getByRole("button", { name: "ENTER COMMAND CENTER", exact: true }).click();
  }
  await page.waitForFunction(() => document.querySelector(".sidebar nav button") !== null, undefined, { timeout: 10000 });
  // Dashboard owns its HUD titlebar and intentionally hides the generic page topbar.
  await page.locator(".cc-titlebar").waitFor({ state: "visible", timeout: 15000 });
  await page.locator(".cc-system-footer").waitFor({ state: "visible", timeout: 7000 });
  await page.waitForFunction(() => {
    const footer = document.querySelector(".cc-system-footer")?.textContent || "";
    return footer.includes("ONLINE") && !footer.includes("WAITING");
  }, undefined, { timeout: 7000 });
  const executiveDetails = page.locator(".cc-executive-details");
  await executiveDetails.locator("summary").click();
  await executiveDetails.locator(".cc-exec-agent-crew").waitFor({ state: "visible", timeout: 7000 });
  assert.equal(await executiveDetails.locator(".cc-exec-agent-card").count(), 8,
    "The expanded Executive Briefing should show up to eight registered agent cards.");
  assert.ok(await executiveDetails.getByText("INASUBIRI KAZI", { exact: true }).count() > 0,
    "Registered agents without an active assignment must be clearly marked idle, not working.");
  await executiveDetails.locator("summary").click();
  completedChecks.push("executive briefing expands to a task-backed Agent Crew roster");
  assert.equal(radarScanRequests, 0, "After initial telemetry refresh completes, dashboard polling must not scan local sensor hardware.");
  const nav = page.locator(".sidebar nav button");
  assert.equal(await nav.count(), 16, "All 16 main navigation entries should render.");
  completedChecks.push("authenticated app startup + 16 main navigation controls");

  const destinations = [
    "Dashboard", "AI Core", "Agents", "Browser Hands", "Device Lab",
    "Creative Studio", "Tracking Map", "Security", "Toolbox", "Web Intelligence",
    "Job Research", "Gmail", "Schedules", "Tasks", "Memory", "Settings",
  ];
  async function waitForDestination(label) {
    if (label === "Dashboard") {
      await page.locator(".cc-titlebar").waitFor({ state: "visible", timeout: 7000 });
      return;
    }
    await page.waitForFunction(expected => document.querySelector(".topbar h1")?.textContent === expected, label, { timeout: 7000 });
  }

  async function goTo(label) {
    await page.locator(".sidebar nav button").filter({ hasText: label }).first().click();
    await waitForDestination(label);
  }
  for (const destination of destinations) await goTo(destination);
  completedChecks.push("all 16 navigation routes open the matching module");

  await goTo("Dashboard");
  await page.locator(".cc-system-status button").click();
  await page.locator(".cc-system-footer").waitFor({ state: "visible" });
  for (const [buttonLabel, expected] of [
    ["SCAN ALL", "ALL · COMPLETE"], ["WIFI SCAN", "WIFI · COMPLETE"],
    ["BLE SCAN", "BLUETOOTH · COMPLETE"], ["ANDROID SCAN", "ANDROID · COMPLETE"],
    ["FASTBOOT SCAN", "FASTBOOT · COMPLETE"], ["RADIO / RF", "RADIO · COMPLETE"],
    ["DATA LINK", "DATA · COMPLETE"],
  ]) {
    await page.locator(".cc-radar-controls button").filter({ hasText: buttonLabel }).click();
    await page.waitForFunction(expectedText => document.querySelector(".cc-radar-status span")?.textContent === expectedText, expected, { timeout: 7000 });
  }
  for (const label of ["SCAN SYSTEM", "ANALYZE DATA", "WEB RESEARCH", "GENERATE REPORT", "SECURITY CHECK", "OPTIMIZE"]) {
    await page.locator(".cc-quick-grid button").filter({ hasText: label }).click();
    await page.waitForFunction(expected => document.querySelector(".cc-quick-head strong")?.textContent?.includes(expected), label, { timeout: 7000 });
  }
  const dashboardSearch = page.locator(".cc-research-search input");
  await dashboardSearch.fill("MR AI smoke query");
  await dashboardSearch.press("Enter");
  await page.getByText("Smoke Search Result", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  const dashboardChatInput = page.locator(".cc-chat-panel .chat-input input");
  await dashboardChatInput.fill("Nisaidie kwa smoke test");
  await page.locator(".cc-chat-panel .chat-input > button").last().click();
  await page.locator(".cc-chat-panel .messages").getByText("E2E response from mocked API", { exact: true }).waitFor({ state: "visible", timeout: 7000 });

  const modeButton = page.locator(".sidebar-footer button").first();
  await modeButton.click();
  await page.locator(".sidebar-footer button").first().getByText("NORMAL MODE", { exact: true }).waitFor({ state: "visible" });
  await page.locator(".sidebar-footer button").first().click();
  const paletteTargets = [
    ["Open Dashboard", "Dashboard"], ["Open AI Core", "AI Core"], ["Open Agents", "Agents"],
    ["Open Browser Hands", "Browser Hands"], ["Open Device Lab", "Device Lab"],
    ["Open Creative Studio", "Creative Studio"], ["Open Tracking Map", "Tracking Map"],
    ["Open Security", "Security"], ["Open Toolbox", "Toolbox"], ["Open Web Intelligence", "Web Intelligence"],
    ["Open Job Research", "Job Research"], ["Open Gmail", "Gmail"], ["Open Schedules", "Schedules"], ["Open Tasks", "Tasks"],
    ["Open Memory", "Memory"], ["Open Settings", "Settings"],
  ];
  for (const [action, destination] of paletteTargets) {
    await page.keyboard.press("Control+k");
    await page.locator(".palette-actions button").filter({ hasText: action }).click();
    await waitForDestination(destination);
  }
  await page.keyboard.press("Control+k");
  await page.getByRole("button", { name: "ESC", exact: true }).click();
  await page.locator(".command-palette").waitFor({ state: "detached" });
  await page.keyboard.press("Control+k");
  await page.locator(".palette-actions button").filter({ hasText: "Toggle Working Mode" }).click();
  await page.locator(".sidebar-footer button").first().getByText("NORMAL MODE", { exact: true }).waitFor({ state: "visible" });
  await goTo("Dashboard");
  await page.locator(".cc-map-toolbar button").filter({ hasText: "OPEN MAP MODULE" }).click();
  await page.waitForFunction(() => document.querySelector(".topbar h1")?.textContent === "Tracking Map");
  await goTo("Dashboard");
  await page.getByRole("button", { name: "SLEEP SYSTEM", exact: true }).click();
  await page.getByRole("dialog", { name: "MR AI Sleep Mode" }).getByRole("button", { name: "WAKE MR AI" }).click();
  await page.getByRole("dialog", { name: "MR AI Sleep Mode" }).waitFor({ state: "detached" });
  completedChecks.push("dashboard telemetry, all radar scans, all six quick commands, search, chat, mode, palette and sleep/wake");

  await goTo("Dashboard");
  await page.locator(".sidebar-voice .voice-button").click();
  await page.waitForFunction(() => document.querySelector(".top-status .mode-label")?.textContent.includes("WORKING MODE"), undefined, { timeout: 5000 });
  await page.locator(".sidebar-footer button").filter({ hasText: "NORMAL MODE" }).click();
  await page.waitForFunction(() => document.querySelector(".top-status .mode-label")?.textContent.includes("NORMAL MODE"), undefined, { timeout: 5000 });
  completedChecks.push("sidebar voice control emits a recognized VIP command and normal-mode reset");

  await goTo("AI Core");
  const runtimeStateLabels = page.locator(".state-grid > span");
  await page.waitForFunction(() => document.querySelector(".state-grid .state-active") !== null, undefined, { timeout: 5000 });
  assert.equal(await runtimeStateLabels.count(), 6,
    "AI Core exposes only backend lifecycle states and derived working/sleep states.");
  assert.equal(await page.locator(".state-grid button").count(), 0,
    "AI runtime state must not be user-editable simulation controls.");
  for (const state of ["IDLE", "THINKING", "SPEAKING", "WORKING", "ERROR", "SLEEPING"]) {
    assert.equal(await runtimeStateLabels.filter({ hasText: new RegExp("^" + state + "$") }).count(), 1,
      `AI Core state indicator ${state} is visible.`);
  }
  assert.equal(await runtimeStateLabels.filter({ hasText: /^LISTENING$/ }).count(), 0,
    "LISTENING must not be presented as live until voice input is connected.");
  await page.locator(".chat-panel select").selectOption("mistral");
  const coreInput = page.locator(".chat-panel .chat-input input");
  await coreInput.fill("Nipe taarifa za mfumo");
  await page.locator(".chat-panel .chat-input > button").last().click();
  await page.locator(".chat-panel .messages").getByText("E2E response from mocked API", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("AI Core state selector, provider selector and chat send");

  await coreInput.fill("Timeout regression test");
  await page.locator(".chat-panel .chat-input > button").last().click();
  try {
    await page.locator(".chat-panel .messages").getByText("Delayed chat response confirmed", { exact: true }).waitFor({ state: "visible", timeout: 25000 });
  } catch (error) {
    const currentMessages = await page.locator(".chat-panel .messages").innerText().catch(() => "(messages unavailable)");
    throw new Error(`Delayed chat regression failed. delayedRequests=${delayedChatRequests}; requestBodies=${JSON.stringify(delayedChatRequestBodies)}; messages=${JSON.stringify(currentMessages)}; consoleErrors=${JSON.stringify(consoleErrors)}; failedResponses=${JSON.stringify(failedResponses)}; original=${error.message}`);
  }
  assert.equal(delayedChatRequests, 1, "The typed timeout-regression message should reach /ai/chat exactly once.");
  assert.equal(delayedChatRequestBodies.at(-1)?.message, "Timeout regression test", "The SEND button must submit the actual typed message, not a React click event.");
  completedChecks.push("AI Core SEND submits typed text and accepts a response delayed beyond 12 seconds");

  await goTo("Agents");
  const missionInput = page.locator(".agent-planner-form input");
  await missionInput.fill("Kagua afya ya mfumo wa MR AI");
  await page.locator(".agent-planner-form button").filter({ hasText: "PANGA KAZI" }).click();
  const planOutput = page.locator(".agent-result-plan").first();
  await planOutput.waitFor({ state: "visible", timeout: 7000 });
  const planText = await planOutput.innerText();
  assert.match(planText, /MR AI Orchestrator/, "System-health plan should route to the Orchestrator.");
  assert.doesNotMatch(planText, /Research Agent/, "System-health plan should not add an unrelated Research Agent.");
  await page.locator(".agent-planner-form button").filter({ hasText: "ANZA KAZI" }).click();
  await page.locator(".agent-result-run .agent-result-step-state").filter({ hasText: "IMEKAMILIKA" }).first().waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("Mission Planner PANGA KAZI + ANZA KAZI path; health plan contains Orchestrator only");

  await goTo("Browser Hands");
  const hands = page.locator(".tool-panel");
  for (const label of ["READ PAGE", "SCROLL DOWN", "SCROLL UP"]) {
    await hands.getByRole("button", { name: label, exact: true }).click();
    await hands.locator(".tool-status").last().getByText(/✕/).waitFor({ state: "visible", timeout: 3000 });
  }
  await hands.locator('input[placeholder="https://..."]').fill("https://example.com/");
  await hands.getByRole("button", { name: "OPEN", exact: true }).click();
  await hands.locator(".tool-status").last().getByText(/✕/).waitFor({ state: "visible", timeout: 3000 });
  await hands.locator('input[placeholder*="CSS selector"]').fill("button.safe");
  await hands.getByRole("button", { name: "CLICK", exact: true }).click();
  await hands.locator(".tool-status").last().getByText(/✕/).waitFor({ state: "visible", timeout: 3000 });
  await hands.locator('input[placeholder="Text to type"]').fill("test value");
  await hands.getByRole("button", { name: "TYPE", exact: true }).click();
  await hands.locator(".tool-status").last().getByText(/✕/).waitFor({ state: "visible", timeout: 3000 });
  await hands.locator('input[placeholder="dx"]').fill("10");
  await hands.locator('input[placeholder="dy"]').fill("5");
  await hands.getByRole("button", { name: "DRAG", exact: true }).click();
  await hands.locator(".tool-status").last().getByText(/✕/).waitFor({ state: "visible", timeout: 3000 });
  completedChecks.push("Browser Hands action handlers and clear missing-extension errors");

  await goTo("Device Lab");
  const deviceLab = page.locator(".tool-panel");
  await deviceLab.locator('input[type="password"]').fill("ui-smoke-bridge-token");
  await deviceLab.getByRole("button", { name: "SAVE", exact: true }).click();
  await page.evaluate(() => {
    window.__mraiConfirmationMessages = [];
    window.__mraiConfirmationResult = true;
    window.confirm = message => {
      window.__mraiConfirmationMessages.push(String(message || ""));
      return window.__mraiConfirmationResult;
    };
  });
  const deviceCases = [
    { button: "BRIDGE", resultLabel: "BRIDGE", outcome: "COMPLETED" },
    { button: "ADB DEVICES", resultLabel: "ANDROID", outcome: "COMPLETED" },
    { button: "FASTBOOT", resultLabel: "FASTBOOT", outcome: "COMPLETED" },
    { button: "WI-FI SCAN", resultLabel: "WI-FI", outcome: "COMPLETED" },
    { button: "BLE SCAN", resultLabel: "BLUETOOTH", outcome: "COMPLETED" },
    { button: "RADIO / RF", resultLabel: "RADIO / RF", outcome: "UNVERIFIED" },
    { button: "RADAR SCAN", resultLabel: "RADAR", outcome: "COMPLETED" },
  ];
  for (const testCase of deviceCases) {
    const promptsBefore = await page.evaluate(() => window.__mraiConfirmationMessages.length);
    await deviceLab.getByRole("button", { name: testCase.button, exact: true }).click();
    await page.waitForFunction(
      expected => document.querySelector(".device-result > strong")?.textContent?.startsWith(expected),
      testCase.resultLabel + ": " + testCase.outcome,
      { timeout: 7000 }
    );
    const promptsAfter = await page.evaluate(() => window.__mraiConfirmationMessages.length);
    assert.equal(promptsAfter, promptsBefore + 1,
      `Device Lab action ${testCase.button} must ask Boss for one explicit confirmation.`);
  }
  for (const testCase of [
    { button: "DEVICE INFO", resultLabel: "INFO" },
    { button: "DIAGNOSTICS", resultLabel: "DIAGNOSTICS" },
    { button: "BOOT STATE", resultLabel: "BOOT STATE" },
  ]) {
    const promptsBefore = await page.evaluate(() => window.__mraiConfirmationMessages.length);
    await deviceLab.getByRole("button", { name: testCase.button, exact: true }).click();
    await page.waitForFunction(
      expected => document.querySelector(".device-result > strong")?.textContent?.startsWith(expected),
      testCase.resultLabel + ": COMPLETED",
      { timeout: 7000 }
    );
    assert.equal(await page.evaluate(() => window.__mraiConfirmationMessages.length), promptsBefore + 1,
      `Device Lab action ${testCase.button} must ask Boss for one explicit confirmation.`);
  }
  const rebootCountBefore = rebootRequests;
  await page.evaluate(() => { window.__mraiConfirmationMessages = []; window.__mraiConfirmationResult = false; });
  await deviceLab.getByRole("button", { name: "REBOOT SYSTEM", exact: true }).click();
  assert.equal(rebootRequests, rebootCountBefore, "Dismissing reboot confirmation must not call the bridge.");
  assert.equal(await page.evaluate(() => window.__mraiConfirmationMessages.length), 1,
    "A rejected reboot must ask for explicit owner confirmation.");
  await page.evaluate(() => { window.__mraiConfirmationMessages = []; window.__mraiConfirmationResult = true; });
  await deviceLab.getByRole("button", { name: "REBOOT SYSTEM", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".device-result > strong")?.textContent?.includes("REBOOT: UNVERIFIED"));
  assert.equal(await page.evaluate(() => window.__mraiConfirmationMessages.length), 2,
    "Reboot action and Device Lab each request explicit confirmation.");
  assert.equal(rebootRequests, rebootCountBefore + 1, "Accepting both Boss confirmations should call the bridge.");
  completedChecks.push("Device Lab save, sensors, device info, diagnostics, boot state and guarded reboot (mock bridge)");

  await goTo("Creative Studio");
  await page.locator('input[placeholder="Title"]').fill("E2E CREATIVE TITLE");
  await page.locator('input[placeholder="Subtitle"]').fill("E2E editable subtitle");
  assert.equal(await page.locator('input[placeholder="Title"]').inputValue(), "E2E CREATIVE TITLE");
  await page.locator('input[type="color"]').fill("#112233");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "EXPORT PNG", exact: true }).click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "mr-ai-design.png");
  completedChecks.push("Creative Studio editable text, colour control and PNG export");

  await goTo("Tracking Map");
  await page.getByRole("button", { name: "LOCATE ONCE", exact: true }).click();
  await page.getByText("LOCATION VERIFIED · FOLLOW OFF", { exact: false }).waitFor({ state: "visible", timeout: 7000 });
  const streetLink = page.getByRole("link", { name: /OPEN STREET VIEW/ });
  assert.ok((await streetLink.getAttribute("href"))?.includes("-6.7924"), "Street View link should be based on the verified test GPS coordinate.");
  await page.getByRole("button", { name: /START LIVE TRACKING/ }).click();
  await page.getByRole("button", { name: "STOP TRACKING", exact: false }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByRole("button", { name: "STOP TRACKING", exact: false }).click();
  await page.getByText("LOCATION VERIFIED · FOLLOW PAUSED", { exact: false }).waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("Tracking Map GPS permission, locate-once, live tracking start/stop and real Street View link");

  await goTo("Security");
  const securityButton = page.locator(".security-grid .security-card button").first();
  const popupPromise = context.waitForEvent("page");
  await securityButton.click();
  const popup = await popupPromise;
  assert.match(popup.url(), /^https:\/\/myaccount\.google\.com\//, "Security OPEN button should launch the official Google account page.");
  await popup.close();
  completedChecks.push("Security external-link button opens its intended official destination");

  await goTo("Toolbox");
  await page.locator('.toolbox-panel input[placeholder*="Search through configured SearXNG"]').fill("test query");
  await page.locator(".toolbox-panel .tool-search button").click();
  await page.getByText("Smoke Search Result", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("Toolbox registry load and web search");

  await goTo("Web Intelligence");
  await page.locator('.web-intelligence-panel input[placeholder*="latest AI tools"]').fill("E2E search");
  await page.locator(".web-intelligence-panel .tool-search-row button").first().click();
  await page.getByText("Smoke Search Result", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.locator('.web-intelligence-panel input[placeholder="https://example.com"]').fill("https://example.com/");
  await page.locator(".web-intelligence-panel .tool-search-row button").nth(1).click();
  await page.getByText(/Browser Hands extension not detected/).waitFor({ state: "visible", timeout: 5000 });
  completedChecks.push("Web Intelligence search results and explicit Browser Hands integration error");

  await goTo("Job Research");
  await page.locator('input[placeholder*="Python developer"]').fill("Python developer");
  await page.getByRole("button", { name: "SEARCH JOBS", exact: true }).click();
  await page.getByText("Python Developer", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByRole("button", { name: "SAVE TO TASKS", exact: true }).click();
  await page.getByRole("button", { name: /SAVED · #/ }).waitFor({ state: "visible", timeout: 7000 });
  await page.locator(".job-results select").first().selectOption("APPLIED");
  await page.locator('.job-results input[type="url"]').first().fill("https://example.com/application/123");
  await page.getByRole("button", { name: "SAVE STATUS", exact: true }).click();
  await page.getByText(/TRACKING SAVED · #\d+ · APPLIED/).waitFor({ state: "visible", timeout: 7000 });
  await page.getByText("OWNER CONFIRMED", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByText("EVIDENCE LINK NOT CHECKED", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  // Verify that tracking lives in task storage rather than only in component state.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector(".sidebar nav button") !== null, undefined, { timeout: 10000 });
  await page.locator(".cc-titlebar").waitFor({ state: "visible", timeout: 15000 });
  await goTo("Job Research");
  await page.locator('input[placeholder*="Python developer"]').fill("Python developer");
  await page.getByRole("button", { name: "SEARCH JOBS", exact: true }).click();
  await page.getByText("Python Developer", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByRole("button", { name: /SAVED · #/ }).waitFor({ state: "visible", timeout: 7000 });
  assert.equal(await page.locator(".job-results select").first().inputValue(), "APPLIED", "Saved job application status should restore after reload.");
  assert.equal(await page.locator('.job-results input[type="url"]').first().inputValue(), "https://example.com/application/123", "Saved evidence URL should restore after reload.");
  await page.getByText("EVIDENCE LINK NOT CHECKED", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("Job Research task persistence, reload restoration, and honest evidence labeling");

  await goTo("Gmail");
  await page.getByRole("button", { name: "CONNECT GMAIL", exact: true }).waitFor({ state: "visible" });
  assert.equal(await page.getByRole("button", { name: "CONNECT GMAIL", exact: true }).isDisabled(), true, "Gmail connect must remain disabled when OAuth is not configured.");
  assert.equal(await page.getByRole("button", { name: "SEARCH", exact: true }).isDisabled(), true, "Gmail search must remain disabled until authorized.");
  completedChecks.push("Gmail displays the unconfigured OAuth state and prevents unavailable actions");

  await goTo("Schedules");
  await page.locator('input[placeholder="Schedule title"]').fill("E2E schedule");
  await page.locator('input[placeholder="Command to queue when due"]').fill("Smoke-test scheduled action");
  await page.locator('input[type="datetime-local"]').fill("2026-12-01T12:00");
  await page.getByRole("button", { name: "CREATE SCHEDULE", exact: true }).click();
  const scheduleRow = page.locator(".schedule-row").filter({ hasText: "E2E schedule" });
  await scheduleRow.waitFor({ state: "visible", timeout: 7000 });
  await scheduleRow.getByRole("button", { name: "PAUSE", exact: true }).click();
  await scheduleRow.getByRole("button", { name: "RESUME", exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await scheduleRow.getByRole("button", { name: "RUN NOW", exact: true }).click();
  await scheduleRow.getByRole("button", { name: "DELETE", exact: true }).click();
  await scheduleRow.waitFor({ state: "detached", timeout: 7000 });
  completedChecks.push("Schedules create, pause, resume, run-now and delete controls");

  await goTo("Tasks");
  await page.locator("#task-center-title").fill("E2E persistent task");
  await page.getByRole("button", { name: "CREATE TASK", exact: true }).click();
  await page.locator(".task-center-row").filter({ hasText: "E2E persistent task" }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByRole("button", { name: "REFRESH", exact: true }).click();
  await page.getByRole("button", { name: "OPEN MISSION PLANNER", exact: true }).click();
  await page.waitForFunction(() => document.querySelector(".topbar h1")?.textContent === "Agents");
  completedChecks.push("Tasks create, refresh and link to Mission Planner");

  await goTo("Memory");
  await page.locator("#memory-center-key").fill("e2e_memory");
  await page.locator("#memory-center-value").fill("Initial value for UI smoke");
  await page.getByRole("button", { name: "SAVE MEMORY", exact: true }).click();
  const memoryRow = page.locator(".memory-center-row").filter({ hasText: "e2e_memory" });
  await memoryRow.waitFor({ state: "visible", timeout: 7000 });
  await memoryRow.getByRole("button", { name: "EDIT", exact: true }).click();
  await memoryRow.getByRole("textbox", { name: "Edit e2e_memory" }).fill("Updated value from UI smoke");
  await memoryRow.getByRole("button", { name: "SAVE", exact: true }).click();
  await page.getByText("MEMORY UPDATED", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  page.on("dialog", dialog => dialog.accept());
  await memoryRow.getByRole("button", { name: "DELETE", exact: true }).click();
  await memoryRow.waitFor({ state: "detached", timeout: 7000 });
  completedChecks.push("Memory create, search-ready list, edit, save and delete controls");

  await goTo("Settings");
  await page.getByRole("button", { name: "RUN SELF-CHECK", exact: true }).click();
  await page.getByText(/CONFIGURATION_CHECKED/).waitFor({ state: "visible", timeout: 7000 });
  await page.getByText("Persistent database", { exact: true }).waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("Settings self-check reports explicit diagnostic evidence");
  await page.getByText("database", { exact: false }).first().waitFor({ state: "visible" });
  await page.getByText(/Verified Service State/).first().waitFor({ state: "visible" });
  await page.getByRole("button", { name: "REFRESH STATUS", exact: true }).click();
  const snapshotDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "EXPORT SNAPSHOT", exact: true }).click();
  const snapshotDownload = await snapshotDownloadPromise;
  assert.equal(snapshotDownload.suggestedFilename(), "mr-ai-runtime-snapshot.json");
  completedChecks.push("Settings service state, refresh and runtime snapshot export");

  await page.setViewportSize({ width: 390, height: 844 });
  await goTo("Dashboard");
  const layoutReport = await page.evaluate(() => {
    const viewport = window.innerWidth;
    const elements = [...document.querySelectorAll("body *")].map(element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        tag: element.tagName.toLowerCase(),
        id: element.id || "",
        className: typeof element.className === "string" ? element.className.slice(0, 100) : "",
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        scrollWidth: element.scrollWidth,
        overflowX: style.overflowX,
        ancestors: (() => {
          const output = [];
          let parent = element.parentElement;
          for (let depth = 0; parent && depth < 5; depth += 1, parent = parent.parentElement) {
            const box = parent.getBoundingClientRect();
            output.push({
              tag: parent.tagName.toLowerCase(),
              className: typeof parent.className === "string" ? parent.className.slice(0, 70) : "",
              left: Math.round(box.left),
              right: Math.round(box.right),
              width: Math.round(box.width),
              overflowX: getComputedStyle(parent).overflowX,
            });
          }
          return output;
        })(),
      };
    }).filter(item => item.width > 0 && (item.left < -4 || item.right > viewport + 4))
      .sort((a, b) => b.right - a.right)
      .slice(0, 35);
    return { viewport, document: document.documentElement.scrollWidth, offenders: elements };
  });
  if (layoutReport.document > layoutReport.viewport + 12) {
    console.error("MOBILE_OVERFLOW_REPORT " + JSON.stringify(layoutReport));
  }
  assert.ok(layoutReport.document <= layoutReport.viewport + 12,
    `Mobile layout has horizontal overflow: viewport=${layoutReport.viewport}px, document=${layoutReport.document}px`);
  const mobilePresentation = await page.evaluate(() => {
    const sidebar = document.querySelector(".app-shell .sidebar");
    const brand = document.querySelector(".app-shell .sidebar .brand");
    const nav = document.querySelector(".app-shell .sidebar nav");
    const footerButtons = [...document.querySelectorAll(".app-shell .sidebar-footer button")];
    return {
      brandVisible: !!brand && getComputedStyle(brand).display !== "none" && brand.getBoundingClientRect().height > 0,
      sidebarWithinViewport: !!sidebar && sidebar.getBoundingClientRect().width <= window.innerWidth,
      horizontalNav: !!nav && getComputedStyle(nav).overflowX === "auto" && nav.scrollWidth > nav.clientWidth,
      footerButtons: footerButtons.length,
      footerTouchTargets: footerButtons.map(button => Math.round(button.getBoundingClientRect().height)),
    };
  });
  assert.ok(mobilePresentation.brandVisible, "Mobile Command Center should show the MR AI identity header.");
  assert.ok(mobilePresentation.sidebarWithinViewport, "Mobile navigation must fit the viewport width.");
  assert.ok(mobilePresentation.horizontalNav, "Mobile navigation should be a horizontal swipe rail rather than a tall desktop menu.");
  assert.equal(mobilePresentation.footerButtons, 3, "Working mode, sleep and disconnect controls must remain available on mobile.");
  assert.ok(mobilePresentation.footerTouchTargets.every(height => height >= 36),
    `Mobile sidebar actions must remain touch-friendly: ${JSON.stringify(mobilePresentation.footerTouchTargets)}`);
  const voiceControlCount = await page.locator(".sidebar-voice .voice-button, .sidebar-voice .voice-disabled").count();
  assert.ok(voiceControlCount > 0, "Voice control should either be actionable or explain that the browser API is unavailable.");
  await page.getByRole("button", { name: "DISCONNECT SESSION", exact: true }).click();
  await page.getByRole("heading", { name: "Command access", exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByRole("button", { name: "Create a new operator account", exact: true }).click();
  await page.getByRole("heading", { name: "Create operator", exact: true }).waitFor({ state: "visible", timeout: 3000 });
  await page.getByRole("button", { name: "Back to login", exact: true }).click();
  await page.getByRole("heading", { name: "Command access", exact: true }).waitFor({ state: "visible", timeout: 3000 });
  await page.getByRole("button", { name: "Create a new operator account", exact: true }).click();
  await page.getByLabel("Username").fill("qa-new-owner");
  await page.getByLabel("Password").fill("qa-registration-password");
  await page.getByRole("button", { name: "CREATE & ENTER", exact: true }).click();
  await page.locator(".sidebar nav button").first().waitFor({ state: "visible", timeout: 7000 });
  await page.getByRole("button", { name: "DISCONNECT SESSION", exact: true }).click();
  await page.getByRole("heading", { name: "Command access", exact: true }).waitFor({ state: "visible", timeout: 7000 });
  await page.getByLabel("Username").fill("qa-owner");
  await page.getByLabel("Password").fill("qa-password-only-for-smoke");
  await page.getByRole("button", { name: "ENTER COMMAND CENTER", exact: true }).click();
  await page.locator(".sidebar nav button").first().waitFor({ state: "visible", timeout: 7000 });
  completedChecks.push("mobile viewport, voice availability, disconnect, auth mode toggle, registration and login submission flows");

  assert.deepEqual(unexpectedApi, [], `Unexpected frontend API calls: ${unexpectedApi.join(", ")}`);
  assert.deepEqual(browserErrors, [], `Unhandled browser errors: ${browserErrors.join(" | ")}`);
  console.log(`PASS: ${completedChecks.length} UI smoke groups`);
  for (const check of completedChecks) console.log(`  ✓ ${check}`);
  console.log("NOTE: integrations that need credentials, a physical Android device, microphone access or an installed Browser Hands extension are mocked or reported as unavailable; this test does not claim those external resources are configured.");
  await browser.close();
}

main().catch(error => {
  console.error(error);
  // Close all browser child processes even when an assertion fails, so CI cannot hang.
  process.exit(1);
});
