function showToast(message) {
  const stack = document.getElementById("toastStack");
  if (!stack) return;
  const toast = document.createElement("div");
  toast.className = "toast-msg";
  toast.textContent = message;
  stack.appendChild(toast);
  setTimeout(() => toast.remove(), 2600);
}

document.addEventListener("click", async (event) => {
  const copyButton = event.target.closest("[data-copy]");
  if (copyButton) {
    await navigator.clipboard.writeText(copyButton.dataset.copy);
    showToast("Copied successfully");
  }

  const menuButton = event.target.closest("[data-toggle-sidebar]");
  if (menuButton) {
    document.querySelector(".sidebar")?.classList.toggle("open");
  }

  const editFixed = event.target.closest(".edit-fixed");
  if (editFixed) {
    document.getElementById("fixedId").value = editFixed.dataset.id;
    document.getElementById("fixedName").value = editFixed.dataset.name;
    document.getElementById("fixedAmount").value = editFixed.dataset.amount;
    document.getElementById("fixedCategory").value = editFixed.dataset.category;
    document.getElementById("fixedDue").value = editFixed.dataset.due;
    showToast("Fixed category loaded for editing");
  }
});

function chartColors() {
  return ["#2563eb", "#10b981", "#f97316", "#8b5cf6", "#ef4444", "#14b8a6", "#eab308", "#64748b", "#db2777"];
}

async function chartData() {
  const response = await fetch("/api/charts");
  return response.json();
}

function makeChart(id, type, data, options = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  return new Chart(el, {
    type,
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { boxWidth: 12 } } },
      ...options,
    },
  });
}

async function loadDashboardCharts() {
  const data = await chartData();
  makeChart("expensePie", "doughnut", {
    labels: data.expensePie.labels,
    datasets: [{ data: data.expensePie.values, backgroundColor: chartColors(), borderWidth: 0 }],
  });
  makeChart("incomeExpense", "line", {
    labels: data.incomeExpense.labels,
    datasets: [
      { label: "Income", data: data.incomeExpense.income, borderColor: "#10b981", tension: 0.35, fill: false },
      { label: "Expenses", data: data.incomeExpense.expenses, borderColor: "#ef4444", tension: 0.35, fill: false },
    ],
  });
}

async function loadReportCharts() {
  const data = await chartData();
  makeChart("monthlyTrend", "bar", {
    labels: data.monthlyTrend.labels,
    datasets: [{ label: "Expenses", data: data.monthlyTrend.values, backgroundColor: "#2563eb" }],
  });
  makeChart("savingsGrowth", "line", {
    labels: data.savingsGrowth.labels,
    datasets: [{ label: "Savings", data: data.savingsGrowth.values, borderColor: "#10b981", tension: 0.35, fill: true, backgroundColor: "rgba(16,185,129,0.16)" }],
  });
}
