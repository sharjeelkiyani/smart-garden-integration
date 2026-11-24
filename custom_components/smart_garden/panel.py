"""The Smart Garden dashboard in Home Assistant's sidebar.

A page drawn by Home Assistant itself from this integration's entities (no web page from the garden,
so it works over HTTPS or not, at home or away, with no second sign-in). Optionally also the full
Smart Garden app as a web-page item, when the options give an address on the same site.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_PANEL_URL, CONF_SIDEBAR, DOMAIN, PANEL_PATH, STATIC_URL

try:                                   # Home Assistant 2026.x validates with probatio
    import probatio as schema_lib
except ImportError:                    # older versions: voluptuous
    import voluptuous as schema_lib

_LOGGER = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).parent / "frontend"
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]


async def async_setup_frontend(hass: HomeAssistant) -> None:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)])
    websocket_api.async_register_command(hass, ws_layout)


def _paths(hass: HomeAssistant, entry: ConfigEntry) -> tuple[str, str]:
    """(dashboard path, app page path): smart-garden for the first garden, smart-garden-<id> for others."""
    entries = sorted(hass.config_entries.async_entries(DOMAIN), key=lambda e: e.entry_id)
    base = PANEL_PATH if entries and entries[0].entry_id == entry.entry_id else f"{PANEL_PATH}-{entry.entry_id[:6]}"
    return base, f"{base}-app"


async def register_panels(hass: HomeAssistant, entry: ConfigEntry, info: dict) -> None:
    dash, app = _paths(hass, entry)
    name = info.get("name") or "Smart Garden"
    if entry.options.get(CONF_SIDEBAR, True):
        try:
            await panel_custom.async_register_panel(
                hass, frontend_url_path=dash, webcomponent_name="smart-garden-panel",
                sidebar_title=name, sidebar_icon="mdi:sprinkler-variant",
                module_url=f"{STATIC_URL}/smart-garden-panel.js?v={VERSION}",
                config={"entry_id": entry.entry_id}, require_admin=False)
        except ValueError as err:
            _LOGGER.warning("Smart Garden dashboard not added to the sidebar: %s", err)
    if url := entry.options.get(CONF_PANEL_URL):
        try:
            frontend.async_register_built_in_panel(
                hass, "iframe", sidebar_title=f"{name} app", sidebar_icon="mdi:open-in-app",
                frontend_url_path=app, config={"url": url}, require_admin=False, update=True)
        except ValueError as err:
            _LOGGER.warning("Smart Garden app page not added to the sidebar: %s", err)


def remove_panels(hass: HomeAssistant, entry: ConfigEntry) -> None:
    for path in _paths(hass, entry):
        if path in hass.data.get("frontend_panels", {}):
            frontend.async_remove_panel(hass, path)


# ---- what the dashboard shows: this garden's entities, by role -------------------------------
def layout(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = entry.runtime_data
    info = coordinator.info
    gid = info["id"]
    reg = er.async_get(hass)
    ids = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)
           if not e.disabled_by}

    def eid(key: str) -> str | None:
        return ids.get(f"{gid}_{key}")

    zones = [{"id": z["id"], "name": z["name"], "plant": z.get("plant"), "max_minutes": z["max_minutes"],
              "default_minutes": z["default_minutes"], "water": eid(f"zone_{z['id']}_water"),
              "enabled": eid(f"zone_{z['id']}_enabled"), "moisture": eid(f"zone_{z['id']}_moisture"),
              "today": eid(f"zone_{z['id']}_today"), "left": eid(f"zone_{z['id']}_left")}
             for z in info["zones"]]
    sensors = [{"name": s["name"], "kind": s["kind"], "entity": eid(f"sensor_{s['id']}")} for s in info["sensors"]]
    schedules = [{"name": s["name"], "enabled": s["enabled"], "button": eid(f"schedule_{s['id']}")}
                 for s in info["schedules"]]
    garden = {k: eid(k) for k in ("watering_now", "time_left", "next_run", "water_today", "raining",
                                  "boards_online", "automatic", "stop_all")}
    return {"entry_id": entry.entry_id, "name": info.get("name") or "Garden", "admin": coordinator.is_admin,
            "app_url": entry.options.get(CONF_PANEL_URL) or info.get("app_url") or "",
            "zones": zones, "sensors": sensors, "schedules": schedules, "garden": garden}


@websocket_api.websocket_command({
    schema_lib.Required("type"): "smart_garden/layout",
    schema_lib.Optional("entry_id"): str,
})
@callback
def ws_layout(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The gardens set up in Home Assistant and which entity shows what (read-only)."""
    entries = [e for e in hass.config_entries.async_entries(DOMAIN)
               if getattr(e, "runtime_data", None) is not None]
    if msg.get("entry_id"):
        entries = [e for e in entries if e.entry_id == msg["entry_id"]] or entries
    connection.send_result(msg["id"], {"gardens": [layout(hass, e) for e in entries]})
