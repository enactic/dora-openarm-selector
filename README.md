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

| Argument               | Required | Description                                                  |
| ---------------------- | -------- | ------------------------------------------------------------ |
| `--sources vr,policy`  | Yes      | Comma-separated source names. Earlier ones have higher priority. |

A source name must not contain `_`.

### Inputs

| Input ID             | Type             | Description                                       |
| -------------------- | ---------------- | ------------------------------------------------- |
| `<source>_<channel>` | Any              | Data to forward such as `vr_right`.               |
| `<source>_enabled`   | bool (length 1)  | `true` enables the source, `false` disables it.   |

You can name channels freely such as `right` and `left`. The source of
an input ID is the part before the first `_`. `enabled` is the channel
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

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

Copyright 2026 Enactic, Inc.

## Code of Conduct

All participation in the OpenArm project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).
