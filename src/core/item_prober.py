from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import traceback

import yaml
import asyncio
import smarttub

from src.core.config_loader import AppConfig
from src.mqtt.topic_mapper import MQTTMessage

# Import ErrorTracker if available (T058)
try:
    from src.core.error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
    HAS_ERROR_TRACKER = True
except ImportError:
    HAS_ERROR_TRACKER = False
    ErrorTracker = None  # type: ignore
    ErrorCategory = None  # type: ignore
    ErrorSeverity = None  # type: ignore

# Import DiscoveryProgressTracker if available (T059)
try:
    from src.core.discovery_progress import DiscoveryProgressTracker, DiscoveryPhase, ComponentType
    HAS_PROGRESS_TRACKER = True
except ImportError:
    HAS_PROGRESS_TRACKER = False
    DiscoveryProgressTracker = None  # type: ignore
    DiscoveryPhase = None  # type: ignore
    ComponentType = None  # type: ignore

logger = logging.getLogger(__name__)


class ItemProber:
    """Probes spas for available items (pumps, lights, heater) and records findings.

    Behaviour:
    - Calls read-only methods (get_status, get_pumps, get_lights) on spa objects.
    - Records discovered items and any non-fatal errors.
    - Writes a YAML file with discovered items under the configured config volume
      (fallback: ./config/discovered_items.yaml).
    - Publishes a JSON summary to MQTT under: {base_topic}/{spa_id}/discovery/result
    """

    # All known light modes from python-smarttub
    ALL_LIGHT_MODES = [
        "OFF", "PURPLE", "ORANGE", "RED", "YELLOW", "GREEN", "AQUA", "BLUE",
        "WHITE", "AMBER", "HIGH_SPEED_COLOR_WHEEL", "HIGH_SPEED_WHEEL",
        "LOW_SPEED_WHEEL", "FULL_DYNAMIC_RGB", "AUTO_TIMER_EXTERIOR", 
        "PARTY", "COLOR_WHEEL", "ON",
    ]
    
    # Brightness levels to test (0-100)
    BRIGHTNESS_LEVELS = [0, 25, 50, 75, 100]
    
    # Delay between light mode tests (seconds)
    LIGHT_TEST_DELAY_SECONDS = 20

    def __init__(
        self, 
        config: AppConfig, 
        smarttub_client: Any, 
        topic_mapper: Any, 
        *, 
        error_tracker: Any | None = None,
        progress_tracker: Any | None = None
    ):
        self.config = config
        self.smarttub_client = smarttub_client
        self.topic_mapper = topic_mapper
        self.error_tracker = error_tracker
        self.progress_tracker = progress_tracker

    async def probe_all(self) -> Dict[str, Any]:
        """Probe all known spas and persist+publish results.

        Returns:
            Dict mapping spa_id to discovery result
        """
        results: Dict[str, Any] = {}

        spas = self.smarttub_client.spas
        
        # Start discovery progress tracking (T059)
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.start_discovery(total_spas=len(spas))
            self.progress_tracker.set_overall_phase(DiscoveryPhase.FETCHING_SPAS)
        
        for spa in spas:
            spa_id = str(getattr(spa, 'id', 'unknown'))
            spa_name = getattr(spa, 'brand', 'Unknown Spa')
            
            # Start spa progress tracking (T059)
            if self.progress_tracker and HAS_PROGRESS_TRACKER:
                self.progress_tracker.start_spa(spa_id, spa_name)
                self.progress_tracker.set_overall_phase(DiscoveryPhase.PROBING_SPA)
            
            try:
                res = await self._probe_spa(spa)
                results[spa_id] = res
                
                # Complete spa progress tracking (T059)
                if self.progress_tracker and HAS_PROGRESS_TRACKER:
                    self.progress_tracker.complete_spa(spa_id)
                    
            except Exception as e:
                logger.error(f"Error probing spa {spa_id}: {e}")
                
                # Track discovery error (T058)
                if self.error_tracker and HAS_ERROR_TRACKER:
                    self.error_tracker.track_error(
                        category=ErrorCategory.DISCOVERY,
                        message=f"Failed to probe spa {spa_id}: {str(e)}",
                        severity=ErrorSeverity.ERROR,
                        error_code="DISCOVERY_PROBE_FAILED",
                        details={"spa_id": spa_id}
                    )
                
                # Complete spa with error (T059)
                if self.progress_tracker and HAS_PROGRESS_TRACKER:
                    self.progress_tracker.complete_spa(spa_id, error=str(e))
                
                results[spa_id] = {
                    "spa_id": spa_id,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }

        # Writing YAML phase (T059)
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.set_overall_phase(DiscoveryPhase.WRITING_YAML)
        
        # Persist results to YAML (sanitize objects first)
        try:
            safe_results = {k: self._make_serializable(v) for k, v in results.items()}
            # Before writing YAML, publish per-pump retained meta topics so
            # they are immediately discoverable via MQTT during --discover.
            try:
                messages = []
                base_topic = self.config.mqtt.base_topic
                for spa_id, payload in safe_results.items():
                    pumps = payload.get('pumps', [])
                    # Publish detailed per-pump simple subtopics (id/type/state/speed/last_updated)
                    # by reusing the topic mapper: construct small state snapshots and
                    # ask the mapper to create the proper messages.
                    snapshot = {
                        "timestamp": payload.get('discovered_at') or datetime.now(timezone.utc).isoformat(),
                        "spa_id": spa_id,
                        "components": {"pumps": []},
                    }
                    for p in pumps:
                        pid = p.get('id') or 'unknown'
                        # attempt to extract state and speed from raw when available
                        raw = p.get('raw', {}) if isinstance(p.get('raw', {}), dict) else {}
                        props = raw.get('properties', {}) if isinstance(raw, dict) else {}

                        def _norm_scalar(v):
                            # treat None, empty dict/list as missing
                            if v is None:
                                return None
                            if isinstance(v, (dict, list)) and not v:
                                return None
                            return v

                        state_val = (_norm_scalar(props.get('state'))
                                     or _norm_scalar(raw.get('state'))
                                     or _norm_scalar(p.get('state'))
                                     or 'unknown')
                        speed_val = (_norm_scalar(props.get('speed'))
                                     or _norm_scalar(raw.get('speed'))
                                     or _norm_scalar(p.get('speed'))
                                     or None)
                        type_val = (_norm_scalar(p.get('type'))
                                    or _norm_scalar(props.get('type'))
                                    or _norm_scalar(raw.get('type'))
                                    or None)
                        snapshot['components']['pumps'].append({
                            "id": pid,
                            "type": type_val,
                            "state": state_val,
                            "speed": speed_val,
                        })

                    # Use topic_mapper to generate messages for this synthetic snapshot
                    try:
                        mapper_messages = []
                        if hasattr(self.topic_mapper, 'publish_state_snapshot'):
                            mapper_messages = self.topic_mapper.publish_state_snapshot(snapshot)
                        else:
                            # fallback: use global helper
                            from src.mqtt.topic_mapper import publish_state_snapshot as _helper
                            mapper_messages = _helper(self.config, snapshot)

                        # Publish via mapper if supported
                        if mapper_messages:
                            if hasattr(self.topic_mapper, 'publish_messages'):
                                self.topic_mapper.publish_messages(mapper_messages)
                            else:
                                mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                                if mqtt_client is not None:
                                    for m in mapper_messages:
                                        mqtt_client.publish(topic=m.topic, payload=m.payload, qos=m.qos, retain=m.retain)

                        # Also publish meta messages as before
                        for p in pumps:
                            pid = p.get('id') or 'unknown'
                            raw_p = p.get('raw', {}) if isinstance(p.get('raw', {}), dict) else {}
                            props_p = raw_p.get('properties', {}) if isinstance(raw_p, dict) else {}
                            # Prefer type from properties (where upstream API usually places it)
                            meta_type = props_p.get('type') or p.get('type') or None
                            meta = {
                                "id": pid,
                                "type": meta_type,
                                "supports": p.get('supports', {}),
                                # T052: Use _writetopic convention instead of set_
                                "state_writetopic": f"{base_topic}/{spa_id}/pumps/{pid}/state_writetopic",
                                "discovered_at": payload.get('discovered_at'),
                            }
                            topic = f"{base_topic}/{spa_id}/pumps/{pid}/meta"
                            messages.append(MQTTMessage(topic=topic, payload=json.dumps(meta), qos=1, retain=True))
                            try:
                                logger.info("created-pump-meta-discovery", extra={"topic": topic, "spa_id": spa_id, "pump_id": pid})
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Failed to generate/publish per-pump subtopics for spa {spa_id}: {e}")

                # publish accumulated meta messages
                if messages and hasattr(self.topic_mapper, 'publish_messages'):
                    self.topic_mapper.publish_messages(messages)
                elif messages:
                    mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                    if mqtt_client is not None:
                        for m in messages:
                            mqtt_client.publish(topic=m.topic, payload=m.payload, qos=m.qos, retain=m.retain)
            except Exception as e:
                logger.debug(f"Failed to publish per-pump meta during discovery: {e}")

            self._write_yaml(safe_results)
        except Exception as e:
            logger.error(f"Failed to write discovered items YAML: {e}")

        # Publish each spa's discovery result as JSON to MQTT
        try:
            messages = []
            for spa_id, payload in results.items():
                topic = f"{self.config.mqtt.base_topic}/{spa_id}/discovery/result"
                # Ensure payload is JSON serializable
                safe_payload = self._make_serializable(payload)
                messages.append(MQTTMessage(topic=topic, payload=json.dumps(safe_payload), qos=1, retain=True))
            # Log at INFO which discovery messages we will publish so operators
            # can see them without enabling DEBUG.
            for m in messages:
                try:
                    logger.info("publishing-discovery-result", extra={"topic": m.topic, "retain": m.retain, "spa_id": spa_id})
                except Exception:
                    pass
            # topic_mapper.publish_messages expects instances of MQTTMessage from mapper class
            # If we were given the mapper instance, it provides publish_messages
            if hasattr(self.topic_mapper, 'publish_messages'):
                self.topic_mapper.publish_messages(messages)
            else:
                # best effort: try to access mqtt_client directly
                mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                if mqtt_client is not None:
                    for m in messages:
                        mqtt_client.publish(topic=m.topic, payload=m.payload, qos=m.qos, retain=m.retain)
        except Exception as e:
            logger.error(f"Failed to publish discovery results to MQTT: {e}")

        # Mark discovery as completed (T059)
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.set_overall_phase(DiscoveryPhase.COMPLETED)

        return results

    async def _probe_spa(self, spa: Any) -> Dict[str, Any]:
        spa_id = str(getattr(spa, 'id', 'unknown'))
        discovered_at = datetime.now(timezone.utc).isoformat()
        
        # Estimate component count for progress tracking (T059)
        # Status + Heater + typical components (we'll adjust as we discover)
        estimated_components = 5  # status, heater, pumps, lights, etc.
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.set_spa_component_count(spa_id, estimated_components)
        
        # Prepare result with the user's preferred structure: first capability hints
        # (from python-smarttub), then basic spa info, then heater/lights/pumps.
        result: Dict[str, Any] = {
            "spa_id": spa_id,
            "discovered_at": discovered_at,
            "capabilities_python-smarttub": {},
            "spa": self._make_serializable(spa),
            "heater": {},
            "lights": [],
            "pumps": [],
            "errors": [],
            # keep a generic capabilities bucket for runtime-added entries (e.g. destructive_probes)
            "capabilities": {},
        }

        # 1) Status (heater, water)
        if self.progress_tracker and HAS_PROGRESS_TRACKER:
            self.progress_tracker.start_component(spa_id, ComponentType.STATUS, "status")
        
        try:
            status = await spa.get_status()
            # Basic heater detection
            heater_present = getattr(status, 'heater1Present', None)
            if heater_present is None:
                # fallback: if status has water temperature -> assume heater exists
                heater_present = getattr(status, 'water', None) is not None

            result['heater'] = {
                "present": bool(heater_present),
                "water_temperature": getattr(getattr(status, 'water', {}), 'temperature', None) if getattr(status, 'water', None) else getattr(status, 'water_temperature', None),
            }
            
            # Complete status component (T059)
            if self.progress_tracker and HAS_PROGRESS_TRACKER:
                self.progress_tracker.complete_component(
                    spa_id, 
                    "status",
                    example_info={"water_temp": result['heater'].get('water_temperature')}
                )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Status probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"status_error: {str(e)}")
            
            # Complete status with error (T059)
            if self.progress_tracker and HAS_PROGRESS_TRACKER:
                self.progress_tracker.complete_component(spa_id, "status", error=str(e))

    # 1.1) Full Status (extended information)
        try:
            status_full = await spa.get_status_full()
            result['status_full'] = self._make_serializable(status_full)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Full status probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"status_full_error: {str(e)}")

        # 1.2) Debug Status
        try:
            debug_status = await spa.get_debug_status()
            result['debug_status'] = self._make_serializable(debug_status)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Debug status probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"debug_status_error: {str(e)}")

        # 1.3) Energy Usage
        try:
            energy_usage = await spa.get_energy_usage()
            result['energy_usage'] = self._make_serializable(energy_usage)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Energy usage probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"energy_usage_error: {str(e)}")

        # 1.4) Errors
        try:
            errors = await spa.get_errors()
            result['errors_list'] = self._make_serializable(errors)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Errors probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"errors_list_error: {str(e)}")

        # 1.5) Reminders
        try:
            reminders = await spa.get_reminders()
            result['reminders'] = self._make_serializable(reminders)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Reminders probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"reminders_error: {str(e)}")

        # 1.6) ClearRay UV System (read-only check)
        try:
            # toggle_clearray is write-only, but we can check whether it's available
            # by introspecting the object
            has_clearray = hasattr(spa, 'toggle_clearray') and callable(getattr(spa, 'toggle_clearray', None))
            result['features'] = result.get('features', {})
            result['features']['clearray_available'] = has_clearray
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"ClearRay feature detection failed for spa {spa_id}: {e}")
            result['errors'].append(f"clearray_detection_error: {str(e)}")

        # 2) Pumps
        try:
            pumps = await spa.get_pumps()
            # Keep the raw pump objects so we can optionally call methods if they are provided
            raw_pump_objects = None
            if pumps and isinstance(pumps, dict) and 'pumps' in pumps:
                raw_pump_objects = pumps.get('pumps', [])
                for p in raw_pump_objects:
                    # p may be a dict or a python-smarttub SpaPump object
                    pid = None
                    p_type = None
                    supports = {}
                    if isinstance(p, dict):
                        pid = p.get('id') or p.get('pumpId')
                        p_type = p.get('type')
                        supports['state'] = 'state' in p or 'mode' in p
                        supports['speed'] = 'speed' in p
                    else:
                        # attempt to read common attributes, fallback to string
                        pid = getattr(p, 'id', None) or getattr(p, 'pumpId', None) or None
                        p_type = getattr(p, 'type', None)
                        supports['state'] = hasattr(p, 'state') or hasattr(p, 'mode')
                        supports['speed'] = hasattr(p, 'speed')

                    # Serialize 'raw' but strip embedded spa metadata to avoid duplication
                    raw_serialized = self._make_serializable(p)
                    if isinstance(raw_serialized, dict) and 'spa' in raw_serialized:
                        raw_serialized.pop('spa', None)
                    item = {"id": pid, "type": p_type, "raw": raw_serialized}
                    item['supports'] = supports
                    # advertise the pump-specific command topic so integrators
                    # and users can discover where to publish control messages
                    # T052: Use _writetopic convention instead of set_
                    try:
                        base = f"{self.config.mqtt.base_topic}/{spa_id}"
                        item['state_writetopic'] = f"{base}/pumps/{pid}/state_writetopic"
                    except Exception:
                        item['state_writetopic'] = None
                    result['pumps'].append(item)
            else:
                # Some spas return list directly or None
                if isinstance(pumps, list):
                    raw_pump_objects = pumps
                    for p in raw_pump_objects:
                        pid = p.get('id') if isinstance(p, dict) else getattr(p, 'id', None)
                        raw_serialized = self._make_serializable(p)
                        if isinstance(raw_serialized, dict) and 'spa' in raw_serialized:
                            raw_serialized.pop('spa', None)
                        item = {"id": pid, "raw": raw_serialized}
                        # T052: Use _writetopic convention instead of set_
                        try:
                            base = f"{self.config.mqtt.base_topic}/{spa_id}"
                            item['state_writetopic'] = f"{base}/pumps/{pid}/state_writetopic"
                        except Exception:
                            item['state_writetopic'] = None
                        result['pumps'].append(item)
                else:
                    raw_pump_objects = []
        except Exception as e:
            logger.debug(f"Pump probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"pumps_error: {str(e)}")

        # 3) Lights
        try:
            lights = await spa.get_lights()
            raw_light_objects = None
            if lights and isinstance(lights, dict) and 'lights' in lights:
                raw_light_objects = lights.get('lights', [])
                for l in raw_light_objects:
                    # l may be a dict or a SpaLight object
                    if isinstance(l, dict):
                        lid = l.get('id') or f"zone_{l.get('zone')}"
                        zone = l.get('zone')
                        color = l.get('color')
                        supports = {
                            'color': bool(color),
                            'brightness': 'intensity' in l or 'brightness' in l,
                        }
                        raw = self._make_serializable(l)
                    else:
                        lid = getattr(l, 'id', None) or f"zone_{getattr(l, 'zone', 'unknown')}"
                        zone = getattr(l, 'zone', None)
                        color = getattr(l, 'color', None)
                        supports = {
                            'color': getattr(l, 'color', None) is not None,
                            'brightness': hasattr(l, 'intensity') or hasattr(l, 'brightness'),
                        }
                        raw = self._make_serializable(l)

                    # Ensure per-light raw doesn't duplicate spa metadata
                    if isinstance(raw, dict) and 'spa' in raw:
                        raw.pop('spa', None)
                    item = {"id": lid, "zone": zone, "raw": raw, "supports": supports}
                    result['lights'].append(item)
            else:
                if isinstance(lights, list):
                    raw_light_objects = lights
                    for l in raw_light_objects:
                        lid = l.get('id') if isinstance(l, dict) else getattr(l, 'id', None)
                        raw_serialized = self._make_serializable(l)
                        if isinstance(raw_serialized, dict) and 'spa' in raw_serialized:
                            raw_serialized.pop('spa', None)
                        result['lights'].append({"id": lid, "raw": raw_serialized})
                else:
                    raw_light_objects = []
        except Exception as e:
            logger.debug(f"Light probe failed for spa {spa_id}: {e}")
            result['errors'].append(f"lights_error: {str(e)}")

        # 4) Non-destructive capability introspection (python-smarttub enums / options)
        try:
            # Attempt to import the upstream library and extract enums so we don't have to re-probe
            import smarttub

            pump_states = [m.name for m in smarttub.SpaPump.PumpState]
            pump_types = [m.name for m in smarttub.SpaPump.PumpType]
            light_modes = [m.name for m in smarttub.SpaLight.LightMode]

            # Put python-smarttub-derived enums into the dedicated key the user requested
            result['capabilities_python-smarttub'].update(
                {
                    "pump_states": pump_states,
                    "pump_types": pump_types,
                    "light_modes": light_modes,
                    # Reasonable assumption / hint for integrators; intensity semantics are not strictly typed
                    "light_intensity": {"min": 0, "max": 100, "example": 50},
                }
            )
        except Exception as e:  # pragma: no cover - best-effort introspection
            logger.debug(f"Could not introspect python-smarttub enums: {e}")

        # 5) Systematic light mode testing if enabled
        if getattr(self.config, 'discovery_test_all_light_modes', False):
            try:
                light_objs = raw_light_objects if 'raw_light_objects' in locals() and raw_light_objects is not None else []
                
                # Publish discovery status: testing
                try:
                    status_topic = f"{self.config.mqtt.base_topic}/{spa_id}/discovery/status"
                    mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                    if mqtt_client:
                        mqtt_client.publish(status_topic, "testing", retain=True)
                except Exception:
                    pass
                
                # Systematic testing of all light modes
                light_test_results = []
                for l_obj in light_objs:
                    zone_results = await self._test_all_light_modes(spa, l_obj, spa_id)
                    light_test_results.append(zone_results)
                
                # Store results in capabilities
                if light_test_results:
                    result['capabilities']['light_mode_tests'] = light_test_results
                
                # Publish discovery status: connected
                try:
                    status_topic = f"{self.config.mqtt.base_topic}/{spa_id}/discovery/status"
                    mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                    if mqtt_client:
                        mqtt_client.publish(status_topic, "connected", retain=True)
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Systematic light mode testing failed for spa {spa_id}: {e}")
                result.setdefault('errors', []).append(f"light_mode_tests_error: {e}")

        # Remove 'errors' key if empty
        if not result['errors']:
            result.pop('errors', None)

        return result

    def _write_yaml(self, discovery_results: Dict[str, Any]) -> None:
        # Try to persist into /config so the directory can be mounted into the container.
        config_dir = Path('/config')
        config_file = config_dir / 'discovered_items.yaml'
        
        # Fallback to local config directory for development
        local_config_dir = Path(__file__).resolve().parents[1] / 'config'
        local_config_file = local_config_dir / 'discovered_items.yaml'
        
        # Sort keys in logical order and clean up duplicates
        sorted_results = {}
        key_order = [
            'spa_id', 'discovered_at', 'capabilities', 'spa', 'heater',
            'pumps', 'lights', 'status_full', 'debug_status', 'errors',
            'reminders', 'energy_usage', 'capabilities_python-smarttub'
        ]

        for spa_id, result in discovery_results.items():
            # Sort the result keys according to our preferred order
            sorted_result = {}
            for key in key_order:
                if key in result:
                    sorted_result[key] = result[key]

            # Add any remaining keys not in our order
            for key in sorted(result.keys()):
                if key not in sorted_result:
                    sorted_result[key] = result[key]

            # Clean up duplicates: since spa_id is already the key, we can remove redundant spa info
            # Keep only essential spa info (name, model) if present
            if 'spa' in sorted_result and isinstance(sorted_result['spa'], dict):
                spa_info = sorted_result['spa']
                # Keep only essential fields, remove duplicates
                essential_spa = {}
                if 'name' in spa_info:
                    essential_spa['name'] = spa_info['name']
                if 'model' in spa_info:
                    essential_spa['model'] = spa_info['model']
                if essential_spa:
                    sorted_result['spa'] = essential_spa
                else:
                    # If no essential info, remove the spa key entirely
                    sorted_result.pop('spa', None)

            # Shorten state_writetopic paths by removing spa_id (since it's already in the parent key)
            # T052: Updated to handle _writetopic suffix instead of set_ prefix
            for component in ['pumps', 'lights']:
                if component in sorted_result and isinstance(sorted_result[component], list):
                    for item in sorted_result[component]:
                        if 'state_writetopic' in item and item['state_writetopic']:
                            # Remove spa_id from topic path: 
                            # base_topic/spa_id/component/id/state_writetopic -> component/id/state_writetopic
                            topic_parts = item['state_writetopic'].split('/')
                            if len(topic_parts) >= 4 and topic_parts[-3] == component:
                                # Reconstruct without spa_id: component/id/state_writetopic
                                item['state_writetopic'] = f"{component}/{topic_parts[-2]}/{topic_parts[-1]}"

            sorted_results[spa_id] = sorted_result

        # Save under top-level key 'discovered_items' mapping spa_id -> payload
        to_write = {"discovered_items": sorted_results}

        try:
            text = yaml.safe_dump(to_write, sort_keys=False)  # Don't sort keys again, we already did it
        except Exception as e:
            logger.error(f"Failed to serialize discovery results to YAML: {e}")
            
            # Track YAML serialization error (T058)
            if self.error_tracker and HAS_ERROR_TRACKER:
                self.error_tracker.track_error(
                    category=ErrorCategory.YAML_PARSING,
                    message=f"YAML serialization failed: {str(e)}",
                    severity=ErrorSeverity.ERROR,
                    error_code="YAML_DUMP_FAILED"
                )
            return  # Cannot proceed without serialized data
        
        # Try to write to /config first
        config_success = False
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file.write_text(text, encoding='utf-8')
            logger.info(f"Wrote discovered items to {config_file}")
            config_success = True
        except Exception as e:
            logger.debug(f"Could not write to {config_file}: {e}")
            
            # Track file write error (T058)
            if self.error_tracker and HAS_ERROR_TRACKER:
                self.error_tracker.track_error(
                    category=ErrorCategory.YAML_PARSING,
                    message=f"Failed to write YAML to {config_file}: {str(e)}",
                    severity=ErrorSeverity.WARNING,
                    error_code="YAML_WRITE_FAILED",
                    details={"file_path": str(config_file)}
                )

        # If /config failed, try local config directory
        if not config_success:
            try:
                local_config_dir.mkdir(parents=True, exist_ok=True)
                local_config_file.write_text(text, encoding='utf-8')
                logger.info(f"Wrote discovered items to {local_config_file} (fallback)")
            except Exception as e:
                logger.warning(f"Could not write to fallback location {local_config_file}: {e}")

        # Also write a copy into the repository tests/ directory so the generated
        # discovery output is visible to developers running in this workspace.
        try:
            repo_path = Path(__file__).resolve().parents[2] / 'tests' / 'discovered_items.generated.yaml'
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            repo_path.write_text(text, encoding='utf-8')
            logger.info(f"Wrote discovered items copy to {repo_path}")
        except Exception:
            # Do not fail the main flow if writing into the workspace fails
            logger.debug("Failed to write discovered items into workspace tests directory")

    def _make_serializable(self, obj: Any) -> Any:
        """Return a JSON/YAML-serializable representation of obj.

        Handles dicts, lists, simple scalars, and attempts to turn objects into
        dicts via to_dict, __dict__ or attribute inspection. Falls back to str().
        """
        # Scalars
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj

        # dict-like
        if isinstance(obj, dict):
            return {str(k): self._make_serializable(v) for k, v in obj.items()}

        # list/tuple
        if isinstance(obj, (list, tuple)):
            return [self._make_serializable(v) for v in obj]

        # Objects from python-smarttub may have to_dict or simple attributes
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
            try:
                return self._make_serializable(obj.to_dict())
            except Exception:
                pass

        # Attempt __dict__ serialization
        if hasattr(obj, '__dict__'):
            try:
                return self._make_serializable({k: v for k, v in vars(obj).items() if not k.startswith('_')})
            except Exception:
                pass

        # Fallback: string representation
        try:
            return str(obj)
        except Exception:
            return None

    async def _test_all_light_modes(self, spa: Any, light_obj: Any, spa_id: str) -> Dict[str, Any]:
        """Systematically test all light modes and brightness levels for a specific light zone.
        
        Args:
            spa: Spa object
            light_obj: Light object to test
            spa_id: Spa ID for MQTT publishing
            
        Returns:
            Dict with test results for this zone
        """
        zone = getattr(light_obj, 'zone', None)
        zone_id = getattr(light_obj, 'id', f"zone_{zone}")
        zone_type = getattr(light_obj, 'zone_type', None)
        
        logger.info(f"Starting exhaustive light mode testing for {spa_id} zone {zone}")
        
        result: Dict[str, Any] = {
            "id": zone_id,
            "zone": zone,
            "zone_type": str(zone_type) if zone_type else None,
            "supported_modes": {},
            "unsupported_modes": [],
            "test_summary": {
                "total_tests": 0,
                "successful_tests": 0,
                "failed_tests": 0,
            }
        }
        
        # Capture original state to restore later
        try:
            orig_mode = getattr(light_obj, 'mode', None)
            orig_intensity = getattr(light_obj, 'intensity', None)
            # Handle both string and enum mode values
            if hasattr(orig_mode, 'name'):
                orig_mode_name = orig_mode.name
            else:
                orig_mode_name = str(orig_mode) if orig_mode else None
        except Exception as e:
            logger.debug(f"Failed to capture original light state: {e}")
            orig_mode_name = None
            orig_intensity = 50
        
        # Optimized two-phase testing:
        # Phase 1: Test every mode at a canonical brightness to quickly filter supported modes.
        #   - OFF -> test at 0%
        #   - others -> test at 100%
        # Phase 2: For modes that passed, test remaining brightness levels [0,25,50,75]
        phase1_candidates: List[str] = []

        total_phase1 = len(self.ALL_LIGHT_MODES)
        # Phase 1
        for idx, mode_name in enumerate(self.ALL_LIGHT_MODES, 1):
            # pick canonical brightness
            if mode_name == "OFF":
                brightness = 0
            else:
                brightness = 100

            # publish progress
            try:
                base_topic = self.config.mqtt.base_topic
                progress_topic = f"{base_topic}/{spa_id}/discovery/progress"
                detail_topic = f"{base_topic}/{spa_id}/discovery/detail"
                mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                if mqtt_client:
                    mqtt_client.publish(progress_topic, f"{idx}/{total_phase1}", retain=False)
                    mqtt_client.publish(detail_topic, f"Phase1: Testing zone {zone}: {mode_name} @ {brightness}%", retain=False)
            except Exception:
                pass

            result["test_summary"]["total_tests"] += 1
            ok = await self._test_light_mode(spa, light_obj, mode_name, brightness, zone, spa_id)
            if ok:
                phase1_candidates.append(mode_name)
                result["test_summary"]["successful_tests"] += 1
            else:
                result["test_summary"]["failed_tests"] += 1

            # brief pause between phase1 tests
            await asyncio.sleep(self.LIGHT_TEST_DELAY_SECONDS)

        # Phase 2: for each candidate, test additional brightness levels (exclude 100)
        secondary_levels = [b for b in self.BRIGHTNESS_LEVELS if b != 100]
        # total tests for progress display
        total_phase2 = sum(len(secondary_levels) if m != "OFF" else 1 for m in phase1_candidates)
        pcount = 0
        for mode_name in phase1_candidates:
            mode_results: Dict[str, Any] = {"brightness_support": [], "rgb": None}
            if mode_name == "OFF":
                # already tested OFF at 0% in phase1
                mode_results["brightness_support"].append(0)
                result["supported_modes"][mode_name] = mode_results
                continue

            for brightness in secondary_levels:
                pcount += 1
                # publish progress (phase2)
                try:
                    base_topic = self.config.mqtt.base_topic
                    progress_topic = f"{base_topic}/{spa_id}/discovery/progress"
                    detail_topic = f"{base_topic}/{spa_id}/discovery/detail"
                    mqtt_client = getattr(self.topic_mapper, 'mqtt_client', None)
                    if mqtt_client:
                        mqtt_client.publish(progress_topic, f"{pcount}/{total_phase2}", retain=False)
                        mqtt_client.publish(detail_topic, f"Phase2: Testing zone {zone}: {mode_name} @ {brightness}%", retain=False)
                except Exception:
                    pass

                result["test_summary"]["total_tests"] += 1
                ok = await self._test_light_mode(spa, light_obj, mode_name, brightness, zone, spa_id)
                if ok:
                    mode_results["brightness_support"].append(brightness)
                    result["test_summary"]["successful_tests"] += 1
                    # For WHITE mode, capture RGB values once
                    if mode_name == "WHITE" and mode_results["rgb"] is None:
                        try:
                            lights = await spa.get_lights()
                            if lights:
                                # get_lights() returns a list directly
                                for l in lights:
                                    if getattr(l, 'zone', None) == zone:
                                        mode_results["rgb"] = {
                                            "red": getattr(l, 'red', 0),
                                            "green": getattr(l, 'green', 0),
                                            "blue": getattr(l, 'blue', 0),
                                            "white": getattr(l, 'white', 0),
                                        }
                                        break
                        except Exception:
                            pass
                else:
                    result["test_summary"]["failed_tests"] += 1

                await asyncio.sleep(self.LIGHT_TEST_DELAY_SECONDS)

            # If canonical 100% succeeded, include 100 in brightness support
            if 100 not in mode_results["brightness_support"]:
                mode_results["brightness_support"].append(100)

            # sort levels
            mode_results["brightness_support"] = sorted(set(mode_results["brightness_support"]))

            result["supported_modes"][mode_name] = mode_results

        # Phase 3: Test RGB color capabilities for FULL_DYNAMIC_RGB mode
        if "FULL_DYNAMIC_RGB" in result["supported_modes"]:
            logger.info(f"Phase 3: Testing RGB color capabilities for zone {zone}")
            rgb_test_result = await self._test_rgb_color_capability(spa, zone, spa_id)
            if rgb_test_result:
                result["supported_modes"]["FULL_DYNAMIC_RGB"]["rgb_capability"] = rgb_test_result

        # Any mode that was not in phase1_candidates is unsupported
        for m in self.ALL_LIGHT_MODES:
            if m not in result["supported_modes"]:
                result["unsupported_modes"].append(m)
        
        # Always turn lights OFF after discovery test (safe default)
        try:
            logger.info(f"Turning off zone {zone} after discovery test")
            await spa.request("PATCH", f"lights/{zone}", {
                "mode": "OFF",
                "intensity": 0
            })
            await asyncio.sleep(3)
            logger.info(f"Zone {zone} turned off successfully")
        except Exception as e:
            logger.error(f"Failed to turn off lights for zone {zone}: {e}")
            # Try alternative method
            try:
                set_mode_fn = getattr(light_obj, 'set_mode', None)
                if callable(set_mode_fn):
                    maybe = set_mode_fn("OFF", 0)
                    if asyncio.iscoroutine(maybe):
                        await asyncio.wait_for(maybe, timeout=self.config.safety.command_timeout_seconds)
                    logger.info(f"Zone {zone} turned off via fallback method")
            except Exception as e2:
                logger.error(f"Fallback method also failed for zone {zone}: {e2}")
        
        logger.info(f"Completed light mode testing for zone {zone}: "
                   f"{result['test_summary']['successful_tests']}/{result['test_summary']['total_tests']} successful")
        
        return result

    async def _test_rgb_color_capability(self, spa: Any, zone: int, spa_id: str) -> Optional[Dict[str, Any]]:
        """Test if RGB color control works for FULL_DYNAMIC_RGB mode.
        
        Tests:
        1. Set pure RED (255,0,0) and verify
        2. Set pure GREEN (0,255,0) and verify
        3. Set pure BLUE (0,0,255) and verify
        4. Set WHITE (255,255,255) and verify
        
        Returns:
            Dict with color test results or None if tests failed
        """
        logger.info(f"Testing RGB color capability for zone {zone}")
        
        test_colors = [
            ("RED", {"red": 255, "green": 0, "blue": 0}),
            ("GREEN", {"red": 0, "green": 255, "blue": 0}),
            ("BLUE", {"red": 0, "green": 0, "blue": 255}),
            ("WHITE", {"red": 255, "green": 255, "blue": 255}),
        ]
        
        results = {
            "color_control_works": False,
            "max_rgb_value": 0,
            "tested_colors": {}
        }
        
        try:
            # First, ensure we're in FULL_DYNAMIC_RGB mode
            await spa.request("PATCH", f"lights/{zone}", {"mode": "FULL_DYNAMIC_RGB"})
            await asyncio.sleep(5)
            
            successful_tests = 0
            
            for color_name, color_values in test_colors:
                try:
                    # Set the color
                    await spa.request("PATCH", f"lights/{zone}", {"color": color_values})
                    await asyncio.sleep(5)
                    
                    # Read back the value
                    lights = await spa.get_lights()
                    if lights:
                        for light in lights:
                            if getattr(light, 'zone', None) == zone:
                                actual_r = getattr(light, 'red', 0)
                                actual_g = getattr(light, 'green', 0)
                                actual_b = getattr(light, 'blue', 0)
                                
                                # Check if color was set correctly (allow small tolerance)
                                tolerance = 5
                                r_match = abs(actual_r - color_values["red"]) <= tolerance
                                g_match = abs(actual_g - color_values["green"]) <= tolerance
                                b_match = abs(actual_b - color_values["blue"]) <= tolerance
                                
                                if r_match and g_match and b_match:
                                    successful_tests += 1
                                    results["tested_colors"][color_name] = {
                                        "requested": color_values,
                                        "actual": {"red": actual_r, "green": actual_g, "blue": actual_b},
                                        "success": True
                                    }
                                    
                                    # Track maximum RGB value actually achieved
                                    max_val = max(actual_r, actual_g, actual_b)
                                    if max_val > results["max_rgb_value"]:
                                        results["max_rgb_value"] = max_val
                                else:
                                    results["tested_colors"][color_name] = {
                                        "requested": color_values,
                                        "actual": {"red": actual_r, "green": actual_g, "blue": actual_b},
                                        "success": False
                                    }
                                
                                logger.debug(f"Color test {color_name}: requested={color_values}, actual=R{actual_r} G{actual_g} B{actual_b}")
                                break
                
                except Exception as e:
                    logger.debug(f"Error testing color {color_name}: {e}")
                    results["tested_colors"][color_name] = {
                        "requested": color_values,
                        "error": str(e),
                        "success": False
                    }
            
            # Consider color control working if at least 3 out of 4 colors work
            if successful_tests >= 3:
                results["color_control_works"] = True
                logger.info(f"✓ RGB color control works for zone {zone} ({successful_tests}/4 colors successful, max RGB value: {results['max_rgb_value']})")
            else:
                logger.info(f"✗ RGB color control does not work reliably for zone {zone} ({successful_tests}/4 colors successful)")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to test RGB color capability for zone {zone}: {e}")
            return None

    async def _test_light_mode(self, spa: Any, light_obj: Any, mode_name: str, brightness: int, 
                               zone: int, spa_id: str) -> bool:
        """Test a specific light mode/brightness combination.
        
        Args:
            spa: Spa object
            light_obj: Light object
            mode_name: Name of the light mode to test
            brightness: Brightness level (0-100)
            zone: Zone number
            spa_id: Spa ID
            
        Returns:
            True if test successful, False otherwise
        """
        try:
            # Import LightMode enum
            import smarttub
            
            # Check if mode exists in enum
            try:
                mode_enum = getattr(smarttub.SpaLight.LightMode, mode_name, None)
                if mode_enum is None:
                    logger.debug(f"Mode {mode_name} not found in LightMode enum, skipping")
                    return False
            except Exception as e:
                logger.debug(f"Failed to check LightMode enum for {mode_name}: {e}")
                return False
            
            # WORKAROUND: Use direct API call instead of set_mode() to avoid python-smarttub bug
            # The library's set_mode() calls _wait_for_state_change() which fails when state.lights is None
            # We'll use spa.request() directly and verify manually afterwards
            try:
                body = {
                    "intensity": brightness,
                    "mode": mode_name,  # API accepts string, not enum
                }
                await spa.request("PATCH", f"lights/{zone}", body)
                logger.debug(f"PATCH lights/{zone} successful with mode={mode_name}, intensity={brightness}")
            except smarttub.APIError as e:
                # API rejected this mode/brightness combination (e.g., 400 Bad Request)
                logger.debug(f"API rejected mode {mode_name} @ {brightness}%: {e}")
                return False
            except Exception as e:
                logger.debug(f"Unexpected error setting mode {mode_name} @ {brightness}%: {e}")
                return False
            
            # Wait longer for API to propagate (we're not using wait_for_state_change anymore)
            await asyncio.sleep(5)
            
            # Verify by calling get_lights() with retry (API sometimes returns None temporarily)
            light_list = None
            for retry in range(5):
                try:
                    lights = await spa.get_lights()
                    if lights and len(lights) > 0:
                        light_list = lights
                        break
                except Exception as e:
                    logger.debug(f"get_lights() raised exception: {e}, retry {retry+1}/5")
                
                logger.debug(f"get_lights() returned None or empty, retry {retry+1}/5")
                await asyncio.sleep(2)
            
            if not light_list:
                logger.warning(f"get_lights() returned no data after 5 retries for zone {zone}")
                return False
            
            # DEBUG: Check light_list type and length
            logger.info(f"DEBUG: light_list type={type(light_list)}, value={light_list}")
            
            # Find our zone in the results
            for l in light_list:
                if getattr(l, 'zone', None) == zone:
                    # Check if mode matches
                    current_mode = getattr(l, 'mode', None)
                    # Handle both string and enum mode values
                    if hasattr(current_mode, 'name'):
                        current_mode_name = current_mode.name
                    else:
                        current_mode_name = str(current_mode) if current_mode else None
                    
                    current_intensity = getattr(l, 'intensity', None)
                    
                    # Verify mode matches (for OFF, we expect mode to be OFF regardless of brightness)
                    if mode_name == "OFF":
                        if current_mode_name == "OFF":
                            logger.debug(f"✓ Zone {zone} mode test successful: {mode_name}")
                            return True
                    else:
                        # For non-OFF modes, check both mode and brightness
                        if current_mode_name == mode_name and current_intensity == brightness:
                            logger.debug(f"✓ Zone {zone} mode test successful: {mode_name} @ {brightness}%")
                            return True
                        elif current_mode_name == mode_name:
                            # Mode matches but brightness doesn't - still count as supported mode
                            logger.debug(f"✓ Zone {zone} mode test partial success: {mode_name} (brightness mismatch: {current_intensity} vs {brightness})")
                            return True
                    
                    logger.debug(f"✗ Zone {zone} mode test failed: expected {mode_name}@{brightness}%, got {current_mode_name}@{current_intensity}%")
                    return False
            
            logger.debug(f"Zone {zone} not found in get_lights() response")
            return False
            
        except asyncio.TimeoutError:
            logger.debug(f"Timeout testing mode {mode_name} @ {brightness}% for zone {zone}")
            return False
        except Exception as e:
            import traceback
            logger.error(f"Error testing mode {mode_name} @ {brightness}% for zone {zone}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
