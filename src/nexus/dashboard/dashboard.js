"use strict";

const dashboardState = {
  snapshot: null,
  activeView: "today",
  replanPreview: null,
};

const csrfToken = document.querySelector('meta[name="nexus-csrf"]').content;
const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
const refreshButton = document.getElementById("refresh-button");
const systemStatus = document.getElementById("system-status");
const systemDot = document.getElementById("system-dot");
const generatedAt = document.getElementById("generated-at");
const replanDialog = document.getElementById("replan-dialog");
const confirmDialog = document.getElementById("confirm-dialog");

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function safeValue(value, fallback = "--") {
  if (value === undefined || value === null || value === "") return fallback;
  if (Array.isArray(value)) return value.join(", ") || fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatDate(value, options) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, options).format(parsed);
}

function statusChip(status) {
  const normalized = safeValue(status, "unknown").toLowerCase();
  return element("span", `status-chip ${normalized}`, normalized);
}

function stateMessage(kind, message) {
  return element("div", `${kind}-state`, message);
}

function surface(title, count) {
  const wrapper = element("section", "surface");
  const header = element("header", "surface-header");
  header.append(element("h3", "", title));
  if (count !== undefined) header.append(element("span", "count-label", String(count).padStart(2, "0")));
  const body = element("div", "surface-body");
  wrapper.append(header, body);
  return { wrapper, body };
}

function detailRow(index, title, detail, status) {
  const row = element("article", "data-row");
  row.append(element("span", "row-index", String(index + 1).padStart(2, "0")));
  const copy = element("div", "row-copy");
  copy.append(element("p", "row-title", title));
  if (detail) copy.append(element("p", "row-detail", detail));
  row.append(copy);
  if (status) row.append(statusChip(status));
  return row;
}

function actionButton(label, className, handler) {
  const button = element("button", `action-button ${className}`, label);
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}

async function withBusy(button, callback) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await callback();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Nexus-CSRF": csrfToken,
    },
    body: JSON.stringify(payload),
  });
  let data = {};
  try {
    data = await response.json();
  } catch (_error) {
    throw new Error("Nexus returned an unreadable response");
  }
  if (!response.ok || data.status !== "ok") throw new Error(data.error || "Action failed");
  return data.result;
}

function confirmAction(message) {
  document.getElementById("confirm-message").textContent = message;
  confirmDialog.returnValue = "";
  confirmDialog.showModal();
  return new Promise((resolve) => {
    confirmDialog.addEventListener("close", () => resolve(confirmDialog.returnValue === "confirm"), { once: true });
  });
}

function renderSectionError(target, section) {
  clearNode(target);
  target.append(stateMessage("error", section.error || "Section unavailable"));
}

function renderToday(section) {
  const target = document.getElementById("today-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const data = section.data;
  document.getElementById("today-date").textContent = formatDate(`${data.date}T00:00:00`, { weekday: "long", month: "long", day: "numeric" });

  const tasks = surface("Priority queue", data.tasks.length);
  tasks.wrapper.classList.add("surface-wide");
  if (!data.tasks.length) tasks.body.append(stateMessage("empty", "No tasks scheduled for today"));
  data.tasks.forEach((task, index) => {
    const detail = [task.goal_title, task.estimated_minutes ? `${task.estimated_minutes} min` : null, task.blocker ? `Blocked: ${task.blocker}` : null].filter(Boolean).join(" / ");
    tasks.body.append(detailRow(index, safeValue(task.title), detail, task.status));
  });

  const jobs = Array.isArray(data.scheduled_jobs) ? data.scheduled_jobs : [];
  const runtime = surface("Schedule", jobs.length);
  if (!jobs.length) runtime.body.append(stateMessage("empty", "No proactive jobs enabled"));
  jobs.forEach((job, index) => {
    const nextRun = job.next_occurrence ? formatDate(job.next_occurrence, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Not scheduled";
    runtime.body.append(detailRow(index, safeValue(job.name), `${safeValue(job.time)} / ${nextRun}`, job.enabled ? "active" : "disabled"));
  });

  const briefs = surface("Briefing and review", 2);
  [["Latest briefing", data.latest_briefing], ["Latest review", data.latest_review]].forEach(([label, notice], index) => {
    briefs.body.append(notice ? detailRow(index, label, safeValue(notice.body, ""), notice.status) : detailRow(index, label, "No entry yet", null));
  });

  const reminders = surface("Reminders", data.reminders.length);
  if (!data.reminders.length) reminders.body.append(stateMessage("empty", "No active reminders"));
  data.reminders.slice(-4).reverse().forEach((item, index) => reminders.body.append(detailRow(index, safeValue(item.title), safeValue(item.body, ""), item.status)));

  const notices = surface("Inbox", data.notifications.length);
  if (!data.notifications.length) notices.body.append(stateMessage("empty", "Inbox is clear"));
  data.notifications.slice(-4).reverse().forEach((item, index) => notices.body.append(detailRow(index, safeValue(item.title), safeValue(item.body, ""), item.status)));
  target.append(tasks.wrapper, runtime.wrapper, briefs.wrapper, reminders.wrapper, notices.wrapper);
}

function renderGoals(section) {
  const target = document.getElementById("goals-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const goals = section.data.items;
  const activeCount = goals.filter((goal) => goal.status === "active").length;
  document.getElementById("goals-count").textContent = `${activeCount} active`;
  if (!goals.length) return target.append(stateMessage("empty", "No goals recorded"));
  goals.forEach((goal, index) => {
    const cadence = goal.cadence_days ? `Review every ${goal.cadence_days} days` : "No cadence";
    const checked = goal.last_check_in ? `Last check-in ${formatDate(goal.last_check_in, { month: "short", day: "numeric" })}` : "No check-in yet";
    target.append(detailRow(index, safeValue(goal.title), `${safeValue(goal.description, "")} / ${cadence} / ${checked}`, goal.status));
  });
}

function renderHabits(section) {
  const target = document.getElementById("habits-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const habits = section.data.items;
  const dueCount = habits.filter((habit) => habit.summary && habit.summary.due_today).length;
  document.getElementById("habits-count").textContent = `${dueCount} due`;
  if (!habits.length) return target.append(stateMessage("empty", "No habits recorded"));

  habits.forEach((habit, index) => {
    const summary = habit.summary || {};
    const row = detailRow(
      index,
      safeValue(habit.name),
      `${summary.today_count || 0}/${habit.target_count || 1} today / ${summary.streak || 0} day streak / ${Math.round((summary.completion_rate || 0) * 100)}% completion`,
      summary.today_complete ? "complete" : habit.status,
    );
    row.classList.add("workspace-row");
    const actions = element("div", "row-actions");
    if (habit.status === "active" && summary.due_today) {
      const checkIn = actionButton(summary.today_complete ? "Add another" : "Check in", "positive", () => withBusy(checkIn, async () => {
        await apiPost(`/api/habits/${encodeURIComponent(habit.id)}/check-in`, { increment: 1 });
        await loadSnapshot();
      }).catch(showActionError));
      actions.append(checkIn);
    }
    row.append(actions);
    target.append(row);
  });
}

function renderProjects(section) {
  const target = document.getElementById("projects-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const projects = section.data.items;
  const activeCount = projects.filter((project) => project.status !== "archived").length;
  document.getElementById("projects-count").textContent = `${activeCount} active`;
  if (!projects.length) return target.append(stateMessage("empty", "No projects recorded"));

  projects.forEach((project, index) => {
    const summary = project.summary || {};
    const current = Number(summary.progress_percent || 0);
    const row = detailRow(
      index,
      safeValue(project.name),
      `${summary.completed_milestones || 0}/${summary.milestone_count || 0} milestones / target ${safeValue(project.target_date, "not set")}`,
      project.status,
    );
    row.classList.add("workspace-row");
    const copy = row.querySelector(".row-copy");
    const track = element("div", "progress-track");
    const value = element("div", "progress-value");
    value.style.width = `${Math.max(0, Math.min(100, current))}%`;
    value.setAttribute("role", "progressbar");
    value.setAttribute("aria-valuenow", String(current));
    value.setAttribute("aria-valuemin", "0");
    value.setAttribute("aria-valuemax", "100");
    track.append(value);
    copy.append(track);

    const actions = element("div", "row-actions");
    if (summary.progress_source === "milestones") {
      actions.append(element("span", "row-detail", "Milestone-derived"));
    } else {
      const input = element("input", "compact-input");
      input.type = "number";
      input.min = "0";
      input.max = "100";
      input.value = String(current);
      input.setAttribute("aria-label", `Progress for ${safeValue(project.name)}`);
      const update = actionButton("Update", "secondary", () => withBusy(update, async () => {
        const percent = Number(input.value);
        if (!Number.isFinite(percent) || percent < 0 || percent > 100) throw new Error("Progress must be between 0 and 100");
        let correction = false;
        if (percent < current) {
          correction = await confirmAction("This lowers recorded progress. Apply it as an explicit correction?");
          if (!correction) return;
        }
        await apiPost(`/api/projects/${encodeURIComponent(project.id)}/progress`, { percent, correction });
        await loadSnapshot();
      }).catch(showActionError));
      actions.append(input, update);
    }
    row.append(actions);
    target.append(row);
  });
}

function renderSuggestions(section) {
  const target = document.getElementById("suggestions-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const suggestions = section.data.items;
  const openCount = suggestions.filter((item) => item.status === "open").length;
  document.getElementById("suggestions-count").textContent = `${openCount} open`;
  if (!suggestions.length) return target.append(stateMessage("empty", "No active suggestions"));

  suggestions.forEach((suggestion, index) => {
    const context = suggestion.context || {};
    const sourceTypes = (suggestion.source_types || []).join(" + ") || "local state";
    const degradations = (context.degradations || []).join(", ");
    const contextStatus = `calendar ${safeValue(context.calendar, "not requested")} / RAG ${safeValue(context.rag, "unavailable")}`;
    const detail = `${safeValue(suggestion.kind)} / ${Math.round(Number(suggestion.confidence || 0) * 100)}% confidence / ${sourceTypes} / ${contextStatus}${degradations ? ` / degraded: ${degradations}` : ""}`;
    const row = detailRow(index, safeValue(suggestion.title), detail, suggestion.status);
    row.classList.add("workspace-row");
    const reason = element("p", "row-detail suggestion-reason", safeValue(suggestion.reason, "No reason provided"));
    row.querySelector(".row-copy").append(reason);
    const actions = element("div", "row-actions");
    if (suggestion.status === "open") {
      const accept = actionButton("Accept", "positive", () => withBusy(accept, async () => {
        if (!await confirmAction("Accept this suggestion and run its allowlisted action?")) return;
        await apiPost(`/api/suggestions/${encodeURIComponent(suggestion.id)}/accept`, {});
        await loadSnapshot();
      }).catch(showActionError));
      const dismiss = actionButton("Dismiss", "danger", () => withBusy(dismiss, async () => {
        await apiPost(`/api/suggestions/${encodeURIComponent(suggestion.id)}/dismiss`, {});
        await loadSnapshot();
      }).catch(showActionError));
      actions.append(accept, dismiss);
    }
    row.append(actions);
    target.append(row);
  });
}

function renderResearch(section) {
  const target = document.getElementById("research-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const projects = section.data.items;
  const activeCount = projects.filter((project) => project.status === "active").length;
  document.getElementById("research-count").textContent = `${activeCount} active`;
  if (!projects.length) return target.append(stateMessage("empty", "No research workspaces recorded"));

  projects.forEach((project, index) => {
    const summary = project.summary || {};
    const detail = `${summary.question_count || 0} questions / ${summary.source_count || 0} sources / ${summary.document_count || 0} documents / ${summary.experiment_count || 0} experiments`;
    const row = detailRow(index, safeValue(project.title), detail, project.status);
    const copy = row.querySelector(".row-copy");
    if (project.objective) copy.append(element("p", "row-detail", project.objective));
    if (project.latest_run) {
      copy.append(element("p", "row-detail", `Research loop: ${safeValue(project.latest_run.terminal_reason)} / ${safeValue(project.latest_run.cycles, 0)} cycle(s)`));
    }
    const synthesis = project.latest_synthesis;
    if (synthesis) {
      const findings = (synthesis.current_findings || []).map((item) => item.text).filter(Boolean).join(" ");
      if (findings) copy.append(element("p", "row-detail suggestion-reason", findings));
      const next = (synthesis.next_actions || [])[0];
      if (next) copy.append(element("p", "row-detail", `Next: ${next}`));
    } else {
      copy.append(element("p", "row-detail", "No synthesis yet"));
    }
    target.append(row);
  });
}

function renderMemory(section) {
  const target = document.getElementById("memory-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const memories = section.data.items;
  document.getElementById("memory-count").textContent = `${memories.length} eligible`;
  if (!memories.length) return target.append(stateMessage("empty", "No eligible memories"));
  memories.forEach((memory) => {
    const row = element("article", "data-row");
    row.append(element("time", "memory-date", formatDate(memory.updated_at, { month: "short", day: "numeric", year: "numeric" })));
    const copy = element("div", "row-copy");
    copy.append(element("p", "row-title", safeValue(memory.text)));
    const tags = element("div", "tag-list");
    (memory.tags || []).forEach((tag) => tags.append(element("span", "tag", tag)));
    copy.append(tags);
    row.append(copy, statusChip(`importance ${safeValue(memory.importance, "--")}`));
    target.append(row);
  });
}

function activityTitle(name) {
  return { tools: "Local tools", mcp: "MCP calls", agents: "Agent runs", automations: "Automations" }[name] || name;
}

function activitySummary(name, event) {
  if (name === "tools") return `${safeValue(event.tool)} / ${safeValue(event.operation)}`;
  if (name === "mcp") return `${safeValue(event.server)} / ${safeValue(event.tool, event.action)}`;
  if (name === "agents") return safeValue(event.workflow, event.run_id);
  return `${safeValue(event.type)} / ${safeValue(event.action)}`;
}

function renderActivity(section) {
  const target = document.getElementById("activity-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  Object.entries(section.data).forEach(([name, records]) => {
    const group = surface(activityTitle(name), records.length);
    if (!records.length) group.body.append(stateMessage("empty", "No recent activity"));
    records.slice(-6).reverse().forEach((event, index) => {
      const timestamp = event.at || event.completed_at || event.started_at;
      const detail = [
        timestamp ? formatDate(timestamp, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null,
        event.duration_ms !== undefined ? `${event.duration_ms} ms` : null,
        event.error,
      ].filter(Boolean).join(" / ");
      group.body.append(detailRow(index, activitySummary(name, event), detail, event.status));
    });
    target.append(group.wrapper);
  });
}

function flattenSettings(value, prefix = "") {
  const rows = [];
  Object.entries(value || {}).forEach(([key, item]) => {
    const label = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === "object" && !Array.isArray(item)) rows.push(...flattenSettings(item, label));
    else rows.push([label, safeValue(item)]);
  });
  return rows;
}

function renderSettings(section) {
  const target = document.getElementById("settings-content");
  if (section.status !== "ok") return renderSectionError(target, section);
  clearNode(target);
  const groups = Object.entries(section.data);
  if (!groups.length) return target.append(stateMessage("empty", "No settings available"));
  groups.forEach(([name, values]) => {
    const group = element("section", "settings-group");
    group.append(element("h3", "", name));
    const rows = flattenSettings(values);
    if (!rows.length) group.append(stateMessage("empty", "No values"));
    rows.forEach(([key, value]) => {
      const row = element("div", "setting-row");
      row.append(element("span", "setting-key", key), element("span", "setting-value", value));
      group.append(row);
    });
    target.append(group);
  });
}

function renderSnapshot(snapshot) {
  const sections = snapshot.sections || {};
  renderToday(sections.today || { status: "error", error: "today_unavailable" });
  renderGoals(sections.goals || { status: "error", error: "goals_unavailable" });
  renderHabits(sections.habits || { status: "error", error: "habits_unavailable" });
  renderProjects(sections.projects || { status: "error", error: "projects_unavailable" });
  renderResearch(sections.research || { status: "error", error: "research_unavailable" });
  renderSuggestions(sections.suggestions || { status: "error", error: "suggestions_unavailable" });
  renderMemory(sections.memory || { status: "error", error: "memory_unavailable" });
  renderActivity(sections.activity || { status: "error", error: "activity_unavailable" });
  renderSettings(sections.settings || { status: "error", error: "settings_unavailable" });
  generatedAt.textContent = formatDate(snapshot.generated_at, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const failed = Object.values(sections).filter((section) => section.status !== "ok").length;
  systemStatus.textContent = failed ? `${failed} section error${failed === 1 ? "" : "s"}` : "Operational";
  systemDot.className = failed ? "status-dot is-error" : "status-dot is-ok";
}

function setLoading() {
  refreshButton.disabled = true;
  refreshButton.classList.add("is-loading");
  systemStatus.textContent = "Refreshing";
  systemDot.className = "status-dot";
  if (!dashboardState.snapshot) {
    ["today-content", "goals-content", "habits-content", "projects-content", "research-content", "suggestions-content", "memory-content", "activity-content", "settings-content"].forEach((id) => {
      const target = document.getElementById(id);
      clearNode(target);
      target.append(stateMessage("loading", "Loading Nexus state"));
    });
  }
}

async function loadSnapshot() {
  setLoading();
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error("snapshot request failed");
    const snapshot = await response.json();
    dashboardState.snapshot = snapshot;
    renderSnapshot(snapshot);
  } catch (_error) {
    systemStatus.textContent = "Connection unavailable";
    systemDot.className = "status-dot is-error";
    const active = document.getElementById(`panel-${dashboardState.activeView}`);
    const target = active.querySelector("[aria-live]");
    clearNode(target);
    target.append(stateMessage("error", "Dashboard data is unavailable"));
  } finally {
    refreshButton.disabled = false;
    refreshButton.classList.remove("is-loading");
  }
}

function showActionError(error) {
  systemStatus.textContent = error && error.message ? error.message : "Action failed";
  systemDot.className = "status-dot is-error";
}

function renderReplanPreview(preview) {
  const target = document.getElementById("replan-preview");
  const lines = [
    `Kept: ${(preview.kept || []).length}`,
    `Moved: ${(preview.moved || []).length}`,
    `Shortened: ${(preview.shortened || []).length}`,
    `Unscheduled: ${(preview.unscheduled || []).length}`,
  ];
  (preview.moved || []).slice(0, 5).forEach((item) => lines.push(`${safeValue(item.title, item.task_id)} -> ${formatDate(item.scheduled_start, { hour: "2-digit", minute: "2-digit" })}`));
  target.textContent = lines.join("\n");
}

document.getElementById("replan-open").addEventListener("click", () => {
  const today = dashboardState.snapshot && dashboardState.snapshot.sections.today;
  const date = today && today.status === "ok" ? today.data.date : new Date().toISOString().slice(0, 10);
  document.getElementById("replan-date").value = date;
  document.getElementById("replan-status").textContent = "";
  document.getElementById("replan-preview").textContent = "No preview generated";
  document.getElementById("replan-apply-button").disabled = true;
  dashboardState.replanPreview = null;
  replanDialog.showModal();
});

const previewButton = document.getElementById("replan-preview-button");
previewButton.addEventListener("click", () => withBusy(previewButton, async () => {
  const payload = {
    date: document.getElementById("replan-date").value,
    working_start: document.getElementById("replan-start").value,
    working_end: document.getElementById("replan-end").value,
  };
  const preview = await apiPost("/api/replan/preview", payload);
  dashboardState.replanPreview = preview;
  renderReplanPreview(preview);
  document.getElementById("replan-status").textContent = "";
  document.getElementById("replan-apply-button").disabled = false;
}).catch((error) => {
  document.getElementById("replan-status").textContent = error.message;
}));

const applyButton = document.getElementById("replan-apply-button");
applyButton.addEventListener("click", () => withBusy(applyButton, async () => {
  if (!dashboardState.replanPreview) return;
  if (!await confirmAction("Apply this schedule to today's pending tasks?")) return;
  await apiPost("/api/replan/apply", { preview: dashboardState.replanPreview });
  await loadSnapshot();
  replanDialog.close();
}).catch((error) => {
  document.getElementById("replan-status").textContent = error.message;
}));

function activateTab(tab, focusPanel = false) {
  const view = tab.dataset.view;
  dashboardState.activeView = view;
  tabs.forEach((item) => {
    const selected = item === tab;
    item.classList.toggle("is-active", selected);
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  panels.forEach((panel) => {
    const selected = panel.id === `panel-${view}`;
    panel.hidden = !selected;
    panel.classList.toggle("is-active", selected);
    if (selected && focusPanel) panel.focus();
  });
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab));
  tab.addEventListener("keydown", (event) => {
    let nextIndex = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
    else if (event.key === "ArrowUp" || event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = tabs.length - 1;
    if (nextIndex !== null) {
      event.preventDefault();
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    }
  });
});

refreshButton.addEventListener("click", loadSnapshot);
loadSnapshot();
