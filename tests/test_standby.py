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

import pytest

from dora_openarm_selector import standby


def test_selected_when_listed():
    assert standby.is_selected("ker", "ker")
    assert standby.is_selected("webxr", "vr,webxr")


def test_not_selected_when_not_listed():
    assert not standby.is_selected("dummy", "ker")
    assert not standby.is_selected("ker", "kerx")


def test_not_selected_when_empty():
    assert not standby.is_selected("", "ker")
    assert not standby.is_selected("ker", "")


def test_selected_with_whitespace():
    assert standby.is_selected(" webxr ", "vr , webxr ")


class _Exec(Exception):
    pass


def _fake_execvp(file, args):
    raise _Exec(file, args)


def test_exec_when_selected(monkeypatch):
    monkeypatch.setenv("SELECTED", "ker")
    monkeypatch.setenv("RUN_WHEN", "ker")
    monkeypatch.setattr(
        "sys.argv", ["dora-openarm-standby", "dora-openarm-ker", "--port", "1"]
    )
    monkeypatch.setattr("os.execvp", _fake_execvp)
    with pytest.raises(_Exec) as error:
        standby.main()
    assert error.value.args == (
        "dora-openarm-ker",
        ["dora-openarm-ker", "--port", "1"],
    )


def test_exit_when_command_not_found(monkeypatch):
    def execvp(file, args):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setenv("SELECTED", "ker")
    monkeypatch.setenv("RUN_WHEN", "ker")
    monkeypatch.setattr("sys.argv", ["dora-openarm-standby", "dora-openarm-kr"])
    monkeypatch.setattr("os.execvp", execvp)
    with pytest.raises(
        SystemExit,
        match="standby: cannot run dora-openarm-kr: .*No such file or directory",
    ):
        standby.main()


def test_stand_by_when_not_selected(monkeypatch, capsys):
    events = [{"type": "INPUT", "id": "tick"}, {"type": "STOP"}, {"type": "INPUT"}]
    monkeypatch.setenv("SELECTED", "webxr")
    monkeypatch.setenv("RUN_WHEN", "ker")
    monkeypatch.setattr("sys.argv", ["dora-openarm-standby", "dora-openarm-ker"])
    monkeypatch.setattr("os.execvp", _fake_execvp)
    iterator = iter(events)
    monkeypatch.setattr(standby.dora, "Node", lambda: iterator)
    standby.main()
    assert capsys.readouterr().out == (
        "standby: not running dora-openarm-ker (SELECTED='webxr', RUN_WHEN='ker')\n"
    )
    assert list(iterator) == [{"type": "INPUT"}]


def test_usage_without_command(monkeypatch):
    monkeypatch.setattr("sys.argv", ["dora-openarm-standby"])
    with pytest.raises(SystemExit, match="usage: dora-openarm-standby"):
        standby.main()


@pytest.mark.parametrize(
    ("selected", "run_when", "message"),
    [
        (None, "ker", "SELECTED must not be empty"),
        (" ", "ker", "SELECTED must not be empty"),
        ("ker", None, "RUN_WHEN must not be empty"),
        ("ker", " ", "RUN_WHEN must not be empty"),
    ],
)
def test_reject_empty_env(monkeypatch, selected, run_when, message):
    for name, value in (("SELECTED", selected), ("RUN_WHEN", run_when)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setattr("sys.argv", ["dora-openarm-standby", "dora-openarm-ker"])
    monkeypatch.setattr("os.execvp", _fake_execvp)
    with pytest.raises(SystemExit, match=message):
        standby.main()
