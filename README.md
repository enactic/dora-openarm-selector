# dora-openarm-selector

A [dora-rs](https://dora-rs.ai) node that receives the same kind of
messages from several sources and forwards only the ones from the
selected source. You can use it to switch arm commands between VR
teleoperation and a policy, for example.

The selected source is the highest-priority one among the enabled
sources. This node doesn't look into values, so it depends on neither
the robot nor the arm.

## Install

```bash
pip install dora-openarm-selector
```

## Usage

```yaml
- id: arm-command-selector
  path: dora-openarm-selector
  args: --sources vr,policy
  inputs:
    vr_enabled: vr-controller/enabled
    vr_right: ik/position_right
    vr_left: ik/position_left
    policy_right: actions-executor/move_position_right
    policy_left: actions-executor/move_position_left
  outputs:
    - right
    - left
    - selected
```

With this dataflow, `policy` drives the arms by default. While
`vr-controller/enabled` is `true`, `vr` takes over because it has the higher
priority.

### Arguments

| Argument               | Environment variable | Required | Description                                                  |
| ---------------------- | -------------------- | -------- | ------------------------------------------------------------ |
| `--sources vr,policy`  | `SOURCES`            | Yes      | Comma-separated source names. Earlier ones have higher priority. |

A source name must not contain `_`. Each source must have at least one
input. Inputs of sources that aren't in `--sources` are ignored. You
can use it to select a source by an environment variable for `dora
run` without changing wiring, because dora-rs expands environment
variables in `env:` values:

```yaml
- id: arm-command-selector
  path: dora-openarm-selector
  env:
    SOURCES: "${TELEOP_SOURCE:-ker}"
  inputs:
    ker_right: leader/follower_position_right
    ker_left: leader/follower_position_left
    webxr_right: ik/position_right
    webxr_left: ik/position_left
  outputs:
    - right
    - left
```

With this configuration, `TELEOP_SOURCE=webxr dora run ...` forwards
only `webxr_*` inputs and `ker_*` inputs are ignored. `ker` is used
when `TELEOP_SOURCE` isn't set. A misspelled `TELEOP_SOURCE` such as
`webrx` is rejected at startup because `webrx` has no input.

### Inputs

| Input ID             | Type             | Description                                       |
| -------------------- | ---------------- | ------------------------------------------------- |
| `<source>_<channel>` | Any              | Data to forward such as `vr_right`.               |
| `<source>_enabled`   | bool (length 1)  | `true` enables the source, `false` disables it.   |

You can name channels freely such as `right` and `left`. The source of
an input ID is the part before the first `_`. An input ID whose source
isn't in `--sources` is ignored, so a misspelled source in an input ID
such as `polcy_right` isn't detected. The format of an ignored input ID
is still checked, so `polcy_selected` is rejected. `enabled` is the channel
for `<source>_enabled` input, so it isn't forwarded. `selected` can't be
used as a channel name because it conflicts with `selected` output.

A source without `<source>_enabled` input is always enabled. A source
with `<source>_enabled` input is disabled until it receives `true`.
Invalid values such as `null` are ignored with an error message.

### Outputs

| Output ID   | Description                                                                                                        |
| ----------- | ------------------------------------------------------------------------------------------------------------------ |
| `<channel>` | `<source>_<channel>` of the selected source as is, with `selected_source` metadata.                               |
| `selected`  | The selected source name (string) at startup and whenever it changes. An empty string if no source is selected.   |

`selected_source` metadata lets a recorder record which source a
command came from. If you don't list `selected` in `outputs:`, this
node doesn't send it.

## Behavior

1. At startup, only sources without `<source>_enabled` input are
   enabled.
2. Every `<source>_enabled` input selects the highest-priority enabled
   source again.
3. Only `<source>_<channel>` of the selected source is forwarded to
   `<channel>`. Others are dropped.
4. Switching doesn't resend previous values. Forwarding starts from the
   next message from the newly selected source.
5. Nothing is forwarded while no source is selected.
6. When `<source>_enabled` input is closed, for example because its
   upstream node exits, the source is disabled. When all
   `<source>_<channel>` inputs of a source are closed, the source is
   never selected. Otherwise it would block lower-priority sources
   forever.

## Example

[`example/dataflow-mujoco.yaml`](example/dataflow-mujoco.yaml)
teleoperates OpenArm in a [MuJoCo](https://mujoco.org/) simulation
([dora-openarm-mujoco](https://github.com/enactic/dora-openarm-mujoco))
with [KER](https://github.com/enactic/dora-openarm-ker) or
[WebXR](https://github.com/enactic/dora-openarm-webxr). Both of them are
always running, so you need a KER connected via USB and a TLS
certificate for WebXR. `TELEOP_SOURCE` environment variable selects
which one moves the arms.

Generate a self-signed TLS certificate into `example/` with
[`example/prepare_tls.sh`](example/prepare_tls.sh). Pass a host name
that your VR device can resolve. See
[dora-openarm-webxr's setup](https://github.com/enactic/dora-openarm-webxr#setup)
for details.

```bash
example/prepare_tls.sh $(hostname).local
```

Then build and run the dataflow:

```bash
pip install dora-rs-cli
dora build example/dataflow-mujoco.yaml
# KER moves the arms. KER is the default.
TELEOP_SOURCE=ker dora run example/dataflow-mujoco.yaml
# WebXR moves the arms.
TELEOP_SOURCE=webxr dora run example/dataflow-mujoco.yaml
```

To use WebXR, open `https://$(hostname).local:8443/` in the Web browser
on your VR device and press the "Start" button.

## Standby

This package also provides `dora-openarm-standby`. It runs a hardware
node only when it's selected by an environment variable such as
`LEADER`. Otherwise, it stands by without opening the device. You can
use it to put several alternative sources such as KER and WebXR in one
dataflow that starts even when only one device is plugged in.

```yaml
- id: ker
  path: dora-openarm-standby
  args: dora-openarm-ker            # the real node and its arguments
  env:
    SELECTED: "${LEADER:-ker}"      # what the dataflow runs now
    RUN_WHEN: ker                   # run the real node for these (comma-separated)
  inputs:
    tick: quittable-tick-leader/tick
  outputs:
    - follower_position_right
```

| Environment variable | Description                                                        |
| -------------------- | ------------------------------------------------------------------ |
| `SELECTED`           | The name that the dataflow runs now such as `ker`.                 |
| `RUN_WHEN`           | Comma-separated names to run the real node for such as `vr,webxr`. |

- Selected: `SELECTED` is one of `RUN_WHEN`. This node execs the real
  node in the same process, so it behaves exactly as without this node.
- Not selected: This node sends no outputs. It keeps reading events and
  exits when dora-rs stops it or its inputs close, for example because
  a quitter tick stops on Quit. So a normal Quit still ends the
  dataflow.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

Copyright 2026 Enactic, Inc.

## Code of Conduct

All participation in the OpenArm project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).
