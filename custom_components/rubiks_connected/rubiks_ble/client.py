"""Async BLE client for the Rubik's Connected cube with auto-reconnect."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.exc import BleakError

from .protocol import (
    BATTERY_REQUEST,
    HANDSHAKE_REQUEST,
    NOTIFY_UUID,
    WRITE_UUID,
    BatteryEvent,
    MoveEvent,
    StateEvent,
    decode,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY   = 5    # seconds between reconnect attempts
BATTERY_INTERVAL  = 300  # seconds between periodic battery polls


class RubiksClient:
    """Manages the BLE connection to one Rubik's Connected cube."""

    def __init__(
        self,
        address: str,
        on_move:          Callable[[MoveEvent], None],
        on_battery:       Callable[[int], None],
        on_state:         Callable[[StateEvent], None] | None = None,
        on_connected:     Callable[[], None] | None = None,
        on_disconnected:  Callable[[], None] | None = None,
        ble_device_getter: Callable[[], object] | None = None,
    ) -> None:
        self._address          = address
        self._on_move          = on_move
        self._on_battery       = on_battery
        self._on_state         = on_state
        self._on_connected     = on_connected
        self._on_disconnected  = on_disconnected
        self._ble_device_getter = ble_device_getter

        self._running     = False
        self._stop_event  = asyncio.Event()
        self._client: BleakClient | None = None

    # ── public API ────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Connect and stay connected; call this as a long-running task."""
        self._running = True
        self._stop_event.clear()
        while self._running:
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                break
            except BleakError as exc:
                _LOGGER.warning("BLE error (%s): %s", self._address, exc)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("Unexpected error (%s): %s", self._address, exc)

            if self._running:
                _LOGGER.debug("Reconnecting in %ds …", RECONNECT_DELAY)
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()),
                        timeout=RECONNECT_DELAY,
                    )
                except asyncio.TimeoutError:
                    pass  # reconnect delay elapsed normally

    async def stop(self) -> None:
        """Gracefully stop the client."""
        self._running = False
        self._stop_event.set()
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def request_battery(self) -> None:
        """Ask the cube for its current battery level."""
        if self._client and self._client.is_connected:
            await self._client.write_gatt_char(
                WRITE_UUID, BATTERY_REQUEST, response=False
            )

    # ── internals ─────────────────────────────────────────────────────────────

    def _handle_notification(self, _char: object, data: bytearray) -> None:
        _LOGGER.debug("Notification: %s", data.hex(" "))
        event = decode(data)
        if isinstance(event, MoveEvent):
            self._on_move(event)
        elif isinstance(event, BatteryEvent):
            self._on_battery(event.level)
        elif isinstance(event, StateEvent) and self._on_state:
            self._on_state(event)

    async def _battery_loop(self) -> None:
        while True:
            await asyncio.sleep(BATTERY_INTERVAL)
            try:
                await self.request_battery()
            except Exception:  # noqa: BLE001
                pass

    async def _connect_once(self) -> None:
        disconnected = asyncio.Event()

        def _on_disconnect(_: BleakClient) -> None:
            disconnected.set()
            if self._on_disconnected:
                self._on_disconnected()

        _LOGGER.debug("Connecting to %s …", self._address)

        if self._ble_device_getter is not None:
            from bleak_retry_connector import establish_connection  # noqa: PLC0415
            ble_device = self._ble_device_getter()
            if ble_device is None:
                raise BleakError(f"No BLE device available for {self._address}")
            client = await establish_connection(
                BleakClient,
                ble_device,
                self._address,
                disconnected_callback=_on_disconnect,
            )
        else:
            client = BleakClient(self._address, disconnected_callback=_on_disconnect)
            await client.connect()

        self._client = client
        _LOGGER.info("Connected to %s", self._address)

        try:
            await client.start_notify(NOTIFY_UUID, self._handle_notification)
            _LOGGER.debug("Subscribed to notifications on %s", self._address)
            await client.write_gatt_char(WRITE_UUID, HANDSHAKE_REQUEST, response=False)
            _LOGGER.debug("Handshake sent to %s", self._address)
            await self.request_battery()
            _LOGGER.debug("Battery request sent to %s", self._address)

            if self._on_connected:
                self._on_connected()

            battery_task = asyncio.create_task(self._battery_loop())
            try:
                await asyncio.wait(
                    [
                        asyncio.ensure_future(disconnected.wait()),
                        asyncio.ensure_future(self._stop_event.wait()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                battery_task.cancel()
        finally:
            self._client = None
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

        _LOGGER.info("Disconnected from %s", self._address)
