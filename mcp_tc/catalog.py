from __future__ import annotations

import json
import os
from typing import Any

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json")

_catalog: dict[str, Any] | None = None
_actions: list[dict[str, Any]] | None = None


def load() -> dict[str, Any]:
    global _catalog
    if _catalog is None:
        with open(_PATH, encoding="utf-8") as handle:
            _catalog = json.load(handle)
    return _catalog


def flatten() -> list[dict[str, Any]]:
    global _actions
    if _actions is None:
        items: list[dict[str, Any]] = []
        for service, doc in load().items():
            for action, meta in doc.get("actions", {}).items():
                items.append(
                    {
                        "service": service,
                        "version": doc["version"],
                        "product": doc.get("product", service),
                        "action": action,
                        "summary": meta.get("summary", ""),
                        "requiresRegion": meta.get("requiresRegion", True) is not False,
                        "dangerous": meta.get("dangerous", False) is True,
                        "params": meta.get("params", {}),
                        "docUrl": doc.get("docUrl", ""),
                    }
                )
        _actions = items
    return _actions


def resolve_version(service: str) -> str | None:
    doc = load().get(service.strip().lower())
    return doc.get("version") if doc else None


def action_meta(service: str, action: str) -> dict[str, Any] | None:
    doc = load().get(service)
    if not doc:
        return None
    return doc.get("actions", {}).get(action)


def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = [t for t in query.lower().replace("/", " ").replace(",", " ").split() if t]
    if not terms:
        return flatten()[:limit]

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in flatten():
        haystack = " ".join(
            [
                entry["service"],
                entry["product"],
                entry["action"],
                entry["summary"],
                " ".join(entry["params"].keys()),
                " ".join(str(v) for v in entry["params"].values()),
            ]
        ).lower()
        score = 0
        for term in terms:
            if term not in haystack:
                continue
            score += 1
            if term in entry["action"].lower():
                score += 2
            if term == entry["service"]:
                score += 1
        if score:
            scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:limit]]
