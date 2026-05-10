"""Config flow: discover and add a Rubik's Connected cube."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME

from .const import CONF_ADDRESS, DOMAIN

from .rubiks_ble.protocol import SERVICE_UUID

NUS_SERVICE_UUID = SERVICE_UUID


class RubiksConnectedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adding the Rubik's Connected integration."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}   # address → name

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Show discovered cubes or let the user enter an address manually."""
        # Collect cubes already found by HA's bluetooth scanner
        for info in async_discovered_service_info(self.hass):
            if NUS_SERVICE_UUID in (info.service_uuids or []):
                self._discovered[info.address] = info.name or info.address
            # Also match by name prefix in case service UUID isn't advertised
            elif (info.name or "").lower().startswith("rubiks"):
                self._discovered[info.address] = info.name or info.address

        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            name    = self._discovered.get(address) or user_input.get(CONF_NAME, address)

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: address, CONF_NAME: name},
            )

        if self._discovered:
            # Offer a selector populated with discovered devices
            options = {
                addr: f"{name} ({addr})"
                for addr, name in self._discovered.items()
            }
            schema = vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(options)}
            )
        else:
            # Fall back to a free-text address entry
            schema = vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="Rubik's Connected"): str,
                }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "found": str(len(self._discovered)),
            },
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Called automatically when HA's bluetooth scanner spots the cube."""
        address = discovery_info.address
        name    = discovery_info.name or address

        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": name}
        self._discovered[address] = name

        return await self.async_step_user()
