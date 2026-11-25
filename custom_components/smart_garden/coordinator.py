"""Polls the garden every 10 seconds; re-reads its zones, sensors and schedules every few minutes."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GardenApi, GardenAuthError, GardenError
from .const import DOMAIN, INFO_EVERY, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


def layout(info: dict) -> tuple:
    """What entities exist: if this changes, the integration reloads to add/remove them."""
    return (tuple((z["id"], z["name"]) for z in info.get("zones", [])),
            tuple((s["id"], s["name"], s["kind"]) for s in info.get("sensors", [])),
            tuple((s["id"], s["name"]) for s in info.get("schedules", [])),
            tuple((b["key"], b["name"]) for b in info.get("batteries", [])),
            info.get("role"))


class GardenCoordinator(DataUpdateCoordinator[dict]):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: GardenApi, info: dict) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL, config_entry=entry)
        self.api = api
        self.info = info
        self._polls = 0
        self.garden_device_id: str | None = None
        self.panels: list[str] = []          # sidebar paths this garden added

    @property
    def garden_id(self) -> str:
        return self.info["id"]

    @property
    def is_admin(self) -> bool:
        return self.info.get("role") == "admin"

    def zone(self, zone_id: int) -> dict:
        return next((z for z in self.info["zones"] if z["id"] == zone_id), {})

    async def _async_update_data(self) -> dict:
        try:
            self._polls += 1
            if self._polls % INFO_EVERY == 0:
                info = await self.api.info()
                if layout(info) != layout(self.info):
                    _LOGGER.info("Smart Garden zones, sensors or schedules changed - reloading")
                    self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
                self.info = info
            return await self.api.state()
        except GardenAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GardenError as err:
            raise UpdateFailed(str(err)) from err
