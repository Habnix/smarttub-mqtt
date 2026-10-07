/* Shared browser behaviour for the SmartTub control pages. */
(function () {
  function messageFrom(response) {
    if (typeof response?.detail === "string") return response.detail;
    if (Array.isArray(response?.detail)) return response.detail[0]?.msg || "Ungültige Eingabe";
    return response?.message || "Die Aktion konnte nicht ausgeführt werden.";
  }

  async function sendCommand(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(messageFrom(data));
    return data;
  }

  function showFeedback(element, message, success) {
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("command-success", success);
    element.classList.toggle("command-error", !success);
    element.style.display = "block";
  }

  function refreshStateAge() {
    const element = document.getElementById("last-updated");
    if (!element || !element.dataset.timestamp) return;
    const timestamp = new Date(element.dataset.timestamp);
    if (Number.isNaN(timestamp.getTime())) return;
    const seconds = Math.max(0, Math.floor((Date.now() - timestamp.getTime()) / 1000));
    const text = seconds < 60 ? `vor ${seconds} s` : `vor ${Math.floor(seconds / 60)} min`;
    element.textContent = text;
    element.title = timestamp.toLocaleString("de-DE");
  }

  function formatTemperature(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(1)}°C` : "—";
  }

  function labelForState(value) {
    const labels = {
      ready: "Bereit",
      heating: "Heizt",
      running: "Läuft",
      on: "Ein",
      off: "Aus",
      high: "Hohe Stufe",
      low: "Niedrige Stufe",
      init: "Initialisierung",
      unknown: "Unbekannt",
    };
    const normalized = String(value || "unknown").toLowerCase();
    return labels[normalized] || normalized.replaceAll("_", " ");
  }

  function labelForSpeed(value) {
    const labels = {
      one_speed: "Einfachgeschwindigkeit",
      two_speed: "Zweifachgeschwindigkeit",
      high: "Hohe Stufe",
      low: "Niedrige Stufe",
    };
    const normalized = String(value || "").toLowerCase();
    if (normalized === "off") return "Aus";
    return labels[normalized] || (value ? String(value).replaceAll("_", " ") : "—");
  }

  function labelForCommand(value) {
    const labels = {
      "lights/state_writetopic": "Lichtzustand ändern",
      "lights/mode_writetopic": "Lichtmodus ändern",
      "lights/color_writetopic": "Lichtfarbe ändern",
      "lights/brightness_writetopic": "Lichthelligkeit ändern",
      "pumps/state_writetopic": "Pumpenzustand ändern",
      "heater/temperature_writetopic": "Zieltemperatur ändern",
      "heater/mode_writetopic": "Heizmodus ändern",
      "filtration/mode_writetopic": "Filtermodus ändern",
    };
    return labels[value] || String(value || "Befehl").replaceAll("_", " ");
  }

  function labelForCommandStatus(value) {
    return {
      success: "Erfolgreich",
      accepted: "Angenommen",
      sent: "An SmartTub gesendet",
      confirmed: "Über SmartTub-API bestätigt",
      failed: "Fehlgeschlagen",
      unknown: "Ergebnis nicht überprüfbar",
      pending: "Ausstehend",
    }[value] || String(value || "Unbekannt");
  }

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function updateDashboardNotice(qualityStatus, timestamp, requestFailed = false) {
    const notice = document.getElementById("state-notice");
    if (!notice) return;
    const available = qualityStatus !== "unavailable";
    const stale = qualityStatus !== "live" || !timestamp || Date.now() - new Date(timestamp).getTime() > 120000;
    const container = document.getElementById("state-container");
    if (container) container.classList.toggle("state-stale", !available || stale);
    const freshnessBadge = document.getElementById("state-freshness-badge");
    if (freshnessBadge) freshnessBadge.classList.toggle("d-none", available && !stale);
    notice.className = `alert ${available && !stale ? "alert-success" : "alert-warning"}`;
    notice.textContent = requestFailed
      ? "Statusaktualisierung fehlgeschlagen. Die zuletzt bekannten Werte werden angezeigt."
      : available && !stale
      ? "Datenverbindung aktiv. Werte werden alle 30 Sekunden aktualisiert."
      : available
      ? "Keine aktuellen Daten vom Whirlpool verfügbar. Die zuletzt bekannten Werte werden angezeigt."
      : "Noch keine Daten vom Whirlpool verfügbar. Es werden keine Gerätewerte angenommen.";
  }

  function componentCards(component) {
    return [...document.querySelectorAll(`[data-component-card="${component}"]`)];
  }

  function updateLightRgbControls(lightId, mode) {
    const normalizedMode = String(mode || "").toUpperCase();
    const rgbMode = normalizedMode === "FULL_DYNAMIC_RGB";
    document.querySelectorAll("[data-light-rgb-controls]").forEach((element) => {
      if (element.dataset.lightId === String(lightId)) element.classList.toggle("d-none", !rgbMode);
    });
    document.querySelectorAll("[data-light-rgb-unavailable]").forEach((element) => {
      if (element.dataset.lightId === String(lightId)) element.classList.toggle("d-none", rgbMode);
    });
    if (!rgbMode) {
      const brightness = document.getElementById(`brightness-${lightId}`);
      const output = document.getElementById(`brightness-value-${lightId}`);
      if (brightness) brightness.value = "100";
      if (output) output.textContent = "100";
    }
  }

  function setComponentClass(element, className) {
    if (element) element.className = className;
  }

  function isActiveComponent(state) {
    return ["running", "on", "high", "low"].includes(String(state).toLowerCase());
  }

  function spaStatusClass(state) {
    const normalized = String(state || "unknown").toLowerCase();
    if (["ready", "heating", "running"].includes(normalized)) return "on";
    if (normalized === "init") return "warning";
    return "unknown";
  }

  function updatePumpCards(pumps) {
    const pumpsById = new Map((Array.isArray(pumps) ? pumps : []).map((pump) => [String(pump.id), pump]));
    componentCards("pump").forEach((card) => {
      const pump = pumpsById.get(card.dataset.componentId);
      const active = pump && isActiveComponent(pump.state);
      const state = pump ? String(pump.state || "unknown") : "unknown";
      const header = card.querySelector("[data-component-header]");
      const indicator = card.querySelector("[data-component-indicator]");
      const badge = card.querySelector("[data-component-state]");
      const speed = card.querySelector("[data-component-speed]");
      const progress = card.querySelector("[data-component-progress]");
      const progressWrapper = card.querySelector("[data-component-progress-wrapper]");
      const activity = card.querySelector("[data-component-activity]");

      setComponentClass(header, `card-header ${active ? "bg-primary text-white" : "bg-light"}`);
      setComponentClass(indicator, `status-indicator status-${active ? "on" : "off"}`);
      setComponentClass(badge, `badge fs-4 ${active ? "bg-primary" : "bg-secondary"}`);
      if (badge) badge.textContent = labelForState(state);
      if (speed) speed.textContent = `Geschwindigkeit: ${labelForSpeed(pump?.speed)}`;
      if (progressWrapper) progressWrapper.setAttribute("aria-valuenow", active ? "100" : "0");
      setComponentClass(progress, `progress-bar ${active ? "bg-primary w-100" : "bg-secondary w-0"}`);
      if (activity) activity.textContent = active ? "Läuft" : state === "unknown" ? "Nicht verfügbar" : "Aus";
    });
  }

  function updateLightCards(lights) {
    const lightsById = new Map((Array.isArray(lights) ? lights : []).map((light) => [String(light.id), light]));
    componentCards("light").forEach((card) => {
      const light = lightsById.get(card.dataset.componentId);
      const active = light && isActiveComponent(light.state || light.mode);
      const state = light ? String(light.state || light.mode || "unknown") : "unknown";
      const header = card.querySelector("[data-component-header]");
      const indicator = card.querySelector("[data-component-indicator]");
      const color = card.querySelector("[data-component-color]");
      const brightness = card.querySelector("[data-component-brightness]");
      const icon = card.querySelector("[data-component-icon]");
      const progress = card.querySelector("[data-component-progress]");
      const progressWrapper = card.querySelector("[data-component-progress-wrapper]");
      const activity = card.querySelector("[data-component-activity]");

      setComponentClass(header, `card-header ${active ? "bg-warning text-dark" : "bg-light"}`);
      setComponentClass(indicator, `status-indicator status-${active ? "on" : "off"}`);
      if (color) color.textContent = `Farbe: ${light?.color || "—"}`;
      if (brightness) brightness.textContent = `Helligkeit: ${light?.brightness ?? "—"}%`;
      if (icon) icon.style.color = light?.color || "#6c757d";
      if (progress) {
        progress.className = `progress-bar ${active ? "bg-warning" : "bg-secondary"}`;
        progress.style.width = `${Math.min(100, Math.max(0, Number(light?.brightness) || 0))}%`;
      }
      if (progressWrapper) {
        progressWrapper.setAttribute("aria-valuenow", String(Math.min(100, Math.max(0, Number(light?.brightness) || 0))));
      }
      if (activity) activity.textContent = active ? "Ein" : state === "unknown" ? "Nicht verfügbar" : "Aus";
    });
  }

  function updateDashboardState(state) {
    const components = state.components || {};
    const spa = components.spa || {};
    const heater = components.heater || {};
    const qualityStatus = state.quality?.status || "unavailable";
    const timestamp = state.timestamp;

    setText("water-temperature", formatTemperature(spa.water_temperature));
    setText("air-temperature", formatTemperature(spa.air_temperature));
    setText("heater-water-temperature", formatTemperature(spa.water_temperature));
    setText("heater-target-temperature", formatTemperature(heater.target_temperature));
    setText("spa-state", labelForState(spa.state));
    setText("heater-state", heater.state === "on" ? "Aktiv" : heater.state === "off" ? "Inaktiv" : "Unbekannt");

    const spaState = document.getElementById("spa-state");
    if (spaState) spaState.className = `badge fs-5 ${["ready", "running"].includes(String(spa.state).toLowerCase()) ? "bg-success" : spa.state === "heating" ? "bg-warning" : "bg-secondary"}`;
    const spaIndicator = document.getElementById("spa-status-indicator");
    if (spaIndicator) spaIndicator.className = `status-indicator status-${spaStatusClass(spa.state)}`;
    const heaterIndicator = document.getElementById("heater-status-indicator");
    if (heaterIndicator) heaterIndicator.className = `status-indicator status-${heater.state === "on" ? "on" : heater.state === "off" ? "off" : "unknown"}`;
    const heaterProgress = document.getElementById("heater-progress");
    if (heaterProgress) heaterProgress.setAttribute("aria-valuenow", heater.state === "on" ? "100" : "0");

    updatePumpCards(components.pumps);
    updateLightCards(components.lights);

    const lastUpdated = document.getElementById("last-updated");
    if (lastUpdated && timestamp) lastUpdated.dataset.timestamp = timestamp;
    updateDashboardNotice(qualityStatus, timestamp);
    refreshStateAge();
  }

  async function refreshDashboardState() {
    if (!document.getElementById("state-container")) return;
    try {
      const response = await fetch("/api/state", { headers: { Accept: "application/json" } });
      const state = await response.json();
      if (!response.ok) throw new Error(messageFrom(state));
      updateDashboardState(state);
    } catch (error) {
      updateDashboardNotice("unavailable", undefined, true);
    }
  }

  async function runCommand(url, payload, feedback, controls) {
    controls.forEach((control) => { control.disabled = true; });
    showFeedback(feedback, "Befehl wird gesendet …", true);
    try {
      const result = await sendCommand(url, payload);
      showFeedback(feedback, result.message || "Befehl ausgeführt.", true);
      window.dispatchEvent(new CustomEvent("smarttub:command-succeeded", { detail: { url, payload } }));
      return true;
    } catch (error) {
      showFeedback(feedback, error.message, false);
      return false;
    } finally {
      controls.forEach((control) => { control.disabled = false; });
    }
  }

  async function refreshCommandHistory() {
    const container = document.getElementById("command-history");
    if (!container) return;
    try {
      const response = await fetch("/api/commands/history", { headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!response.ok) throw new Error(messageFrom(data));
      container.replaceChildren();
      if (data.commands.length === 0) {
        container.textContent = "Noch keine Befehle ausgeführt.";
        return;
      }
      const list = document.createElement("ul");
      list.className = "list-group list-group-flush";
      data.commands.forEach((command) => {
        const item = document.createElement("li");
        item.className = "list-group-item px-0";
        const timestamp = new Date(command.timestamp).toLocaleTimeString("de-DE");
        item.textContent = `${timestamp} · ${labelForCommand(command.command)} · ${labelForCommandStatus(command.status)}`;
        list.appendChild(item);
      });
      container.appendChild(list);
    } catch (error) {
      container.textContent = `Historie nicht verfügbar: ${error.message}`;
    }
  }

  function startLiveEvents() {
    if (!window.EventSource) return;
    let reconnectDelay = 1000;
    let source;
    const connect = () => {
      source = new EventSource("/api/events");
      source.addEventListener("state", (event) => {
        try { updateDashboardState(JSON.parse(event.data)); } catch (_) { /* polling remains the fallback */ }
      });
      source.addEventListener("command", () => refreshCommandHistory());
      source.addEventListener("discovery", (event) => {
        try {
          window.dispatchEvent(new CustomEvent("smarttub:discovery", { detail: JSON.parse(event.data) }));
        } catch (_) { /* discovery polling remains the fallback */ }
      });
      source.onopen = () => { reconnectDelay = 1000; };
      source.onerror = () => {
        source.close();
        window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      };
    };
    connect();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const navigationToggle = document.querySelector("[data-navigation-toggle]");
    const navigationMenu = document.querySelector("[data-navigation-menu]");
    if (navigationToggle && navigationMenu) {
      navigationToggle.addEventListener("click", () => {
        const isOpen = navigationMenu.classList.toggle("is-open");
        navigationToggle.setAttribute("aria-expanded", String(isOpen));
      });
    }

    document.querySelectorAll("[data-range-output]").forEach((input) => {
      input.addEventListener("input", () => {
        const output = document.getElementById(input.dataset.rangeOutput);
        if (output) output.textContent = input.value;
      });
    });

    document.querySelectorAll("[data-light-mode-select]").forEach((select) => {
      select.addEventListener("change", async () => {
        const form = select.form;
        const lightId = form?.querySelector("[name='light_id']")?.value;
        const previousMode = select.dataset.currentMode || "";
        const feedback = document.getElementById(form?.dataset.feedbackTarget || "");
        const succeeded = await runCommand(
          form.action,
          Object.fromEntries(new FormData(form).entries()),
          feedback,
          [select],
        );
        if (succeeded) {
          select.dataset.currentMode = select.value;
          updateLightRgbControls(lightId, select.value);
        } else {
          select.value = previousMode;
          updateLightRgbControls(lightId, previousMode);
        }
      });
    });

    refreshStateAge();
    startLiveEvents();
    setInterval(refreshStateAge, 10000);
    refreshCommandHistory();
    window.addEventListener("smarttub:command-succeeded", refreshCommandHistory);
    window.addEventListener("smarttub:command-succeeded", (event) => {
      const detail = event.detail || {};
      if (String(detail.url || "").endsWith("/api/commands/set_light_mode")) {
        updateLightRgbControls(detail.payload?.light_id, detail.payload?.mode);
      }
    });
    document.querySelectorAll("[data-command-form]:not([data-light-mode-form])").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(form).entries());
        const feedback = document.getElementById(form.dataset.feedbackTarget);
        runCommand(form.action, payload, feedback, [...form.querySelectorAll("button, input, select")]);
      });
    });

    document.querySelectorAll("[data-command-button]").forEach((button) => {
      button.addEventListener("click", () => {
        const feedback = document.getElementById(button.dataset.feedbackTarget);
        runCommand(
          button.dataset.commandButton,
          JSON.parse(button.dataset.commandPayload || "{}"),
          feedback,
          [button],
        );
      });
    });

    const refreshDelay = Number(document.body.dataset.stateRefreshMs || 0);
    if (refreshDelay > 0) {
      refreshDashboardState();
      setInterval(refreshDashboardState, refreshDelay);
    }
  });
}());
