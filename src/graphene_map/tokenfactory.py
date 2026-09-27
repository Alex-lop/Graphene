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
LISTED = 10  # seconds a try at the model list waits for an answer: offline, init must not wait a minute


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


def endpoint() -> str:
    """Who answered, as a usage row says it: "token factory", or "a stand-in" when
    GRAPHENE_TOKENFACTORY_URL points anywhere else (the tests' fake, a proxy). Never the URL itself: it
    could name a host of the person's."""
    return "token factory" if base() == BASE else "a stand-in"


def _request(
    method: str, path: str, body: dict | None = None, timeout: float = 60, tries: int = TRIES
) -> tuple[dict, dict]:
    """One request, tried again on a 429 or a 5xx. Returns the JSON answer and the response headers."""
    key = os.environ.get(KEY)
    if not key:
        raise Unreachable(f"{KEY} is not set: Token Factory needs a key (tokenfactory.nebius.com)")
    data = json.dumps(body).encode() if body is not None else None
    wait = 2.0
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(base() + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                answer, headers = resp.read(), dict(resp.headers)
            try:
                return json.loads(answer or b"{}"), headers
            except ValueError:  # a sign-in page, a proxy's: not Token Factory speaking
                raise Unreachable(f"Token Factory's answer at {base()} is not JSON: a proxy, or a wrong "
                                  "GRAPHENE_TOKENFACTORY_URL?") from None  # fmt: skip
        except urllib.error.HTTPError as no:
            said = no.read().decode("utf-8", "replace")[:300]
            if (no.code == 429 or no.code >= 500) and attempt < tries:
                after = no.headers.get("Retry-After")
                time.sleep(float(after) if after and after.replace(".", "", 1).isdigit() else wait)
                wait *= 2
                continue
            raise Unreachable(f"Token Factory answered {no.code} to {method} /{path}: {said}"
                              f"{_then(no.code, attempt)}") from None  # fmt: skip
        except (urllib.error.URLError, TimeoutError, OSError) as no:
            slow = isinstance(no, TimeoutError) or "timed out" in str(no)
            if slow and method == "POST":  # a completion that took the whole timeout: once more, not six
                tries = min(tries, attempt + 1)
            if attempt < tries:
                time.sleep(wait)
                wait *= 2
                continue
            then = _then(0, attempt, timeout) if slow and method == "POST" else ""
            raise Unreachable(f"Token Factory could not be reached at {base()}: {no}{then}") from None
    raise AssertionError("unreachable")  # pragma: no cover


def _then(code: int, tried: int, timeout: float = 0) -> str:
    """What a person can do next, after ``tried`` tries ended in ``code`` (0: no answer in time)."""
    times = "once" if tried == 1 else f"{tried} times"
    if code == 429:
        return (f" (asked {times}: Token Factory limits how fast this key may ask; wait a minute and run "
                "again, or run fewer leaves at once)")  # fmt: skip
    if code >= 500:
        return f" (asked {times}: the fault is on Token Factory's side; try again later)"
    if code == 0:
        return (f" (no answer in {timeout:g} s, asked {times}: try again later, or ask for a shorter answer "
                "with --max-tokens)")  # fmt: skip
    return ""


@lru_cache(maxsize=4)
def _listed(url: str, tries: int = TRIES) -> tuple[Model, ...]:
    said, _ = _request("GET", "models?verbose=true", timeout=LISTED, tries=tries)
    out = []
    for m in said.get("data") or []:
        price = m.get("pricing") or {}
        out.append(Model(m["id"], float(price.get("prompt") or 0), float(price.get("completion") or 0),
                         int(m.get("created") or 0)))  # fmt: skip
    return tuple(out)


def models(tries: int = TRIES) -> list[Model]:
    """Every model Token Factory lists for this key, with its list price (asked once a process)."""
    return list(_listed(base(), tries))


ROLES = ("ultra", "super", "nano")


def _size(model_id: str) -> str | None:
    """The Nemotron size an id names (ultra, super or nano), or None when it names none."""
    name = model_id.lower()
    return next((r for r in ROLES if r in name), None) if "nemotron" in name else None


def roles(listed: list[Model] | None = None) -> dict[str, str]:
    """The NVIDIA Nemotron models in the live list, by size: ``{"ultra": id, "super": id, "nano": id}``
    for those that are there. Where one size is listed twice, the newest wins; a "-fast" variant is a
    second choice. Nothing here names an id: whatever the list says is what is used."""
    listed = models() if listed is None else listed
    found: dict[str, Model] = {}
    for m in listed:
        size = _size(m.id)
        if size is None:
            continue
        rank = (not m.id.lower().endswith("-fast"), m.created)
        if size not in found or rank > (not found[size].id.lower().endswith("-fast"), found[size].created):
            found[size] = m
    return {r: found[r].id for r in ROLES if r in found}


def resolve(given: list[str], role: str, listed: list[Model] | None = None) -> tuple[list[str], list[str]]:
    """The model ids ``role`` (the planner or the executor) uses, and one line for each that is not
    the one it was given or would have had. Token Factory retires models on notice, so an id `graphene
    init` wrote into a repository, or one given with --model, can leave the list before the run that
    names it. The rule stays within the family:

    - an id the live list has is used as it is;
    - an id it lacks that names a Nemotron size is replaced by the listed Nemotron of that size that
      ``roles`` picks (the newest), else by the nearest size listed, the larger of two as near: a
      ladder's rung above stays above, and the check still decides what lands;
    - an id that names no Nemotron size, or any id while no Nemotron is listed, is kept: Token
      Factory's own answer then says what is wrong with it;
    - with no id given, the planner has the largest Nemotron listed and the executor the smallest, and
      a line says so when that is not Ultra or Nano.

    An empty list back means no Nemotron is listed at all."""
    listed = models() if listed is None else listed
    found, ids = roles(listed), {m.id for m in listed}
    rank = ROLES[::-1].index  # nano 0, super 1, ultra 2
    sizes = sorted(found, key=rank)
    if not given:
        if not sizes:
            return [], []
        planner = role == "planner"
        size, wanted, most = (sizes[-1], "ultra", "largest") if planner else (sizes[0], "nano", "smallest")
        if size == wanted:
            return [found[size]], []
        return [found[size]], [f"Token Factory lists no Nemotron {wanted.title()}; the {role} uses "
                               f"{found[size]}, the {most} Nemotron listed"]  # fmt: skip
    out, said = [], []
    for g in given:
        size = _size(g)
        if g in ids or size is None or not sizes:
            out.append(g)
            continue
        near = min(sizes, key=lambda s: (abs(rank(s) - rank(size)), -rank(s)))
        which = f"the Nemotron {near.title()} listed" + ("" if near == size else ", the nearest size")
        out.append(found[near])
        said.append(f"{g} is not in Token Factory's list (retired?); the {role} uses {found[near]} instead, "
                    f"{which}. `graphene init --{role} nemotron` writes the ids listed now")  # fmt: skip
    return out, said


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
    finish = (said.get("choices") or [{}])[0].get("finish_reason")
    out = {"message": message, "usage": usage, "dollars": cost, "seconds": round(took, 3), "model": model,
           "finish": finish}  # fmt: skip
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


def reach(tries: int = TRIES) -> str | None:
    """What could not be reached, in one line, or None when the key works and a Nemotron model is
    listed. `graphene init` says it, asking once (``tries=1``): offline, it must not wait a minute."""
    try:
        found = roles(models(tries))
    except Unreachable as no:
        return " ".join(str(no).split())  # a gateway's error page has lines of its own
    if not found:
        return "Token Factory lists no NVIDIA Nemotron model for this key"
    return None
