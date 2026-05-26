"""Calibrate (mark as solved) button for Rubik's Connected."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities([RubiksCalibrateButton(coordinator, entry)])


class RubiksCalibrateButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Calibrate (mark as solved)"
    _attr_icon = "mdi:cube-scan"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        address = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_calibrate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Rubik's / GoCube",
            model="Rubik's Connected",
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_connection_listener(self._on_connection)

    def _on_connection(self, connected: bool) -> None:
        self._attr_available = connected
        self.async_write_ha_state()

    async def async_press(self) -> None:
        await self._coordinator.calibrate()
