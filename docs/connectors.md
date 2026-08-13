# Connectors

A connector is a named way of getting something out of TapScript, or into it.
They exist so that adapting this to a particular setup does not mean editing the
compiler.

## What ships

| Name | Does | Needs |
|---|---|---|
| `file` | Writes MIDI and audio to a directory | nothing |
| `playback` | Plays through this machine's speakers | an audio player |
| `midi-port` | Streams to a connected MIDI instrument | `mido`, a port |
| `webhook` | POSTs the arrangement to a URL | network |

```python
from tapscript.connectors import iter_connectors

for connector in iter_connectors():
    print(connector["name"], connector["available"], connector["detail"])
```

A connector reports why it is unavailable, not just that it is:

```
midi-port  False  midi_ports: pip install mido python-rtmidi, then connect a MIDI device
```

## Using one

```python
from tapscript.connectors import run
from tapscript.notation import arrange, parse

arrangement = arrange(parse(open("harbour.tap").read()))
result = run("midi-port", arrangement, port="Elektron Digitakt")

print(result.ok, result.detail, result.outputs)
```

## Writing one

Drop a module into `<workspace>/connectors/`. It is discovered on the next run
with no registration step:

```python
"""Send finished renders to the studio machine."""

from pathlib import Path
from tapscript.connectors.base import Connector, ConnectorResult, registry
from tapscript.render.midi import write_midi


@registry.register
class StudioConnector(Connector):
    name = "studio"
    summary = "Copy the MIDI to the studio share"
    requires = ()          # capability names from `tapscript doctor`

    def send(self, arrangement, **options):
        target = Path(options.get("share", "/Volumes/studio/incoming"))
        if not target.is_dir():
            return ConnectorResult(False, detail=f"{target} is not mounted")
        path = write_midi(arrangement, target / f"{arrangement.meta.title}.mid")
        return ConnectorResult(True, detail="copied", outputs=[str(path)])
```

Three rules:

- Declare what you need in `requires`, using capability names from
  `tapscript doctor`. Availability is then checked for you and reported
  usefully.
- Return a `ConnectorResult`, including for failure. Do not raise for a
  condition the user can fix.
- Do not assume a path exists. A connector that works only on the machine it was
  written on is the thing this system is trying to get away from.

The build agent writes connectors into the same directory, and they get no
special treatment — a generated connector is an ordinary connector.

## Plugins

Connectors are also loaded from the plugins directory, which is per-user rather
than per-project:

```bash
tapscript doctor          # prints data_dir; plugins live in <data_dir>/plugins
```

A module that fails to import is skipped rather than taking the others with it.
