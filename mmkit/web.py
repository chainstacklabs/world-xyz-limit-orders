"""JSON over HTTPS for the public APIs (World's router, Jupiter, token metadata)."""

import json
import urllib.error
import urllib.request

HEADERS = {"user-agent": "world-xyz-limit-orders", "accept": "application/json"}


def get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={**HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())  # APIs such as Jupiter explain a refusal in a JSON body
        except ValueError:
            raise SystemExit(f"{url.split('?')[0]}: HTTP {e.code}") from None
    except (OSError, ValueError):
        raise SystemExit(f"{url.split('?')[0]}: unreachable or not JSON") from None


def post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={**HEADERS, "content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{url}: HTTP {e.code}") from None
    except (OSError, ValueError):
        raise SystemExit(f"{url}: unreachable or not JSON") from None
