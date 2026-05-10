"""Move event entity for Rubik's Connected.

Each face turn fires an HA event with type "<color>_<direction>", e.g.
"white_cw", "red_ccw".  The extra state attributes carry the face angle.

In an automation trigger this looks like:
  platform: event
  event_type: rubiks_connected_move   # optional HA event bus event
  # or use the entity trigger:
  entity_id: event.rubiks_connected_move
  event_types:
    - white_cw
"""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ADDRESS, DOMAIN

from .rubiks_ble.protocol import Direction, Face, MoveEvent

# All 12 possible event types
_EVENT_TYPES = [
    f"{face.value}_{direction.value}"
    for face in Face
    for direction in Direction
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RubiksMoveEventEntity(coordinator, entry)])


class RubiksMoveEventEntity(EventEntity):
    _attr_has_entity_name = True
    _attr_name            = "Move"
    _attr_event_types     = _EVENT_TYPES
    _attr_device_class    = EventDeviceClass.BUTTON

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        address           = entry.data[CONF_ADDRESS]
        self._attr_unique_id   = f"{address}_move"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Rubik's / GoCube",
            model="Rubik's Connected",
        )

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_move_listener(self._on_move)
        self._coordinator.register_connection_listener(self._on_connection)

    def _on_move(self, event: MoveEvent) -> None:
        event_type = f"{event.face.value}_{event.direction.value}"
        self._trigger_event(event_type, {"angle": event.angle})
        self.async_write_ha_state()

    def _on_connection(self, connected: bool) -> None:
        self._attr_available = connected
        self.async_write_ha_state()
