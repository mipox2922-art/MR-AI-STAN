const SECRET_PATTERNS = [
  [/\bBearer\s+[A-Za-z0-9._~+/\-=]+/gi, "Bearer [REDACTED]"],
  [/\bsk-or-v1-[A-Za-z0-9_-]{20,}\b/g, "[REDACTED_API_KEY]"],
  [/\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/g, "[REDACTED_API_KEY]"],
  [/\bAIza[0-9A-Za-z_-]{30,}\b/g, "[REDACTED_API_KEY]"],
  [/\bgh[pousr]_[A-Za-z0-9_]{25,}\b/g, "[REDACTED_TOKEN]"],
  [/\bxai-[A-Za-z0-9_-]{20,}\b/g, "[REDACTED_API_KEY]"],
  [/\b(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[^\s,;]+/gi, "$1=[REDACTED]"],
];

export function sanitizeAssistantMessage(value) {
  let safe = String(value ?? "");
  for (const [pattern, replacement] of SECRET_PATTERNS) safe = safe.replace(pattern, replacement);
  // Provider moderation/debug metadata is not an answer for the user.
  safe = safe.replace(/^\s*(?:user\s+)?safety\s*:\s*(?:safe|unsafe|unknown|allowed|blocked)\s*$/gim, "").trim();
  // Do not block normal prose, uppercase headings, status labels, or short replies.
  return safe || "Jibu la AI halikuwa na maudhui ya kuonyesha. Jaribu tena.";
}
