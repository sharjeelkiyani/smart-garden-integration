"""Talks to the Smart Garden app's /api/v1 with a connection key."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class GardenError(Exception):
    """The garden could not be reached or answered with an error."""


class GardenAuthError(GardenError):
    """The connection key is wrong, revoked, or its account is disabled."""


class GardenRefused(GardenError):
    """The garden refused the command (e.g. zone turned off, over its limit)."""


class GardenNoPairing(GardenError):
    """The address answers but isn't a Smart Garden that can pair (or the app needs updating)."""


class GardenBusy(GardenError):
    """The garden turned a pairing request away for now (too many waiting, or too many tries)."""


class GardenApi:
    def __init__(self, session: aiohttp.ClientSession, url: str, key: str) -> None:
        self._session = session
        self.url = url.rstrip("/")
        self._key = key

    async def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        try:
            async with asyncio.timeout(15):
                resp = await self._session.request(
                    method, f"{self.url}/api/v1{path}", json=body,
                    headers={"Authorization": f"Bearer {self._key}"}, allow_redirects=False)
                async with resp:
                    if resp.status in (401, 403) and method == "GET":
                        raise GardenAuthError(await _error(resp))
                    if resp.status == 429:
                        raise GardenAuthError("too many failed attempts - wait 15 minutes")
                    if resp.status >= 400:
                        raise GardenRefused(await _error(resp))
                    if resp.status >= 300 or resp.content_type != "application/json":
                        raise GardenError("that address isn't a Smart Garden with the integration API "
                                          "(update the app, or check the address)")
                    return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GardenError(f"can't reach {self.url}: {err}") from err

    async def _public(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """Calls that work before there is a key: hello and pairing."""
        try:
            async with asyncio.timeout(15):
                resp = await self._session.request(method, f"{self.url}/api/v1{path}", json=body,
                                                   allow_redirects=False)
                async with resp:
                    try:
                        data = await resp.json(content_type=None)
                    except ValueError:
                        data = None
                    return resp.status, data if isinstance(data, dict) else {}
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GardenError(f"can't reach {self.url}: {err}") from err

    async def hello(self) -> dict:
        """The garden's id and name, without a key. Raises GardenNoPairing for anything else."""
        status, data = await self._public("GET", "/hello")
        if status != 200 or data.get("app") != "smart-garden":
            raise GardenNoPairing("not a Smart Garden that can pair (update the app, or use a connection key)")
        return data

    async def pair_start(self, name: str) -> dict:
        """Ask to connect: returns {"token", "code", "expires_in"}; the code is shown to the person."""
        status, data = await self._public("POST", "/pair", {"client": "Home Assistant", "name": name})
        if status == 429:
            raise GardenBusy(data.get("error") or "busy - try again in a few minutes")
        if status != 200 or not data.get("token"):
            raise GardenNoPairing("this Smart Garden can't pair (update the app, or use a connection key)")
        return data

    async def pair_poll(self, token: str) -> dict:
        """{"status": "waiting" | "approved" | "denied" | "expired"} and "key" once approved."""
        _status, data = await self._public("GET", f"/pair/{token}")
        return data if data.get("status") else {"status": "expired"}

    async def info(self) -> dict:
        return await self._call("GET", "/info")

    async def state(self) -> dict:
        return await self._call("GET", "/state")

    async def water(self, zone_id: int, minutes: float | None = None, until_soil: bool = False) -> dict:
        body: dict = {"until_soil": True} if until_soil else {}
        if minutes is not None and not until_soil:
            body["minutes"] = minutes
        return await self._call("POST", f"/zones/{zone_id}/water", body)

    async def stop_zone(self, zone_id: int) -> dict:
        return await self._call("POST", f"/zones/{zone_id}/stop")

    async def zone_enabled(self, zone_id: int, on: bool) -> dict:
        return await self._call("POST", f"/zones/{zone_id}/enabled", {"on": on})

    async def stop_all(self) -> dict:
        return await self._call("POST", "/stop")

    async def run_schedule(self, schedule_id: int) -> dict:
        return await self._call("POST", f"/schedules/{schedule_id}/run")

    async def automatic(self, on: bool) -> dict:
        return await self._call("POST", "/automatic", {"on": on})


async def _error(resp: aiohttp.ClientResponse) -> str:
    try:
        data = await resp.json(content_type=None)
        return str(data.get("error") or resp.reason)
    except (ValueError, aiohttp.ContentTypeError, AttributeError):
        return f"HTTP {resp.status}"
