"""Battery level sensor for Rubik's Connected."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ADDRESS, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RubiksBatterySensor(coordinator, entry)])


class RubiksBatterySensor(SensorEntity):
    _attr_device_class  = SensorDeviceClass.BATTERY
    _attr_state_class   = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_has_entity_name = True
    _attr_name = "Battery"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry       = entry
        address           = entry.data[CONF_ADDRESS]
        self._attr_unique_id  = f"{address}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Rubik's / GoCube",
            model="Rubik's Connected",
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_battery_listener(self._on_battery)
        self._coordinator.register_connection_listener(self._on_connection)
        # Reflect any battery level already received
        if self._coordinator.battery_level is not None:
            self._attr_native_value = self._coordinator.battery_level

    def _on_battery(self, level: int) -> None:
        self._attr_native_value = level
        self.async_write_ha_state()

    def _on_connection(self, connected: bool) -> None:
        self._attr_available = connected
        self.async_write_ha_state()
