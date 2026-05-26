"""Rubik's Connected Home Assistant integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ADDRESS, DOMAIN, PLATFORMS

from .rubiks_ble.client import RubiksClient
from .rubiks_ble.protocol import CubeStateEvent, MoveEvent, StateEvent

_LOGGER = logging.getLogger(__name__)

type RubiksConfigEntry = ConfigEntry[RubiksCoordinator]


class RubiksCoordinator:
    """Owns the BLE client and fans events out to registered HA entities."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass           = hass
        self.address        = address
        self.battery_level: int | None = None
        self.is_solved:     bool | None = None
        self.connected      = False

        self._move_listeners:    list[callable] = []
        self._battery_listeners: list[callable] = []
        self._conn_listeners:    list[callable] = []
        self._solved_listeners:  list[callable] = []

        self._client = RubiksClient(
            address=address,
            on_move=self._on_move,
            on_battery=self._on_battery,
            on_state=self._on_state,
            on_cube_state=self._on_cube_state,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
            ble_device_getter=lambda: async_ble_device_from_address(
                hass, address, connectable=True
            ),
        )
        self._task: asyncio.Task | None = None

    # ── listener registration ─────────────────────────────────────────────────

    def register_move_listener(self, cb: callable) -> None:
        self._move_listeners.append(cb)

    def register_battery_listener(self, cb: callable) -> None:
        self._battery_listeners.append(cb)

    def register_connection_listener(self, cb: callable) -> None:
        self._conn_listeners.append(cb)

    def register_solved_listener(self, cb: callable) -> None:
        self._solved_listeners.append(cb)

    # ── public actions ────────────────────────────────────────────────────────

    async def calibrate(self) -> None:
        """Send 0x35 — tells the cube its current physical state is solved."""
        await self._client.calibrate()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._task = asyncio.create_task(self._client.run())

    async def stop(self) -> None:
        await self._client.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── BLE callbacks (called from bleak's thread/loop) ───────────────────────

    def _on_move(self, event: MoveEvent) -> None:
        self.hass.loop.call_soon_threadsafe(self._dispatch_move, event)

    def _on_battery(self, level: int) -> None:
        self.battery_level = level
        self.hass.loop.call_soon_threadsafe(self._dispatch_battery, level)

    def _on_state(self, event: StateEvent) -> None:
        pass  # reserved for future use

    def _on_cube_state(self, event: CubeStateEvent) -> None:
        self.is_solved = event.is_solved
        self.hass.loop.call_soon_threadsafe(self._dispatch_solved, event.is_solved)

    def _on_connected(self) -> None:
        self.connected = True
        self.hass.loop.call_soon_threadsafe(self._dispatch_connection, True)

    def _on_disconnected(self) -> None:
        self.connected = False
        self.hass.loop.call_soon_threadsafe(self._dispatch_connection, False)

    # ── dispatch helpers (always run on the HA event loop) ───────────────────

    def _dispatch_move(self, event: MoveEvent) -> None:
        for cb in self._move_listeners:
            try:
                cb(event)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error in move listener")

    def _dispatch_battery(self, level: int) -> None:
        for cb in self._battery_listeners:
            try:
                cb(level)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error in battery listener")

    def _dispatch_connection(self, connected: bool) -> None:
        for cb in self._conn_listeners:
            try:
                cb(connected)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error in connection listener")

    def _dispatch_solved(self, is_solved: bool) -> None:
        for cb in self._solved_listeners:
            try:
                cb(is_solved)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error in solved listener")


# ── HA entry points ───────────────────────────────────────────────────────────

async def async_setup_entry(hass: HomeAssistant, entry: RubiksConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    coordinator = RubiksCoordinator(hass, address)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.start()

    entry.async_on_unload(coordinator.stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RubiksConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
