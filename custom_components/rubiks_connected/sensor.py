"""Sensors for Rubik's Connected."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_last_service_info,
    async_register_callback,
)
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
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
        RubiksBatterySensor(coordinator, entry),
        RubiksSignalStrengthSensor(coordinator, entry),
    ])


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
        if self._coordinator.battery_level is not None:
            self._attr_native_value = self._coordinator.battery_level

    def _on_battery(self, level: int) -> None:
        self._attr_native_value = level
        self.async_write_ha_state()

    def _on_connection(self, connected: bool) -> None:
        self._attr_available = connected
        self.async_write_ha_state()


class RubiksSignalStrengthSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class  = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_has_entity_name = True
    _attr_name = "Signal Strength"
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        address = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_rssi"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Rubik's / GoCube",
            model="Rubik's Connected",
        )
        self._unsub_bluetooth: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        # Seed with the most recent advertisement HA has already seen
        service_info = async_last_service_info(
            self.hass, self._coordinator.address, connectable=True
        )
        if service_info:
            self._attr_native_value = service_info.rssi
            self._attr_available = True

        # Update on every future advertisement (fires when cube is scanning/waking)
        self._unsub_bluetooth = async_register_callback(
            self.hass,
            self._on_advertisement,
            BluetoothCallbackMatcher(address=self._coordinator.address),
            BluetoothScanningMode.PASSIVE,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_bluetooth:
            self._unsub_bluetooth()

    @callback
    def _on_advertisement(
        self,
        service_info: BluetoothServiceInfoBleak,
        _change: object,
    ) -> None:
        self._attr_native_value = service_info.rssi
        self._attr_available = True
        self.async_write_ha_state()
