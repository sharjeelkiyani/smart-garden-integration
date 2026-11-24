"""Set up: the garden's address + a connection key made in Smart Garden (My account → Connection keys)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import GardenApi, GardenAuthError, GardenError
from .const import CONF_KEY, CONF_PANEL_URL, CONF_SIDEBAR, DOMAIN

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))


def _clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    return url


class SmartGardenConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, url: str, key: str) -> tuple[dict | None, dict[str, str]]:
        api = GardenApi(async_get_clientsession(self.hass), url, key.strip())
        try:
            return await api.info(), {}
        except GardenAuthError:
            return None, {"base": "invalid_auth"}
        except GardenError:
            return None, {"base": "cannot_connect"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _clean_url(user_input[CONF_URL])
            info, errors = await self._check(url, user_input[CONF_KEY])
            if info:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_configured(updates={CONF_URL: url, CONF_KEY: user_input[CONF_KEY].strip()})
                return self.async_create_entry(title=info.get("name") or "Smart Garden",
                                               data={CONF_URL: url, CONF_KEY: user_input[CONF_KEY].strip()})
        schema = vol.Schema({
            vol.Required(CONF_URL, default=(user_input or {}).get(CONF_URL, "http://")): URL,
            vol.Required(CONF_KEY): PASSWORD,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            info, errors = await self._check(entry.data[CONF_URL], user_input[CONF_KEY])
            if info:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_mismatch(reason="wrong_garden")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_KEY: user_input[CONF_KEY].strip()})
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_KEY): PASSWORD}),
                                    errors=errors, description_placeholders={"url": entry.data[CONF_URL]})

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the garden's address (e.g. moved to a new IP or a domain)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _clean_url(user_input[CONF_URL])
            info, errors = await self._check(url, entry.data[CONF_KEY])
            if info:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_mismatch(reason="wrong_garden")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_URL: url})
        return self.async_show_form(step_id="reconfigure", errors=errors, data_schema=vol.Schema(
            {vol.Required(CONF_URL, default=entry.data[CONF_URL]): URL}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SmartGardenOptionsFlow()


class SmartGardenOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_PANEL_URL] = _clean_url(user_input.get(CONF_PANEL_URL, ""))
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional(CONF_SIDEBAR, default=o.get(CONF_SIDEBAR, True)): bool,
            vol.Optional(CONF_PANEL_URL, description={"suggested_value": o.get(CONF_PANEL_URL, "")}): URL,
        }))
