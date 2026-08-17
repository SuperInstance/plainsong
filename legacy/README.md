# legacy/

The code this project grew out of, kept for reference and for anyone who needs
to reproduce an old render exactly.

Nothing here is imported by the `tapscript` package, nothing here is tested in
CI, and nothing here is maintained. It is safe to delete this directory.

## What is in here

| Path | What it was |
|---|---|
| `scripts/tapscript.py` | The first engine. Roman numerals and scale degrees, resolved against the key at compile time. Flask, port 5557. |
| `scripts/tapscript_v2.py` | The second engine. Scientific pitch, labelled rows. stdlib `http.server`, also port 5557. |
| `scripts/gallery_v4.py`, `gallery_v5.py` | An image generation gallery. Unrelated to notation; needed a local Stable Diffusion install and a DeepInfra key. |
| `scripts/midi_studio.py` | A MIDI generator driven by form fields rather than notation. |
| `scripts/fakebook_generator.py` | The bulk generator that produced `docs/fakebook/`. Hardcodes an absolute path from the machine it ran on. |
| `scripts/generate_*.py`, `image_api.py` | Image generation helpers. |
| `src/` | Python ports of unrelated projects: a 96 PPQ pulse grid, an 8-byte MIDI wire codec, a groove tracker. Never imported by the compilers. |
| `tests/` | The old test suite, which imports `scripts/tapscript.py` directly. |

## Why it was replaced

The two engines were separate implementations of the same idea that had drifted
apart: different notation, different internal representation, duplicated GM
tables, duplicated envelopes, duplicated CSS. A fix in one did not reach the
other. Both hardcoded output to `~/.openclaw/workspace/output/audio`, both
hardcoded port 5557, and the newest feature had landed in only one of them.

The current `tapscript/` package is one engine that reads both notations, with
paths, providers and rendering backends resolved at runtime instead of being
compiled in. Known bugs from the old parser -- documented in
`../examples/edge-cases/BUGS.md` -- are covered by specs in `../specs/`.

## Running it anyway

The old engines need packages the current one does not:

```bash
pip install numpy scipy pretty_midi flask
python3 legacy/scripts/tapscript_v2.py --cli song.tap --midi out.mid --wav out.wav
python3 -m pytest legacy/tests/ -v
```
