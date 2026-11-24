"""Smart Garden: zones, soil sensors and watering controls from a Smart Garden controller."""
from __future__ import annotations

import logging

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GardenApi, GardenAuthError, GardenError
from .const import DOMAIN, CONF_KEY, CONF_PANEL_URL, CONF_SIDEBAR, PANEL_PATH
from .coordinator import GardenCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

type GardenConfigEntry = ConfigEntry[GardenCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> bool:
    api = GardenApi(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_KEY])
    try:
        info = await api.info()
    except GardenAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except GardenError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = GardenCoordinator(hass, entry, api, info)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    garden = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, info["id"])}, name=info.get("name") or "Garden",
        manufacturer="Smart Garden", model="Garden controller",
        configuration_url=info.get("app_url") or entry.data[CONF_URL])
    coordinator.garden_device_id = garden.id
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _panel(hass, entry, info)
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> bool:
    _remove_panel(hass, entry)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _options_changed(hass: HomeAssistant, entry: GardenConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _panel_path(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """smart-garden for the first garden, smart-garden-<id> for any others."""
    entries = sorted(hass.config_entries.async_entries("smart_garden"), key=lambda e: e.entry_id)
    return PANEL_PATH if entries and entries[0].entry_id == entry.entry_id else f"{PANEL_PATH}-{entry.entry_id[:6]}"


def _panel(hass: HomeAssistant, entry: ConfigEntry, info: dict) -> None:
    """The full Smart Garden app as a sidebar item (a web page inside Home Assistant)."""
    if not entry.options.get(CONF_SIDEBAR, True):
        return
    url = entry.options.get(CONF_PANEL_URL) or info.get("app_url") or entry.data[CONF_URL]
    try:
        frontend.async_register_built_in_panel(
            hass, "iframe", sidebar_title=info.get("name") or "Smart Garden", sidebar_icon="mdi:sprinkler-variant",
            frontend_url_path=_panel_path(hass, entry), config={"url": url}, require_admin=False,
            update=True)
    except ValueError as err:          # path taken by something else
        _LOGGER.warning("Smart Garden sidebar item not added: %s", err)


def _remove_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    try:
        frontend.async_remove_panel(hass, _panel_path(hass, entry), warn_if_unknown=False)
    except TypeError:                  # older Home Assistant without warn_if_unknown
        frontend.async_remove_panel(hass, _panel_path(hass, entry))
