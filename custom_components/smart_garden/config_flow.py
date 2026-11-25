"""Set up a Smart Garden.

Easiest: Home Assistant finds the garden on the network by itself (Settings → Devices → Discovered),
shows a 6-digit code, and an admin taps Allow in Smart Garden - no address or key to type.
Or add it by hand: the address, then either pair the same way or paste a connection key made in
Smart Garden (My account → Connection keys).
"""
from __future__ import annotations

import asyncio
import ipaddress
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import (SOURCE_REAUTH, ConfigEntry, ConfigFlow, ConfigFlowResult,
                                          OptionsFlow)
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import GardenApi, GardenAuthError, GardenBusy, GardenError, GardenNoPairing
from .const import CONF_KEY, CONF_PANEL_URL, CONF_SIDEBAR, DOMAIN

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
POLL_S = 2
PAIR_TIMEOUT_S = 10 * 60


def _clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    return url


def _is_ip_url(url: str) -> bool:
    """True for http://192.168.1.50:5120 - an address that may change and discovery may correct."""
    try:
        ipaddress.ip_address(urlsplit(url).hostname or "")
        return True
    except ValueError:
        return False


class PairDenied(Exception):
    """An admin pressed Deny."""


class PairExpired(Exception):
    """Nobody answered within 10 minutes."""


class SmartGardenConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._url = ""
        self._name = "Smart Garden"
        self._pair: dict = {}
        self._pair_task: asyncio.Task | None = None

    def _api(self, url: str, key: str = "") -> GardenApi:
        return GardenApi(async_get_clientsession(self.hass), url, key.strip())

    async def _check(self, url: str, key: str) -> tuple[dict | None, dict[str, str]]:
        try:
            return await self._api(url, key).info(), {}
        except GardenAuthError:
            return None, {"base": "invalid_auth"}
        except GardenError:
            return None, {"base": "cannot_connect"}

    async def _start_pairing(self) -> dict[str, str]:
        """Ask the garden for a pairing code; {} when that worked, else form errors."""
        try:
            self._pair = await self._api(self._url).pair_start(self.hass.config.location_name or "Home")
        except GardenBusy:
            return {"base": "pair_busy"}
        except GardenNoPairing:
            return {"base": "pair_unsupported"}
        except GardenError:
            return {"base": "cannot_connect"}
        self._pair_task = None
        return {}

    async def _finish(self, key: str) -> ConfigFlowResult:
        """A working key: add the garden (or, when reconnecting, store the new key)."""
        info, errors = await self._check(self._url, key)
        if not info:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(info["id"])
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_garden")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates={CONF_KEY: key})
        self._abort_if_unique_id_configured(updates={CONF_URL: self._url, CONF_KEY: key})
        return self.async_create_entry(title=info.get("name") or "Smart Garden",
                                       data={CONF_URL: self._url, CONF_KEY: key})

    # ---- found on the network ------------------------------------------------------------
    async def async_step_zeroconf(self, discovery_info: Any) -> ConfigFlowResult:
        props = discovery_info.properties or {}
        gid = props.get("id")
        if not gid:
            return self.async_abort(reason="not_a_garden")
        host = str(discovery_info.ip_address) if getattr(discovery_info, "ip_address", None) else discovery_info.host
        if ":" in host:
            host = f"[{host}]"
        self._url = f"http://{host}:{discovery_info.port}"
        self._name = props.get("name") or "Smart Garden"
        await self.async_set_unique_id(gid)
        # Already set up: follow a new IP address, but never replace a name or https address someone chose.
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, gid)
        moved = entry is not None and _is_ip_url(entry.data[CONF_URL]) and entry.data[CONF_URL] != self._url
        self._abort_if_unique_id_configured(updates={CONF_URL: self._url} if moved else None)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if key := (user_input.get(CONF_KEY) or "").strip():
                info, errors = await self._check(self._url, key)
                if info:
                    return await self._finish(key)
            else:
                errors = await self._start_pairing()
                if not errors:
                    return await self.async_step_pair()
        return self.async_show_form(
            step_id="zeroconf_confirm", errors=errors,
            data_schema=vol.Schema({vol.Optional(CONF_KEY): PASSWORD}),
            description_placeholders={"name": self._name, "url": self._url})

    # ---- added by hand -----------------------------------------------------------------------
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._url = _clean_url(user_input[CONF_URL])
            if key := (user_input.get(CONF_KEY) or "").strip():
                info, errors = await self._check(self._url, key)
                if info:
                    return await self._finish(key)
            else:
                try:
                    hello = await self._api(self._url).hello()
                except GardenNoPairing:
                    errors = {"base": "pair_unsupported"}
                except GardenError:
                    errors = {"base": "cannot_connect"}
                else:
                    self._name = hello.get("name") or self._name
                    await self.async_set_unique_id(hello["id"])
                    self._abort_if_unique_id_configured()
                    errors = await self._start_pairing()
                    if not errors:
                        return await self.async_step_pair()
        schema = vol.Schema({
            vol.Required(CONF_URL, default=(user_input or {}).get(CONF_URL, "http://")): URL,
            vol.Optional(CONF_KEY): PASSWORD,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ---- waiting for Allow -------------------------------------------------------------------
    async def _wait_for_allow(self) -> str:
        api, token = self._api(self._url), self._pair["token"]
        deadline = time.monotonic() + min(PAIR_TIMEOUT_S, int(self._pair.get("expires_in") or PAIR_TIMEOUT_S))
        while time.monotonic() < deadline:
            try:
                answer = await api.pair_poll(token)
            except GardenError:          # Wi-Fi blip: keep waiting
                answer = {"status": "waiting"}
            if answer.get("status") == "approved" and answer.get("key"):
                return answer["key"]
            if answer.get("status") == "denied":
                raise PairDenied
            if answer.get("status") not in ("waiting", None):
                raise PairExpired
            await asyncio.sleep(POLL_S)
        raise PairExpired

    async def async_step_pair(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._pair_task is None:
            self._pair_task = self.hass.async_create_task(self._wait_for_allow())
        if not self._pair_task.done():
            return self.async_show_progress(
                step_id="pair", progress_action="pair", progress_task=self._pair_task,
                description_placeholders={"code": self._pair.get("code", ""), "name": self._name,
                                          "url": self._url})
        return self.async_show_progress_done(next_step_id="pair_finish")

    async def async_step_pair_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        task, self._pair_task = self._pair_task, None
        try:
            key = task.result() if task else ""
        except PairDenied:
            return self.async_abort(reason="pair_denied")
        except (PairExpired, asyncio.CancelledError):
            return self.async_abort(reason="pair_expired")
        return await self._finish(key)

    # ---- key revoked: pair again or paste a new key ------------------------------------------
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        self._url = entry.data[CONF_URL]
        self._name = entry.title
        errors: dict[str, str] = {}
        if user_input is not None:
            if key := (user_input.get(CONF_KEY) or "").strip():
                info, errors = await self._check(self._url, key)
                if info:
                    return await self._finish(key)
            else:
                errors = await self._start_pairing()
                if not errors:
                    return await self.async_step_pair()
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Optional(CONF_KEY): PASSWORD}),
                                    errors=errors, description_placeholders={"url": self._url})

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
