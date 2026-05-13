from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib import request

DEFAULT_LAYER_FACTS_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "system-facts" / "layers.json"
)
DEFAULT_MEMORY_SERVICE_URL = "http://localhost:8030"


def load_layer_facts(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Layer facts must be a JSON array.")
    return [validate_layer_fact(item) for item in data]


def validate_layer_fact(item: object) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Each layer fact must be a JSON object.")
    for field in ("id", "name", "status", "exists_now", "main_gap", "next_validation"):
        if field not in item:
            raise ValueError(f"Layer fact is missing required field: {field}")
    return dict(item)


def memory_items_from_layers(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for layer in layers:
        layer_id = str(layer["id"]).lower()
        content = {
            "type": "synarch.layer_status",
            "layer": layer,
        }
        items.append(
            {
                "id": f"memory_system_layer_{layer_id}_v1",
                "scope": "global",
                "agent_id": None,
                "project_id": None,
                "content": json.dumps(content, ensure_ascii=True, sort_keys=True),
            }
        )
    return items


def post_memory_item(memory_service_url: str, item: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(item).encode("utf-8")
    target = f"{memory_service_url.rstrip('/')}/memory-items"
    http_request = request.Request(
        target,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=10) as response:
        response_body = response.read().decode("utf-8")
        if response.status != 201:
            raise RuntimeError(f"Memory service returned {response.status}: {response_body}")
        payload = json.loads(response_body)
        if not isinstance(payload, dict):
            raise RuntimeError("Memory service returned a non-object response.")
        return dict(payload)


def seed_system_memory(
    *,
    memory_service_url: str,
    facts_path: Path,
    dry_run: bool,
) -> list[dict[str, Any]]:
    items = memory_items_from_layers(load_layer_facts(facts_path))
    if dry_run:
        return items
    return [post_memory_item(memory_service_url, item) for item in items]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Synarch system facts into memory-service.")
    parser.add_argument(
        "--memory-service-url",
        default=os.getenv("MEMORY_SERVICE_URL", DEFAULT_MEMORY_SERVICE_URL),
    )
    parser.add_argument("--facts-path", type=Path, default=DEFAULT_LAYER_FACTS_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    items = seed_system_memory(
        memory_service_url=args.memory_service_url,
        facts_path=args.facts_path,
        dry_run=args.dry_run,
    )
    print(json.dumps({"seeded": len(items), "ids": [item["id"] for item in items]}, indent=2))


if __name__ == "__main__":
    main()
