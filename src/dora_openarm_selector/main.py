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

"""Source selector node.

This dora-rs node receives the same kind of messages from several
sources and forwards only the ones from the selected source. The
selected source is the highest-priority one among the enabled sources.

Inputs are named ``<source>_<channel>`` and ``<source>_enabled``. A
source that has no ``<source>_enabled`` input wired is always enabled.
Values are forwarded as is, so this node depends on neither the robot
nor the meaning of the values.
"""

import argparse

import dora
import pyarrow as pa

_ENABLED_CHANNEL = "enabled"
_SELECTED_OUTPUT = "selected"
_SELECTED_SOURCE_METADATA = "selected_source"


class Selector:
    """Selection state of sources.

    Args:
        sources: Source names. The first one has the highest priority.
        input_ids: Input IDs of this node. A source without
            ``<source>_enabled`` in them is always enabled. A source
            whose data inputs are all closed is never selected.

    Raises:
        ValueError: If a source name is invalid or an input ID doesn't
            belong to any source.

    """

    def __init__(self, sources, input_ids):
        """Initialize the selection state."""
        for source in sources:
            if not source:
                raise ValueError("source name must not be empty")
            if "_" in source:
                raise ValueError(f"source name must not contain '_': {source}")
        if len(set(sources)) != len(sources):
            raise ValueError(f"source names must be unique: {sources}")
        self.sources = sources
        self.enabled = {source: True for source in self.sources}
        self.open_data_inputs = {source: set() for source in self.sources}
        # Parsing also rejects miswired input IDs at startup, not at
        # their first message.
        for input_id in input_ids:
            source, channel = self.parse_input_id(input_id)
            if channel == _ENABLED_CHANNEL:
                self.enabled[source] = False
            else:
                self.open_data_inputs[source].add(input_id)

    @property
    def selected(self):
        """The highest-priority enabled source with open data inputs or ``None``."""
        return next(
            (
                source
                for source in self.sources
                if self.enabled[source] and self.open_data_inputs[source]
            ),
            None,
        )

    def parse_input_id(self, input_id):
        """Split an input ID into its source and channel.

        Args:
            input_id: Input ID such as ``vr_right``.

        Returns:
            ``(source, channel)``.

        Raises:
            ValueError: If the input ID doesn't belong to any source or
                its channel conflicts with the ``selected`` output.

        """
        source, _, channel = input_id.partition("_")
        if source not in self.sources or not channel:
            raise ValueError(
                f"input ID must be <source>_<channel> "
                f"with source in {self.sources}: {input_id}"
            )
        if channel == _SELECTED_OUTPUT:
            raise ValueError(
                f"channel name '{_SELECTED_OUTPUT}' is reserved: {input_id}"
            )
        return source, channel

    def set_enabled(self, source, enabled):
        """Enable or disable a source and select again.

        Args:
            source: Source name.
            enabled: Whether the source is enabled.

        Returns:
            ``True`` if the selected source has changed.

        """
        previous = self.selected
        self.enabled[source] = enabled
        return self.selected != previous

    def close_input(self, input_id):
        """Close an input and select again.

        A source whose ``<source>_enabled`` input is closed is disabled
        because nobody can enable it any more. A source whose data
        inputs are all closed is never selected because it has nothing
        to forward. Otherwise, they would block lower-priority sources
        forever.

        Args:
            input_id: Closed input ID.

        Returns:
            ``True`` if the selected source has changed.

        """
        source, channel = self.parse_input_id(input_id)
        previous = self.selected
        if channel == _ENABLED_CHANNEL:
            self.enabled[source] = False
        else:
            self.open_data_inputs[source].discard(input_id)
        return self.selected != previous


def parse_sources(text):
    """Parse comma-separated source names.

    Args:
        text: Comma-separated source names such as ``vr,policy``.

    Returns:
        Source names without surrounding whitespace.

    """
    return [source.strip() for source in text.split(",")]


def _parse_enabled(value):
    if len(value) != 1 or not pa.types.is_boolean(value.type) or value.null_count > 0:
        raise ValueError(f"enabled must be a non-null bool array of length 1: {value}")
    return value[0].as_py()


class SelectorNode:
    """Event handler that forwards messages from the selected source.

    Args:
        node: dora-rs node.
        selector: Selection state.
        output_ids: Output IDs of this node. ``selected`` is sent only
            if it's in them.

    """

    def __init__(self, node, selector, output_ids):
        """Initialize the event handler."""
        self.node = node
        self.selector = selector
        self.has_selected_output = _SELECTED_OUTPUT in output_ids

    def start(self):
        """Send the initial selection."""
        self._send_selected()

    def process_event(self, event):
        """Process a dora-rs event.

        Args:
            event: dora-rs event.

        """
        if event["type"] == "INPUT":
            self._process_input(event)
        elif event["type"] == "INPUT_CLOSED":
            self._process_input_closed(event)
        elif event["type"] == "ERROR":
            print(f"dora-rs error: {event['error']}", flush=True)

    def _process_input(self, event):
        source, channel = self.selector.parse_input_id(event["id"])
        if channel == _ENABLED_CHANNEL:
            try:
                enabled = _parse_enabled(event["value"])
            except ValueError as error:
                print(error, flush=True)
                return
            if self.selector.set_enabled(source, enabled):
                self._send_selected()
            return
        if source != self.selector.selected:
            return
        metadata = {**event["metadata"], _SELECTED_SOURCE_METADATA: source}
        self.node.send_output(channel, event["value"], metadata)

    def _process_input_closed(self, event):
        if self.selector.close_input(event["id"]):
            print(
                f"{event['id']} is closed: select {self.selector.selected}",
                flush=True,
            )
            self._send_selected()

    def _send_selected(self):
        if self.has_selected_output:
            self.node.send_output(
                _SELECTED_OUTPUT, pa.array([self.selector.selected or ""])
            )


def main():
    """Run the node."""
    parser = argparse.ArgumentParser(
        description="Forward messages only from the selected source"
    )
    parser.add_argument(
        "--sources",
        required=True,
        help="Comma-separated source names. Earlier ones have higher priority.",
    )
    args = parser.parse_args()

    node = dora.Node()
    config = node.node_config()
    selector = Selector(parse_sources(args.sources), config["inputs"])
    selector_node = SelectorNode(node, selector, config["outputs"])
    selector_node.start()
    for event in node:
        selector_node.process_event(event)


if __name__ == "__main__":
    main()
