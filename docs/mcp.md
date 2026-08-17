# The MCP server

Plainsong speaks the Model Context Protocol, so an agent can drive the whole
system directly rather than shelling out to the CLI and reading text back.

```bash
python3 -m plainsong.mcp          # stdio: what an MCP client launches
python3 -m plainsong mcp          # the same thing through the CLI
python3 -m plainsong.mcp --http   # loopback HTTP, for several clients at once
```

Point a client at it. For Claude Code, `~/.claude/mcp.json` or the project's:

```json
{
  "mcpServers": {
    "plainsong": {
      "command": "python3",
      "args": ["-m", "plainsong.mcp"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

The working directory matters: paths, the workspace and the ensemble sessions
are all resolved from it the same way the CLI resolves them.

## What is served

| Method | What it does |
|---|---|
| `initialize` | agrees a protocol version, advertises tools, resources and prompts |
| `notifications/initialized` | acknowledged with silence, as a notification must be |
| `ping` | empty result |
| `tools/list` | every tool in the agent's registry, with its JSON Schema |
| `tools/call` | runs one, returning content the model can read |
| `resources/list` | the notation reference, the host capabilities, the specs, the sessions |
| `resources/templates/list` | the parameterised sets: library entries, sessions, specs |
| `resources/read` | one resource, as text or JSON |
| `prompts/list`, `prompts/get` | the composer and builder prompts |

The protocol version offered is `2025-06-18`; `2025-03-26` and `2024-11-05` are
answered in kind if a client asks for them.

## Tools are not listed twice

`tools/list` is `ToolRegistry.specs()`, which the agent already uses to describe
its tools to a model. Anything registered anywhere in the codebase — the
compiler tools, the performance tools in `perform/`, the ensemble tools here —
appears over the protocol without this package changing. There is no second
list to keep in step, for the same reason there is one GM table and one
`compile_text`.

That means the tool surface is roughly:

- **Notation** — `notation_reference`, `write_score`, `compile_score`,
  `transpose_score`, `search_library`, `read_library`
- **Machine** — `probe_host`, `verify_specs`, `list_files`, `read_file`,
  `write_file`, `record_decision`
- **Ensemble** — `ensemble_open`, `ensemble_join`, `ensemble_leave`,
  `ensemble_read`, `ensemble_write_part`, `ensemble_render`, `ensemble_log`,
  `ensemble_status` (see [ensemble.md](ensemble.md))
- **Analysis** — `analyze_features`, `apply_directives`
- **Performance** — `stage_reference`, `ensemble_report`, `speech_profiles`,
  `directive_reference`, `conduct_score` (see [performance.md](performance.md))

## Errors, and what is not one

A malformed request is a protocol error and comes back as an error object:
`-32700` for JSON that will not parse, `-32600` for a request that is not
JSON-RPC 2.0, `-32601` for an unknown method, `-32602` for bad parameters —
including an unknown tool or a missing `uri` — and `-32603` for a handler that
raised. A missing resource is `-32002`, MCP's own code for it.

A tool that could not do what was asked is **not** a protocol error. It comes
back as a result with `isError: true` and the reason in the text, because the
model has to read that reason and try something else; an error object tells it
the server is broken instead. Every tool in the registry returns its failures
this way, so the server recognises them by shape: text beginning `error:`, or a
JSON object with an `error` key.

Notifications — messages with no `id` — are never answered, whatever they say.
An unknown method does not stop the loop.

When a tool's result is a JSON object it is also returned as
`structuredContent`, so a client that wants the data does not have to re-parse
the text.

## Resources

| URI | Contents |
|---|---|
| `plainsong://notation-reference` | how to write notation, as Markdown |
| `plainsong://capabilities` | what this machine can do, as JSON |
| `plainsong://spec/{id}` | one spec: what it promises and the checks that prove it |
| `plainsong://library/{name}` | one notation file from the bundled library |
| `plainsong://session/{name}` | one ensemble session, including the merged score |

The library and the sessions are given as templates rather than listed. There
are several thousand notation files in a checkout and putting them all in a
client's context would be worse than useless; `search_library` is the way in.

## The HTTP transport

Same messages, same bodies, one JSON-RPC message per POST:

```bash
python3 -m plainsong.mcp --http --port 8766

curl -s localhost:8766 -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

`GET /` reports the version and the methods served. A notification gets `202`
and no body.

It binds to loopback, refuses cross-origin requests, and says so loudly if you
bind it anywhere else — every tool it offers can write to the workspace, so
anyone who can reach the port can write there too. This is the posture the web
interface already takes.

## Features, for a model that has to listen

`analyze_features` describes each bar as sixteen numbers, in the layout
fleet-jepa-midi's bandleader consumes:

    note_density  avg_pitch    rhythmic_complexity  harmonic_tension
    register_spread  velocity_mean  velocity_std    syncopation
    contour_direction  interval_size  rest_ratio    chord_density
    bass_register  treble_activity  dynamic_range   sustain_ratio

Each is normalised into roughly `[0, 1]` — `contour_direction` alone is signed —
against the fixed references in `plainsong/mcp/features.py`, not against the
piece itself. Normalising against the piece would make a bar's numbers depend on
which other bars you happened to include, and two agents analysing two excerpts
would disagree about the same bar.

Two of them are measured inside a voice and then averaged rather than over the
merged stream: `contour_direction` and `interval_size`. The interval between
consecutive notes of a three-part texture is mostly the distance from the bass
to the tune, which saturates and says nothing.

The analysis is pure: an `Arrangement` in, numbers out, no rendering and nothing
optional. That makes the several thousand `.song` files in this repository a
labelled corpus, and lets a bandleader perceive a score that was written rather
than played.

## Directives

`apply_directives` passes a bandleader's directive JSON to
`plainsong.perform.conduct` and returns the result as data: the directives as
they were read, the arrangement before and after, and the sixteen features per
bar of each — enough to close the loop of perceive, instruct, perceive again. It
accepts an ensemble session as well as a file or inline notation.

`conduct_score`, from `perform/`, does the same thing and reports it in prose.
Use that one when a person is going to read the answer.

The import of the conductor is soft. If `plainsong.perform` is missing or has a
different shape, the tool says so and the rest of the server carries on.

## Checking it

```bash
python3 -m plainsong spec --tag mcp
python3 -m unittest tests.test_mcp tests.test_ensemble
python3 -m plainsong.mcp --list-tools
```

The spec drives a real server with real JSON-RPC messages, including malformed
ones. See `specs/mcp.toml`.
