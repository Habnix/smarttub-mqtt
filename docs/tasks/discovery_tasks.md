# Tasks: Discovery / Item Probing

Short task list for implementing and testing startup discovery of spa items.

- [ ] Review python-smarttub API for available control methods (non-destructive) and document safe probe calls.
- [x] Implement `ItemProber` to call `get_status`, `get_pumps`, `get_lights` and collect results (already implemented).
- [x] Persist discovery results to YAML under configured config volume (`discovered_items.yaml`).
- [x] Publish JSON discovery summary to MQTT under `<base_topic>/<spa_id>/discovery/result` (retained).
- [ ] Add unit tests for `ItemProber` mocking spa objects (happy path + partial failures).
- [ ] Add an opt-in config flag to re-run probing periodically or force refresh via API/UI.
- [ ] Optionally: implement a safe capability-to-command mapper that attempts a non-destructive query for available enums/options.
