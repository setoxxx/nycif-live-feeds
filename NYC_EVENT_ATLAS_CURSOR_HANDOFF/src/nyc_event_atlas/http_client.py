from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AtlasHttpClient:
    """HTTP client with hashed immutable snapshots.

    robots_policy:
      - obey (default): honor robots.txt
      - official_feed: allow known public machine feeds even when robots blocks
        HTML crawling paths (e.g. NYC Parks BigApps JSON under /xml/)
    """

    def __init__(
        self,
        cache_dir="data/raw",
        user_agent=None,
        delay=None,
        timeout=None,
        robots_policy: str = "obey",
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or os.getenv(
            "NYC_ATLAS_USER_AGENT", "NYCEventAtlas/1.0 (+research)"
        )
        self.delay = float(delay or os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
        self.timeout = int(timeout or os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self.robots_policy = robots_policy
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        retry = Retry(
            total=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self._last_request = 0.0
        self._robots = {}

    def _allowed(self, url: str) -> bool:
        if self.robots_policy == "official_feed":
            return True
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = robotparser.RobotFileParser()
            rp.set_url(root + "/robots.txt")
            try:
                rp.read()
                self._robots[root] = rp
            except Exception:
                self._robots[root] = None
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    def get(self, url: str, params=None, force=False, ext_hint: str | None = None):
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows automated access: {url}")
        elapsed = time.time() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        r = self.session.get(url, params=params, timeout=self.timeout)
        self._last_request = time.time()
        r.raise_for_status()
        body = r.content
        sha = hashlib.sha256(body).hexdigest()
        ctype = r.headers.get("Content-Type", "")
        if ext_hint:
            ext = ext_hint
        elif "json" in ctype or url.endswith(".json"):
            ext = ".json"
        elif "pdf" in ctype or url.lower().endswith(".pdf"):
            ext = ".pdf"
        elif "calendar" in ctype or url.lower().endswith(".ics"):
            ext = ".ics"
        else:
            ext = ".html"
        path = self.cache_dir / f"{sha}{ext}"
        if force or not path.exists():
            path.write_bytes(body)
        meta = {
            "url": r.url,
            "status": r.status_code,
            "content_type": ctype,
            "etag": r.headers.get("ETag"),
            "last_modified": r.headers.get("Last-Modified"),
            "sha256": sha,
            "local_path": str(path),
            "robots_policy": self.robots_policy,
        }
        (self.cache_dir / f"{sha}.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        return r, meta
