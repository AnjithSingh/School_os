/* School OS front-end behaviour. No dependencies except the local Chart.js build. */
(function () {
  "use strict";

  /* --- Off-canvas navigation ------------------------------------------- */
  function closeNav() {
    document.body.classList.remove("nav-open");
    var toggle = document.querySelector("[data-nav-toggle]");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-nav-toggle]");
    if (toggle) {
      var open = document.body.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    if (document.body.classList.contains("nav-open")) {
      var sidebar = document.getElementById("sidebar");
      if (sidebar && !sidebar.contains(event.target)) closeNav();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeNav();
  });

  document.addEventListener("click", function (event) {
    var back = event.target.closest("[data-back]");
    if (back) {
      var fallback = back.getAttribute("data-back-fallback");
      var fromSameSite = false;
      try {
        fromSameSite = !!document.referrer && new URL(document.referrer).origin === window.location.origin;
      } catch (error) {
        fromSameSite = false;
      }
      if (fromSameSite || !fallback) {
        window.history.back();
      } else {
        window.location.assign(fallback);
      }
    }
    if (event.target.closest("[data-print]")) window.print();
    var toggle = event.target.closest("[data-toggle-target]");
    if (toggle) {
      var panel = document.querySelector(toggle.getAttribute("data-toggle-target"));
      if (panel) {
        panel.hidden = !panel.hidden;
        toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
      }
    }
    var copy = event.target.closest("[data-copy]");
    if (copy) {
      var field = document.querySelector(copy.getAttribute("data-copy"));
      if (field) {
        field.select();
        if (navigator.clipboard) {
          navigator.clipboard.writeText(field.value).then(function () {
            copy.textContent = "Copied";
          });
        } else {
          document.execCommand("copy");
          copy.textContent = "Copied";
        }
      }
    }
  });

  /* --- Flash messages --------------------------------------------------- */
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-dismiss-flash]");
    if (!button) return;
    var alert = button.closest(".flash");
    if (alert) alert.remove();
  });

  /* --- Confirmation dialog ---------------------------------------------- */
  var confirmDialog = document.getElementById("confirm-dialog");
  var confirmMessage = document.getElementById("confirm-dialog-message");
  var confirmAccept = document.getElementById("confirm-dialog-accept");
  var confirmCancel = document.getElementById("confirm-dialog-cancel");
  var confirmAction = null;
  var confirmReturnFocus = null;

  function openConfirm(message, action) {
    if (!confirmDialog || !confirmMessage || !confirmAccept || !confirmCancel) {
      if (window.confirm(message)) action();
      return;
    }
    confirmAction = action;
    confirmReturnFocus = document.activeElement;
    confirmMessage.textContent = message;
    confirmDialog.hidden = false;
    confirmAccept.focus();
  }

  function closeConfirm() {
    confirmAction = null;
    if (confirmDialog) confirmDialog.hidden = true;
    if (confirmReturnFocus && confirmReturnFocus.focus) confirmReturnFocus.focus();
    confirmReturnFocus = null;
  }

  if (confirmAccept) {
    confirmAccept.addEventListener("click", function () {
      var action = confirmAction;
      closeConfirm();
      if (action) action();
    });
  }
  if (confirmCancel) confirmCancel.addEventListener("click", closeConfirm);
  if (confirmDialog) {
    confirmDialog.addEventListener("click", function (event) {
      if (event.target === confirmDialog) closeConfirm();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !confirmDialog.hidden) closeConfirm();
    });
  }

  /* --- Confirm before destructive submits ------------------------------- */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var message = form.getAttribute("data-confirm");
    if (!message) return;
    if (form.getAttribute("data-confirmed") === "1") {
      form.removeAttribute("data-confirmed");
      return;
    }
    event.preventDefault();
    var submitter = event.submitter;
    openConfirm(message, function () {
      form.setAttribute("data-confirmed", "1");
      if (form.requestSubmit) form.requestSubmit(submitter || undefined);
      else form.submit();
      setTimeout(function () { form.removeAttribute("data-confirmed"); }, 0);
    });
  });

  /* --- Confirm before following destructive links ----------------------- */
  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-confirm]");
    if (!link || event.defaultPrevented) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.getAttribute("data-confirmed") === "1") {
      link.removeAttribute("data-confirmed");
      return;
    }
    event.preventDefault();
    openConfirm(link.getAttribute("data-confirm"), function () {
      link.setAttribute("data-confirmed", "1");
      window.location.assign(link.href);
    });
  });

  /* --- Tabs ------------------------------------------------------------- */
  function activateTab(group, name) {
    group.querySelectorAll("[data-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-tab") === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    group.querySelectorAll("[data-tab-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-tab-panel") !== name;
    });
  }

  document.querySelectorAll("[data-tab-group]").forEach(function (group) {
    var first = group.querySelector("[data-tab]");
    if (first) activateTab(group, first.getAttribute("data-tab"));
    group.addEventListener("click", function (event) {
      var tab = event.target.closest("[data-tab]");
      if (!tab) return;
      event.preventDefault();
      activateTab(group, tab.getAttribute("data-tab"));
    });
  });

  /* --- Table row filtering (client-side, no data leaves the page) ------- */
  document.querySelectorAll("[data-filter-input]").forEach(function (input) {
    var target = document.querySelector(input.getAttribute("data-filter-input"));
    if (!target) return;
    input.addEventListener("input", function () {
      var needle = input.value.toLowerCase().trim();
      target.querySelectorAll("tbody tr").forEach(function (row) {
        row.hidden = needle !== "" && row.textContent.toLowerCase().indexOf(needle) === -1;
      });
    });
  });

  /* --- Marks: mark a student absent and clear the mark ------------------ */
  document.addEventListener("change", function (event) {
    var select = event.target.closest("[data-mark-status]");    if (!select) return;
    var row = select.closest("tr");
    var input = row && row.querySelector("input[name^='marks_']");
    if (row) row.classList.toggle("is-absent", select.value === "ABSENT");
    if (input && select.value === "ABSENT") input.value = "";
  });

  /* --- Attendance quick actions ----------------------------------------- */
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-mark-all]");
    if (!button) return;
    var scope = button.closest("form") || document;
    scope.querySelectorAll("[data-mark-status]").forEach(function (select) {
      select.value = button.getAttribute("data-mark-all");
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });

  /* --- Automatic totals ------------------------------------------------- */
  document.querySelectorAll("[data-total-for]").forEach(function (output) {
    var inputs = document.querySelectorAll(output.getAttribute("data-total-for"));
    function update() {
      var total = 0;
      inputs.forEach(function (input) {
        var value = parseFloat(input.value);
        if (!isNaN(value)) total += value;
      });
      output.textContent = total.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    inputs.forEach(function (input) { input.addEventListener("input", update); });
    update();
  });

  /* --- Charts ----------------------------------------------------------- */
  function renderCharts() {
    if (typeof Chart === "undefined") return;
    document.querySelectorAll("canvas[data-chart-src]").forEach(function (canvas) {
      if (canvas.dataset.chartReady) return;
      canvas.dataset.chartReady = "1";
      fetch(canvas.getAttribute("data-chart-src"), {
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      })
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return response.json();
        })
        .then(function (payload) {
          var type = canvas.getAttribute("data-chart-type") || "line";
          new Chart(canvas.getContext("2d"), {
            type: type,
            data: { labels: payload.labels || [], datasets: payload.datasets || [] },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: "index", intersect: false },
              plugins: {
                legend: { display: (payload.datasets || []).length > 1, position: "bottom" },
                tooltip: { padding: 10, cornerRadius: 8 }
              },
              scales: type === "doughnut" || type === "pie" ? {} : {
                y: { beginAtZero: true, grid: { color: "rgba(11,27,43,.07)" } },
                x: { grid: { display: false } }
              }
            }
          });
        })
        .catch(function () {
          canvas.hidden = true;
        });
    });
  }

  function loadChartLibrary(callback) {
    if (typeof Chart !== "undefined") return callback();
    var script = document.createElement("script");
    script.src = document.body.getAttribute("data-chart-lib") || "";
    script.onload = callback;
    document.head.appendChild(script);
  }

  if (document.querySelector("canvas[data-chart-src]")) {
    if (typeof Chart !== "undefined") {
      renderCharts();
    } else {
      loadChartLibrary(renderCharts);
    }
  }
})();
