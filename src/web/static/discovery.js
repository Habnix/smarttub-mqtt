/* Browser behaviour for the light-mode discovery page. */
(() => {
  "use strict";

  let selectedMode = "quick";
  let statusInterval = null;

  const modeConfigs = {
    yaml_only: {
      modes: [],
      description: "Kein Testlauf; gespeicherte Ergebnisse werden verwendet.",
    },
    quick: {
      modes: [],
      description: "Repräsentative Modi im Schnelltest",
    },
    full: {
      modes: [],
      description: "Alle Modi aus python-smarttub",
    },
  };

  function element(tagName, className, content) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function modeBadge(mode, className = "bg-primary") {
    return element("span", `badge ${className} me-1 mb-1`, mode);
  }

  const resultStatusMeta = {
    supported: { label: "Unterstützt", className: "bg-success" },
    mode_only: { label: "Modus erkannt", className: "bg-warning text-dark" },
    brightness_unsupported: { label: "Helligkeit abweichend", className: "bg-warning text-dark" },
    api_rejected: { label: "API abgelehnt", className: "bg-danger" },
    timeout: { label: "Timeout", className: "bg-secondary" },
    error: { label: "Fehler", className: "bg-danger" },
    cancelled: { label: "Abgebrochen", className: "bg-secondary" },
  };

  function resultStatusBadge(status) {
    const meta = resultStatusMeta[status] || { label: status || "Unbekannt", className: "bg-secondary" };
    return modeBadge(meta.label, meta.className);
  }

  function formatDuration(milliseconds) {
    if (typeof milliseconds !== "number") return "—";
    if (milliseconds < 1000) return `${milliseconds} ms`;
    return `${(milliseconds / 1000).toFixed(1)} s`;
  }

  function formatIntensity(value) {
    return value === null || value === undefined ? "—" : `${value} %`;
  }

  function createModeResultsDetails(light) {
    const modeResults = light.mode_results || {};
    const entries = Object.entries(modeResults).sort(([left], [right]) => left.localeCompare(right));
    const details = document.createElement("details");
    details.className = "mt-2";
    const summary = document.createElement("summary");
    summary.className = "small text-primary";
    summary.textContent = entries.length
      ? `${entries.length} Einzelprüfungen anzeigen`
      : "Keine Einzelprüfungen gespeichert";
    details.append(summary);

    if (!entries.length) return details;

    const table = element("table", "table table-sm mb-0 mt-2");
    const head = element("thead");
    const headRow = element("tr");
    ["Modus", "Status", "Helligkeit", "Dauer", "Hinweis"].forEach((label) => {
      const cell = element("th", "small", label);
      cell.scope = "col";
      headRow.append(cell);
    });
    head.append(headRow);
    const body = element("tbody");
    entries.forEach(([mode, result]) => {
      const row = element("tr");
      row.append(element("th", "small", mode));
      const statusCell = element("td");
      statusCell.append(resultStatusBadge(result?.status));
      const intensityCell = element(
        "td",
        "small",
        `${formatIntensity(result?.requested_intensity)} → ${formatIntensity(result?.verified_intensity)}`,
      );
      const durationCell = element("td", "small", formatDuration(result?.elapsed_ms));
      const noteCell = element("td", "small text-danger", result?.error || "");
      row.append(statusCell, intensityCell, durationCell, noteCell);
      body.append(row);
    });
    table.append(head, body);
    details.append(table);
    return details;
  }

  function responseMessage(data, fallback) {
    return data?.detail || data?.error || fallback;
  }

  function setText(id, value) {
    const target = document.getElementById(id);
    if (target) target.textContent = value;
  }

  function updateModesToTestDisplay() {
    const config = modeConfigs[selectedMode];
    const container = document.getElementById("modes-to-test-list");
    container.replaceChildren();
    if (config.modes.length === 0) {
      container.append(element("span", "text-muted", "Keine Modi im YAML-Modus zu testen."));
      return;
    }
    const badges = element("div", "mb-2");
    config.modes.forEach((mode) => badges.append(modeBadge(mode)));
    container.append(badges, element("small", "text-muted", config.description));
  }

  function updateModeCatalog(catalog) {
    const available = Array.isArray(catalog?.all) ? catalog.all : [];
    modeConfigs.quick.modes = Array.isArray(catalog?.quick) ? catalog.quick : [];
    modeConfigs.full.modes = available;
    const counts = catalog?.counts || {};
    setText(
      "quick-mode-description",
      `Testet ${counts.quick || modeConfigs.quick.modes.length} Modi im Schnelltest`,
    );
    setText(
      "full-mode-description",
      `Testet ${counts.all || available.length} Modi im vollständigen Test`,
    );
    setText(
      "available-modes",
      available.length
        ? `Verfügbare Modi (python-smarttub): ${available.join(", ")}`
        : "Verfügbare Modi konnten nicht geladen werden.",
    );
    updateModesToTestDisplay();
  }

  function selectMode(mode) {
    if (!modeConfigs[mode]) return;
    selectedMode = mode;
    document.querySelectorAll(".mode-input").forEach((input) => {
      const selected = input.value === mode;
      input.checked = selected;
      const card = document.querySelector(`label[for="${input.id}"]`);
      if (!card) return;
      card.classList.toggle("selected", selected);
    });
    updateModesToTestDisplay();
  }

  function setModeSelectionAvailability(available) {
    document.querySelectorAll(".mode-input").forEach((input) => {
      input.disabled = !available;
    });
  }

  function setModeSelectionError(message) {
    const fieldset = document.getElementById("mode-selection");
    const error = document.getElementById("mode-selection-error");
    const hasError = Boolean(message);
    fieldset.classList.toggle("has-error", hasError);
    error.textContent = message || "";
    error.classList.toggle("d-none", !hasError);
    document.querySelectorAll(".mode-input").forEach((input) => {
      input.setAttribute("aria-invalid", String(hasError));
    });
  }

  async function readResponse(response) {
    return response.json().catch(() => ({}));
  }

  async function startDiscovery() {
    if (
      selectedMode === "full"
      && !window.confirm("Der vollständige Durchlauf verändert nacheinander die Lichtmodi. Fortfahren?")
    ) {
      return;
    }
    document.getElementById("start-btn").disabled = true;
    try {
      const response = await fetch("/api/discovery/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: selectedMode }),
      });
      const data = await readResponse(response);
      if (!response.ok) {
        const message = responseMessage(data, "Erkennung konnte nicht gestartet werden.");
        setModeSelectionError(message);
        showToast(message, "danger");
        return;
      }
      setModeSelectionError("");
      showToast("Erkennung wurde gestartet.", "success");
      startStatusPolling();
    } catch (error) {
      showToast(`Fehler beim Starten: ${error.message}`, "danger");
    } finally {
      await refreshStatus();
    }
  }

  async function stopDiscovery() {
    try {
      const response = await fetch("/api/discovery/stop", { method: "POST" });
      const data = await readResponse(response);
      if (!response.ok) {
        showToast(responseMessage(data, "Erkennung konnte nicht gestoppt werden."), "danger");
        return;
      }
      showToast("Erkennung wurde gestoppt.", "warning");
      stopStatusPolling();
    } catch (error) {
      showToast(`Fehler beim Stoppen: ${error.message}`, "danger");
    }
  }

  async function resetState() {
    if (!window.confirm("Discovery-Status und erkannte Ergebnisse zurücksetzen?")) return;
    try {
      const response = await fetch("/api/discovery/reset", { method: "POST" });
      const data = await readResponse(response);
      if (!response.ok) {
        showToast(responseMessage(data, "Status konnte nicht zurückgesetzt werden."), "danger");
        return;
      }
      showToast("Status wurde zurückgesetzt.", "info");
      await refreshStatus();
    } catch (error) {
      showToast(`Fehler beim Zurücksetzen: ${error.message}`, "danger");
    }
  }

  function setDiscoveryAvailability(available) {
    setModeSelectionAvailability(available);
    if (available) return;
    setModeSelectionError("Discovery ist derzeit nicht verfügbar.");
    ["start-btn", "stop-btn", "reset-btn"].forEach((id) => {
      document.getElementById(id).disabled = true;
    });
    setText("status-text", "Nicht verfügbar");
  }

  async function refreshStatus() {
    try {
      const response = await fetch("/api/discovery/status");
      const data = await readResponse(response);
      if (!response.ok || !data.success) {
        setDiscoveryAvailability(false);
        showToast(responseMessage(data, "Discovery-Status konnte nicht geladen werden"), "danger");
        return;
      }
      updateUI(data);
      if (data.is_running) startStatusPolling();
      else stopStatusPolling();
    } catch (_) {
      setDiscoveryAvailability(false);
      showToast("Discovery-Status konnte nicht geladen werden", "danger");
    }
  }

  function updateUI(data) {
    const statusLabels = {
      idle: "Bereit",
      running: "Läuft",
      completed: "Abgeschlossen",
      failed: "Fehlgeschlagen",
    };
    const progress = data.progress || {};
    const percentage = Math.round(progress.percentage || 0);
    const errorSection = document.getElementById("error-section");
    const isRunning = Boolean(data.is_running);

    updateModeCatalog(data.mode_catalog);
    setModeSelectionError("");

    document.getElementById("status-indicator").className = `status-indicator status-${data.status}`;
    setText("status-text", statusLabels[data.status] || "Unbekannt");
    setText("mode-text", data.mode ? data.mode.toUpperCase() : "-");
    setText("started-text", data.started_at ? new Date(data.started_at).toLocaleString() : "-");
    setText("completed-text", data.completed_at ? new Date(data.completed_at).toLocaleString() : "-");
    setText("progress-text", percentage);
    setText("modes-tested", progress.modes_tested || 0);
    setText("modes-total", progress.modes_total || 0);
    setText("current-spa-text", progress.current_spa || "-");
    setText("current-light-text", progress.current_light || "-");

    const progressBar = document.getElementById("progress-bar");
    progressBar.style.width = `${percentage}%`;
    progressBar.textContent = `${percentage}%`;
    progressBar.setAttribute("aria-valuenow", String(percentage));

    errorSection.classList.toggle("d-none", !data.error);
    setText("error-text", data.error || "");
    document.getElementById("start-btn").disabled = isRunning;
    document.getElementById("stop-btn").disabled = !isRunning;
    document.getElementById("reset-btn").disabled = isRunning;
    setModeSelectionAvailability(!isRunning);

    updateTestedModesDisplay(data);
    if (data.status === "completed" && data.results) showResults(data.results, data.completed_at);
    else document.getElementById("results-card").classList.add("d-none");
  }

  function updateTestedModesDisplay(data) {
    const container = document.getElementById("tested-modes-list");
    const results = data.results;
    container.replaceChildren();
    if (results?.spas) {
      const detectedModes = new Set();
      const modeCounts = {};
      Object.values(results.spas).forEach((spa) => {
        (spa.lights || []).forEach((light) => {
          (light.detected_modes || []).forEach((mode) => {
            detectedModes.add(mode);
            modeCounts[mode] = (modeCounts[mode] || 0) + 1;
          });
        });
      });
      if (detectedModes.size === 0) {
        container.append(element("span", "text-warning", "⚠ Keine Modi erkannt"));
        return;
      }
      const badges = element("div", "mb-2");
      [...detectedModes].sort().forEach((mode) => {
        const count = modeCounts[mode];
        const totalLights = results.total_lights || 1;
        const badge = modeBadge(`${count === totalLights ? "✓" : "⚠"} ${mode}`, "bg-success");
        badge.title = `${count}/${totalLights} Lichtzonen`;
        badges.append(badge);
      });
      container.append(
        badges,
        element("small", "text-muted", `${detectedModes.size} Modi in ${results.total_lights} Lichtzonen erkannt`),
      );
      return;
    }
    if (data.is_running) {
      const progress = data.progress || {};
      container.append(element("div", "text-info", `Test läuft … (${progress.modes_tested || 0}/${progress.modes_total || 0})`));
      return;
    }
    container.append(element("span", "text-muted", "Noch keine Modi getestet"));
  }

  function showResults(results, completedAt) {
    document.getElementById("results-card").classList.remove("d-none");
    const lastCompletedAt = results.completed_at || completedAt;
    setText("results-completed", lastCompletedAt ? new Date(lastCompletedAt).toLocaleString() : "-");
    setText("results-lights", results.total_lights || 0);
    setText("results-modes", results.total_modes_detected || 0);
    setText("results-yaml", results.yaml_path || "-");

    const tableBody = document.getElementById("results-tbody");
    tableBody.replaceChildren();
    const statusCounts = {};
    let restoreSuccesses = 0;
    let restoreFailures = 0;
    let restoreUnavailable = 0;
    Object.entries(results.spas || {}).forEach(([spaId, spa]) => {
      (spa.lights || []).forEach((light) => {
        const row = document.createElement("tr");
        const modes = element("td");
        (light.detected_modes || []).forEach((mode) => modes.append(modeBadge(mode)));
        const modeResults = light.mode_results || {};
        Object.values(modeResults).forEach((result) => {
          const status = result?.status || "unknown";
          statusCounts[status] = (statusCounts[status] || 0) + 1;
        });
        if (light.state_restored === true) restoreSuccesses += 1;
        else if (light.state_restored === false) restoreFailures += 1;
        else restoreUnavailable += 1;

        const details = element("td");
        details.append(createModeResultsDetails(light));
        row.append(element("td", "", spaId), element("td", "", light.id), modes, details);
        tableBody.append(row);
      });
    });
    const statusSummary = Object.entries(statusCounts)
      .map(([status, count]) => `${count} × ${(resultStatusMeta[status] || { label: status }).label}`)
      .join(" · ");
    setText("results-status-summary", statusSummary || "Keine Detaildaten vorhanden");
    setText(
      "results-restore-summary",
      restoreFailures
        ? `${restoreSuccesses} erfolgreich, ${restoreFailures} fehlgeschlagen`
        : restoreUnavailable
          ? `${restoreSuccesses} erfolgreich, für ${restoreUnavailable} nicht verfügbar`
          : `${restoreSuccesses} erfolgreich`,
    );
  }

  function startStatusPolling() {
    if (!statusInterval) statusInterval = setInterval(refreshStatus, 2000);
  }

  function stopStatusPolling() {
    if (statusInterval) clearInterval(statusInterval);
    statusInterval = null;
  }

  function showToast(message, type = "info") {
    const alertClass = {
      success: "alert-success",
      danger: "alert-danger",
      warning: "alert-warning",
      info: "alert-info",
    }[type] || "alert-info";
    const alert = element("div", `alert ${alertClass} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3`);
    alert.setAttribute("role", "alert");
    alert.style.zIndex = 9999;
    alert.append(document.createTextNode(message));
    const closeButton = element("button", "btn-close");
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "Schließen");
    closeButton.addEventListener("click", () => alert.remove());
    alert.append(closeButton);
    document.body.append(alert);
    setTimeout(() => alert.remove(), 5000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    updateModesToTestDisplay();
    document.querySelectorAll(".mode-input").forEach((input) => {
      input.addEventListener("change", () => selectMode(input.value));
    });
    const actions = { start: startDiscovery, stop: stopDiscovery, reset: resetState, refresh: refreshStatus };
    document.querySelectorAll("[data-discovery-action]").forEach((button) => {
      button.addEventListener("click", actions[button.dataset.discoveryAction]);
    });
    refreshStatus();
    window.addEventListener("smarttub:discovery", (event) => {
      const data = event.detail;
      if (!data?.success) return;
      updateUI(data);
      if (data.is_running) startStatusPolling();
      else stopStatusPolling();
    });
  });
})();
