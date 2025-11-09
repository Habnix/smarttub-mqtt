# Task Plan: Background Discovery (v0.3.0)

**Ziel:** Discovery läuft parallel zum WebUI/MQTT als Hintergrund-Task mit Status-Tracking und WebUI-Integration

**Variante:** B - Vollständige Integration (Discovery als optionaler Background-Task)

---

## Phase 1: Core Background Discovery Infrastructure

### Task 1.1: Discovery State Manager
**Datei:** `src/core/discovery_state.py` (NEU)

**Ziel:** Zentrales State-Management für Discovery-Prozess

**Implementierung:**
```python
@dataclass
class DiscoveryState:
    status: Literal["idle", "running", "completed", "failed"]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    progress: DiscoveryProgress
    results: Optional[DiscoveryResults]
    error: Optional[str]

@dataclass
class DiscoveryProgress:
    current_spa: Optional[str]
    current_light: Optional[str]
    lights_total: int
    lights_tested: int
    modes_tested: int
    modes_total: int
    percentage: float

class DiscoveryStateManager:
    def __init__(self):
        self._state: DiscoveryState
        self._lock: asyncio.Lock
        self._observers: List[Callable]
    
    async def get_state() -> DiscoveryState
    async def update_state(updates: dict)
    async def subscribe(callback: Callable)
    async def notify_observers()
```

**Akzeptanzkriterien:**
- ✅ Thread-safe State-Management
- ✅ Observer-Pattern für State-Changes
- ✅ Atomare Updates mit Lock
- ✅ Progress-Tracking (0-100%)

**Geschätzte Zeit:** 2-3 Stunden

---

### Task 1.2: Background Discovery Runner
**Datei:** `src/core/background_discovery.py` (NEU)

**Ziel:** Async Discovery-Prozess der parallel läuft

**Implementierung:**
```python
class BackgroundDiscoveryRunner:
    def __init__(
        self,
        state_manager: DiscoveryStateManager,
        smarttub_client: SmartTubClient,
        config: Config
    ):
        self._task: Optional[asyncio.Task]
        self._stop_event: asyncio.Event
    
    async def start_discovery(
        test_mode: Literal["full", "quick", "yaml_only"]
    ) -> bool
    
    async def stop_discovery() -> bool
    
    async def _run_discovery_loop():
        # Main discovery logic
        # - Load spa
        # - Iterate lights
        # - Test modes (if enabled)
        # - Update progress
        # - Save YAML
    
    async def is_running() -> bool
    
    async def get_status() -> DiscoveryState
```

**Akzeptanzkriterien:**
- ✅ Non-blocking execution (asyncio.Task)
- ✅ Graceful stop support
- ✅ Progress updates während Execution
- ✅ Error handling mit State-Update
- ✅ YAML auto-save nach Completion

**Geschätzte Zeit:** 3-4 Stunden

---

### Task 1.3: Discovery Coordinator
**Datei:** `src/core/discovery_coordinator.py` (NEU)

**Ziel:** High-level API für Discovery-Management

**Implementierung:**
```python
class DiscoveryCoordinator:
    """
    Facade für Discovery-Funktionalität.
    Koordiniert State Manager und Runner.
    """
    def __init__(self, config: Config):
        self.state_manager = DiscoveryStateManager()
        self.runner = BackgroundDiscoveryRunner(...)
        self._mqtt_publisher: Optional[MQTTPublisher]
    
    async def start_discovery(
        mode: Literal["full", "quick", "yaml_only"] = "quick"
    ) -> dict
    
    async def stop_discovery() -> dict
    
    async def get_status() -> dict
    
    async def publish_status_to_mqtt()
        # Publish discovery state to MQTT topic
        # smarttub-mqtt/discovery/status
    
    async def on_state_change(state: DiscoveryState):
        # Observer callback
        await self.publish_status_to_mqtt()
```

**Akzeptanzkriterien:**
- ✅ Einfache API für WebUI/CLI
- ✅ MQTT Status-Publishing
- ✅ Auto-publish on state changes
- ✅ Singleton Pattern (nur 1 Discovery gleichzeitig)

**Geschätzte Zeit:** 2-3 Stunden

---

## Phase 2: MQTT Integration

### Task 2.1: Discovery MQTT Topics
**Datei:** `src/mqtt/topic_mapper.py` (MODIFY)

**Ziel:** Neue MQTT Topics für Discovery-Status

**Topics:**
```
smarttub-mqtt/discovery/status
{
  "status": "running|idle|completed|failed",
  "started_at": "2025-11-09T15:00:00Z",
  "progress": {
    "percentage": 45.5,
    "current_light": "zone_1",
    "modes_tested": 5,
    "modes_total": 18
  },
  "error": null
}

smarttub-mqtt/discovery/control (Command Topic)
{
  "action": "start|stop",
  "mode": "full|quick|yaml_only"
}

smarttub-mqtt/discovery/result (Retained)
{
  "completed_at": "2025-11-09T15:30:00Z",
  "lights": [...],
  "yaml_path": "/config/discovered_items.yaml"
}
```

**Implementierung:**
```python
class TopicMapper:
    # Existing methods...
    
    def publish_discovery_status(
        self,
        state: DiscoveryState
    ) -> List[MQTTMessage]:
        # Publish current discovery state
        pass
    
    def subscribe_discovery_control(
        self,
        callback: Callable
    ):
        # Subscribe to control commands
        pass
```

**Akzeptanzkriterien:**
- ✅ Status topic updates alle 5 Sekunden während Discovery
- ✅ Command topic für Start/Stop
- ✅ Result topic retained nach Completion
- ✅ Home Assistant MQTT Discovery kompatibel

**Geschätzte Zeit:** 2-3 Stunden

---

### Task 2.2: MQTT Command Handler
**Datei:** `src/mqtt/discovery_handler.py` (NEU)

**Ziel:** Handle MQTT Commands für Discovery

**Implementierung:**
```python
class DiscoveryMQTTHandler:
    def __init__(
        self,
        coordinator: DiscoveryCoordinator,
        broker_client: BrokerClient
    ):
        pass
    
    async def on_control_message(
        self,
        topic: str,
        payload: dict
    ):
        action = payload.get("action")
        if action == "start":
            await self.coordinator.start_discovery(...)
        elif action == "stop":
            await self.coordinator.stop_discovery()
    
    async def subscribe_control_topic(self):
        # Subscribe to discovery/control
        pass
```

**Akzeptanzkriterien:**
- ✅ Start Discovery via MQTT
- ✅ Stop Discovery via MQTT
- ✅ Validate command payloads
- ✅ Return status in response topic

**Geschätzte Zeit:** 1-2 Stunden

---

## Phase 3: WebUI Integration

### Task 3.1: Discovery Status API Endpoint
**Datei:** `src/web/app.py` (MODIFY)

**Ziel:** REST API für Discovery-Status

**Endpoints:**
```python
@app.get("/api/discovery/status")
async def get_discovery_status():
    state = await coordinator.get_status()
    return state.to_dict()

@app.post("/api/discovery/start")
async def start_discovery(mode: str = "quick"):
    result = await coordinator.start_discovery(mode)
    return result

@app.post("/api/discovery/stop")
async def stop_discovery():
    result = await coordinator.stop_discovery()
    return result

@app.get("/api/discovery/results")
async def get_discovery_results():
    # Load discovered_items.yaml
    return yaml_data
```

**Akzeptanzkriterien:**
- ✅ GET /api/discovery/status (live updates)
- ✅ POST /api/discovery/start (with mode)
- ✅ POST /api/discovery/stop
- ✅ GET /api/discovery/results (YAML content)
- ✅ Proper error handling
- ✅ JSON responses

**Geschätzte Zeit:** 2 Stunden

---

### Task 3.2: WebUI Discovery Page
**Datei:** `src/web/templates/discovery.html` (NEU)

**Ziel:** Dedicated Discovery Page im WebUI

**Features:**
- **Status Badge:** "Idle" / "Running" / "Completed" / "Failed"
- **Progress Bar:** 0-100% mit Animation
- **Live Progress:** Current light, modes tested
- **Control Buttons:**
  - Start Discovery (Quick)
  - Start Discovery (Full)
  - Stop Discovery
- **Results Display:** Table mit detected modes per light
- **Auto-Refresh:** Polling alle 2 Sekunden während Discovery

**Implementierung:**
```html
<!-- discovery.html -->
<div class="container">
  <h1>Light Mode Discovery</h1>
  
  <!-- Status Card -->
  <div class="card">
    <div class="card-header">
      <span class="badge" id="status-badge">Idle</span>
    </div>
    <div class="card-body">
      <!-- Progress Bar -->
      <div class="progress mb-3">
        <div class="progress-bar" id="progress-bar"></div>
      </div>
      
      <!-- Live Info -->
      <div id="live-info">
        <p>Current Light: <strong id="current-light">-</strong></p>
        <p>Modes Tested: <strong id="modes-tested">0 / 0</strong></p>
      </div>
    </div>
  </div>
  
  <!-- Control Buttons -->
  <div class="btn-group">
    <button id="btn-start-quick">Start Quick Discovery</button>
    <button id="btn-start-full">Start Full Discovery</button>
    <button id="btn-stop" disabled>Stop</button>
  </div>
  
  <!-- Results Table -->
  <div id="results-section" style="display: none">
    <h2>Discovery Results</h2>
    <table id="results-table"></table>
  </div>
</div>

<script>
  // Auto-refresh status
  setInterval(updateStatus, 2000);
  
  async function updateStatus() {
    const res = await fetch('/api/discovery/status');
    const state = await res.json();
    updateUI(state);
  }
  
  async function startDiscovery(mode) {
    await fetch('/api/discovery/start', {
      method: 'POST',
      body: JSON.stringify({ mode })
    });
  }
</script>
```

**Akzeptanzkriterien:**
- ✅ Live Status Updates (Polling)
- ✅ Progress Bar Animation
- ✅ Start/Stop Buttons funktional
- ✅ Results Table nach Completion
- ✅ Responsive Design (Bootstrap)
- ✅ Error Messages Display

**Geschätzte Zeit:** 3-4 Stunden

---

### Task 3.3: Navbar Discovery Link
**Datei:** `src/web/templates/overview.html` (MODIFY)

**Ziel:** Link zur Discovery-Page in Navbar

**Implementierung:**
```html
<nav class="navbar">
  <a href="/">Overview</a>
  <a href="/discovery">Discovery</a>  <!-- NEU -->
  <span>Version: {{ versions.smarttub_mqtt }}</span>
</nav>
```

**Akzeptanzkriterien:**
- ✅ Discovery-Link in Navbar
- ✅ Active state highlighting
- ✅ Mobile responsive

**Geschätzte Zeit:** 30 Minuten

---

## Phase 4: Startup Integration

### Task 4.1: YAML Fallback Publisher
**Datei:** `src/core/yaml_fallback.py` (NEU)

**Ziel:** Publish detected_modes from YAML at startup

**Implementierung:**
```python
class YAMLFallbackPublisher:
    """
    Publishes light meta with detected_modes from YAML
    at startup (before first live API call).
    """
    def __init__(
        self,
        topic_mapper: TopicMapper,
        broker_client: BrokerClient
    ):
        pass
    
    async def publish_from_yaml(
        self,
        yaml_path: Path = Path("/config/discovered_items.yaml")
    ) -> bool:
        # Load YAML
        # For each spa -> light
        #   Create light meta message with detected_modes
        #   Publish to MQTT
        pass
```

**Akzeptanzkriterien:**
- ✅ Load discovered_items.yaml at startup
- ✅ Publish light meta topics mit detected_modes
- ✅ Skip if YAML not found (log warning)
- ✅ Publish before first API snapshot

**Geschätzte Zeit:** 1-2 Stunden

---

### Task 4.2: Conditional Discovery at Startup
**Datei:** `src/cli/run.py` (MODIFY)

**Ziel:** Discovery nur bei Env-Var `DISCOVERY_MODE`

**Implementierung:**
```python
async def main():
    # Existing setup...
    
    # NEW: YAML Fallback Publishing
    yaml_publisher = YAMLFallbackPublisher(...)
    await yaml_publisher.publish_from_yaml()
    
    # NEW: Conditional Background Discovery
    discovery_mode = os.getenv("DISCOVERY_MODE", "off")
    # Options: "off", "startup_quick", "startup_full", "manual"
    
    if discovery_mode == "startup_quick":
        logger.info("Starting background discovery (quick mode)...")
        await coordinator.start_discovery("quick")
    elif discovery_mode == "startup_full":
        logger.info("Starting background discovery (full mode)...")
        await coordinator.start_discovery("full")
    else:
        logger.info("Discovery mode: manual (use WebUI or MQTT)")
    
    # Start WebUI + MQTT
    await asyncio.gather(
        web_server.run(),
        mqtt_loop.run()
    )
```

**Environment Variables:**
```bash
DISCOVERY_MODE=off           # No auto-discovery (default)
DISCOVERY_MODE=startup_quick # Run quick discovery at startup
DISCOVERY_MODE=startup_full  # Run full discovery at startup
DISCOVERY_MODE=manual        # Only via WebUI/MQTT
```

**Akzeptanzkriterien:**
- ✅ YAML fallback publishing always runs
- ✅ Background discovery optional via env var
- ✅ WebUI starts immediately (nicht warten auf Discovery)
- ✅ Discovery läuft parallel

**Geschätzte Zeit:** 1-2 Stunden

---

## Phase 5: Testing & Documentation

### Task 5.1: Unit Tests
**Datei:** `tests/unit/test_background_discovery.py` (NEU)

**Tests:**
- ✅ DiscoveryStateManager state updates
- ✅ BackgroundDiscoveryRunner start/stop
- ✅ DiscoveryCoordinator API
- ✅ Progress calculation
- ✅ Error handling

**Geschätzte Zeit:** 2-3 Stunden

---

### Task 5.2: Integration Tests
**Datei:** `tests/integration/test_discovery_flow.py` (NEU)

**Tests:**
- ✅ Full discovery flow (start -> progress -> completion)
- ✅ MQTT command handling
- ✅ WebUI API endpoints
- ✅ YAML fallback publishing

**Geschätzte Zeit:** 2-3 Stunden

---

### Task 5.3: Documentation
**Dateien:**
- `docs/discovery.md` (NEU)
- `README.md` (UPDATE)
- `CHANGELOG.md` (UPDATE)

**Inhalte:**
- Discovery Mode Explanation
- Environment Variables
- WebUI Usage Guide
- MQTT Control Examples
- Troubleshooting

**Geschätzte Zeit:** 2 Stunden

---

## Phase 6: Docker & Release

### Task 6.1: Docker Environment Variables
**Datei:** `docker-compose.yml` (MODIFY)

**Neue Env-Vars:**
```yaml
environment:
  - DISCOVERY_MODE=manual  # off|startup_quick|startup_full|manual
  - DISCOVERY_YAML_PATH=/config/discovered_items.yaml
```

**Geschätzte Zeit:** 30 Minuten

---

### Task 6.2: Release v0.3.0
**Tasks:**
- ✅ Update CHANGELOG.md
- ✅ Bump version to 0.3.0
- ✅ Git tag v0.3.0
- ✅ Build Docker image
- ✅ Push to Docker Hub
- ✅ GitHub Release Notes

**Geschätzte Zeit:** 1 Stunde

---

## Zusammenfassung

### Gesamtaufwand
- **Phase 1:** 7-10 Stunden (Core Infrastructure)
- **Phase 2:** 3-5 Stunden (MQTT Integration)
- **Phase 3:** 5.5-6.5 Stunden (WebUI)
- **Phase 4:** 2-4 Stunden (Startup Integration)
- **Phase 5:** 6-8 Stunden (Testing & Docs)
- **Phase 6:** 1.5 Stunden (Docker & Release)

**Total:** ~25-35 Stunden

### Prioritäten
1. **MUSS (MVP):**
   - Phase 1: Core Infrastructure
   - Phase 2.1: MQTT Status Topics
   - Phase 3.1-3.2: WebUI Discovery Page
   - Phase 4: Startup Integration

2. **SOLLTE:**
   - Phase 2.2: MQTT Command Handler
   - Phase 5.1: Unit Tests
   - Phase 5.3: Documentation

3. **KANN:**
   - Phase 5.2: Integration Tests (kann später folgen)

### Milestones

**M1: Core Discovery (1-2 Tage)**
- Tasks 1.1, 1.2, 1.3
- Deliverable: Background Discovery läuft

**M2: MQTT Integration (1 Tag)**
- Tasks 2.1, 2.2
- Deliverable: Discovery via MQTT steuerbar

**M3: WebUI Integration (1-2 Tage)**
- Tasks 3.1, 3.2, 3.3
- Deliverable: Discovery Page funktional

**M4: Production Ready (1 Tag)**
- Tasks 4.1, 4.2, 5.3, 6.1, 6.2
- Deliverable: v0.3.0 Release

---

## Nächste Schritte

**Vorschlag:**
1. Review diesen Task Plan
2. Anpassungen/Feedback
3. Start mit **Task 1.1** (Discovery State Manager)

Sollen wir mit Task 1.1 starten? 🚀
