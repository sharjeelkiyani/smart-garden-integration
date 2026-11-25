"""Sensors: soil moisture and watering per zone; garden sensors and their batteries; what's watering, time left,
next run."""
from __future__ import annotations

import re
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import GardenConfigEntry
from .entity import GardenEntity

KINDS = {
    "moisture": (PERCENTAGE, SensorDeviceClass.MOISTURE),
    "humidity": (PERCENTAGE, SensorDeviceClass.HUMIDITY),
    "temperature": (UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
}


async def async_setup_entry(hass: HomeAssistant, entry: GardenConfigEntry, add: AddEntitiesCallback) -> None:
    c = entry.runtime_data
    ents: list[SensorEntity] = []
    for z in c.info["zones"]:
        ents += [ZoneMoisture(c, z["id"]), ZoneToday(c, z["id"]), ZoneLeft(c, z["id"])]
    for s in c.info["sensors"]:
        if s["kind"] in KINDS:
            ents.append(GardenSensor(c, s))
    ents += [SensorBattery(c, b) for b in c.info.get("batteries", [])]
    ents += [WateringNow(c), TimeLeft(c), NextRun(c), WaterToday(c)]
    add(ents)


class ZoneMoisture(GardenEntity, SensorEntity):
    _attr_translation_key = "soil_moisture"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.MOISTURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, zone_id):
        super().__init__(c, f"zone_{zone_id}_moisture", zone_id)

    @property
    def native_value(self):
        return self.zone_state.get("moisture")


class ZoneToday(GardenEntity, SensorEntity):
    _attr_translation_key = "watered_today"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-outline"

    def __init__(self, c, zone_id):
        super().__init__(c, f"zone_{zone_id}_today", zone_id)

    @property
    def native_value(self):
        return self.zone_state.get("today_min")


class ZoneLeft(GardenEntity, SensorEntity):
    _attr_translation_key = "time_left"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_icon = "mdi:timer-sand"

    def __init__(self, c, zone_id):
        super().__init__(c, f"zone_{zone_id}_left", zone_id)

    @property
    def native_value(self):
        return self.zone_state.get("left_min", 0)


class GardenSensor(GardenEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c, s):
        super().__init__(c, f"sensor_{s['id']}")
        self._sid = str(s["id"])
        self._attr_name = s["name"]
        self._attr_native_unit_of_measurement, self._attr_device_class = KINDS[s["kind"]]

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("sensors", {}).get(self._sid)


def battery_slug(key: str) -> str:
    """zb1:Soil 1 -> zb1_soil_1 (stable part of the unique id)."""
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


class SensorBattery(GardenEntity, SensorEntity):
    """Battery of a Zigbee sensor device (one per device, named after the sensors on it)."""
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, c, b):
        super().__init__(c, f"battery_{battery_slug(b['key'])}")
        self._key = b["key"]
        self._attr_name = f"{b['name']} battery"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("batteries", {}).get(self._key)


class WateringNow(GardenEntity, SensorEntity):
    _attr_translation_key = "watering_now"
    _attr_icon = "mdi:water"

    def __init__(self, c):
        super().__init__(c, "watering_now")

    @property
    def native_value(self):
        return ((self.coordinator.data or {}).get("now") or {}).get("zone")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {"queue": d.get("queue", []), "valves_not_confirmed_off": d.get("pending_off", [])}


class TimeLeft(GardenEntity, SensorEntity):
    _attr_translation_key = "time_left"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_icon = "mdi:timer-sand"

    def __init__(self, c):
        super().__init__(c, "time_left")

    @property
    def native_value(self):
        return ((self.coordinator.data or {}).get("now") or {}).get("left_min", 0)


class NextRun(GardenEntity, SensorEntity):
    _attr_translation_key = "next_run"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, c):
        super().__init__(c, "next_run")

    @property
    def native_value(self) -> datetime | None:
        v = (self.coordinator.data or {}).get("next_run")
        return dt_util.parse_datetime(v) if v else None


class WaterToday(GardenEntity, SensorEntity):
    _attr_translation_key = "water_today"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-outline"

    def __init__(self, c):
        super().__init__(c, "water_today")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("today_min")
