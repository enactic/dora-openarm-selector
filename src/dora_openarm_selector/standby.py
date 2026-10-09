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

"""Standby node.

This dora-rs node runs another node only when it's selected. The real
node and its arguments are given as arguments of this node. If
``SELECTED`` environment variable is one of the comma-separated names in
``RUN_WHEN`` environment variable, this node execs the real node in the
same process. Otherwise, it stands by without starting the real node,
so a device that isn't plugged in doesn't fail the dataflow.
"""

import os
import sys

import dora


def is_selected(selected, run_when):
    """Return whether a name is selected.

    Args:
        selected: Name that the dataflow runs now such as ``ker``.
        run_when: Comma-separated names to run the real node for such as
            ``vr,webxr``.

    Returns:
        ``True`` if ``selected`` is one of ``run_when``.

    """
    return selected.strip() in {name.strip() for name in run_when.split(",")}


def main():
    """Exec the real node if selected, otherwise idle until dora stops us."""
    command = sys.argv[1:]
    if not command:
        sys.exit("usage: dora-openarm-standby <node> [args...]")
    selected = os.environ.get("SELECTED", "")
    run_when = os.environ.get("RUN_WHEN", "")
    if is_selected(selected, run_when):
        # Same process and environment, so dora sees the real node.
        os.execvp(command[0], command)

    node = dora.Node()
    print(
        f"standby: not running {command[0]} "
        f"(SELECTED={selected!r}, RUN_WHEN={run_when!r})",
        flush=True,
    )
    for event in node:
        if event["type"] == "STOP":
            break


if __name__ == "__main__":
    main()
