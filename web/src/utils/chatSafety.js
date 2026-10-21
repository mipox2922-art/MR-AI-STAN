export function sanitizeAssistantMessage(value) {
  const lines = String(value || "").replace(/\r\n/g, "\n").split("\n");
  const safeLines = lines.filter(line => {
    const trimmed = line.trim();
    if (!trimmed) return true;
    if (/user\s*safety\s*:|\bNO_TOOL_MATCH\b|\btool_call\b|\bsystem_telemetry\b/i.test(trimmed)) {
      return false;
    }

    // Hide uppercase debug/data labels that have no normal sentence after the colon.
    if (
      !/[.!?]\s*$/.test(trimmed) &&
      /^[A-Z][A-Z0-9_]*(?:\s+[A-Z][A-Z0-9_]*)?:\s*\S/.test(trimmed)
    ) {
      return false;
    }
    return true;
  });
  const safeText = safeLines.join("\n").trim();
  return safeText || "Jibu lilichujwa kwa sababu lilikuwa na metadata ya ndani pekee.";
}
