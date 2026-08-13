# Agents

Two agents ship with TapScript. Both are the same loop with a different prompt
and the same tools; neither is required for the compiler to work.

| | |
|---|---|
| **composer** | Writes and revises notation. `tapscript agent "..."` |
| **builder** | Adapts this installation to your machine and use case. `tapscript build` |

## The composer

```bash
tapscript agent "sixteen bars of slow blues in G, walking bass, brushes feel"
tapscript agent --role composer "make the chorus lift — try a IV before the turnaround"
tapscript agent                       # no prompt: an interactive session
```

It reads the notation reference before writing, writes with a tool that parses
the notation before anything reaches disk, compiles what it wrote, and reads the
diagnostics. A piece that comes back with zero notes is a failure it is expected
to notice and fix, not report as success.

Inside a session: `/reset` clears the conversation, `/exit` leaves. Transcripts
are saved unless you set `agent.transcript = false`.

## The build agent

```bash
tapscript build
tapscript build "I want to drive my hardware synth from a Raspberry Pi"
```

It probes the host first, so what it offers depends on what you actually have.
Then it asks at most a couple of questions, writes `PLAN.md` into the workspace,
carries the plan out, verifies with `tapscript spec`, and records each decision
in `BUILD-JOURNAL.md`.

It prefers configuration over code and a small connector over a large one. What
it produces is ordinary: a config change, or a connector module in
`<workspace>/connectors/` that is discovered exactly like the built-in ones. See
[connectors.md](connectors.md).

The journal is the point. A later session — yours or another agent's — reads it
to find out why this install is set up the way it is.

## The workspace

An agent may read the project and write only inside its workspace:

```
.tapscript/workspace/          (inside a project; a data directory otherwise)
  output/                      compiled MIDI and audio
  connectors/                  generated connectors
  specs/                       generated specs
  sessions/                    saved transcripts
  PLAN.md, BUILD-JOURNAL.md
```

Paths that escape it are refused, and the refusal is returned to the model as a
tool error so it can correct itself rather than crash the run.

```bash
tapscript agent --workspace ./scratch "..."
```

## Tools

| Tool | Does |
|---|---|
| `notation_reference` | Returns the notation language reference |
| `probe_host` | Platform, optional libraries, soundfonts, MIDI ports, playback, network |
| `list_files`, `read_file`, `write_file` | Ordinary file access, sandboxed |
| `write_score` | Parses notation, reports problems, writes only if it is valid |
| `compile_score` | Compiles and returns the arrangement summary and diagnostics |
| `transpose_score` | Moves a file to another key |
| `search_library`, `read_library` | The bundled notation library |
| `verify_specs` | Runs the system's own checks |
| `record_decision` | Appends to the build journal |

Tools return strings, including for failures. A model that gets `error: ...`
back can try something else; an exception would end the run.

## Adding a tool

```python
from tapscript.agent.tools import ToolRegistry

registry = ToolRegistry()
registry.add(
    name="export_stems",
    description="Render each voice to its own audio file.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "A .tap file"}},
        "required": ["path"],
    },
    handler=lambda path: f"rendered stems for {path}",
)
```

Pass the registry to `Agent(...)`. The description is what the model reads to
decide whether to call it, so write it for a reader who has not seen the code.

## Using the loop directly

```python
from tapscript.agent import Agent, ToolRegistry
from tapscript.llm import get_provider

agent = Agent(provider=get_provider(), tools=ToolRegistry(), role="composer")
result = agent.run("a lullaby in 6/8, harp and voice")

print(result.reply, result.steps, result.tool_calls)
```

`Agent(on_event=...)` receives `step`, `tool_call`, `tool_result`, `message`,
`error` and `done` events — that is how the CLI prints progress and the web
interface shows what the agent did.

## Limits

`agent.max_steps` (default 24) bounds one run. A run that hits it returns what
it has with `stopped_because` set, rather than looping.

Model calls cost money and send your notation to whoever provides the model. The
agent is the only part of TapScript that talks to a network, and only when you
invoke it.
