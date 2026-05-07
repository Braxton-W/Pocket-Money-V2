function $(id) { return document.getElementById(id); }

function setStatus(msg) {
  $("status").textContent = msg || "";
}

function money(n) {
  const v = Number(n);
  const safe = Number.isFinite(v) ? v : 0;
  return safe.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

// ---------- Navigation ----------
const viewMeta = {
  dashboardView: {
    title: "Dashboard",
    subtitle: "Your categories, budgets, and remaining amounts."
  },
  setupView: {
    title: "Monthly Setup",
    subtitle: "Add categories and set budgets for this month."
  },
  purchaseView: {
    title: "Log Purchase",
    subtitle: "Add a purchase and track how much you have left."
  },
  chartView: {
    title: "Spending Chart",
    subtitle: "View an interactive budget vs spending visual summary."
  }
};

function showView(viewId) {
  // Hide all panels
  const panels = document.querySelectorAll(".panel");
  panels.forEach(p => p.classList.add("is-hidden"));
  // Show the chosen one
  const panel = document.getElementById(viewId);
  if (panel) panel.classList.remove("is-hidden");

  // Update nav active state
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach(b => {
    if (b.dataset.view === viewId) b.classList.add("is-active");
    else b.classList.remove("is-active");
  });

  // Update header text
  const meta = viewMeta[viewId] || { title: "Pocket Money", subtitle: "" };
  $("pageTitle").textContent = meta.title;
  $("pageSubtitle").textContent = meta.subtitle;
}

// ---------- API Helpers ----------
async function apiGet(path) {
  const res = await fetch(path, { method: "GET" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || ("Request failed: " + res.status));
  return data;
}

async function apiJson(path, method, payload) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || ("Request failed: " + res.status));
  return data;
}

// ---------- Render ----------
function renderBudgetTable(categories) {
  const body = $("budgetTableBody");
  body.innerHTML = "";

  if (!categories || categories.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="4" class="muted">No categories yet. Go to Monthly Setup and add one.</td>';
    body.appendChild(tr);
    return;
  }

  for (const row of categories) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.category}</td>
      <td class="num">${money(row.budget)}</td>
      <td class="num">${money(row.spent)}</td>
      <td class="num">${money(row.remaining)}</td>
    `;
    body.appendChild(tr);
  }
}

function renderPurchaseTable(purchases) {
  const body = $("purchaseTableBody");
  body.innerHTML = "";

  if (!purchases || purchases.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="3" class="muted">No purchases logged yet.</td>';
    body.appendChild(tr);
    return;
  }

  // Show most recent first (simple reverse)
  const list = purchases.slice().reverse();

  for (const p of list) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.name}</td>
      <td>${p.category}</td>
      <td class="num">${money(p.amount)}</td>
    `;
    body.appendChild(tr);
  }
}

function setCategorySelectOptions(selectEl, categories) {
  selectEl.innerHTML = "";
  if (!categories || categories.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Add a category first";
    selectEl.appendChild(opt);
    selectEl.disabled = true;
    return;
  }

  selectEl.disabled = false;
  for (const c of categories) {
    const opt = document.createElement("option");
    opt.value = c.category;
    opt.textContent = c.category;
    selectEl.appendChild(opt);
  }
}

async function fetchChart() {
  setStatus("Loading chart...");
  try {
    const data = await apiGet("/api/viewbudget");
    const budgets = {};
    const spending = {};

    data.categories.forEach(row => {
      budgets[row.category] = row.budget;
      spending[row.category] = row.spent;
    });

    if (Object.keys(budgets).length === 0) {
      $("chartImage").src = "";
      setStatus("Add a budget category first to generate a chart.");
      return;
    }

    const chartData = await apiJson("/api/chart", "POST", { budgets, spending });
    $("chartImage").src = chartData.chart_path + "?t=" + Date.now();
    setStatus("");
  } catch (err) {
    $("chartImage").src = "";
    setStatus(err.message);
  }
}


// ---------- Load / Refresh ----------
async function refreshAll() {
  setStatus("Loading...");
  try {
    const data = await apiGet("/api/viewbudget");
    renderBudgetTable(data.categories);
    renderPurchaseTable(data.purchases);

    // Fill dropdowns from categories
    setCategorySelectOptions($("budgetCategory"), data.categories);
    setCategorySelectOptions($("purchaseCategory"), data.categories);

    setStatus("");
  } catch (err) {
    setStatus(err.message);
  }
}

// ---------- Actions ----------
async function onAddCategory(e) {
  e.preventDefault();
  const category = $("categoryName").value.trim();
  if (!category) return;

  setStatus("Adding category...");
  try {
    await apiJson("/api/addcategory", "POST", { category });
    $("categoryName").value = "";
    await refreshAll();
    setStatus("Category added.");
  } catch (err) {
    setStatus(err.message);
  }
}

async function onSetBudget(e) {
  e.preventDefault();
  const category = $("budgetCategory").value;
  const amount = Number($("budgetAmount").value);

  if (!category) return;

  setStatus("Saving budget...");
  try {
    await apiJson("/api/setbudget", "PUT", { category, amount });
    $("budgetAmount").value = "";
    await refreshAll();
    setStatus("Budget saved.");
  } catch (err) {
    setStatus(err.message);
  }
}

async function onLogPurchase(e) {
  e.preventDefault();
  const name = $("purchaseName").value.trim();
  const category = $("purchaseCategory").value;
  const amount = Number($("purchaseAmount").value);

  if (!name || !category) return;

  setStatus("Logging purchase...");
  try {
    await apiJson("/api/logpurchase", "POST", { name, category, amount });
    $("purchaseName").value = "";
    $("purchaseAmount").value = "";
    await refreshAll();
    setStatus("Purchase logged.");
    showView("dashboardView");
  } catch (err) {
    setStatus(err.message);
  }
}

async function onReset() {
  setStatus("Resetting...");
  try {
    await apiJson("/api/reset", "POST", {});
    await refreshAll();
    setStatus("Reset complete.");
    showView("setupView");
  } catch (err) {
    setStatus(err.message);
  }
}


// ---------- Initial Setup Modal ----------
function showSetupModal(show) {
  const m = $("setupModal");
  if (!m) return;
  if (show) m.classList.remove("is-hidden");
  else m.classList.add("is-hidden");
}

function parseBulkLines(text) {
  // Returns [{category, amount}, ...]
  const lines = (text || "").split("\n");
  const items = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    // Allow "Category, Amount" or "Category - Amount"
    let parts = line.split(",");
    if (parts.length < 2) parts = line.split("-");
    if (parts.length < 2) continue;

    const category = parts[0].trim();
    const amount = Number(parts[1].trim());

    if (!category) continue;
    if (!Number.isFinite(amount)) continue;

    items.push({ category, amount });
  }
  return items;
}

async function runInitialSetup(items) {
  // For each line: addcategory then setbudget
  for (let i = 0; i < items.length; i++) {
    const it = items[i];

    // add category (ignore if already exists)
    try { await apiJson("/api/addcategory", "POST", { category: it.category }); }
    catch (e) { /* ok if already exists */ }

    // set budget
    await apiJson("/api/setbudget", "PUT", { category: it.category, amount: it.amount });
  }
}

async function maybeOpenSetupModal() {
  // If there are no categories yet, show the first-time setup modal.
  try {
    const data = await apiGet("/api/viewbudget");
    const hasCategories = data.categories && data.categories.length > 0;
    if (!hasCategories) showSetupModal(true);
  } catch (e) {
    setStatus(e.message);
  }
}

async function onBulkSetupSubmit(e) {
  e.preventDefault();
  const items = parseBulkLines($("bulkLines").value);

  if (items.length === 0) {
    setStatus("Enter at least one line like: Food, 250");
    return;
  }

  setStatus("Saving setup...");
  try {
    await runInitialSetup(items);
    showSetupModal(false);
    $("bulkLines").value = "";
    await refreshAll();
    setStatus("Setup saved.");
  } catch (err) {
    setStatus(err.message);
  }
}

function wireSetupModal() {
  if (!$("setupModal")) return;
  $("bulkSetupForm").addEventListener("submit", onBulkSetupSubmit);
  $("bulkCancelBtn").addEventListener("click", () => showSetupModal(false));
  $("setupSkipBtn").addEventListener("click", () => showSetupModal(false));
  $("setupBackdrop").addEventListener("click", () => showSetupModal(false));
}


// ---------- Init ----------
function init() {
  // nav
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      showView(btn.dataset.view);
      if (btn.dataset.view === "dashboardView") refreshAll();
      else if (btn.dataset.view === "chartView") fetchChart();
    });
  });

  $("refreshBtn").addEventListener("click", refreshAll);
  $("refreshChartBtn").addEventListener("click", fetchChart);
  $("addCategoryForm").addEventListener("submit", onAddCategory);
  $("setBudgetForm").addEventListener("submit", onSetBudget);
  $("logPurchaseForm").addEventListener("submit", onLogPurchase);
  $("resetBtn").addEventListener("click", onReset);

  showView("dashboardView");
  wireSetupModal();
  refreshAll();
  maybeOpenSetupModal();
}

document.addEventListener("DOMContentLoaded", function () {
  init();

  // Banner slideshow
  const bannerImages = [
    "static/images/finbud-banner.png",
    "static/images/files-banner.png",
    "static/images/teams-banner.png",
    "static/images/quackening-banner.png"
  ];

  let currentBanner = 0;
  const bannerImage = document.getElementById("bannerImage");

  if (bannerImage) {
    setInterval(function () {
      currentBanner++;

      if (currentBanner >= bannerImages.length) {
        currentBanner = 0;
      }

      bannerImage.src = bannerImages[currentBanner];
    }, 3000);
  }
});
