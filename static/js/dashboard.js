(() => {
  function readJson(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function waitForChart(cb) {
    if (window.Chart) {
      cb();
      return;
    }
    let n = 0;
    const t = setInterval(() => {
      n += 1;
      if (window.Chart || n > 40) {
        clearInterval(t);
        if (window.Chart) cb();
      }
    }, 50);
  }

  const PALETTE = [
    "#0d9488",
    "#0284c7",
    "#d97706",
    "#7c3aed",
    "#dc2626",
    "#64748b",
  ];

  function init() {
    if (!document.querySelector("[data-dashboard]")) return;
    waitForChart(() => {
      const text = cssVar("--text", "#142033");
      const muted = cssVar("--text-muted", "#5b6b7c");
      const border = cssVar("--border", "#e2e8f0");
      const accent = cssVar("--accent", "#0d9488");
      const elevated = cssVar("--bg-elevated", "#fff");
      const font = cssVar("--font", "sans-serif");

      const tip = {
        bodyFont: { size: 11 },
        titleFont: { size: 11 },
        padding: 8,
      };

      const att = readJson("dash-att-data");
      const attCanvas = document.getElementById("dash-att-chart");
      if (att && attCanvas) {
        new Chart(attCanvas, {
          type: "doughnut",
          data: {
            labels: att.labels,
            datasets: [
              {
                data: att.values,
                backgroundColor: PALETTE,
                borderWidth: 2,
                borderColor: elevated,
                hoverOffset: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "68%",
            plugins: {
              legend: {
                position: "right",
                labels: {
                  color: muted,
                  boxWidth: 8,
                  boxHeight: 8,
                  padding: 8,
                  font: { size: 10, family: font },
                },
              },
              tooltip: tip,
            },
            layout: { padding: 0 },
          },
        });
      }

      const dept = readJson("dash-dept-data");
      const deptCanvas = document.getElementById("dash-dept-chart");
      if (dept && deptCanvas) {
        new Chart(deptCanvas, {
          type: "bar",
          data: {
            labels: dept.labels,
            datasets: [
              {
                data: dept.values,
                backgroundColor: accent,
                borderRadius: 4,
                maxBarThickness: 14,
                barPercentage: 0.7,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: { legend: { display: false }, tooltip: tip },
            scales: {
              x: {
                ticks: {
                  color: muted,
                  precision: 0,
                  font: { size: 10 },
                  maxTicksLimit: 5,
                },
                grid: { color: border, drawBorder: false },
                border: { display: false },
              },
              y: {
                ticks: { color: text, font: { size: 10 } },
                grid: { display: false },
                border: { display: false },
              },
            },
            layout: { padding: { top: 2, right: 4, bottom: 2, left: 0 } },
          },
        });
      }

      const trend = readJson("dash-trend-data");
      const trendCanvas = document.getElementById("dash-trend-chart");
      if (trend && trendCanvas) {
        new Chart(trendCanvas, {
          type: "line",
          data: {
            labels: trend.labels,
            datasets: [
              {
                label: "Present",
                data: trend.present,
                borderColor: "#0d9488",
                backgroundColor: "rgba(13, 148, 136, 0.12)",
                fill: true,
                tension: 0.35,
                pointRadius: 2,
                pointHoverRadius: 4,
                borderWidth: 2,
              },
              {
                label: "Absent",
                data: trend.absent,
                borderColor: "#dc2626",
                backgroundColor: "transparent",
                tension: 0.35,
                pointRadius: 2,
                pointHoverRadius: 4,
                borderWidth: 2,
              },
              {
                label: "On leave",
                data: trend.on_leave,
                borderColor: "#d97706",
                backgroundColor: "transparent",
                tension: 0.35,
                pointRadius: 2,
                pointHoverRadius: 4,
                borderWidth: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: {
                position: "top",
                align: "end",
                labels: {
                  color: muted,
                  boxWidth: 10,
                  boxHeight: 10,
                  padding: 10,
                  font: { size: 10, family: font },
                },
              },
              tooltip: tip,
            },
            scales: {
              x: {
                ticks: {
                  color: muted,
                  font: { size: 9 },
                  maxRotation: 0,
                  autoSkip: true,
                  maxTicksLimit: 7,
                },
                grid: { display: false },
                border: { display: false },
              },
              y: {
                beginAtZero: true,
                ticks: {
                  color: muted,
                  precision: 0,
                  font: { size: 10 },
                  maxTicksLimit: 4,
                },
                grid: { color: border, drawBorder: false },
                border: { display: false },
              },
            },
            layout: { padding: { top: 0, right: 4, bottom: 0, left: 0 } },
          },
        });
      }

      const leave = readJson("dash-leave-data");
      const leaveCanvas = document.getElementById("dash-leave-chart");
      if (leave && leaveCanvas) {
        new Chart(leaveCanvas, {
          type: "doughnut",
          data: {
            labels: leave.labels,
            datasets: [
              {
                data: leave.values,
                backgroundColor: PALETTE,
                borderWidth: 2,
                borderColor: elevated,
                hoverOffset: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "64%",
            plugins: {
              legend: {
                position: "right",
                labels: {
                  color: muted,
                  boxWidth: 8,
                  boxHeight: 8,
                  padding: 6,
                  font: { size: 10, family: font },
                },
              },
              tooltip: tip,
            },
          },
        });
      }

      const exp = readJson("dash-exp-data");
      const expCanvas = document.getElementById("dash-exp-chart");
      if (exp && expCanvas) {
        new Chart(expCanvas, {
          type: "bar",
          data: {
            labels: exp.labels,
            datasets: [
              {
                data: exp.values,
                backgroundColor: "#0284c7",
                borderRadius: 4,
                maxBarThickness: 14,
                barPercentage: 0.7,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: { legend: { display: false }, tooltip: tip },
            scales: {
              x: {
                ticks: {
                  color: muted,
                  font: { size: 9 },
                  maxTicksLimit: 4,
                  callback(v) {
                    return Number(v).toLocaleString();
                  },
                },
                grid: { color: border, drawBorder: false },
                border: { display: false },
              },
              y: {
                ticks: { color: text, font: { size: 10 } },
                grid: { display: false },
                border: { display: false },
              },
            },
            layout: { padding: { top: 2, right: 4, bottom: 2, left: 0 } },
          },
        });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
