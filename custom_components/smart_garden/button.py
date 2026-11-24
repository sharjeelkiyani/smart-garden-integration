"""Buttons: stop all watering; run each schedule now."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenConfigEntry
from .api import GardenError
from .entity import GardenEntity


async def async_setup_entry(hass: HomeAssistant, entry: GardenConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    add([StopAll(c)] + [RunSchedule(c, s) for s in c.info["schedules"]])


class StopAll(GardenEntity, ButtonEntity):
    _attr_translation_key = "stop_all"
    _attr_icon = "mdi:stop-circle"

    def __init__(self, c):
        super().__init__(c, "stop_all")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.stop_all()
        except GardenError as err:
            raise HomeAssistantError(f"Smart Garden: {err}") from err
        await self.coordinator.async_request_refresh()


class RunSchedule(GardenEntity, ButtonEntity):
    _attr_translation_key = "run_schedule"
    _attr_icon = "mdi:play-circle"

    def __init__(self, c, s):
        super().__init__(c, f"schedule_{s['id']}")
        self._schedule_id = s["id"]
        self._attr_translation_placeholders = {"name": s["name"]}

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.run_schedule(self._schedule_id)
        except GardenError as err:
            raise HomeAssistantError(f"Smart Garden: {err}") from err
        await self.coordinator.async_request_refresh()
