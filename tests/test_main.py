# Copyright 2026 Enactic, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pyarrow as pa
import pytest

from dora_openarm_selector import main


class _FakeNode:
    def __init__(self):
        self.outputs = []

    def send_output(self, output_id, value, metadata=None):
        self.outputs.append((output_id, value, metadata))

    def values(self):
        return [(output_id, value.to_pylist()) for output_id, value, _ in self.outputs]


def _input(input_id, value, metadata=None):
    return {"type": "INPUT", "id": input_id, "value": value, "metadata": metadata or {}}


def _input_closed(input_id):
    return {"type": "INPUT_CLOSED", "id": input_id}


def _enabled(source, enabled):
    return _input(f"{source}_enabled", pa.array([enabled]))


INPUT_IDS = ["vr_enabled", "vr_right", "vr_left", "policy_right", "policy_left"]
OUTPUT_IDS = ["right", "left", "selected"]


@pytest.fixture
def selector():
    return main.Selector(["vr", "policy"], INPUT_IDS)


@pytest.fixture
def node():
    return _FakeNode()


@pytest.fixture
def handler(node, selector):
    return main.SelectorNode(node, selector, OUTPUT_IDS)


def test_initial_selection_without_enabled_input(selector):
    assert selector.selected == "policy"


def test_initial_selection_none():
    selector = main.Selector(["vr", "policy"], ["vr_enabled", "policy_enabled"])
    assert selector.selected is None


def test_initial_selection_all_always_enabled():
    selector = main.Selector(["vr", "policy"], ["vr_right", "policy_right"])
    assert selector.selected == "vr"


@pytest.mark.parametrize(
    "sources",
    [[""], ["vr_left"], ["vr", "vr"]],
)
def test_invalid_sources(sources):
    with pytest.raises(ValueError):
        main.Selector(sources, [])


def test_source_without_input():
    with pytest.raises(ValueError, match="source has no input: typo"):
        main.Selector(["typo", "vr", "policy"], INPUT_IDS)


def test_parse_sources():
    assert main.parse_sources("vr, policy ") == ["vr", "policy"]


@pytest.mark.parametrize(
    "input_id",
    ["vr", "vr_", "vr_selected", "_right", "other", "other_", "other_selected"],
)
def test_invalid_input_id(input_id):
    with pytest.raises(ValueError):
        main.Selector(["vr", "policy"], ["policy_right", input_id])


def test_ignore_other_sources(node, capsys):
    selector = main.Selector(["policy"], INPUT_IDS)
    assert selector.ignored_input_ids == ["vr_enabled", "vr_right", "vr_left"]
    handler = main.SelectorNode(node, selector, OUTPUT_IDS)
    handler.start()
    handler.process_event(_input("vr_right", pa.array([1.0])))
    handler.process_event(_input_closed("vr_left"))
    handler.process_event(_input("policy_right", pa.array([2.0])))
    assert node.values() == [("selected", ["policy"]), ("right", [2.0])]
    assert capsys.readouterr().out == (
        "ignore inputs of other sources: ['vr_enabled', 'vr_right', 'vr_left']\n"
    )


def test_channel_with_underscore(selector):
    assert selector.parse_input_id("vr_right_arm") == ("vr", "right_arm")


def test_start(node, handler):
    handler.start()
    assert node.values() == [("selected", ["policy"])]


def test_without_selected_output(node, selector):
    handler = main.SelectorNode(node, selector, ["right", "left"])
    handler.start()
    handler.process_event(_enabled("vr", True))
    assert node.outputs == []


def test_forward_selected(node, handler):
    value = pa.array([1.0, 2.0])
    handler.process_event(_input("policy_right", value, {"a": 1}))
    assert node.outputs == [
        ("right", value, {"a": 1, "selected_source": "policy"}),
    ]


def test_drop_unselected(node, handler):
    handler.process_event(_input("vr_right", pa.array([1.0])))
    assert node.outputs == []


def test_switch(node, handler):
    handler.process_event(_enabled("vr", True))
    handler.process_event(_input("policy_left", pa.array([1.0])))
    handler.process_event(_input("vr_left", pa.array([2.0])))
    handler.process_event(_enabled("vr", False))
    handler.process_event(_input("vr_left", pa.array([3.0])))
    handler.process_event(_input("policy_left", pa.array([4.0])))
    assert node.values() == [
        ("selected", ["vr"]),
        ("left", [2.0]),
        ("selected", ["policy"]),
        ("left", [4.0]),
    ]


def test_selected_only_on_change(node, handler):
    handler.process_event(_enabled("vr", False))
    handler.process_event(_enabled("vr", True))
    handler.process_event(_enabled("vr", True))
    assert node.values() == [("selected", ["vr"])]


def test_selected_empty_when_none(node):
    selector = main.Selector(["vr"], ["vr_enabled", "vr_right"])
    handler = main.SelectorNode(node, selector, OUTPUT_IDS)
    handler.process_event(_enabled("vr", True))
    handler.process_event(_enabled("vr", False))
    handler.process_event(_input("vr_right", pa.array([1.0])))
    assert node.values() == [("selected", ["vr"]), ("selected", [""])]


@pytest.mark.parametrize(
    "value",
    [
        pa.array([True, False]),
        pa.array([1]),
        pa.array([], pa.bool_()),
        pa.array([None], pa.bool_()),
    ],
)
def test_invalid_enabled(node, selector, handler, value):
    handler.process_event(_enabled("vr", True))
    handler.process_event(_input("vr_enabled", value))
    assert node.values() == [("selected", ["vr"])]
    assert selector.selected == "vr"


def test_enabled_input_closed(node, handler):
    handler.process_event(_enabled("vr", True))
    handler.process_event(_input_closed("vr_enabled"))
    handler.process_event(_input("policy_right", pa.array([1.0])))
    assert node.values() == [
        ("selected", ["vr"]),
        ("selected", ["policy"]),
        ("right", [1.0]),
    ]


def test_data_input_closed(selector, handler):
    handler.process_event(_enabled("vr", True))
    handler.process_event(_input_closed("vr_right"))
    assert selector.selected == "vr"


def test_ignore_other_events(node, handler):
    handler.process_event({"type": "STOP"})
    assert node.outputs == []


def test_all_data_inputs_closed(node, selector, handler):
    handler.process_event(_enabled("vr", True))
    handler.process_event(_input_closed("vr_right"))
    handler.process_event(_input_closed("vr_left"))
    handler.process_event(_enabled("vr", True))
    assert node.values() == [("selected", ["vr"]), ("selected", ["policy"])]


def test_always_enabled_data_inputs_closed(node):
    selector = main.Selector(["policy", "fallback"], ["policy_right", "fallback_right"])
    handler = main.SelectorNode(node, selector, OUTPUT_IDS)
    handler.process_event(_input_closed("policy_right"))
    handler.process_event(_input("fallback_right", pa.array([1.0])))
    assert node.values() == [("selected", ["fallback"]), ("right", [1.0])]


def test_source_without_data_input():
    selector = main.Selector(["vr", "policy"], ["vr_enabled", "policy_right"])
    selector.set_enabled("vr", True)
    assert selector.selected == "policy"


def test_error_event(node, handler, capsys):
    handler.process_event({"type": "ERROR", "error": "boom"})
    assert node.outputs == []
    assert capsys.readouterr().out == "dora-rs error: boom\n"


def test_empty_sources_environment_variable(monkeypatch):
    monkeypatch.setenv("SOURCES", "")
    monkeypatch.setattr("sys.argv", ["dora-openarm-selector"])
    with pytest.raises(SystemExit):
        main.main()
