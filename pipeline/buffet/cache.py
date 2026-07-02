"""Polite HTTP with an on-disk JSON cache.

Every fetcher goes through get_json/post_json with a cache key. A cached
response is returned without touching the network unless max_age_days has
passed, so re-runs are cheap and a flaky source can't break a refresh that
already has data.
"""
import hashlib
import json
import time
from urllib.parse import urlparse

import requests

from . import config

_last_hit = {}  # host -> monotonic time of last request


def _throttle(url):
    host = urlparse(url).netloc
    min_gap = config.MIN_INTERVAL.get(host, 1.0)
    last = _last_hit.get(host)
    if last is not None:
        wait = min_gap - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.monotonic()


def _cache_path(key):
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:80]
    return config.RAW_DIR / f"{safe}.{digest}.json"


def _read_cache(key, max_age_days):
    path = _cache_path(key)
    if not path.exists():
        return None
    if max_age_days is not None:
        age = time.time() - path.stat().st_mtime
        if age > max_age_days * 86400:
            return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(key, data):
    path = _cache_path(key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def _read_cache_any_age(key):
    return _read_cache(key, max_age_days=None)


def request_json(method, url, *, key, max_age_days=1.0, retries=3, headers=None, json_body=None, params=None):
    cached = _read_cache(key, max_age_days)
    if cached is not None:
        return cached

    hdrs = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    last_err = None
    for attempt in range(retries):
        _throttle(url)
        try:
            resp = requests.request(method, url, headers=hdrs, json=json_body,
                                    params=params, timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests", response=resp)
            resp.raise_for_status()
            data = resp.json()
            _write_cache(key, data)
            return data
        except (requests.RequestException, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt * 2)

    # Network dead: fall back to a stale cache rather than failing the run.
    stale = _read_cache_any_age(key)
    if stale is not None:
        print(f"  [cache] {key}: network failed ({last_err}), using stale cache")
        return stale
    raise RuntimeError(f"fetch failed for {key}: {last_err}")


def get_json(url, **kw):
    return request_json("GET", url, **kw)


def post_json(url, body, **kw):
    return request_json("POST", url, json_body=body, **kw)


def get_bytes(url, *, key, max_age_days=7.0, retries=3, headers=None):
    """get_text for binary bodies (zip archives)."""
    path = _cache_path(key).with_suffix(".bin")
    if path.exists() and (time.time() - path.stat().st_mtime) <= max_age_days * 86400:
        return path.read_bytes()

    hdrs = {"User-Agent": config.USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries):
        _throttle(url)
        try:
            resp = requests.get(url, headers=hdrs, timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(resp.content)
            tmp.replace(path)
            return resp.content
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 ** attempt * 2)
    if path.exists():
        return path.read_bytes()
    raise RuntimeError(f"fetch failed for {key}: {last_err}")


def get_text(url, *, key, max_age_days=1.0, retries=3, headers=None):
    """Same contract as request_json but for non-JSON bodies (RSS XML)."""
    path = _cache_path(key)
    if path.exists() and (time.time() - path.stat().st_mtime) <= max_age_days * 86400:
        return path.read_text()

    hdrs = {"User-Agent": config.USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries):
        _throttle(url)
        try:
            resp = requests.get(url, headers=hdrs, timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            tmp = path.with_suffix(".tmp")
            tmp.write_text(resp.text)
            tmp.replace(path)
            return resp.text
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 ** attempt * 2)
    if path.exists():
        return path.read_text()
    raise RuntimeError(f"fetch failed for {key}: {last_err}")
