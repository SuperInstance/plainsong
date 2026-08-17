# Integration

Driving Plainsong from other software. Four ways in, in rough order of how much
you have to buy into: the CLI with `--json`, the Python API, the HTTP interface,
and MCP.

Everything below was run against an installed build. The conventions section at
the end is the part worth reading before you write any code — most of it is not
guessable.

## The CLI, with `--json`

Every command takes `--json` and prints one JSON object on stdout.

```bash
plainsong --json info song.song
```

**The flag goes before the subcommand.** `plainsong --json info song.song`
works; `plainsong info --json song.song` does not. It is a global option, and
this catches nearly everyone once.

| Command | Top-level keys |
|---|---|
| `info` | `title`, `key`, `tempo`, `meter`, `dialect`, `sections`, `bars`, `arrangement` |
| `check` | `checked`, `failures`, `warnings`, `ok`, `sources` |
| `compile` | `ok`, `midi`, `audio`, `notes`, `seconds`, `tracks` |
| `transpose` | `source`, `target`, `written`, `content` |
| `stage` | voices, distances, solved times |
| `doctor` | capabilities, paths, providers |
| `spec` | per-spec results |
| `library` | matching entries |

In JSON mode the human-readable output is suppressed, so you get JSON and
nothing else — safe to pipe straight into a parser.

### Exit codes

| | |
|---|---|
| `0` | succeeded |
| `1` | the work failed — a compile error, a failing spec |
| `2` | bad invocation — no such file, unreadable key |

Worth knowing: **`check` exits 0 on warnings.** A file with an unreadable chord
that silently became silence is a warning, not an error. If you are gating CI on
notation quality, read `warnings` out of the JSON rather than trusting the exit
code alone.

## As a Python library

The most direct path. No subprocess, no temp files unless you want them.

```python
from plainsong import pipeline

NOTATION = """**TRACK: Library Test**
[MetaData]
key: C | tempo: 120 | time: 4/4

[V1] (Verse - 2 Bars)
Chords: | C . . . | F . . . |
Melody: | C4 D4 E4 F4 | G4 A4 B4 C5 |
"""

result = pipeline.compile_text(NOTATION, midi="out.mid")
print(result.ok, result.score.meta.title, result.arrangement.note_count)

for track, note in result.arrangement.iter_notes():
    print(track.name, note.start, note.pitch, note.velocity, note.duration)
```

```
True Library Test 14
chords 0.0 48 68 4.0
chords 0.0 52 59 4.0
chords 0.0 55 58 4.0
...
```

`iter_notes()` yields `(Track, Note)` pairs. `note.start` and `note.duration`
are in beats; `pitch` is MIDI note number; `velocity` is 0–127.

For finer control, the two halves are separate and you can stop between them:

```python
from plainsong.notation import parse, arrange

score = parse(NOTATION)          # structure and tokens, timing still implicit
arrangement = arrange(score)     # timed notes
```

`parse` never raises on bad notation — it collects diagnostics instead. Check
`score.has_errors` and read `score.errors()` and `score.warnings()`, each a list
of diagnostics with `.format()`.

## The HTTP interface

```bash
plainsong serve --port 8799
```

Loopback by default. `GET /` returns the single-page application; the API is
under `/api/`.

```python
import json, urllib.request

payload = json.dumps({"content": NOTATION}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8799/api/compile",
    data=payload,
    headers={"Content-Type": "application/json"},
)
print(json.load(urllib.request.urlopen(request)))
```

**The field is `content`.** Not `notation`, not `text`, not `source`.
`/api/transpose` takes `content` and `key`.

**Errors come back as HTTP 200 with an `error` key**, not as a 4xx. Check for
`"error" in response`, not the status code.

### What it refuses

Cross-origin POSTs get 403. So do requests whose `Host` header is not a loopback
name — that closes DNS rebinding, where an attacker points a domain at 127.0.0.1
and `Origin` and `Host` then match each other perfectly.

There is **no authentication**. It is a local tool. If you bind it to `0.0.0.0`
it warns you, and anyone who can reach the port can run every tool against your
workspace.

## MCP

```bash
plainsong mcp                # JSON-RPC 2.0 over stdio
plainsong mcp --http         # loopback HTTP
plainsong mcp --list-tools   # what it offers
```

One JSON message per line. The handshake:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"my-client","version":"1"}}}
```

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":false},"resources":{"subscribe":false,"listChanged":false},"prompts":{"listChanged":false}},"serverInfo":{"name":"plainsong","title":"Plainsong","version":"1.0.0"},"instructions":"..."}}
```

Then `tools/list` gives 27 tools, and `tools/call` runs one:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"compile_score","arguments":{"content":"..."}}}
```

**Tool names are not CLI command names** — `compile_score`, not `compile` — and
their arguments use `content`, matching the HTTP API rather than the CLI's
positional file argument.

A malformed line gets `-32700`; an unknown method `-32601`; bad params `-32602`.
A *tool* that fails is not a protocol error: it comes back as a normal result
with `isError: true` and a message the model is meant to read and act on.

A notification — a message with no `id` — draws no response at all.

The server is developed in its own repository,
[plainsong-mcp](https://github.com/SuperInstance/plainsong-mcp), which is where
a client should install it from.

## Conventions worth knowing before you start

Collected because every one of these cost somebody time:

1. **`--json` goes before the subcommand.**
2. **JSON and HTTP APIs use `content`**; the CLI takes a file path positionally.
3. **MCP tool names differ from CLI command names** (`compile_score` vs
   `compile`).
4. **HTTP errors arrive as 200 with an `error` key.**
5. **`check` exits 0 on warnings** — read the JSON if warnings matter to you.
6. **An unreadable chord is a warning, not an error**, and becomes silence. If
   you are generating notation programmatically, check `warnings` or you will
   ship holes.
7. **Player rows take no colon** in music (`@bass |`) but do inside `[Stage]`
   (`@bass: pos 0,0`).
8. **The bundled songbook is chord charts only** — no melody, no lyrics.

## See also

- [MCP server](mcp.md) — the full protocol surface
- [Connectors](connectors.md) — pushing output into other systems
- [Architecture](architecture.md) — how the pieces fit
