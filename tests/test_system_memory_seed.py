import json

from scripts.seed_system_memory import (
    DEFAULT_LAYER_FACTS_PATH,
    load_layer_facts,
    memory_items_from_layers,
)


def test_layer_facts_seed_one_global_memory_item_per_architecture_layer() -> None:
    layers = load_layer_facts(DEFAULT_LAYER_FACTS_PATH)

    assert [layer["id"] for layer in layers] == list("ABCDEFGHI")
    items = memory_items_from_layers(layers)
    assert len(items) == 9
    assert {item["scope"] for item in items} == {"global"}
    assert {item["agent_id"] for item in items} == {None}
    assert {item["project_id"] for item in items} == {None}

    first_content = json.loads(items[0]["content"])
    assert first_content["type"] == "synarch.layer_status"
    assert first_content["layer"]["id"] == "A"
    assert first_content["layer"]["source"] == "docs/roadmap.md"
