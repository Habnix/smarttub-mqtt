# Discovery & Item Probing

This spec describes the startup discovery behaviour for SmartTub items (pumps, lights, heater) and how discovered items are persisted and published.

Goals

- Probe each spa at startup to enumerate pumps, lights and heater properties using read-only API calls.
- Persist the discovered items to a YAML file under the configured config volume (default: `config/discovered_items.yaml`).
- Publish a JSON summary of each spa's discovery result to MQTT under `<base_topic>/<spa_id>/discovery/result` (retained).
- Only read-only operations are performed by default. If a probe finds methods or supported options it may record them, but the probe avoids changing spa state.

Data format

- YAML persisted structure (top-level key `discovered_items`): mapping spa_id -> discovery object

Example (simplified):

```yaml
discovered_items:
  "100946961":
    spa_id: "100946961"
    discovered_at: "2025-10-25T12:34:56Z"
    pumps:
      - id: P1
        type: circulation
        supports:
          state: true
          speed: true
    lights:
      - id: zone_1
        zone: 1
        supports:
          color: true
          brightness: true
    heater:
      present: true
      water_temperature: 29.0

```

MQTT topic

- `{{mqtt.base_topic}}/{{spa_id}}/discovery/result` — JSON payload mirroring the YAML entry, retained.

Compatibility note

- For backwards compatibility the bridge also publishes legacy aggregated component state
  messages to the older, non‑spa topics (for example `{{mqtt.base_topic}}/heater/state`).
  This allows existing integrations that expect the old topic layout to continue working.

- Caveat: when multiple spas are present the legacy non‑spa topics will contain the
  payload of the most recent publish and therefore can be ambiguous. Integrations
  that need per‑spa clarity should subscribe to the spa scoped topic `{{mqtt.base_topic}}/{{spa_id}}/...`.

Fields

- spa_id: string — the spa identifier
- discovered_at: ISO-8601 timestamp when discovery ran
- pumps: list of pump descriptors
  - id: pump id or null
  - type: optional pump type
  - supports: dict of detected capabilities (state/speed)
- lights: list of light/zone descriptors
  - id: zone id
  - zone: numeric zone if available
  - supports: dict (color, brightness)
- heater: dict with at least `present: bool` and optional `water_temperature`

