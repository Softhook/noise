"""HTTP access to WebTrak, using only the standard library.

Only public, unauthenticated endpoints are used: the same ones the WebTrak page calls in a browser.
Requests are spaced out (one a second by default), and follow mode asks for one new chunk every
30 s, which is what an open WebTrak tab does.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import parse

SITES_URL = "https://eu.webtrak.aero/api/sites"
CONFIG_URL = "https://focus-apis.emsbk.com/productinfo"
FALLBACK_DATA_HOST = "webtrak-server-eu.emsbk.com"
USER_AGENT = "thamesmead-noise-survey/0.1 (personal, non-commercial noise research)"


class Client:
    def __init__(self, site="lcy", min_interval=1.0, timeout=20, retries=3, opener=None, sleep=time.sleep,
                 clock=time.monotonic):
        self.site = site
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self._clock = clock
        self._last = None
        self._data_host = None

    # --- plumbing -------------------------------------------------------------------------

    def _request(self, url, data=None):
        headers = {"User-Agent": USER_AGENT, "Referer": f"https://eu.webtrak.aero/{self.site}"}
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        delay = 5
        for attempt in range(self.retries + 1):
            if self._last is not None:
                wait = self.min_interval - (self._clock() - self._last)
                if wait > 0:
                    self._sleep(wait)
            self._last = self._clock()
            try:
                request = urllib.request.Request(url, data=body, headers=headers)
                with self._open(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8", "replace")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
                if isinstance(error, urllib.error.HTTPError) and 400 <= error.code < 500 and error.code != 429:
                    raise
                if attempt == self.retries:
                    raise
                self._sleep(delay)
                delay *= 3

    def data_host(self):
        if self._data_host is None:
            try:
                sites = json.loads(self._request(SITES_URL))
                match = [s for s in sites if s.get("site_name") == self.site]
                self._data_host = match[0]["server_name"] if match else FALLBACK_DATA_HOST
            except (ValueError, KeyError, OSError):
                self._data_host = FALLBACK_DATA_HOST
        return self._data_host

    def _data_url(self, path):
        return f"https://{self.data_host()}/WebTrak/{self.site}/data/{path}"

    # --- endpoints ------------------------------------------------------------------------

    def latest_handle(self):
        """The newest chunk WebTrak will serve. It runs about 25 minutes behind real time."""
        text = self._request(self._data_url("handle/now"))
        found = re.search(r'startHandle="(\d+)"', text)
        if not found:
            raise parse.NotAvailable(f"unexpected handle/now reply: {text[:200]!r}")
        return int(found.group(1))

    def date_range(self):
        """The first and last local times WebTrak holds, as two strings."""
        text = self._request(self._data_url("daterange"))
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', text))
        return (f"{attrs.get('startDate')} {attrs.get('startTime')}", f"{attrs.get('endDate')} {attrs.get('endTime')}")

    def chunk_text(self, handle):
        return self._request(self._data_url(f"{handle}.mobile"))

    def chunk(self, handle):
        return parse.parse_chunk(self.chunk_text(handle), handle)

    def monitors(self):
        """Noise monitor locations from the site's public configuration."""
        form = {"app": "focus", "product": "WebTrak", "sitename": self.site, "action": "get_config",
                "send_all": "false", "exclude_layers": "true"}
        config = json.loads(self._request(CONFIG_URL, data=form))
        found = config.get("nmt_locations") or []
        if isinstance(found, dict):
            found = [found]
        return [{"id": str(m.get("locid")), "name": m.get("name", ""), "lat": float(m.get("latitude")),
                 "lon": float(m.get("longitude")), "status": m.get("status", "")} for m in found]
