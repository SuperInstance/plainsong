# The host bridge

If you are reading this from inside Claude Code, openclaw, Cursor or a similar
tool, there is already a capable model in the room, and it already has
credentials. The host bridge lets Plainsong's agent use that model instead of
asking you for a second API key.

```bash
plainsong setup host
```

`plainsong doctor` will tell you whether a host was detected.

## Three ways to connect

### Command — simplest, works with most agents

Plainsong runs a subprocess, writes the prompt to its standard input, and reads
the reply from its standard output.

```bash
plainsong config set llm.provider host
plainsong config set llm.host_mode command
plainsong config set llm.host_command "claude -p"
```

Anything with a headless mode works:

```bash
plainsong config set llm.host_command "openclaw run --quiet"
plainsong config set llm.host_command "ollama run llama3.2"
plainsong config set llm.host_command "llm -m gpt-4o"
```

### File — works with any agent that can read and write files

Plainsong writes a request into the bridge directory and waits for an answer to
appear next to it. The host agent does not need a headless mode, a plugin, or a
network port — only the ability to work with files, which every agent has.

```bash
plainsong config set llm.host_mode file
plainsong bridge status        # where the directory is
```

### Stdio — for hosts that pipe us directly

Plainsong writes one JSON line between sentinels to standard output and reads
one back from standard input.

```bash
plainsong config set llm.host_mode stdio
```

## The file protocol

Everything lives under the bridge directory, which `plainsong bridge status`
prints (by default `.plainsong/workspace/bridge` inside a project).

```
bridge/
  requests/<id>.json     written by plainsong, read by the host
  responses/<id>.json     written by the host, read by plainsong
```

A request:

```json
{
  "id": "1723542891-a3f9c210",
  "created": 1723542891.42,
  "protocol": "plainsong.bridge/1",
  "prompt": "# Instructions\n...\n\n# User\nwrite a slow waltz ...",
  "messages": [{"role": "system", "content": "..."}],
  "tools": [
    {"name": "write_score", "description": "...", "parameters": {"type": "object"}}
  ]
}
```

`prompt` is the whole conversation flattened into something you can act on
directly. `messages` is the same conversation structured, if you would rather
work from that. When `tools` is non-empty, the reply may call one.

A response is a file with the matching id:

```json
{"id": "1723542891-a3f9c210", "text": "Here is the waltz ..."}
```

To call a tool instead of answering, put a JSON object in `text`:

```json
{"id": "1723542891-a3f9c210",
 "text": "{\"tool\": \"write_score\", \"arguments\": {\"path\": \"waltz.song\", \"content\": \"...\"}}"}
```

To report a failure, use `error` instead of `text`. Plainsong deletes both files
once it has read the answer, and gives up after `llm.host_timeout` seconds
(default 900).

## Answering by hand

```bash
plainsong bridge list                                   # what is waiting
plainsong bridge answer <id> --text "your reply"
cat reply.txt | plainsong bridge answer <id>            # or from stdin
plainsong bridge watch                                  # print requests as they arrive
```

## Driving Plainsong from a host agent

If you are the host agent, the useful shape is:

1. `plainsong doctor --json` to see what the machine can do.
2. `plainsong agent --provider host ...`, or drive the CLI directly — every
   command takes `--json`, so you do not have to parse tables.
3. Watch `bridge/requests/`, answer with `plainsong bridge answer`.

The CLI is the stable interface. `--json` output is part of it and will not
change shape without a deprecation cycle.

## Limitations

- **No streaming.** A host reply arrives whole.
- **No token accounting.** The host does not tell us what it spent.
- **Tool calls go through a text protocol**, so a host model that ignores the
  requested JSON shape will have its reply treated as prose. The protocol is
  stated in every prompt that offers tools.
- **File mode polls** four times a second. It is not built for high throughput,
  and it does not need to be.
