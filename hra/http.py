"""Polite HTTP client: per-host spacing, retries, clear errors, injectable for tests."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = (f'HumanResponseAtlas/{__version__} (open research prototype; '
              'https://www.clinpgx.org data credited)')
# Seconds between requests to the same host (all within each provider's published limits).
SPACING = {
    'eutils.ncbi.nlm.nih.gov': 0.4,           # NCBI: 3 requests/second without a key
    'www.ncbi.nlm.nih.gov': 0.4,              # PubTator3: 3 requests/second
    'www.ebi.ac.uk': 0.2,                     # Europe PMC / ChEMBL: "reasonable use"
    'clinicaltrials.gov': 0.3,
    'api.clinpgx.org': 0.6,                   # ClinPGx: 2 requests/second
}


class SourceError(RuntimeError):
    """A source could not be searched. Never treated as 'no results'."""


class Http:
    def __init__(self, transport=None, timeout: int = 60, retries: int = 3):
        self.transport = transport or self._urllib
        self.timeout, self.retries = timeout, retries
        self._last: dict[str, float] = {}

    def _urllib(self, url: str, data: bytes | None, headers: dict) -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def get(self, url: str, params: dict | None = None, data: dict | None = None,
            accept: str = 'application/json') -> bytes:
        if params:
            url = f'{url}?{urllib.parse.urlencode(params, doseq=True)}'
        body = urllib.parse.urlencode(data).encode() if data else None
        host = urllib.parse.urlparse(url).hostname or ''
        headers = {'User-Agent': USER_AGENT, 'Accept': accept}
        last_err = None
        for attempt in range(1, self.retries + 1):
            wait = SPACING.get(host, 0.3) - (time.monotonic() - self._last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                out = self.transport(url, body, headers)
                self._last[host] = time.monotonic()
                return out
            except urllib.error.HTTPError as e:
                self._last[host] = time.monotonic()
                last_err = f'HTTP {e.code} from {host}'
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = f'could not reach {host}: {getattr(e, "reason", e)}'
            time.sleep(min(2 * attempt, 6))
        raise SourceError(last_err or f'request to {host} failed')

    def json(self, url: str, params: dict | None = None) -> dict:
        raw = self.get(url, params)
        try:
            return json.loads(raw.decode('utf-8'))
        except ValueError as e:
            raise SourceError(f'unreadable response from {urllib.parse.urlparse(url).hostname}: {e}')
