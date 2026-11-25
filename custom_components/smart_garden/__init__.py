"""Smart Garden: zones, soil sensors and watering controls from a Smart Garden controller."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv

from .api import GardenApi, GardenAuthError, GardenError
from .const import CONF_KEY, DOMAIN
from .coordinator import GardenCoordinator
from .panel import async_setup_frontend, register_panels, remove_panels

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

type GardenConfigEntry = ConfigEntry[GardenCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Once per Home Assistant start: the dashboard's files and its websocket command."""
    await async_setup_frontend(hass)
    return True


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
    coordinator.panels = await register_panels(hass, entry, info)
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> bool:
    remove_panels(hass, getattr(entry.runtime_data, "panels", []))
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _options_changed(hass: HomeAssistant, entry: GardenConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


