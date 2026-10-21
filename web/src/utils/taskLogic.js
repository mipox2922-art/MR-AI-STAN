export function normalizeMode(value) {
  const status = String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");

  if (["normal", "normal_mode"].includes(status)) return "normal";
  if (["working", "working_mode"].includes(status)) return "working";
  if (["sleep", "sleeping", "sleep_mode"].includes(status)) return "sleep";
  return null;
}

export function getBackendMode(status) {
  const candidates = [
    status?.mode,
    status?.operational_mode,
    status?.runtime?.mode,
    status?.state?.mode,
    status?.ai?.mode,
  ];

  for (const value of candidates) {
    const mode = normalizeMode(value);
    if (mode) return mode;
  }
  return null;
}

export function normalizeTaskStatus(taskOrStatus) {
  const value = taskOrStatus && typeof taskOrStatus === "object"
    ? taskOrStatus.status
    : taskOrStatus;

  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

export function hasAssignedAgent(task) {
  return Boolean(String(task?.agent ?? "").trim());
}

export function isTaskInProgress(task) {
  return normalizeTaskStatus(task) === "in_progress" && hasAssignedAgent(task);
}

export function isTaskWaiting(task) {
  return ["waiting", "queued"].includes(normalizeTaskStatus(task));
}

export function isTaskFailed(task) {
  return normalizeTaskStatus(task) === "failed";
}

export function isTaskCompleted(task) {
  return normalizeTaskStatus(task) === "completed";
}

function agentKey(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

export function taskBelongsToAgent(task, agent) {
  if (!hasAssignedAgent(task) || !agent) return false;

  const owner = agentKey(task.agent);
  const id = agentKey(agent.id);
  const name = agentKey(agent.name);

  return Boolean(owner && (
    owner === id ||
    owner === name ||
    owner === id.replace(/^mr_ai_?/, "") ||
    owner.replace(/^mr_ai_?/, "") === id
  ));
}

export function getActiveTaskForAgent(agent, tasks = []) {
  return tasks.find(task =>
    isTaskInProgress(task) && taskBelongsToAgent(task, agent)
  ) || null;
}

export function getAssignedTaskForAgent(agent, tasks = []) {
  const assigned = tasks.filter(task => taskBelongsToAgent(task, agent));
  return (
    assigned.find(task => isTaskInProgress(task)) ||
    assigned.find(task => isTaskWaiting(task)) ||
    assigned.find(task => !["completed", "failed", "cancelled"].includes(normalizeTaskStatus(task))) ||
    null
  );
}

export function getTaskSummary(tasks = [], agents = []) {
  const rows = Array.isArray(tasks) ? tasks : [];
  const registeredAgents = Array.isArray(agents) ? agents : [];
  const inProgressTasks = rows.filter(isTaskInProgress);
  const agentCount = registeredAgents.length
    ? registeredAgents.filter(agent => getActiveTaskForAgent(agent, rows)).length
    : new Set(inProgressTasks.map(task => agentKey(task.agent)).filter(Boolean)).size;

  return {
    total: rows.length,
    inProgress: inProgressTasks.length,
    waiting: rows.filter(isTaskWaiting).length,
    failed: rows.filter(isTaskFailed).length,
    completed: rows.filter(isTaskCompleted).length,
    workingNow: agentCount,
  };
}
