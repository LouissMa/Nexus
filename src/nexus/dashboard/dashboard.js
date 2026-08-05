"use strict";

const dashboardState = {
  snapshot: null,
  activeView: "today",
};

const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
const refreshButton = document.getElementById("refresh-button");
const systemStatus = document.getElementById("system-status");
const systemDot = document.getElementById("system-dot");
const generatedAt = document.getElementById("generated-at");

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

function safeValue(value, fallback = "--") {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  if (Array.isArray(value)) {
    return value.join(", ") || fallback;
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function formatDate(value, options) {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
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
  if (count !== undefined) {
    header.append(element("span", "count-label", String(count).padStart(2, "0")));
  }
  const body = element("div", "surface-body");
  wrapper.append(header, body);
  return { wrapper, body };
}

function detailRow(index, title, detail, status) {
  const row = element("article", "data-row");
  row.append(element("span", "row-index", String(index + 1).padStart(2, "0")));
  const copy = element("div", "row-copy");
  copy.append(element("p", "row-title", title));
  if (detail) {
    copy.append(element("p", "row-detail", detail));
  }
  row.append(copy);
  if (status) {
    row.append(statusChip(status));
  }
  return row;
}

function renderSectionError(target, section) {
  clearNode(target);
  target.append(stateMessage("error", section.error || "Section unavailable"));
}

function renderToday(section) {
  const target = document.getElementById("today-content");
  if (section.status !== "ok") {
    renderSectionError(target, section);
    return;
  }
  clearNode(target);
  const data = section.data;
  document.getElementById("today-date").textContent = formatDate(
    `${data.date}T00:00:00`,
    { weekday: "long", month: "long", day: "numeric" },
  );

  const tasks = surface("Priority queue", data.tasks.length);
  tasks.wrapper.classList.add("surface-wide");
  if (data.tasks.length === 0) {
    tasks.body.append(stateMessage("empty", "No tasks scheduled for today"));
  } else {
    data.tasks.forEach((task, index) => {
      const detail = [
        task.goal_title,
        task.estimated_minutes ? `${task.estimated_minutes} min` : null,
        task.blocker ? `Blocked: ${task.blocker}` : null,
      ].filter(Boolean).join(" / ");
      tasks.body.append(detailRow(index, safeValue(task.title), detail, task.status));
    });
  }

  const scheduledJobs = Array.isArray(data.scheduled_jobs) ? data.scheduled_jobs : [];
  const runtime = surface("Schedule", scheduledJobs.length);
  if (scheduledJobs.length === 0) {
    runtime.body.append(stateMessage("empty", "No proactive jobs enabled"));
  } else {
    scheduledJobs.forEach((job, index) => {
      const nextRun = job.next_occurrence
        ? formatDate(job.next_occurrence, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
        : "Not scheduled";
      runtime.body.append(
        detailRow(index, safeValue(job.name), `${safeValue(job.time)} / ${nextRun}`, job.enabled ? "active" : "disabled"),
      );
    });
  }

  const briefs = surface("Briefing and review", 2);
  const briefItems = [
    ["Latest briefing", data.latest_briefing],
    ["Latest review", data.latest_review],
  ];
  briefItems.forEach(([label, notice], index) => {
    if (notice) {
      briefs.body.append(
        detailRow(index, label, safeValue(notice.body, ""), notice.status),
      );
    } else {
      briefs.body.append(detailRow(index, label, "No entry yet", null));
    }
  });

  const reminders = surface("Reminders", data.reminders.length);
  if (data.reminders.length === 0) {
    reminders.body.append(stateMessage("empty", "No active reminders"));
  } else {
    data.reminders.slice(-4).reverse().forEach((reminder, index) => {
      reminders.body.append(
        detailRow(index, safeValue(reminder.title), safeValue(reminder.body, ""), reminder.status),
      );
    });
  }

  const notices = surface("Inbox", data.notifications.length);
  if (data.notifications.length === 0) {
    notices.body.append(stateMessage("empty", "Inbox is clear"));
  } else {
    data.notifications.slice(-4).reverse().forEach((notice, index) => {
      notices.body.append(
        detailRow(index, safeValue(notice.title), safeValue(notice.body, ""), notice.status),
      );
    });
  }

  target.append(tasks.wrapper, runtime.wrapper, briefs.wrapper, reminders.wrapper, notices.wrapper);
}

function renderGoals(section) {
  const target = document.getElementById("goals-content");
  if (section.status !== "ok") {
    renderSectionError(target, section);
    return;
  }
  clearNode(target);
  const goals = section.data.items;
  const activeCount = goals.filter((goal) => goal.status === "active").length;
  document.getElementById("goals-count").textContent = `${activeCount} active`;
  if (goals.length === 0) {
    target.append(stateMessage("empty", "No goals recorded"));
    return;
  }
  goals.forEach((goal, index) => {
    const cadence = goal.cadence_days ? `Review every ${goal.cadence_days} days` : "No cadence";
    const checked = goal.last_check_in
      ? `Last check-in ${formatDate(goal.last_check_in, { month: "short", day: "numeric" })}`
      : "No check-in yet";
    target.append(detailRow(index, safeValue(goal.title), `${safeValue(goal.description, "")} / ${cadence} / ${checked}`, goal.status));
  });
}

function renderMemory(section) {
  const target = document.getElementById("memory-content");
  if (section.status !== "ok") {
    renderSectionError(target, section);
    return;
  }
  clearNode(target);
  const memories = section.data.items;
  document.getElementById("memory-count").textContent = `${memories.length} eligible`;
  if (memories.length === 0) {
    target.append(stateMessage("empty", "No eligible memories"));
    return;
  }
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
  return {
    tools: "Local tools",
    mcp: "MCP calls",
    agents: "Agent runs",
    automations: "Automations",
  }[name] || name;
}

function activitySummary(name, event) {
  if (name === "tools") {
    return `${safeValue(event.tool)} / ${safeValue(event.operation)}`;
  }
  if (name === "mcp") {
    return `${safeValue(event.server)} / ${safeValue(event.tool, event.action)}`;
  }
  if (name === "agents") {
    return safeValue(event.workflow, event.run_id);
  }
  return `${safeValue(event.type)} / ${safeValue(event.action)}`;
}

function renderActivity(section) {
  const target = document.getElementById("activity-content");
  if (section.status !== "ok") {
    renderSectionError(target, section);
    return;
  }
  clearNode(target);
  Object.entries(section.data).forEach(([name, records]) => {
    const group = surface(activityTitle(name), records.length);
    if (records.length === 0) {
      group.body.append(stateMessage("empty", "No recent activity"));
    } else {
      records.slice(-6).reverse().forEach((event, index) => {
        const timestamp = event.at || event.completed_at || event.started_at;
        const detail = [
          timestamp ? formatDate(timestamp, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null,
          event.duration_ms !== undefined ? `${event.duration_ms} ms` : null,
          event.error,
        ].filter(Boolean).join(" / ");
        group.body.append(detailRow(index, activitySummary(name, event), detail, event.status));
      });
    }
    target.append(group.wrapper);
  });
}

function flattenSettings(value, prefix = "") {
  const rows = [];
  Object.entries(value || {}).forEach(([key, item]) => {
    const label = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === "object" && !Array.isArray(item)) {
      rows.push(...flattenSettings(item, label));
    } else {
      rows.push([label, safeValue(item)]);
    }
  });
  return rows;
}

function renderSettings(section) {
  const target = document.getElementById("settings-content");
  if (section.status !== "ok") {
    renderSectionError(target, section);
    return;
  }
  clearNode(target);
  const groups = Object.entries(section.data);
  if (groups.length === 0) {
    target.append(stateMessage("empty", "No settings available"));
    return;
  }
  groups.forEach(([name, values]) => {
    const group = element("section", "settings-group");
    group.append(element("h3", "", name));
    const rows = flattenSettings(values);
    if (rows.length === 0) {
      group.append(stateMessage("empty", "No values"));
    } else {
      rows.forEach(([key, value]) => {
        const row = element("div", "setting-row");
        row.append(element("span", "setting-key", key), element("span", "setting-value", value));
        group.append(row);
      });
    }
    target.append(group);
  });
}

function renderSnapshot(snapshot) {
  const sections = snapshot.sections || {};
  renderToday(sections.today || { status: "error", error: "today_unavailable" });
  renderGoals(sections.goals || { status: "error", error: "goals_unavailable" });
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
    ["today-content", "goals-content", "memory-content", "activity-content", "settings-content"].forEach((id) => {
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
    if (!response.ok) {
      throw new Error("snapshot request failed");
    }
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
    if (selected && focusPanel) {
      panel.focus();
    }
  });
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab));
  tab.addEventListener("keydown", (event) => {
    let nextIndex = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabs.length - 1;
    }
    if (nextIndex !== null) {
      event.preventDefault();
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    }
  });
});

refreshButton.addEventListener("click", loadSnapshot);
loadSnapshot();
