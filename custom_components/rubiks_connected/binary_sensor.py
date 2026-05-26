"""Binary sensors for Rubik's Connected."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    async_add_entities([
        RubiksIsSolvedSensor(coordinator, entry),
        RubiksConnectivitySensor(coordinator, entry),
    ])


class RubiksIsSolvedSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Solved"
    _attr_icon = "mdi:cube-outline"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        address = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_is_solved"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Rubik's / GoCube",
            model="Rubik's Connected",
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_solved_listener(self._on_solved)
        self._coordinator.register_connection_listener(self._on_connection)
        if self._coordinator.is_solved is not None:
            self._attr_is_on = self._coordinator.is_solved

    def _on_solved(self, is_solved: bool) -> None:
        self._attr_is_on = is_solved
        self.async_write_ha_state()

    def _on_connection(self, connected: bool) -> None:
        self._attr_available = connected
        self.async_write_ha_state()


class RubiksConnectivitySensor(BinarySensorEntity):
    """Tracks whether the cube is currently connected over BLE.

    Always available — 'off' means disconnected, which is itself useful data.
    Use HA history to measure idle-before-sleep duration and wake behaviour.
    """

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        address = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Rubik's / GoCube",
            model="Rubik's Connected",
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_connection_listener(self._on_connection)
        self._attr_is_on = self._coordinator.connected

    def _on_connection(self, connected: bool) -> None:
        self._attr_is_on = connected
        self.async_write_ha_state()
