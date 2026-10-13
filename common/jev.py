"""Adapter for Jev (TypeSafe AI), a decision model: typed questions in, probabilities out, no text generation.

The ONLY module that talks to Jev, so the vendor can be swapped. Use it for closed-set judgments that gate or
narrow a Claude call (routing, triage). It never replaces Claude, and a probability is never a permission.

UNVERIFIED: the wire format below (endpoint, body, response shape) comes from third-party guides that disagree.
Check it against TypeSafe's docs before a live call. Tests and evals inject a `transport`, so nothing here
touches the network unless you leave `transport` unset and have TYPESAFE_API_KEY.
"""
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

JEV_VERSION = "jev-1.13"  # pin: the API is changing weekly
URL = "https://api.typesafe.ai/v1/systemone"  # unverified, see module docstring
UNKNOWN = "other"  # every Choice gets an escape hatch, or Jev must pick a wrong option (0.31 'sales' for cafeteria)
RETRYABLE = {429, 500, 502, 503, 504}


@dataclass
class Choice:
    options: dict[str, str]  # name -> description


@dataclass
class Score:
    levels: list[str]  # ordered, e.g. ["low", "medium", "high"]


@dataclass
class Noul:
    statement: str  # a yes/no statement; the answer is P(true)


@dataclass
class Answer:
    probs: dict[str, float]  # Choice/Score: per option. Noul: {"true": p}

    @property
    def top(self) -> str:
        return max(self.probs, key=self.probs.get)

    @property
    def confidence(self) -> float:
        return self.probs[self.top]


def _payload(state: dict, questions: dict, version: str) -> dict:
    qs = {}
    for name, q in questions.items():
        if isinstance(q, Choice):
            qs[name] = {"type": "choice", "options": {**q.options, UNKNOWN: "none of the above / unclear"}}
        elif isinstance(q, Score):
            qs[name] = {"type": "score", "levels": q.levels}
        else:
            qs[name] = {"type": "noul", "statement": q.statement}
    return {"model": version, "state": state, "questions": qs}


def _parse(raw: dict, questions: dict, version: str) -> dict[str, Answer] | None:
    """Validate shape, version and probabilities. Any surprise returns None (the caller falls back):
    a valid-looking JSON response is not evidence that the decision is right."""
    try:
        if raw.get("model") and not str(raw["model"]).startswith(version):
            return None  # a silently upgraded model has different calibration
        out = {}
        for name, q in questions.items():
            a = raw["answers"][name]
            probs = {"true": float(a["probability"])} if isinstance(q, Noul) else \
                {k: float(v) for k, v in a["probabilities"].items()}
            allowed = {"true"} if isinstance(q, Noul) else \
                set(q.options) | {UNKNOWN} if isinstance(q, Choice) else set(q.levels)
            if not set(probs) <= allowed or any(not 0 <= p <= 1 for p in probs.values()):
                return None
            out[name] = Answer(probs)
        return out
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def http_transport(payload: dict, timeout: float) -> dict:
    key = os.getenv("TYPESAFE_API_KEY")
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is not set")
    req = urllib.request.Request(URL, json.dumps(payload).encode(), {
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def decide(state: dict, questions: dict, *, version: str = JEV_VERSION, timeout: float = 2.0, retries: int = 2,
           transport: Callable[[dict, float], dict] | None = None) -> dict[str, Answer] | None:
    """Ask all questions about one state in one call. Returns None on ANY failure (caller must have a fallback).
    Retries only retryable failures (429, 5xx, connection), with a short backoff, within the same timeout."""
    transport = transport or http_transport
    payload = _payload(state, questions, version)
    for attempt in range(retries + 1):
        try:
            return _parse(transport(payload, timeout), questions, version)
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE:
                return None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        except Exception:  # unexpected (missing key, bad JSON): do not retry, do not crash the run
            return None
        time.sleep(0.2 * (attempt + 1))
    return None
