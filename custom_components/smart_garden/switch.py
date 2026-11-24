"""Switches: water each zone; (admin key) zone on/off and automatic watering."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenConfigEntry
from .api import GardenError
from .entity import GardenEntity

SERVICE_WATER = "water"


async def async_setup_entry(hass: HomeAssistant, entry: GardenConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    entities: list[SwitchEntity] = [ZoneWater(c, z["id"]) for z in c.info["zones"]]
    if c.is_admin:
        entities += [ZoneEnabled(c, z["id"]) for z in c.info["zones"]]
        entities.append(Automatic(c))
    add(entities)
    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_WATER,
        {vol.Optional("minutes"): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=240)),
         vol.Optional("until_soil", default=False): cv.boolean},
        "async_water")


async def _do(coro) -> None:
    try:
        await coro
    except GardenError as err:
        raise HomeAssistantError(f"Smart Garden: {err}") from err


class ZoneWater(GardenEntity, SwitchEntity):
    """On = water for the zone's usual minutes (waits its turn if another zone is watering). Off = stop."""
    _attr_translation_key = "water"
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator, zone_id: int) -> None:
        super().__init__(coordinator, f"zone_{zone_id}_water", zone_id)

    @property
    def is_on(self) -> bool:
        return bool(self.zone_state.get("on") or self.zone_state.get("queued"))

    @property
    def available(self) -> bool:
        return super().available and self.zone_state.get("enabled", True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"watering": bool(self.zone_state.get("on")), "queued": bool(self.zone_state.get("queued")),
                "minutes_left": self.zone_state.get("left_min"), "zone_id": self.zone_id}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await _do(self.coordinator.api.water(self.zone_id))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await _do(self.coordinator.api.stop_zone(self.zone_id))
        await self.coordinator.async_request_refresh()

    async def async_water(self, minutes: float | None = None, until_soil: bool = False) -> None:
        await _do(self.coordinator.api.water(self.zone_id, minutes, until_soil))
        await self.coordinator.async_request_refresh()


class _NotAZone:
    async def async_water(self, minutes: float | None = None, until_soil: bool = False) -> None:
        raise HomeAssistantError("Pick a zone's Water switch to water it.")


class ZoneEnabled(_NotAZone, GardenEntity, SwitchEntity):
    """Off = the zone never waters (schedules, top-ups or by hand) until turned back on."""
    _attr_translation_key = "zone_enabled"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:power"

    def __init__(self, coordinator, zone_id: int) -> None:
        super().__init__(coordinator, f"zone_{zone_id}_enabled", zone_id)

    @property
    def is_on(self) -> bool:
        return bool(self.zone_state.get("enabled", True))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await _do(self.coordinator.api.zone_enabled(self.zone_id, True))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await _do(self.coordinator.api.zone_enabled(self.zone_id, False))
        await self.coordinator.async_request_refresh()


class Automatic(_NotAZone, GardenEntity, SwitchEntity):
    _attr_translation_key = "automatic"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "automatic")

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("automatic"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await _do(self.coordinator.api.automatic(True))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await _do(self.coordinator.api.automatic(False))
        await self.coordinator.async_request_refresh()
