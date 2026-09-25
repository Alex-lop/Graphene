"""Token Factory: Nebius's OpenAI-compatible inference API, which the Nemotron planner and executor call.

Standard library only: two endpoints (the model list and chat completions) need no client library.
The key is read from ``NEBIUS_API_KEY`` when a call is made, sent in one header, and written nowhere:
not in the store, a log, the ledger or a recording.

Model ids are never written here. ``roles`` reads them from the live list (``GET /models``), so an id
Graphene uses is one Token Factory said it has. Each call's usage is priced at the list price that same
list gives, per token, and appended to the spend ledger when one is named (``GRAPHENE_LEDGER``); a
ledger whose total has reached ``GRAPHENE_SPEND_CAP_USD`` refuses the next call before it is made.

``GRAPHENE_TOKENFACTORY_URL`` points everything at another endpoint (the tests' recorded fake), and
``GRAPHENE_TOKENFACTORY_RECORD`` appends each exchange to a file, so a live run can be replayed later.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE = "https://api.tokenfactory.nebius.com/v1/"
KEY = "NEBIUS_API_KEY"
TRIES = 6  # a 429 or a 5xx is tried again, waiting what the server asks or twice as long each time
TIMEOUT = 300  # seconds for one completion: a long reasoning answer from the largest model takes minutes


class Unreachable(Exception):
    """Token Factory could not be reached, or said no; the message says which, in one line."""


class Spent(Unreachable):
    """The ledger's total has reached the cap: no call is made."""


@dataclass(frozen=True)
class Model:
    id: str
    prompt: float  # dollars a prompt token, at list price
    completion: float  # dollars a completion token
    created: int = 0


def base() -> str:
    return os.environ.get("GRAPHENE_TOKENFACTORY_URL", BASE).rstrip("/") + "/"


def _request(method: str, path: str, body: dict | None = None, timeout: float = 60) -> tuple[dict, dict]:
    """One request, tried again on a 429 or a 5xx. Returns the JSON answer and the response headers."""
    key = os.environ.get(KEY)
    if not key:
        raise Unreachable(f"{KEY} is not set: Token Factory needs a key (tokenfactory.nebius.com)")
    data = json.dumps(body).encode() if body is not None else None
    wait = 2.0
    for attempt in range(1, TRIES + 1):
        req = urllib.request.Request(base() + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read() or b"{}"), dict(resp.headers)
        except urllib.error.HTTPError as no:
            said = no.read().decode("utf-8", "replace")[:300]
            if (no.code == 429 or no.code >= 500) and attempt < TRIES:
                after = no.headers.get("Retry-After")
                time.sleep(float(after) if after and after.replace(".", "", 1).isdigit() else wait)
                wait *= 2
                continue
            raise Unreachable(f"Token Factory answered {no.code} to {method} /{path}: {said}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as no:
            if attempt < TRIES:
                time.sleep(wait)
                wait *= 2
                continue
            raise Unreachable(f"Token Factory could not be reached at {base()}: {no}") from None
    raise AssertionError("unreachable")  # pragma: no cover


@lru_cache(maxsize=4)
def _listed(url: str) -> tuple[Model, ...]:
    said, _ = _request("GET", "models?verbose=true")
    out = []
    for m in said.get("data") or []:
        price = m.get("pricing") or {}
        out.append(Model(m["id"], float(price.get("prompt") or 0), float(price.get("completion") or 0),
                         int(m.get("created") or 0)))  # fmt: skip
    return tuple(out)


def models() -> list[Model]:
    """Every model Token Factory lists for this key, with its list price (asked once a process)."""
    return list(_listed(base()))


ROLES = ("ultra", "super", "nano")


def roles(listed: list[Model] | None = None) -> dict[str, str]:
    """The NVIDIA Nemotron models in the live list, by size: ``{"ultra": id, "super": id, "nano": id}``
    for those that are there. Where one size is listed twice, the newest wins; a "-fast" variant is a
    second choice. Nothing here names an id: whatever the list says is what is used."""
    listed = models() if listed is None else listed
    found: dict[str, Model] = {}
    for m in listed:
        name = m.id.lower()
        if "nemotron" not in name:
            continue
        size = next((r for r in ROLES if r in name), None)
        if size is None:
            continue
        rank = (not name.endswith("-fast"), m.created)
        if size not in found or rank > (not found[size].id.lower().endswith("-fast"), found[size].created):
            found[size] = m
    return {r: found[r].id for r in ROLES if r in found}


def price(model_id: str) -> Model:
    return next((m for m in models() if m.id == model_id), Model(model_id, 0.0, 0.0))


def dollars(usage: dict, model_id: str) -> float:
    m = price(model_id)
    return (usage.get("prompt_tokens") or 0) * m.prompt + (usage.get("completion_tokens") or 0) * m.completion


# -- the ledger: every call's usage at list price, and the cap -------------------------------------------


def _ledger() -> Path | None:
    named = os.environ.get("GRAPHENE_LEDGER")
    return Path(named) if named else None


def cap() -> float | None:
    said = os.environ.get("GRAPHENE_SPEND_CAP_USD")
    try:
        return float(said) if said else None
    except ValueError:
        return None


def spent() -> float:
    """The ledger's total, in dollars at list price (0 with no ledger)."""
    ledger = _ledger()
    if ledger is None or not ledger.exists():
        return 0.0
    total = 0.0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(line).get("dollars") or 0)
        except (ValueError, AttributeError):
            continue
    return total


def chat(model: str, messages: list[dict], tools: list[dict] | None = None, tag: str = "", **params) -> dict:
    """One chat completion. Returns ``{"message", "usage", "dollars", "seconds", "model"}``: the
    assistant's message as Token Factory sent it (``content``, ``tool_calls``, any reasoning), its usage,
    and that usage at list price. ``params`` go into the request as they are (temperature, max_tokens,
    and whatever a model reads beyond those). ``tag`` names the caller in the ledger (a leaf's id)."""
    limit = cap()
    if limit is not None and _ledger() is not None and spent() >= limit:
        raise Spent(f"the spend cap is reached: ${spent():.2f} of ${limit:.2f} (GRAPHENE_SPEND_CAP_USD)")
    body = {"model": model, "messages": messages, **({"tools": tools} if tools else {}), **params}
    began = time.monotonic()
    said, headers = _request("POST", "chat/completions", body, timeout=TIMEOUT)
    took = time.monotonic() - began
    try:
        message = said["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise Unreachable(f"Token Factory sent no message: {json.dumps(said)[:300]}") from None
    usage = said.get("usage") or {}
    cost = dollars(usage, model)
    out = {"message": message, "usage": usage, "dollars": cost, "seconds": round(took, 3), "model": model}
    _write(_ledger(), {"at": time.time(), "tag": tag, "model": model, "usage": usage, "dollars": cost,
                       "seconds": out["seconds"]})  # fmt: skip
    record = os.environ.get("GRAPHENE_TOKENFACTORY_RECORD")
    if record:
        _write(Path(record), {"request": body, "response": said})
    return out


def _write(path: Path | None, row: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def reach() -> str | None:
    """What could not be reached, in one line, or None when the key works and a Nemotron model is
    listed. `graphene init` says it."""
    try:
        found = roles()
    except Unreachable as no:
        return str(no)
    if not found:
        return "Token Factory lists no NVIDIA Nemotron model for this key"
    return None
