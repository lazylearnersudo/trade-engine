"use strict";
const $ = (s) => document.querySelector(s);
const escapeHtml = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (n) =>
  n == null
    ? "â€”"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
      }).format(Number(n));
const date = (s) =>
  s
    ? new Date(s).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "â€”";
let token = sessionStorage.getItem("trade-token"),
  refreshToken = sessionStorage.getItem("trade-refresh"),
  user,
  config,
  dashboard,
  strategyItems = [],
  page = "dashboard",
  loading = false;
const admin = () => user && user.role !== "USER";
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  setTimeout(() => ($("#toast").hidden = true), 5000);
}
async function api(path, options = {}) {
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...options.headers,
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw Error("Service response unavailable");
  }
  if (response.status === 401 && refreshToken && !path.startsWith("/auth/")) {
    const result = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (result.ok) {
      const renewed = await result.json();
      saveTokens(renewed);
      return api(path, options);
    }
    clearSession();
  }
  if (!response.ok) throw Error(data.message || "Request failed");
  return data;
}
const post = (path, data = {}) =>
  api(path, { method: "POST", body: JSON.stringify(data) });
const put = (path, data) =>
  api(path, { method: "PUT", body: JSON.stringify(data) });
function saveTokens(data) {
  token = data.access_token;
  sessionStorage.setItem("trade-token", token);
  if (data.refresh_token) {
    refreshToken = data.refresh_token;
    sessionStorage.setItem("trade-refresh", refreshToken);
  }
}
function clearSession() {
  token = null;
  refreshToken = null;
  sessionStorage.removeItem("trade-token");
  sessionStorage.removeItem("trade-refresh");
  $("#workspace").hidden = true;
  $("#auth").hidden = false;
}
function theme(value) {
  if (value === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = value;
  localStorage.setItem("trade-theme", value);
  $("#theme").value = value;
}
theme(localStorage.getItem("trade-theme") || "system");
$("#theme").onchange = (e) => theme(e.target.value);
function badge(status) {
  const good = [
    "CONNECTED",
    "CONNECTED_READ_ONLY",
    "FILLED",
    "COMPLETED",
    "OK",
    "APPROVED",
    "MATCHED",
  ];
  const bad = ["REJECTED", "AMBIGUOUS", "DISCREPANCY", "DENIED", "DEGRADED"];
  return `<span class="badge ${good.includes(status) ? "good" : bad.includes(status) ? "bad" : "warn"}">${escapeHtml(status)}</span>`;
}
function header(title, sub, actions = "") {
  return `<div class="page-head"><div><h1>${title}</h1><p>${sub}</p></div><div class="page-actions">${actions}</div></div>`;
}
function table(
  headers,
  rows,
  empty = "Nothing here yet",
  detail = "Activity will appear as you use the workspace.",
) {
  if (!rows.length)
    return `<div class="empty"><strong>${empty}</strong>${detail}</div>`;
  return `<div class="table-scroll"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function panel(title, body, action = "") {
  return `<div class="panel"><div class="panel-header"><h2>${title}</h2>${action}</div>${body}</div>`;
}
function orderTable(orders) {
  return table(
    ["INSTRUMENT", "QUANTITY", "PRICE", "STATUS", "PLACED", "ACTION"],
    orders.map((o) => [
      `${escapeHtml(o.symbol)}<small>${escapeHtml(o.broker || "DUMMY")} Â· ${escapeHtml(o.reason || "BUY")}</small>`,
      `${o.filled_quantity} / ${o.quantity}`,
      money(o.price),
      badge(o.status),
      date(o.created_at),
      ["OPEN", "PARTIAL"].includes(o.status)
        ? `<button data-cancel="${escapeHtml(o.id)}">Cancel</button>`
        : "â€”",
    ]),
    "No orders yet",
    "Create and run an ETF strategy to see your first simulated order.",
  );
}
async function loadPage() {
  if (!user || loading) return;
  loading = true;
  try {
    dashboard = await api("/dashboard");
    $("#environment").textContent = config.environment.toUpperCase();
    $("#safety-banner").textContent =
      `${config.execution_mode} EXECUTION Â· ${config.environment === "local" ? "LOCAL DEVELOPMENT Â· " : ""}Live trading disarmed${dashboard.controls.kill_switch ? " Â· KILL SWITCH ACTIVE â€” new orders blocked" : " Â· All prices and fills are simulated"}`;
    $("#safety-banner").classList.toggle(
      "danger",
      dashboard.controls.kill_switch || config.execution_mode === "LIVE",
    );
    document
      .querySelectorAll("nav a")
      .forEach((a) => a.classList.toggle("active", a.dataset.page === page));
    const labels = {
      dashboard: "Overview",
      strategies: "Strategies",
      orders: "Orders",
      positions: "Positions",
      brokers: "Brokers",
      risk: "Risk & operations",
      audit: "Activity log",
      users: "Administration",
    };
    $("#breadcrumb").textContent = "Workspace / " + labels[page];
    const views = {
      dashboard: renderDashboard,
      strategies: renderStrategies,
      orders: renderOrders,
      positions: renderPositions,
      brokers: renderBrokers,
      risk: renderRisk,
      audit: renderAudit,
      users: renderUsers,
    };
    $("#content").innerHTML = await views[page]();
    bindActions();
    $("#connection").textContent = "Connected";
  } catch (e) {
    $("#connection").textContent = "Unavailable";
    toast(e.message);
  } finally {
    loading = false;
  }
}
async function renderDashboard() {
  const [positions, quotes] = await Promise.all([
    api("/positions"),
    api("/quotes"),
  ]);
  const value = positions.reduce((n, p) => n + Number(p.market_value || 0), 0),
    pnl = positions.reduce((n, p) => n + Number(p.unrealized_pnl || 0), 0);
  return (
    header(
      "Execution overview",
      "A clear view of your strategies, capital, and execution health.",
      `<button data-refresh>â†» Refresh</button><button class="primary" data-create>+ New strategy</button>`,
    ) +
    `<div class="metrics"><div class="metric"><small>Portfolio value</small><strong>${money(value)}</strong><span class="note">${positions.length} instrument${positions.length === 1 ? "" : "s"} Â· simulated positions</span></div><div class="metric"><small>Unrealized P&L</small><strong class="positive">${money(pnl)}</strong><span class="note">Based on current simulated prices</span></div><div class="metric"><small>Active strategies</small><strong>${dashboard.strategies.active}<small> / ${dashboard.strategies.total}</small></strong><span class="note">Persistent schedules Â· Asia/Kolkata</span></div><div class="metric"><small>Execution protection</small><strong>${dashboard.controls.kill_switch ? "Paused" : "Guarded"}</strong><span class="note">${dashboard.ambiguous_orders} orders require reconciliation</span></div></div>` +
    `<div class="grid-two"><div>${panel("Recent orders", orderTable(dashboard.recent_orders), '<a href="#orders">View all â†’</a>')}${panel("Reference prices", `<div class="panel-body">${quotes.map((q) => `<div class="quote"><div><strong>${q.symbol}</strong><small>SIMULATED Â· ${date(q.updated_at)}</small></div><strong>${money(q.price)}</strong></div>`).join("")}</div>`)}</div><div>${panel("Broker connections", `<div class="panel-body">${dashboard.brokers.map((b) => `<div class="connection-row"><div><strong>${b.id}</strong><small>${b.id === "DUMMY" ? "Paper account Â· " + money(b.cash) : "Credentials required"}</small></div>${badge(b.id === "DUMMY" ? (b.scenario === "OUTAGE" ? "DEGRADED" : "CONNECTED") : "DISABLED")}</div>`).join("")}</div>`, '<a href="#brokers">Manage â†’</a>')}${panel("Operational safeguards", `<div class="panel-body"><div class="connection-row"><span>Live trading</span>${badge("DISARMED")}</div><div class="connection-row"><span>Kill switch</span>${badge(dashboard.controls.kill_switch ? "ACTIVE" : "STANDBY")}</div><div class="connection-row"><span>Risk checks</span>${badge("ENFORCED")}</div><p class="muted">All order intents pass through shared risk validation. Unknown submissions are never retried automatically.</p><a href="#risk">Open risk controls â†’</a></div>`)}</div></div>`
  );
}
async function renderStrategies() {
  strategyItems = await api("/strategies");
  return (
    header(
      "Strategies",
      "Configurable ETF allocation with persisted execution history.",
      '<button class="primary" data-create>+ New strategy</button>',
    ) +
    panel(
      "ETF allocation strategies",
      table(
        [
          "STRATEGY",
          "ALLOCATION",
          "SCHEDULE (IST)",
          "STATE",
          "LAST RUN",
          "ACTIONS",
        ],
        strategyItems.map((s) => [
          `${escapeHtml(s.name)}<small>${escapeHtml(s.symbol)} Â· ${s.broker} / ${escapeHtml(s.account_id)}</small>`,
          money(s.budget) +
            `<small>${s.limit_price ? "Limit " + money(s.limit_price) : "Market order"}</small>`,
          s.schedule_time || "Manual",
          badge(s.enabled ? "ENABLED" : "DISABLED"),
          date(s.last_run_at),
          `<button data-edit="${s.id}">Edit</button> <button data-runs="${s.id}">History</button> ${s.enabled ? `<button class="primary" data-run="${s.id}">Run now</button>` : ""}`,
        ]),
        "No strategies configured",
        "Start with a small ETF allocation in the dummy account.",
      ),
    ) +
    '<div id="run-history"></div>'
  );
}
async function renderOrders() {
  return (
    header(
      "Orders",
      "Submission, fills, rejections, and unknown outcomes in one ledger.",
      admin() ? "<button data-reconcile>Reconcile orders</button>" : "",
    ) + panel("Order ledger", orderTable(await api("/orders")))
  );
}
async function renderPositions() {
  const items = await api("/positions");
  return (
    header(
      "Positions",
      "Normalized holdings with reference prices and reconciliation status.",
    ) +
    panel(
      "Portfolio",
      table(
        [
          "INSTRUMENT",
          "ACCOUNT",
          "QUANTITY",
          "AVG PRICE",
          "MARKET VALUE",
          "UNREALIZED P&L",
          "RECONCILIATION",
        ],
        items.map((p) => [
          escapeHtml(p.symbol),
          escapeHtml(p.broker) +
            "<small>" +
            escapeHtml(p.account_id) +
            "</small>",
          p.quantity,
          money(p.average_price),
          money(p.market_value),
          money(p.unrealized_pnl),
          badge(p.reconciliation_status),
        ]),
        "No positions yet",
        "Filled simulated orders will appear here.",
      ),
    )
  );
}
async function renderBrokers() {
  const items = await api("/brokers");
  return (
    header(
      "Broker connections",
      "Broker credentials remain on the execution server. Live order routing is disabled.",
    ) +
    `<div class="broker-grid">${items.map((b) => `<div class="panel broker-card"><h2>${b.id}${badge(b.status)}</h2><p>${escapeHtml(b.integration)}</p><div class="connection-row"><span>Account</span><span class="mono">${escapeHtml(b.account_id)}</span></div>${b.id === "DUMMY" ? `<div class="connection-row"><span>Available cash</span><strong>${money(b.cash)}</strong></div>${admin() ? `<label>Available simulated cash (₹)<input data-cash type="number" min="0" max="10000000" step="0.01" value="${b.cash}"></label><label>Execution scenario<select data-scenario>${["NORMAL", "REJECT", "PARTIAL", "OUTAGE", "AMBIGUOUS"].map((s) => `<option ${b.scenario === s ? "selected" : ""}>${s}</option>`).join("")}</select></label><button data-broker-toggle class="primary">${b.enabled ? "Disable" : "Enable"} dummy broker</button>` : ""}` : `<p>OAuth / token setup required. Consult the private broker setup guide.</p>`}${admin() ? `<button data-check="${b.id}">Check connection</button>` : ""}</div>`).join("")}</div>`
  );
}
async function renderRisk() {
  const controls = await api("/risk"),
    r = controls.risk;
  return (
    header(
      "Risk & operations",
      "Conservative limits apply to every order intent.",
    ) +
    `<div class="grid-two"><div>${panel(
      "Capital and exposure limits",
      `<form id="risk-form" class="panel-body"><div class="risk-grid">${[
        ["max_order_value", "Maximum order value (â‚¹)"],
        ["max_quantity", "Maximum quantity"],
        ["max_position_value", "Maximum position value (â‚¹)"],
        ["max_daily_capital", "Maximum daily capital (â‚¹)"],
        ["max_open_orders", "Maximum open orders"],
        ["max_quote_age_seconds", "Quote freshness (seconds)"],
      ]
        .map(
          ([k, label]) =>
            `<label>${label}<input type="number" name="${k}" min="1" value="${r[k]}" required ${admin() ? "" : "disabled"}></label>`,
        )
        .join(
          "",
        )}</div><label>Allowed instruments<input name="allowed_instruments" value="${escapeHtml(r.allowed_instruments.join(","))}" ${admin() ? "" : "disabled"}></label><label>Allowed brokers<input name="allowed_brokers" value="${escapeHtml(r.allowed_brokers.join(","))}" ${admin() ? "" : "disabled"}></label><label>Allowed accounts<input name="allowed_accounts" value="${escapeHtml(r.allowed_accounts.join(","))}" ${admin() ? "" : "disabled"}></label><label class="check"><input type="checkbox" name="market_hours_only" ${r.market_hours_only ? "checked" : ""} ${admin() ? "" : "disabled"}> Enforce Indian market session for live brokers</label>${admin() ? '<button class="primary">Save risk controls</button>' : ""}</form>`,
    )}</div><div>${panel("Operational controls", `<div class="panel-body"><div class="control-row"><div><strong>Kill switch</strong><p>Block all new order submissions.</p></div>${badge(controls.kill_switch ? "ACTIVE" : "STANDBY")}</div><p class="muted">Existing orders may still fill. Cancellation is a separate action. This control never liquidates positions.</p>${admin() ? `<button data-kill class="danger-button">${controls.kill_switch ? "Release kill switch" : "Activate kill switch"}</button>` : ""}<hr><div class="control-row"><div><strong>Live execution</strong><p>Account validation is pending.</p></div>${badge("DISARMED")}</div><p class="muted">Local machines cannot place live orders. Approved outbound IP, broker mappings, and validated adapters are required before arming becomes available.</p>${admin() ? "<button data-disarm>Disarm live execution</button><hr><button data-reconcile>Reconcile orders & positions</button>" : ""}</div>`)}</div></div>`
  );
}
async function renderAudit() {
  const events = await api("/audit");
  return (
    header(
      "Activity log",
      "Traceable strategy, risk, broker, and administrative events.",
    ) +
    panel(
      "Audit trail",
      table(
        ["TIME (IST)", "ACTION", "ACTOR", "OUTCOME", "DETAILS"],
        events.map((e) => [
          date(e.created_at),
          escapeHtml(e.action),
          `<span class="mono">${escapeHtml(e.actor.slice(0, 16))}</span>`,
          badge(e.outcome),
          escapeHtml(JSON.stringify(e.details)),
        ]),
        "No activity yet",
      ),
    )
  );
}
async function renderUsers() {
  if (!admin()) return header("Administration", "Administrator role required.");
  const users = await api("/users");
  return (
    header(
      "Administration",
      "Server-side roles control access to operational actions.",
    ) +
    panel(
      "Users",
      table(
        ["EMAIL", "ROLE", "CREATED", "ACTION"],
        users.map((u) => [
          escapeHtml(u.email),
          badge(u.role),
          date(u.created_at),
          user.role === "SUPERUSER" && u.id !== user.id
            ? `<select data-role="${u.id}">${["USER", "ADMIN", "SUPERUSER"].map((r) => `<option ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}</select>`
            : "â€”",
        ]),
      ),
    )
  );
}
function bind(selector, event, handler) {
  document.querySelectorAll(selector).forEach((el) =>
    el.addEventListener(event, async (e) => {
      try {
        await handler(e, el);
      } catch (error) {
        toast(error.message);
      }
    }),
  );
}
function bindActions() {
  bind("[data-refresh]", "click", () => loadPage());
  bind("[data-create]", "click", () => openStrategy());
  bind("[data-edit]", "click", (e, el) =>
    openStrategy(strategyItems.find((s) => s.id === el.dataset.edit)),
  );
  bind("[data-run]", "click", async (e, el) => {
    el.disabled = true;
    try {
      const result = await post("/strategies/" + el.dataset.run + "/run", {
        idempotency_key: crypto.randomUUID(),
      });
      toast(
        `${result.run.status}${result.run.reason ? ": " + result.run.reason : ""}`,
      );
      await loadPage();
    } finally {
      el.disabled = false;
    }
  });
  bind("[data-runs]", "click", async (e, el) => {
    const runs = await api("/strategies/" + el.dataset.runs + "/runs");
    $("#run-history").innerHTML = panel(
      "Run history",
      table(
        ["STARTED", "STATUS", "REASON", "CORRELATION"],
        runs.map((r) => [
          date(r.started_at),
          badge(r.status),
          escapeHtml(r.reason || "Completed"),
          `<span class="mono">${r.id}</span>`,
        ]),
        "No runs yet",
      ),
    );
  });
  bind("[data-cancel]", "click", async (e, el) => {
    await post("/orders/" + el.dataset.cancel + "/cancel");
    toast("Order cancelled");
    await loadPage();
  });
  bind("[data-kill]", "click", async () => {
    await put("/controls", { kill_switch: !dashboard.controls.kill_switch });
    toast("Kill switch updated");
    await loadPage();
  });
  bind("[data-disarm]", "click", async () => {
    await post("/controls/disarm");
    toast("Live execution disarmed");
  });
  bind("[data-reconcile]", "click", async () => {
    const r = await post("/reconcile");
    toast(`Reconciliation complete: ${r.discrepancies.length} discrepancies`);
    await loadPage();
  });
  bind("[data-check]", "click", async (e, el) => {
    const r = await post("/brokers/" + el.dataset.check + "/check");
    toast(r.status + (r.reason ? ": " + r.reason : ""));
  });
  bind("[data-scenario]", "change", async (e, el) => {
    const b = dashboard.brokers.find((b) => b.id === "DUMMY");
    await put("/brokers/DUMMY", { enabled: b.enabled, scenario: el.value });
    toast("Dummy scenario updated");
    await loadPage();
  });
  bind("[data-cash]", "change", async (e, el) => {
    const b = dashboard.brokers.find((b) => b.id === "DUMMY");
    await put("/brokers/DUMMY", {
      enabled: b.enabled,
      scenario: b.scenario,
      cash: el.value,
    });
    toast("Simulated cash updated");
    await loadPage();
  });
  bind("[data-broker-toggle]", "click", async () => {
    const b = dashboard.brokers.find((b) => b.id === "DUMMY");
    await put("/brokers/DUMMY", { enabled: !b.enabled, scenario: b.scenario });
    await loadPage();
  });
  bind("[data-role]", "change", async (e, el) => {
    await put("/users/" + el.dataset.role + "/role", { role: el.value });
    toast("Role updated");
  });
  if ($("#risk-form"))
    $("#risk-form").onsubmit = async (e) => {
      e.preventDefault();
      const f = new FormData(e.target),
        body = {};
      for (const [k, v] of f) {
        if (k.startsWith("allowed_"))
          body[k] = v
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
        else if (k !== "market_hours_only") body[k] = Number(v);
      }
      body.market_hours_only = f.has("market_hours_only");
      try {
        await put("/risk", body);
        toast("Risk limits saved");
        await loadPage();
      } catch (err) {
        toast(err.message);
      }
    };
}
function openStrategy(item) {
  const form = $("#strategy-form");
  form.reset();
  form.elements.id.value = item?.id || "";
  $("#strategy-title").textContent = item ? "Edit strategy" : "Create strategy";
  if (item) {
    for (const key of [
      "name",
      "broker",
      "account_id",
      "symbol",
      "budget",
      "limit_price",
      "schedule_time",
    ])
      form.elements[key].value = item[key] ?? "";
    form.elements.enabled.checked = item.enabled;
  }
  $("#strategy-error").textContent = "";
  $("#strategy-dialog").showModal();
}
$("#close-dialog").onclick = () => $("#strategy-dialog").close();
$("#strategy-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target),
    body = {
      name: f.get("name"),
      broker: f.get("broker"),
      account_id: f.get("account_id"),
      symbol: f.get("symbol"),
      budget: f.get("budget"),
      limit_price: f.get("limit_price") || null,
      schedule_time: f.get("schedule_time") || null,
      enabled: f.has("enabled"),
    };
  try {
    f.get("id")
      ? await put("/strategies/" + f.get("id"), body)
      : await post("/strategies", body);
    $("#strategy-dialog").close();
    toast("Strategy saved");
    page = "strategies";
    location.hash = page;
    await loadPage();
  } catch (err) {
    $("#strategy-error").textContent = err.message;
  }
};
async function enterWorkspace() {
  user = await api("/auth/me");
  $("#identity-name").textContent = user.email;
  $("#identity-role").textContent = user.role;
  $("#admin-nav").hidden = !admin();
  $("#auth").hidden = true;
  $("#workspace").hidden = false;
  page = location.hash.slice(1) || "dashboard";
  if (
    ![
      "dashboard",
      "strategies",
      "orders",
      "positions",
      "brokers",
      "risk",
      "audit",
      "users",
    ].includes(page)
  )
    page = "dashboard";
  await loadPage();
}
$("#login-form").onsubmit = async (e) => {
  e.preventDefault();
  $("#auth-error").textContent = "";
  const f = new FormData(e.target);
  try {
    saveTokens(
      await post("/auth/login", {
        email: f.get("email"),
        password: f.get("password"),
      }),
    );
    await enterWorkspace();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
};
$("#logout").onclick = async () => {
  try {
    await post("/auth/logout");
  } catch (e) {
    toast(e.message);
  } finally {
    clearSession();
  }
};
$("#forgot-button").onclick = async () => {
  const email = $("#login-form").elements.email.value;
  if (!email) {
    $("#auth-error").textContent = "Enter your email or local username first.";
    return;
  }
  try {
    const r = await post("/auth/forgot", { email });
    toast(r.message);
    if (r.local_reset_token) {
      $("#reset-form").hidden = false;
      $("#reset-form").elements.token.value = r.local_reset_token;
    }
  } catch (e) {
    $("#auth-error").textContent = e.message;
  }
};
$("#reset-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await post("/auth/reset", {
      token: f.get("token"),
      password: f.get("password"),
    });
    toast("Password updated. Sign in again.");
    $("#reset-form").hidden = true;
    clearSession();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
};
window.addEventListener("hashchange", () => {
  const next = location.hash.slice(1);
  if (
    [
      "dashboard",
      "strategies",
      "orders",
      "positions",
      "brokers",
      "risk",
      "audit",
      "users",
    ].includes(next)
  ) {
    page = next;
    loadPage();
  }
});
async function start() {
  config = await api("/config");
  $("#auth-mode").textContent =
    config.environment === "local"
      ? "LOCAL DEVELOPMENT Â· DUMMY EXECUTION Â· Sign in with admin / admin"
      : "DEPLOYED Â· DUMMY EXECUTION Â· Sign in with your Supabase account";
  const recovery = new URLSearchParams(location.hash.slice(1));
  if (recovery.get("type") === "recovery" && recovery.get("access_token")) {
    $("#reset-form").hidden = false;
    $("#reset-form").elements.token.value = recovery.get("access_token");
    history.replaceState(null, "", location.pathname);
    return;
  }
  if (token) {
    try {
      await enterWorkspace();
    } catch {
      clearSession();
    }
  }
}
start().catch((e) => ($("#auth-error").textContent = e.message));
setInterval(() => {
  if (
    user &&
    !$("#workspace").hidden &&
    ["dashboard", "orders", "positions"].includes(page)
  )
    loadPage();
}, 15000);
