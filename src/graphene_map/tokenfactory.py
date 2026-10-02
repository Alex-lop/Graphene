"""Token Factory: Nebius's OpenAI-compatible inference API, which the Nemotron planner and executor call.

Standard library only: two endpoints (the model list and chat completions) need no client library.
The key is found when a call is made (``keys.find``: ``NEBIUS_API_KEY``, then the keychain), sent in one
header, and written nowhere:
not in the store, a log, the ledger or a recording.

Model ids are never written here. ``roles`` reads them from the live list (``GET /models``), so an id
Graphene uses is one Token Factory said it has. Each call's usage is priced at the list price that same
list gives, per token, and appended to the spend ledger when one is named (``GRAPHENE_LEDGER``); a
ledger whose total has reached ``GRAPHENE_SPEND_CAP_USD`` refuses the next call before it is made.

While the person's opening is set (``GRAPHENE_AGENT_LIVE_USD``), each call also reserves its worst case in
the night's ledger before it is sent and settles to its usage after (``night``): one that would take the
night past its cap is refused, and nothing is sent.

``GRAPHENE_TOKENFACTORY_URL`` points everything at another endpoint (the tests' recorded fake), and
``GRAPHENE_TOKENFACTORY_RECORD`` appends each exchange to a file, so a live run can be replayed later.
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from graphene_map import keys, night

# the retry loop's wait, by a name of its own: a test that stops it must not catch the polls of
# Popen.wait(timeout=...), which sleep through time.sleep too (0.001, 0.002, ... on a slow child)
_sleep = time.sleep

BASE = "https://api.tokenfactory.nebius.com/v1/"
KEY = "NEBIUS_API_KEY"
TRIES = 6  # a 429 or a 5xx is tried again, waiting what the server asks or twice as long each time
TIMEOUT = 300  # seconds for one completion: a long reasoning answer from the largest model takes minutes
LISTED = 10  # seconds a try at the model list waits for an answer: offline, init must not wait a minute


# Shaped like a key: 20 or more letters and digits in a row, a capital, a small letter and a digit among
# them (a key, a token, a JWT's part). The whole word it sits in goes (up to a space, a slash or a quote),
# so no piece of a key is left. A git sha, a uuid, a node's id, a log's name and a model's name have none.
ALNUM = "[A-Za-z0-9]"
SHAPED = re.compile(rf"(?<!{ALNUM})(?={ALNUM}*[A-Z])(?={ALNUM}*[a-z])(?={ALNUM}*[0-9]){ALNUM}{{20}}")
WORD = re.compile(r"[\w.\-]{20,}", re.ASCII)
# base64, which a word above ends at a / or a + (an AWS secret access key): 30 or more of its letters with a
# capital, a small letter, a digit and a / or a +, and its padding. A . - or _ breaks it, so a path is kept
# unless 30 of its characters in a row are letters, digits and slashes alone.
B64 = "[A-Za-z0-9+/]"
BASE64 = re.compile(
    rf"(?<!{B64})(?={B64}*[A-Z])(?={B64}*[a-z])(?={B64}*[0-9])(?={B64}*[+/]){B64}{{30,}}=*"
)
REMOVED = "[removed: shaped like a key]"


def unkeyed(value: str) -> str:
    """``value`` with every word shaped like a key, and every run of base64 shaped like one, taken out."""
    return WORD.sub(lambda word: REMOVED if SHAPED.search(word[0]) else word[0], BASE64.sub(REMOVED, value))


class Unreachable(Exception):
    """Token Factory could not be reached, or said no; the message says which, in one line."""


class Spent(Unreachable):
    """The ledger's total has reached the cap, the night's would pass its own, or an agent's shell has not
    been opened to spend (``night.person_only``): no call is made."""


class Late(Unreachable):
    """A completion that may have reached the model and got no answer: a try that timed out, a 5xx, or a
    connection that broke once made. Token Factory may have done the work, and billed it."""


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
    key = keys.find()
    if not key:
        raise Unreachable(f"{KEY} is not set: Token Factory needs a key (tokenfactory.nebius.com)")
    if any(c.isspace() for c in key):  # a header cannot carry it, and its error would print the key
        raise Unreachable(f"the key found holds a space or a line break: set {KEY} or `graphene key set`")
    if not (key.isascii() and key.isprintable()):  # a pasted en dash: the header is never built
        raise Unreachable(f"the key found holds a character that is not plain ASCII letters, digits and "
                          f"punctuation (a pasted dash?): set {KEY} or `graphene key set` again")  # fmt: skip
    data = json.dumps(body).encode() if body is not None else None
    wait, maybe = 2.0, False  # maybe: a try may have reached the model; only a 4xx or no connection says not
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(base() + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                answer, headers = resp.read(), dict(resp.headers)
            try:
                return json.loads(answer or b"{}"), headers
            except ValueError:  # a sign-in page, a proxy's: not Token Factory (an earlier try may have been)
                said = (f"Token Factory's answer at {base()} is not JSON: a proxy, or a wrong "
                        "GRAPHENE_TOKENFACTORY_URL?")  # fmt: skip
                raise (Late if maybe and method == "POST" else Unreachable)(said) from None
        except urllib.error.HTTPError as no:
            # a gateway's page may echo the Authorization header: the key goes before the cut can halve it
            said = unkeyed(no.read(65536).decode("utf-8", "replace").replace(key, "…"))[:300]
            maybe = maybe or no.code >= 500
            if (no.code == 429 or no.code >= 500) and attempt < tries:
                after = no.headers.get("Retry-After")
                _sleep(float(after) if after and after.replace(".", "", 1).isdigit() else wait)
                wait *= 2
                continue
            raise (Late if maybe and method == "POST" else Unreachable)(
                f"Token Factory answered {no.code} to {method} /{path}: {said}{_then(no.code, attempt)}"
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as no:
            slow = isinstance(no, TimeoutError) or "timed out" in str(no)
            never = (ConnectionRefusedError, socket.gaierror)  # nothing listened, or no such host: never sent
            maybe = maybe or not isinstance(getattr(no, "reason", no), never)
            if slow and method == "POST":  # a completion that took the whole timeout: once more, not six
                tries = min(tries, attempt + 1)
            if attempt < tries:
                _sleep(wait)
                wait *= 2
                continue
            then = _then(0, attempt, timeout) if slow and method == "POST" else ""
            said = f"Token Factory could not be reached at {base()}: {no}{then}"
            raise (Late if maybe and method == "POST" else Unreachable)(said) from None
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


def worst(body: dict, model_id: str) -> float:
    """The most a call may cost at list price: its prompt at a token for every 3 bytes of the request (a
    token is about 4 characters of English, so 3 overestimates it) and its max_tokens of completion
    (night.UNSAID when it names none)."""
    m = price(model_id)
    return len(json.dumps(body)) / 3 * m.prompt + int(body.get("max_tokens") or night.UNSAID) * m.completion


def dollars(usage: dict, model_id: str) -> float:
    m = price(model_id)
    return (usage.get("prompt_tokens") or 0) * m.prompt + (usage.get("completion_tokens") or 0) * m.completion


# -- the ledger: every call's usage at list price, and the cap -------------------------------------------


def _ledger() -> Path | None:
    named = os.environ.get("GRAPHENE_LEDGER")
    return Path(named) if named else None


def cap() -> float | None:
    """GRAPHENE_SPEND_CAP_USD in dollars, or None when it is not set: no cap. A figure that is not a
    number (``$10``, ``nan``) raises Spent, so every call is refused rather than none (as ``night.cap``)."""
    said = os.environ.get("GRAPHENE_SPEND_CAP_USD")
    if not said:
        return None
    try:
        if math.isfinite(dollars := float(said)):
            return dollars
    except ValueError:
        pass
    raise Spent(f"GRAPHENE_SPEND_CAP_USD is {said!r}, not a number of dollars: set it as "
                "GRAPHENE_SPEND_CAP_USD=10, or unset it for no cap")  # fmt: skip


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


def chat(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tag: str = "",
    tries: int | None = None,
    timeout: float | None = None,
    **params,
) -> dict:
    """One chat completion. Returns ``{"message", "usage", "dollars", "seconds", "model"}``: the
    assistant's message as Token Factory sent it (``content``, ``tool_calls``, any reasoning), its usage,
    and that usage at list price. ``params`` go into the request as they are (temperature, max_tokens,
    and whatever a model reads beyond those). ``tag`` names the caller in the ledger (a leaf's id).
    ``tries`` and ``timeout`` are the request's: a helper nobody waits on asks once, briefly."""
    limit = cap()
    if limit is not None and _ledger() is not None and spent() >= limit:
        raise Spent(f"the spend cap is reached: ${spent():.2f} of ${limit:.2f} (GRAPHENE_SPEND_CAP_USD)")
    body = {"model": model, "messages": messages, **({"tools": tools} if tools else {}), **params}
    try:
        if endpoint() == "token factory":  # the real host; the fake and a proxy are anyone's
            night.person_only(f"a call to {model}")
        most = worst(body, model) if night.cap() is not None else 0.0
        held = night.reserve(model, most, tag, endpoint())
    except night.Refused as no:
        raise Spent(str(no)) from None
    began = time.monotonic()
    try:
        said, headers = _request("POST", "chat/completions", body, timeout or TIMEOUT, tries or TRIES)
    except Unreachable as no:  # a 4xx, no connection, no key: nothing was done; else (Late) maybe it was
        night.settle(held, model, most if isinstance(no, Late) else 0.0)
        raise
    except BaseException:  # stopped while it was out (Ctrl-C, or TERM as SystemExit): maybe done, and billed
        night.settle(held, model, most)
        raise
    # ponytail: a try that may have been done (it timed out, a 5xx) and then another that answered is settled
    # at the answer's usage alone
    took = time.monotonic() - began
    usage = (said.get("usage") if isinstance(said, dict) else None) or {}
    cost = dollars(usage, model)
    night.settle(held, model, cost, usage)
    try:
        message = said["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise Unreachable(f"Token Factory sent no message: {json.dumps(said)[:300]}") from None
    finish = (said.get("choices") or [{}])[0].get("finish_reason")
    out = {"message": message, "usage": usage, "dollars": cost, "seconds": round(took, 3), "model": model,
           "finish": finish}  # fmt: skip
    _write(_ledger(), {"at": time.time(), "tag": tag, "model": model, "usage": usage, "dollars": cost,
                       "seconds": out["seconds"], **({"practice": True} if held else {})})  # fmt: skip
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
