"""Shared entity base: one device for the garden, one device per zone (linked to the garden)."""
from __future__ import annotations

import inspect

from homeassistant.helpers.device_registry import DeviceInfo, DeviceRegistry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenCoordinator

# Home Assistant 2026.x links child devices by device id; older versions by identifiers.
_VIA_ID = "via_device_id" in inspect.signature(DeviceRegistry.async_get_or_create).parameters


class GardenEntity(CoordinatorEntity[GardenCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: GardenCoordinator, key: str, zone_id: int | None = None) -> None:
        super().__init__(coordinator)
        gid = coordinator.garden_id
        self.zone_id = zone_id
        self._attr_unique_id = f"{gid}_{key}"
        info = coordinator.info
        if zone_id is None:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, gid)}, name=info.get("name") or "Garden", manufacturer="Smart Garden",
                model="Garden controller", configuration_url=info.get("app_url") or coordinator.api.url)
        else:
            zone = coordinator.zone(zone_id)
            link = ({"via_device_id": coordinator.garden_device_id} if _VIA_ID and coordinator.garden_device_id
                    else {"via_device": (DOMAIN, gid)})
            self._attr_device_info = DeviceInfo(  # type: ignore[typeddict-item]
                identifiers={(DOMAIN, f"{gid}_zone_{zone_id}")}, name=zone.get("name") or f"Zone {zone_id}",
                manufacturer="Smart Garden", model=f"Zone · {zone.get('plant') or 'garden'}", **link)

    @property
    def zone_state(self) -> dict:
        return (self.coordinator.data or {}).get("zones", {}).get(str(self.zone_id), {})
