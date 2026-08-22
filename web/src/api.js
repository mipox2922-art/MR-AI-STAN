function detectApiUrl() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  const { hostname, protocol } = window.location;
  if (hostname.endsWith(".app.github.dev")) {
    return `${protocol}//${hostname.replace(/-\d+\.app\.github\.dev$/, "-8000.app.github.dev")}`;
  }
  return "http://localhost:8000";
}
const API_URL = detectApiUrl();

export function getToken() {
  return localStorage.getItem("mr_ai_token");
}

export function setToken(token) {
  localStorage.setItem("mr_ai_token", token);
}

export function clearToken() {
  localStorage.removeItem("mr_ai_token");
}

async function request(path, options = {}) {
  const token = getToken();

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers
  });

  const data = await response.json();

  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
    }

    throw new Error(data.detail || "Request failed");
  }

  return data;
}

export async function register(username, password, email) {
  const data = await request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, email: email || username + "@mrai.local" })
  });

  setToken(data.access_token);
  return data;
}

export async function login(username, password) {
  const data = await request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });

  setToken(data.access_token);
  return data;
}

export function chat(message, provider = "gemini") {
  return request("/ai/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      provider
    })
  });
}

export function getStatus() {
  return request("/system/status");
}

export function getActivity() {
  return request("/activity");
}

export function getTasks() {
  return request("/tasks");
}

export function createTask(title) {
  return request("/tasks", {
    method: "POST",
    body: JSON.stringify({ title })
  });
}

export function getMemories() {
  return request("/memory");
}

export function createMemory(key, value) {
  return request("/memory", {
    method: "POST",
    body: JSON.stringify({ key, value })
  });
}
