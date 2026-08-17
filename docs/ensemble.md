# Many agents, one score

Several agents write one piece at the same time, one voice each. The problem is
not that a sixteen-track piece is large; it is that contributors must not
corrupt each other, and an agent cannot hold a lock while it thinks — a model
call takes seconds, and a lock held across one will eventually be found
abandoned.

This is the layer that makes that safe. It is served over MCP (see
[mcp.md](mcp.md)) and the tools are also available to the built-in agent.

> Not to be confused with `plainsong ensemble`, which reports what a listener on
> a physical stage hears. That is [performance.md](performance.md).

## A session is a directory

```
<workspace>/ensemble/<name>/
    manifest.json      the header, the form, the voices and the version
    parts/bass.song     one file per voice, written by its owner
    parts/violin1.song
    score.song          the merged result -- generated, never hand-edited
    log.jsonl          one line per accepted change, oldest first
```

The manifest holds what every part is written against: title, key, tempo, metre,
subdivision and the sections. A part is rows and section headers only; it never
carries its own header, so two voices cannot disagree about the tempo.

## Claims and versions

Two rules, doing two different jobs.

**A voice has one owner at a time.** `ensemble_join` claims it; another agent
asking for the same voice is refused and told which voices are free. This is
what stops two agents choosing the same part in the first place, and it is the
softer of the two rules — take a voice with `takeover` if its owner has stopped,
and the log records that you did.

**Every write states the version it was made against.** The session has a
version that increases by one on every accepted change, and each voice carries
the version of its last write. A write is refused if *that voice* has changed
since the base you name. Writing to another voice moves the session version but
cannot invalidate your work, so:

- two agents writing two voices at once both succeed;
- two writes to one voice from the same base leave one winner, and the loser is
  handed the current part to rebase onto rather than a bare failure.

No lock is held while an agent is thinking. There is a lock file, but it is
taken to swap a file and dropped microseconds later, and it is broken
automatically if a writer dies holding it. Parts are written to a temporary file
and moved into place with `os.replace`, so a crash cannot leave half a part on
disk.

Notation is parsed and checked against the session header before anything
reaches disk, exactly as `write_score` does, and a part may only contain rows for
its own voice. Invalid notation never lands, and one voice cannot rewrite
another's rows through the merge.

## The merge

`score.song` is rewritten from the parts after every accepted write and by
`ensemble_render`; reading a session merges in memory. It is deterministic: the same parts and
the same header always produce the same bytes. Sections come out in the order
the manifest declares them, then in the order a part first introduced them;
rows come out in the order a lead sheet reads — `Chords:`, `Melody:`, `Lyrics:`,
then the players alphabetically. Line endings and trailing whitespace are
normalised on the way in, so two agents on two platforms cannot produce two
different scores from the same notation.

## What a joining agent reads

`ensemble_read` answers in one call. An agent about to write bars 3 and 4 of the
viola should not have to read the whole piece to do it.

```json
{
  "session": "harbour",
  "version": 5,
  "directory": "/…/.plainsong/workspace/ensemble/harbour",
  "meta": {
    "title": "Harbour Lights", "key": "Am", "tempo": 96,
    "meter": "4/4", "subdivision": "8th", "swing": "0%", "bars": 4
  },
  "sections": [{"name": "A", "description": "Verse - 4 Bars", "bars": 4}],
  "voices": [
    {"voice": "@bass", "name": "bass", "kind": "player", "owner": "alice",
     "held": true, "claimed_at": "2026-08-13T09:12:04+00:00", "version": 3,
     "updated": "2026-08-13T09:12:05+00:00", "bars": 4, "notes": 8,
     "summary": "walking line under the verse"}
  ],
  "free_voices": ["@violin1"],
  "you": {
    "voice": "@violin1", "owner": "carol", "yours": true,
    "base_version": 0, "content": ""
  },
  "window": {
    "from": 2, "to": 3, "total_bars": 4, "meter": "4/4",
    "bars": [
      {"bar": 2, "section": "A",
       "voices": {"Chords:": "F . . .", "@bass": "f1 . c2 ."}},
      {"bar": 3, "section": "A",
       "voices": {"Chords:": "C . . .", "@bass": "c2 . g1 ."}}
    ]
  },
  "recent": [
    {"version": 5, "time": "2026-08-13T09:12:05+00:00", "agent": "bob",
     "voice": "chords", "action": "write", "bars": 4, "summary": "verse changes"}
  ],
  "score_path": "/…/ensemble/harbour/score.song"
}
```

`meta` and `sections` are the header and the form. `voices` says who is playing
what and who holds it, with a one-line summary of each contribution. `window` is
the part an agent cannot work without: for the bars it is about to write, what
every other voice already plays there, as written. `you` carries your own part
and the `base_version` to write against. `recent` is the tail of the log, which
is how an agent that has just arrived finds out what has happened.

Ask for the bars you care about with `bars: "5-8"`; the default is all of them.

## Two agents, one piece

Alice takes the bass, Bob takes the violin. Neither waits for the other.

```jsonc
// Alice
{"name": "ensemble_open", "arguments": {
  "session": "harbour", "title": "Harbour Lights", "key": "Am", "tempo": 96,
  "bars": 4, "sections": [{"name": "A", "description": "Verse - 4 Bars", "bars": 4}],
  "voices": ["@bass", "@violin1", "chords"]}}

{"name": "ensemble_join", "arguments": {
  "session": "harbour", "voice": "@bass", "agent": "alice"}}
// -> you.base_version: 0, free_voices: ["@violin1", "Chords:"]

// Bob, at the same moment
{"name": "ensemble_join", "arguments": {
  "session": "harbour", "voice": "@violin1", "agent": "bob"}}
// -> you.base_version: 0

// Both write. Different voices, so both land.
{"name": "ensemble_write_part", "arguments": {
  "session": "harbour", "voice": "@bass", "agent": "alice", "base_version": 0,
  "content": "[A]\n@bass | a1 . e2 . | f1 . c2 . | c2 . g1 . | e2 . e1 . |",
  "summary": "walking line under the verse"}}
// -> accepted: true, version: 4

{"name": "ensemble_write_part", "arguments": {
  "session": "harbour", "voice": "@violin1", "agent": "bob", "base_version": 0,
  "content": "[A]\n@violin1 | e4 . a4 . | c5 . f4 . | e5 . g4 . | b4 . e4 . |",
  "summary": "counter-line above the bass"}}
// -> accepted: true, version: 5
```

Bob now revises his line, but against version 0, which is his own last-but-one
read:

```jsonc
{"name": "ensemble_write_part", "arguments": {
  "session": "harbour", "voice": "@violin1", "agent": "bob", "base_version": 0, "…": "…"}}
// -> isError, and:
// {"error": "@violin1 has moved on: you wrote against version 0, it is now at 5. …",
//  "rebase": {"session": "harbour", "version": 5, "voice": "@violin1", "voice_version": 5,
//             "owner": "bob", "yours": true, "content": "[A]\n@violin1 | e4 …"}}
```

He writes again with `base_version: 5` and it lands. Alice never noticed.

Then either of them:

```jsonc
{"name": "ensemble_render", "arguments": {"session": "harbour", "audio": true}}
```

## The rest of the tools

| Tool | For |
|---|---|
| `ensemble_open` | start a session, or reopen one; sets the header and the form |
| `ensemble_join` | claim a voice, and get everything needed to start |
| `ensemble_leave` | release it |
| `ensemble_read` | the call above |
| `ensemble_write_part` | write your voice, against a base version |
| `ensemble_render` | merge and compile to MIDI, and optionally audio |
| `ensemble_log` | the whole change log |
| `ensemble_status` | version, voices, bars, and whether the score still compiles |

`analyze_features` and `apply_directives` both take a `session` instead of a
file, so a bandleader can perceive and shape what the ensemble has written so
far.

## Checking it

```bash
python3 -m unittest tests.test_ensemble
python3 -m plainsong spec --tag mcp
```

The tests run the concurrent cases with threads: several agents writing several
voices at once, several writing one, and twenty claiming twenty voices at the
same time.
