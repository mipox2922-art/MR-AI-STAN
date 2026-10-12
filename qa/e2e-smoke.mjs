import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "playwright";

const qaDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(qaDir, "..");
const webDir = path.join(repoRoot, "web");
const origin = "http://127.0.0.1:4173";
const apiBase = origin + "/__api";
const bridgeBase = "http://127.0.0.1:8765";
const failures = [];
const passed = [];
const calls = [];
let server;

const agents = [
  ["orchestrator", "MR AI Orchestrator", "LOW"],
  ["research", "Research Agent", "LOW"],
  ["browser", "Browser Agent", "MEDIUM"],
  ["gmail", "Gmail Agent", "MEDIUM"],
  ["jobs", "Job Research Agent", "MEDIUM"],
  ["coding", "Coding Agent", "MEDIUM"],
  ["creative", "Creative Studio Agent", "LOW"],
  ["device", "Device Lab Agent", "HIGH"],
  ["security", "Security Agent", "HIGH"],
  ["memory", "Memory Agent", "LOW"],
  ["scheduler", "Scheduler Agent", "MEDIUM"],
].map(([id, name, risk]) => ({
  id, name, risk,
  description: name + " test specialist",
  capabilities: ["test", "verify"],
  tools: ["test_tool"],
}));

const systemSnapshot = {
  status: "ONLINE",
  services: {
    ai_core: "READY", database: "ONLINE", memory: "ONLINE", web_app: "ONLINE",
    agents: "ONLINE", extension: "NOT_CONNECTED", gmail: "NOT_CONFIGURED",
    openrouter: "CONFIGURED", gemini: "NOT_CONFIGURED", kimi: "NOT_CONFIGURED",
    mistral: "NOT_CONFIGURED", grok: "NOT_CONFIGURED",
  },
  telemetry: {
    cpu_percent: 24.5, memory_percent: 57.2, storage_percent: 78.1,
    network: { bytes_sent: 20480, bytes_received: 40960 },
    gpu: { utilization_percent: null }, uptime_seconds: 123456,
    source: "host_runtime",
  },
  ai: { model: "openrouter/free", tier: "OPENROUTER_FREE", ready: true },
};

let tasks = [{
  id: 41, title: "Existing test task", description: "Seeded QA task",
  status: "PENDING", progress: 0, priority: "NORMAL",
  agent: "orchestrator", created_at: "2026-10-12T12:00:00Z",
  updated_at: "2026-10-12T12:00:00Z", result: null, error: null,
}];
let memories = [{
  id: 11, key: "preferred_language", value: "Kiswahili",
  created_at: "2026-10-12T12:00:00Z", updated_at: "2026-10-12T12:00:00Z",
}];
let schedules = [];
let nextTaskId = 42;
let nextMemoryId = 12;
let nextScheduleId = 21;

function json(route, payload, status = 200, extraHeaders = {}) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: extraHeaders,
    body: JSON.stringify(payload),
  });
}

async function mockApi(route) {
  const request = route.request();
  const url = new URL(request.url());
  const method = request.method();
  const routePath = url.pathname.replace(/^\/__api/, "") || "/";
  calls.push({ method, path: routePath });

  const body = () => request.postDataJSON?.() || {};
  const taskMatch = routePath.match(/^\/tasks\/(\d+)$/);
  const memoryMatch = routePath.match(/^\/memory\/(\d+)$/);
  const scheduleMatch = routePath.match(/^\/scheduler\/(\d+)(?:\/(run-now))?$/);

  if (method === "GET" && routePath === "/auth/status") return json(route, { setup_required: false });
  if (method === "POST" && routePath === "/auth/login") return json(route, { access_token: "qa-fake-token", token_type: "bearer" });
  if (method === "POST" && routePath === "/auth/register") return json(route, { access_token: "qa-fake-token", token_type: "bearer" });
  if (method === "GET" && routePath === "/system/status") return json(route, systemSnapshot);
  if (method === "GET" && routePath === "/agents") return json(route, agents);
  if (method === "POST" && routePath === "/agents/plan") {
    const requestText = body().request || "";
    const selected = /system|mfumo|afya/i.test(requestText) ? [agents[0]] : [agents[0], agents[1]];
    return json(route, {
      request: requestText, status: "PLANNED",
      agents: selected.map(item => item.name),
      steps: selected.map((item, index) => ({ step: index + 1, agent: item.id, name: item.name, status: "PLANNED", tools: item.tools, risk: item.risk })),
      verification: ["Verify execution evidence"],
    });
  }
  if (method === "POST" && routePath === "/agents/mission") {
    const requestText = body().request || "";
    return json(route, {
      status: "COMPLETED",
      mission: { id: 77, title: requestText, status: "COMPLETED", progress: 100, agent: "orchestrator", result: "QA: 1 completed, 0 waiting", error: null },
      plan: { request: requestText, status: "PLANNED", agents: [agents[0].name], steps: [{ step: 1, agent: "orchestrator", name: agents[0].name, status: "PLANNED", tools: ["system_telemetry"] }] },
      steps: [{ step: 1, agent: "orchestrator", tool: "system_telemetry", status: "COMPLETED", verified: true, evidence: systemSnapshot }],
      next_action: "Mission verified complete.",
    });
  }
  if (method === "GET" && routePath === "/tasks") return json(route, tasks);
  if (method === "POST" && routePath === "/tasks") {
    const data = body();
    const item = { id: nextTaskId++, title: data.title, description: data.description || "", status: "PENDING", progress: 0, priority: data.priority || "NORMAL", agent: data.agent || null, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), result: null, error: null };
    tasks.unshift(item);
    return json(route, item, 201);
  }
  if (method === "PATCH" && taskMatch) {
    const item = tasks.find(task => task.id === Number(taskMatch[1]));
    if (!item) return json(route, { detail: "Task not found" }, 404);
    Object.assign(item, body(), { updated_at: new Date().toISOString() });
    return json(route, item);
  }
  if (method === "GET" && routePath === "/memory") return json(route, memories);
  if (method === "GET" && routePath === "/memory/search") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    return json(route, memories.filter(item => (item.key + " " + item.value).toLowerCase().includes(q)));
  }
  if (method === "POST" && routePath === "/memory") {
    const data = body();
    const now = new Date().toISOString();
    const item = { id: nextMemoryId++, key: data.key, value: data.value, created_at: now, updated_at: now };
    memories.unshift(item);
    return json(route, item, 201);
  }
  if (method === "PUT" && memoryMatch) {
    const item = memories.find(memory => memory.id === Number(memoryMatch[1]));
    if (!item) return json(route, { detail: "Memory not found" }, 404);
    item.value = body().value;
    item.updated_at = new Date().toISOString();
    return json(route, item);
  }
  if (method === "DELETE" && memoryMatch) {
    const oldLength = memories.length;
    memories = memories.filter(memory => memory.id !== Number(memoryMatch[1]));
    return json(route, { deleted: memories.length !== oldLength });
  }
  if (method === "GET" && routePath === "/activity") return json(route, []);
  if (method === "GET" && routePath === "/integrations/gmail/status") return json(route, { status: "NOT_CONFIGURED", configured: false, connected: false, scope: [] });
  if (method === "GET" && routePath === "/ai/history") return json(route, { messages: [] });
  if (method === "POST" && routePath === "/ai/chat") return json(route, { response: "MR AI QA response received.", provider: "openrouter", request_id: "qa-1" });
  if (method === "GET" && routePath === "/tools") return json(route, {
    total: 2, ready: 1, optional: 0, not_connected: 1,
    tools: [
      { id: "searxng", name: "SearXNG", category: "RESEARCH", status: "NOT_CONNECTED", description: "Mock search service", mode: "API", free: true },
      { id: "system_telemetry", name: "System Telemetry", category: "SYSTEM", status: "READY", description: "Mock runtime status", mode: "LOCAL", free: true },
    ],
  });
  if (method === "POST" && routePath === "/tools/search") return json(route, {
    status: "READY",
    results: [{ title: "MR AI QA Search Result", url: "https://example.com/qa", content: "Mock evidence for interaction tests.", engine: "mock" }],
  });
  if (method === "POST" && routePath === "/tools/dispatch") return json(route, { status: "COMPLETED", message: "Mock dispatch completed.", result: { telemetry: systemSnapshot.telemetry, services: systemSnapshot.services } });
  if (method === "POST" && routePath === "/tools/route") return json(route, { status: "ROUTED", route: { tool: "system_telemetry", agent: "orchestrator" }, result: { telemetry: systemSnapshot.telemetry } });
  if (method === "GET" && routePath === "/scheduler") return json(route, schedules);
  if (method === "POST" && routePath === "/scheduler") {
    const data = body();
    const item = { id: nextScheduleId++, title: data.title, command: data.command, status: "ACTIVE", run_at: data.run_at, next_run_at: data.run_at, interval_minutes: data.interval_minutes || null };
    schedules.unshift(item);
    return json(route, item, 201);
  }
  if (method === "PATCH" && scheduleMatch && !scheduleMatch[2]) {
    const item = schedules.find(job => job.id === Number(scheduleMatch[1]));
    if (!item) return json(route, { detail: "Schedule not found" }, 404);
    Object.assign(item, body());
    return json(route, item);
  }
  if (method === "POST" && scheduleMatch && scheduleMatch[2] === "run-now") {
    const item = schedules.find(job => job.id === Number(scheduleMatch[1]));
    if (!item) return json(route, { detail: "Schedule not found" }, 404);
    return json(route, { status: "QUEUED", schedule_id: item.id });
  }
  if (method === "DELETE" && scheduleMatch) {
    schedules = schedules.filter(job => job.id !== Number(scheduleMatch[1]));
    return json(route, { deleted: true });
  }
  return json(route, { detail: "No QA mock for " + method + " " + routePath }, 501);
}

async function mockBridge(route) {
  const request = route.request();
  const url = new URL(request.url());
  const pathName = url.pathname;
  calls.push({ method: request.method(), path: "BRIDGE " + pathName });
  if (pathName === "/health") return json(route, { status: "healthy", service: "local_device_bridge", bind: "127.0.0.1:8765", adb: true, fastboot: true });
  if (pathName === "/radar/scan") return json(route, {
    status: "READY",
    findings: [{ type: "wifi", label: "QA-NETWORK", signal: "82%", source: "QA MOCK" }],
    counts: { total: 1, wifi: 1, bluetooth: 0, android: 0, fastboot: 0 },
    sensor_status: {
      wifi: { status: "SCANNED", count: 1 },
      bluetooth: { status: "SCANNED", count: 0 },
      android: { status: "SCANNED", count: 0 },
      fastboot: { status: "SCANNED", count: 0 },
      radio: { status: "NO_SDR_TOOL", scan_status: "NOT_IMPLEMENTED" },
    },
  });
  if (pathName === "/devices/android") return json(route, { devices: [{ serial: "QA-ANDROID-001", state: "device", details: ["model:QA"] }] });
  if (pathName === "/devices/fastboot") return json(route, { devices: [{ serial: "QA-FASTBOOT-001", transport: "usb" }] });
  if (pathName === "/wifi/scan") return json(route, { platform: "windows", source: "QA MOCK", networks: [{ ssid: "QA-WIFI", signal_percent: "88" }] });
  if (pathName === "/bluetooth/scan") return json(route, { devices: [{ name: "QA BLE", address: "00:11:22:33:44:55", rssi: -58, distance_estimate_m: 1.2, distance_confidence: 65, direction: "UNKNOWN" }] });
  if (pathName === "/radio/status") return json(route, { receive_only: true, status: "NO_SDR_TOOL", scan_status: "NOT_IMPLEMENTED", detected_signals: [] });
  const deviceMatch = pathName.match(/^\/devices\/([^/]+)\/(info|diagnostics|boot-state|reboot)$/);
  if (deviceMatch) {
    if (deviceMatch[2] === "info") return json(route, { serial: deviceMatch[1], model: "QA Android", brand: "QA", android_version: "15", sdk: "35", security_patch: "2026-09-01" });
    if (deviceMatch[2] === "diagnostics") return json(route, { serial: deviceMatch[1], adb_state: "device", battery: "level: 88", storage: "64G total" });
    if (deviceMatch[2] === "boot-state") return json(route, { serial: deviceMatch[1], state: { "ro.boot.verifiedbootstate": "green" } });
    if (deviceMatch[2] === "reboot") return json(route, { serial: deviceMatch[1], mode: (request.postDataJSON?.() || {}).mode || "system", result: "QA reboot mocked; no real device rebooted." });
  }
  return json(route, { detail: "No QA mock for bridge path " + pathName }, 501);
}

async function waitForServer(child) {
  for (let i = 0; i < 80; i += 1) {
    if (child.exitCode !== null) throw new Error("Vite exited before starting.");
    try {
      const response = await fetch(origin);
      if (response.ok) return;
    } catch {}
    await delay(250);
  }
  throw new Error("Vite server did not start at " + origin);
}

async function check(name, fn) {
  try {
    await fn();
    passed.push(name);
    process.stdout.write("PASS  " + name + "\n");
  } catch (error) {
    failures.push({ name, error: error?.stack || String(error) });
    process.stderr.write("FAIL  " + name + " :: " + (error?.message || error) + "\n");
  }
}

async function navTo(page, label, expectedHeading = label) {
  const button = page.locator(".sidebar nav button").filter({ hasText: label }).first();
  await button.waitFor({ state: "visible" });
  await button.click();
  await page.waitForFunction(expected => {
    const heading = document.querySelector(".topbar h1");
    return heading && heading.textContent.trim() === expected;
  }, expectedHeading);
}

server = spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", "4173", "--strictPort"], {
  cwd: webDir,
  env: { ...process.env, VITE_API_URL: "/__api", VITE_BUILD_ID: "INTERACTION-QA" },
  stdio: "ignore",
});

let browser;
try {
  await waitForServer(server);
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    reducedMotion: "reduce",
    acceptDownloads: true,
  });
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: -6.8, longitude: 39.2, accuracy: 9 });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.route("**/__api/**", mockApi);
  await page.route("http://127.0.0.1:8765/**", mockBridge);
  await page.route("https://www.openstreetmap.org/**", route => route.fulfill({ status: 200, contentType: "text/html", body: "<html><body>QA map iframe mock</body></html>" }));
  await page.route("https://fonts.googleapis.com/**", route => route.abort());
  await page.route("https://fonts.gstatic.com/**", route => route.abort());

  await check("Authentication screen and login submission", async () => {
    await page.goto(origin);
    assert.match(await page.locator("h1").first().innerText(), /Command access/i);
    await page.getByLabel("Username").fill("qa-owner");
    await page.getByLabel("Password").fill("qa-test-password");
    await page.getByRole("button", { name: "ENTER COMMAND CENTER" }).click();
    await page.locator(".sidebar nav").waitFor({ state: "visible" });
    assert.equal(await page.locator(".topbar h1").innerText(), "Dashboard");
  });

  await check("All 15 sidebar destinations open the correct view", async () => {
    const pages = [
      ["Dashboard", ".command-center-reference"],
      ["AI Core", ".core-detail"],
      ["Agents", ".agent-grid"],
      ["Browser Hands", "text=AUTHORIZED PAGE CONTROL"],
      ["Device Lab", "text=AUTHORIZED DEVICE LAB"],
      ["Creative Studio", "text=CREATIVE STUDIO"],
      ["Tracking Map", ".cc-live-map-full-page"],
      ["Security", "text=Account Security Console"],
      ["Toolbox", "text=MR AI Toolbox"],
      ["Web Intelligence", "text=MR AI Web"],
      ["Gmail", "text=Gmail Command Channel"],
      ["Calendar", "text=Proactive Operations"],
      ["Tasks", "text=Durable Operations"],
      ["Memory", "text=User-approved memory"],
      ["Settings", "text=Verified Service State"],
    ];
    for (const [label, selector] of pages) {
      await navTo(page, label);
      await page.locator(selector).first().waitFor({ state: "visible" });
    }
    assert.equal(await page.locator(".sidebar nav button").count(), 15);
  });

  await check("Dashboard research, telemetry refresh, and all seven radar controls", async () => {
    await navTo(page, "Dashboard");
    const search = page.locator(".cc-research-search");
    await search.locator("input").fill("MR AI test research");
    await search.locator("button[type=submit]").click();
    await page.getByText("MR AI QA Search Result", { exact: true }).waitFor({ state: "visible" });

    await page.getByRole("button", { name: "REFRESH TELEMETRY" }).click();
    await page.getByText("CPU Usage · BACKEND", { exact: true }).waitFor({ state: "visible" });

    const radarButtons = ["SCAN ALL", "WIFI SCAN", "BLE SCAN", "ANDROID SCAN", "FASTBOOT SCAN", "RADIO / RF", "DATA LINK"];
    for (const label of radarButtons) {
      await page.locator(".cc-radar-controls button").filter({ hasText: label }).click();
      await page.waitForFunction(() => document.querySelector(".cc-radar-status")?.textContent.includes("COMPLETE"));
    }

    const quickLabels = ["SCAN SYSTEM", "ANALYZE DATA", "WEB RESEARCH", "GENERATE REPORT", "SECURITY CHECK", "OPTIMIZE"];
    for (const label of quickLabels) {
      await page.locator(".cc-quick-grid button").filter({ hasText: label }).click();
      await page.locator(".cc-quick-result").waitFor({ state: "visible" });
    }
  });

  await check("AI Core state controls and chat VIP shortcut", async () => {
    await navTo(page, "AI Core");
    for (const state of ["IDLE", "LISTENING", "THINKING", "SPEAKING", "WORKING", "BUSY", "ERROR", "SLEEPING"]) {
      const button = page.locator(".state-grid button").filter({ hasText: state });
      await button.click();
      assert(await button.evaluate(node => node.classList.contains("state-active")), state + " state was not selected");
    }
    await page.locator(".chat-input input").fill("vip");
    await page.locator(".chat-input button").click();
    await page.getByText(/VIP MODE ACTIVATED/, { exact: false }).waitFor({ state: "visible" });
    assert.match(await page.locator(".top-status").innerText(), /WORKING MODE/);
  });

  await check("Agent plan and mission execution controls return visible outcomes", async () => {
    await navTo(page, "Agents");
    await page.locator(".planner-row input").fill("Kagua afya ya mfumo wa MR AI");
    await page.locator(".planner-row button").filter({ hasText: "PLAN" }).click();
    await page.locator(".plan-output").first().waitFor({ state: "visible" });
    assert.match(await page.locator(".plan-output").first().innerText(), /MR AI Orchestrator/);
    await page.locator(".planner-row button").filter({ hasText: "RUN MISSION" }).click();
    await page.locator(".mission-output").waitFor({ state: "visible" });
    assert.match(await page.locator(".mission-output").innerText(), /COMPLETED/);
  });

  await check("Browser Hands surfaces clear extension errors for all six operations", async () => {
    await navTo(page, "Browser Hands");
    const actions = [
      ["READ PAGE", null],
      ["SCROLL DOWN", null],
      ["SCROLL UP", null],
      ["OPEN", "url"],
      ["CLICK", "selector"],
      ["TYPE", "type"],
      ["DRAG", "drag"],
    ];
    for (const [label, field] of actions) {
      if (field === "url") await page.getByPlaceholder("https://...").fill("https://example.com");
      if (field === "selector") await page.getByPlaceholder("CSS selector, e.g. button[type=submit]").fill("button[type=submit]");
      if (field === "type") await page.getByPlaceholder("Text to type").fill("qa typed text");
      if (field === "drag") {
        const numericInputs = page.locator(".tool-row input[inputmode=numeric]");
        await numericInputs.nth(0).fill("10");
        await numericInputs.nth(1).fill("5");
      }
      await page.locator(".tool-grid button, .tool-row button").filter({ hasText: label }).last().click();
      await page.waitForFunction(() => document.querySelectorAll(".tool-status").length >= 2 && document.querySelectorAll(".tool-status")[document.querySelectorAll(".tool-status").length - 1].textContent.includes("MR AI Browser Hands extension not detected"));
    }
  });

  await check("Device Lab bridge, ADB, Fastboot, Wi-Fi, BLE, radio, radar, and device actions", async () => {
    await navTo(page, "Device Lab");
    const actions = [
      ["BRIDGE", "BRIDGE: COMPLETED"],
      ["ADB DEVICES", "ANDROID: COMPLETED"],
      ["FASTBOOT", "FASTBOOT: COMPLETED"],
      ["WI-FI SCAN", "WI-FI: COMPLETED"],
      ["BLE SCAN", "BLUETOOTH: COMPLETED"],
      ["RADIO / RF", "RADIO / RF: COMPLETED"],
      ["RADAR SCAN", "RADAR: COMPLETED"],
    ];
    for (const [label, expected] of actions) {
      await page.locator(".tool-grid button").filter({ hasText: label }).first().click();
      await page.waitForFunction(expectedText => document.querySelector(".device-result strong")?.textContent.includes(expectedText), expected);
    }
    for (const [label, expected] of [
      ["DEVICE INFO", "INFO: COMPLETED"],
      ["DIAGNOSTICS", "DIAGNOSTICS: COMPLETED"],
      ["BOOT STATE", "BOOT STATE: COMPLETED"],
      ["REBOOT SYSTEM", "REBOOT: COMPLETED"],
    ]) {
      await page.locator(".tool-grid button").filter({ hasText: label }).click();
      await page.waitForFunction(expectedText => document.querySelector(".device-result strong")?.textContent.includes(expectedText), expected);
    }
    assert(calls.some(call => call.path === "BRIDGE /devices/android"));
  });

  await check("Creative Studio edits a layer and exports PNG", async () => {
    await navTo(page, "Creative Studio");
    await page.getByPlaceholder("Title").fill("QA VERIFIED DESIGN");
    await page.locator("canvas").waitFor({ state: "visible" });
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "EXPORT PNG" }).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), "mr-ai-design.png");
  });

  await check("Tracking Map GPS locate and live tracking start/stop", async () => {
    await navTo(page, "Tracking Map");
    await page.locator(".cc-map-toolbar button").filter({ hasText: "LOCATE ONCE" }).click();
    await page.waitForFunction(() => document.querySelector(".cc-map-state")?.textContent.includes("LOCATION VERIFIED"));
    assert.match(await page.locator(".cc-map-readout").innerText(), /-6\.80000/);
    await page.locator(".cc-map-track-button").click();
    await page.waitForFunction(() => document.querySelector(".cc-map-state")?.textContent.includes("LIVE TRACKING"));
    await page.locator(".cc-map-track-button").click();
    await page.waitForFunction(() => document.querySelector(".cc-map-state")?.textContent.includes("FOLLOW PAUSED"));
  });

  await check("All security links open", async () => {
    await navTo(page, "Security");
    const cards = page.locator(".security-card");
    assert.equal(await cards.count(), 3);
    const expected = ["myaccount.google.com/security-checkup", "myaccount.google.com/notifications", "mail.google.com"];
    for (let i = 0; i < 3; i += 1) {
      const popupPromise = context.waitForEvent("page");
      await cards.nth(i).getByRole("button", { name: "OPEN" }).click();
      const popup = await popupPromise;
      await popup.waitForLoadState("domcontentloaded").catch(() => {});
      assert((popup.url() || "").includes(expected[i]), "Unexpected security link URL: " + popup.url());
      await popup.close().catch(() => {});
    }
  });

  await check("Toolbox registry and search", async () => {
    await navTo(page, "Toolbox");
    await page.getByText("MR AI Toolbox", { exact: true }).waitFor({ state: "visible" });
    const search = page.locator(".tool-search-row");
    await search.locator("input").fill("Python automation");
    await search.locator("button").click();
    await page.getByText("MR AI QA Search Result", { exact: true }).waitFor({ state: "visible" });
  });

  await check("Web Intelligence search and authorized open-page error feedback", async () => {
    await navTo(page, "Web Intelligence");
    const searches = page.locator(".tool-search-row");
    await searches.nth(0).locator("input").fill("MR AI tools");
    await searches.nth(0).locator("button").click();
    await page.getByText("MR AI QA Search Result", { exact: true }).waitFor({ state: "visible" });
    await searches.nth(1).locator("input").fill("https://example.com");
    await searches.nth(1).locator("button").click();
    await page.getByText(/MR AI Browser Hands extension not detected/, { exact: false }).waitFor({ state: "visible" });
  });

  await check("Gmail reflects the missing OAuth setup without offering a false success", async () => {
    await navTo(page, "Gmail");
    assert.match(await page.locator(".gmail-connection-copy").innerText(), /OAuth client is not configured/i);
    assert(await page.getByRole("button", { name: "CONNECT GMAIL" }).isDisabled());
    assert(await page.getByRole("button", { name: "SEARCH" }).isDisabled());
  });

  await check("Calendar schedule create, pause, resume, run-now, and delete", async () => {
    await navTo(page, "Calendar");
    await page.getByPlaceholder("Schedule title").fill("QA recurring check");
    await page.getByPlaceholder("Command to queue when due").fill("check MR AI system health");
    await page.locator('input[type="datetime-local"]').fill("2026-10-13T10:00");
    await page.getByRole("button", { name: "CREATE SCHEDULE" }).click();
    await page.locator(".schedule-row").first().waitFor({ state: "visible" });
    await page.locator(".schedule-row").first().getByRole("button", { name: "PAUSE" }).click();
    await page.waitForFunction(() => document.querySelector(".schedule-row .schedule-state")?.textContent.includes("PAUSED"));
    await page.locator(".schedule-row").first().getByRole("button", { name: "RESUME" }).click();
    await page.waitForFunction(() => document.querySelector(".schedule-row .schedule-state")?.textContent.includes("ACTIVE"));
    await page.locator(".schedule-row").first().getByRole("button", { name: "RUN NOW" }).click();
    assert(calls.some(call => call.path.includes("/run-now") && call.method === "POST"));
    await page.locator(".schedule-row").first().getByRole("button", { name: "DELETE" }).click();
    await page.locator(".schedule-row").waitFor({ state: "detached" });
    assert.equal(schedules.length, 0);
  });

  await check("Tasks page create, edit status/progress/priority, search, and filter", async () => {
    await navTo(page, "Tasks");
    await page.getByPlaceholder("Kazi mpya ya MR AI...").fill("Test a full interaction path");
    await page.getByPlaceholder("Maelezo ya hiari ya kazi").fill("Created by Playwright QA");
    await page.getByRole("button", { name: "CREATE TASK" }).click();
    await page.getByText("Test a full interaction path", { exact: true }).waitFor({ state: "visible" });
    const card = page.locator(".managed-task-card").filter({ hasText: "Existing test task" }).first();
    await card.getByLabel("Task title 41").fill("Edited test task");
    await card.getByLabel("Task status 41").selectOption("IN_PROGRESS");
    await card.getByLabel("Task priority 41").selectOption("HIGH");
    await card.getByLabel("Task progress 41").fill("35");
    await card.getByRole("button", { name: "SAVE" }).click();
    await page.waitForFunction(() => {
      const row = document.querySelector(".managed-task-card");
      return row && row.textContent.includes("Edited test task");
    });
    assert.equal(tasks.find(task => task.id === 41).status, "IN_PROGRESS");
    assert.equal(tasks.find(task => task.id === 41).progress, 35);
    await page.getByLabel("Search tasks").fill("Edited test task");
    assert.equal(await page.locator(".managed-task-card").count(), 1);
    await page.getByLabel("Filter tasks").selectOption("COMPLETED");
    assert.match(await page.locator(".managed-task-list").innerText(), /No tasks match/);
  });

  await check("Memory page create, search, update, and confirmed delete", async () => {
    await navTo(page, "Memory");
    await page.getByPlaceholder("e.g. project_preferences").fill("qa_test_memory");
    await page.getByPlaceholder("Write the fact or preference to remember...").fill("First draft");
    await page.getByRole("button", { name: "SAVE MEMORY" }).click();
    const card = page.locator(".memory-record").filter({ hasText: "qa_test_memory" }).first();
    await card.waitFor({ state: "visible" });
    await card.getByRole("button", { name: "EDIT" }).click();
    await page.getByLabel("Edit memory " + memories.find(item => item.key === "qa_test_memory").id).fill("Updated from interaction test");
    await card.getByRole("button", { name: "SAVE" }).click();
    assert.equal(memories.find(item => item.key === "qa_test_memory").value, "Updated from interaction test");
    await page.getByLabel("Search memory").fill("qa_test_memory");
    assert.equal(await page.locator(".memory-record").count(), 1);
    page.once("dialog", dialog => dialog.accept());
    await page.locator(".memory-record").first().getByRole("button", { name: "DELETE" }).click();
    await page.locator(".memory-record").waitFor({ state: "detached" });
    assert(!memories.some(item => item.key === "qa_test_memory"));
  });

  await check("Settings refresh and export snapshot", async () => {
    await navTo(page, "Settings");
    await page.getByRole("button", { name: "REFRESH STATUS" }).click();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "EXPORT SNAPSHOT" }).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), "mr-ai-runtime-snapshot.json");
  });

  await check("Command palette includes web, Gmail, Calendar, and closes after navigation", async () => {
    await page.keyboard.press("Control+k");
    await page.getByText("COMMAND PALETTE", { exact: true }).waitFor({ state: "visible" });
    const actions = page.locator(".palette-actions button");
    for (const label of ["Open Web Intelligence", "Open Gmail", "Open Calendar", "Open Creative Studio"]) {
      assert((await actions.allTextContents()).some(text => text.includes(label)), "Command palette is missing " + label);
    }
    await page.locator(".command-palette input").fill("Open Gmail");
    await page.locator(".palette-action").filter({ hasText: "Open Gmail" }).click();
    await page.waitForFunction(() => document.querySelector(".topbar h1")?.textContent.trim() === "Gmail");
    assert.equal(await page.locator(".command-palette").count(), 0);
  });

  await check("Working, sleep, wake, and logout controls", async () => {
    const footer = page.locator(".sidebar-footer");
    await footer.getByRole("button", { name: "WORKING MODE" }).click();
    await page.getByRole("button", { name: "NORMAL MODE" }).waitFor({ state: "visible" });
    await footer.getByRole("button", { name: "NORMAL MODE" }).click();
    await footer.getByRole("button", { name: "SLEEP SYSTEM" }).click();
    await page.getByRole("dialog", { name: "MR AI Sleep Mode" }).waitFor({ state: "visible" });
    await page.getByRole("button", { name: "WAKE MR AI" }).click();
    await page.getByRole("dialog", { name: "MR AI Sleep Mode" }).waitFor({ state: "detached" });
    await footer.getByRole("button", { name: "DISCONNECT SESSION" }).click();
    await page.getByRole("heading", { name: "Command access" }).waitFor({ state: "visible" });
    assert.equal(await page.evaluate(() => localStorage.getItem("mr_ai_token")), null);
  });

  await check("No uncaught JavaScript errors across the full interaction pass", async () => {
    assert.deepEqual(pageErrors, []);
  });

  process.stdout.write("\nSUMMARY: " + passed.length + " passed, " + failures.length + " failed.\n");
  process.stdout.write("API/bridge calls observed: " + calls.length + "\n");
  if (failures.length) {
    for (const failure of failures) process.stderr.write("\n--- " + failure.name + " ---\n" + failure.error + "\n");
    process.exitCode = 1;
  }
  await context.close();
} catch (error) {
  process.stderr.write("FATAL E2E setup error: " + (error?.stack || error) + "\n");
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
  if (server && server.exitCode === null) {
    server.kill("SIGTERM");
    await Promise.race([new Promise(resolve => server.once("exit", resolve)), delay(3000)]);
    if (server.exitCode === null) server.kill("SIGKILL");
  }
}
