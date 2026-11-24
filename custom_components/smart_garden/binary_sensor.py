"""Binary sensors: raining, relay boards online, rain and alarm sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenConfigEntry
from .entity import GardenEntity


async def async_setup_entry(hass: HomeAssistant, entry: GardenConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    ents: list[BinarySensorEntity] = [Raining(c), BoardsOnline(c)]
    ents += [GardenBinary(c, s) for s in c.info["sensors"] if s["kind"] in ("rain", "alarm")]
    add(ents)


class Raining(GardenEntity, BinarySensorEntity):
    _attr_translation_key = "raining"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, c):
        super().__init__(c, "raining")

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("raining"))


class BoardsOnline(GardenEntity, BinarySensorEntity):
    _attr_translation_key = "boards_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, c):
        super().__init__(c, "boards_online")

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("boards_online"))


class GardenBinary(GardenEntity, BinarySensorEntity):
    def __init__(self, c, s):
        super().__init__(c, f"sensor_{s['id']}")
        self._sid = str(s["id"])
        self._attr_name = s["name"]
        self._attr_device_class = (BinarySensorDeviceClass.MOISTURE if s["kind"] == "rain"
                                   else BinarySensorDeviceClass.PROBLEM)

    @property
    def is_on(self):
        return bool((self.coordinator.data or {}).get("sensors", {}).get(self._sid))
