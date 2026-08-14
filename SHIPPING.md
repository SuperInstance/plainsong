# Shipping audit

State of the branch as of `e4f15e1`. Items are struck through as they close. Written from inspection, not memory --
every claim below was checked against the working tree.

## Verified

These have been proven, not assumed.

| Claim | How it was checked |
|---|---|
| MCP protocol is correct | Drove the stdio server with real JSON-RPC. `initialize` returns protocolVersion/capabilities/serverInfo; `notifications/initialized` correctly produces no response; unknown method gives `-32601`; malformed input gives `-32700`; `tools/call` returns content plus `isError`. 27 tools, 9 resources, 2 prompts enumerate. |
| Works on Python 3.10 | Hid `tomllib` entirely and ran the CLI (`info`, `compile`) and all specs through the fallback reader. |
| The TOML fallback matches the real one | Differential test: every TOML file in the repo plus 17 edge cases parsed by both readers and compared. |
| Arrival timing is arithmetically right | Hand-checked a three-voice stage: 14 m at 343.21 m/s is 40.8 ms, plus 140 ms pipe speech and 60 ms perceptual attack gives the organ's -241 ms. Spread is 0 ms at the podium and non-zero at every player's desk. |
| Notation compatibility held | 6,322 `.tap` files parse with 0 errors. |
| No hidden dependencies | CI installs nothing on 4 Python versions x 3 operating systems. |
| No hardcoded paths | A test greps the package for `~/.openclaw`, `/home/eileen`, `/Users/`. |
| Nothing half-written | No TODO, FIXME, XXX, HACK or `NotImplementedError` anywhere in `tapscript/`. |

| The new tests would catch a regression | Each guard was removed and the suite confirmed to go red: retryable statuses, the `[DONE]` stream terminator, the User-Agent and header merge, the same-origin refusal, the `/files/` basename and containment guards together, the null-byte guard, percent-decoding, the `MAX_BODY` limit, `ConnectorResult.__bool__`, the broken-connector skip, and the availability check in `run()`. |

514 tests, 7 specs, ruff clean.

## Blockers

Must be closed before this ships.

### B1. The changelog does not mention the three new features — CLOSED

`CHANGELOG.md` contains zero references to arrival-centric timing, the MCP
server, or the ensemble layer. `CONTRIBUTING.md` states that a notation change
requires a changelog entry, and the `[Stage]` block is a notation change. The
project is currently in breach of its own documented rule.

### B2. The README does not mention MCP or the ensemble — CLOSED

`docs/mcp.md` and `docs/ensemble.md` exist but are linked from nowhere, and the
README's documentation table predates both. The headline capability -- many
agents co-authoring one score -- is undiscoverable by a reader of the front
page.

### B3. The TUI has never been executed — CLOSED

`tapscript/interfaces/tui.py` is 429 lines. No test imports it. Its only spec
check is `check_importable`, which is marked `optional` and `requires =
"terminal"`, so it **skips in CI** -- non-interactive runners have no tty. One
of the three advertised interfaces is entirely unverified. A syntax-level
mistake in a draw routine would ship undetected.

**Closed** by 35 tests covering everything reachable without a terminal. Running
them on Windows CI immediately found that stock Python there ships no
`curses` at all, so the TUI does not run on Windows — now documented and
reported at runtime with the fix.

## Should fix

Not ship-blocking, but each is a real gap.

### S1. `docs/mcp.md` and `docs/ensemble.md` are unreviewed — CLOSED

Written by the agent that built the feature and never checked against what it
actually built. The agent was killed by a spend limit before its own final
verification pass, so its documentation is the least-trustworthy artefact in
the tree.

Audited. Two things to fix: `ensemble.md`'s rebase example shows 3 of the 7
fields actually returned, and the `record_decision` tool is not documented.
Everything else checked out, including all 16 feature names and the protocol
version negotiation.

**Closed.** Both fixes applied: the conflict example now shows all seven
fields the code returns, and `record_decision` is documented.

### S2. `ensemble.py` and `server.py` have not been read end to end — CLOSED

**Closed.** Read end to end. The write_part critical section is correct, merge
determinism holds (three write orders, identical bytes -- checked, not assumed),
and the validator refuses a part that speaks for a voice other than its own.

Found and fixed: the server set `isError` by reading the result text while the
registry, which knows when it could not run something, said nothing. The
registry now reports it.

Found and left: `protocol.py` answers a parse error carrying no id but stays
silent on an invalid request carrying no id. Defensible -- a request without an
id is a notification -- but the two paths disagree.

### S3. `render/backends.py` is untested — CLOSED

The fluidsynth, ffmpeg, playback and MIDI-port wrappers have no test. They all
shell out and all claim to degrade gracefully; none of that is proven. Lower
risk than it sounds, because the built-in path never touches them.

**Closed** by 44 tests with the tools mocked absent. Writing them found that
`BackendResult` had no `__bool__`, so every failure was truthy.

### S4. Two different things are called "ensemble" — CLOSED

`tapscript stage` analyses what each listener on a stage hears. The MCP
`ensemble_*` tools manage a shared multi-agent session. Unrelated concepts,
same word, both user-facing.

**Closed.** The analysis is now `tapscript stage`, and the MCP server and
ensemble layer have moved to their own repository, `tapscript-mcp`.

### S6. Three surfaces had no tests at all — CLOSED

`interfaces/web/server.py` (343 lines), `llm/transport.py` (146) and
`connectors/` (289) were never executed by the suite. This is the same gap as
B3, and closing B3 immediately found a Windows bug, so it was worth closing
these too.

**Closed** by 102 tests. Two real defects came out of it:

- `transform.transpose` accepted a target that names no key. `parse_key` is
  forgiving by design and reads `"banana"` as B major, so a mistyped key
  silently moved a whole score by a semitone rather than failing. Now refused,
  with the refusal checked by `tapscript spec`.
- The web interface never percent-decoded `/files/`, so a rendered file with a
  space in its name 404'd. Latent for compile output, which is always slugged;
  live for what the TUI and the connectors write.

Worth recording: the first versions of the traversal, `MAX_BODY` and
same-origin tests all passed against a deliberately broken server. `urllib`
normalises `..` out of a path before the request is sent and recomputes
Content-Length from the body it was handed, so the guards were never reached
and the 404s came from elsewhere. They now go over a raw `http.client`
connection. A security test that has never seen the code fail is not evidence.

### B4. The academy teaches a language that does not exist — OPEN, needs a decision

Found by extending `tapscript check` to markdown. Fourteen of the seventeen
fenced `tapscript` blocks in the repository compiled to **zero notes**, and they
are not near-misses — they are four unrelated invented languages:

- `academy/.../04-dynamics-and-velocity.md` teaches a bouncing-ball physics
  simulation, `entity Orb { position, velocity, damping, maxSpeed }`, because
  something saw the word *velocity*.
- `academy/.../04-reading-notation.md` teaches variables and operators,
  `let myNumber = 5; print myNumber + 2`, with an exercise whose expected answers
  are `7` and `30`.
- `academy/.../05-compile-and-listen.md` instructs the reader to build with
  `tapc listen.tap -o listen.tbc` and run `tap run listen.tbc`. There is no
  bytecode compiler and never has been.
- Several lessons point at a server on `localhost:5557`.
- `01-chord-progressions.md` uses `prog "X" { chord C func:T beat:2 }`.

**Nothing caught this.** `tapscript check docs examples academy` walks `.tap`
files; `academy/` contains none, so aiming the check at it passed vacuously and
reported "ok 6322 files checked". A check that cannot fail is worse than no
check, because it is quoted as evidence.

**Done now:** `check` reads fenced blocks out of markdown, with file:line
reporting; `tests/test_notation.py::TestDocumentedNotation` fails if any
documented example stops compiling or stops making a sound (verified by breaking
one and watching it fail); the fabricated blocks are relabelled `text` — which
is simply true, they are not TapScript — and each affected lesson carries a
banner saying so; a genuine proposal for future syntax is tagged
`tapscript-proposed`; the one block that was real but incomplete is fixed.

**Still open, and not mine to decide:** the prose is fabricated too, so
relabelling the code fences does not make these lessons usable. Thirty-five
markdown files claim to teach a product that does not match this one. They want
rewriting or removing before anyone is invited to learn from them.

### B5. The fakebook ships melody and lyrics for in-copyright songs — OPEN

1,902 of the 6,309 `.tap` files carry both a `Melody:` row and a `Lyrics:` row.
The policy this project documents is full melody plus lyrics only for
public-domain works, chord charts otherwise.

It is not being met. `docs/fakebook/hindi/folk-traditional/tere-bina-jiya-jaye-na.tap`
carries a full melody and three verses of lyrics for a 1979 R. D. Burman /
Gulzar film song. The directory name is what defeated the policy: it is filed
under `folk-traditional`, and it is not folk.

The exposure is at its worst on announcement day, when attention is highest.
Needs a decision: reclassify and downgrade to chord charts, strip the lyric rows
across the set, or restrict what ships to verified public domain.

### S5. Windows lock contention — SETTLED

Two fixes landed (release no longer raises; acquisition treats a delete-pending
`PermissionError` as contention). `test_the_manifest_survives_a_crowd` now
passes on Windows across 3.10 through 3.13.

## Known limitations -- ship with these, documented

- The built-in synthesiser is a preview renderer. Mono, approximate timbres.
  fluidsynth with a soundfont is the quality path.
- The host bridge cannot stream and reports no token usage.
- `docs/fakebook/` is generated material carrying ~3,800 bar-count warnings. It
  parses; it is not all well written.
- `legacy/` is dead weight kept for reference and can be deleted.
- The TUI needs `curses`, which stock Python on Windows does not ship. It
  reports this and points at `windows-curses` or the web interface. Found by
  the new TUI tests running on Windows CI for the first time.
- The MCP server has never had a real MCP client connect to it. The protocol is
  verified by hand-driven JSON-RPC, which is strong evidence but not the same
  thing as Claude Desktop or an SDK client connecting.

## Not blocking, worth knowing

- `master` has been red on its own older workflow since before this branch, for
  reasons unrelated to it.
- The three Rust-to-Python ports that arrived on master mid-session
  (`counterpoint_analyzer`, `genome`, `tradition_dna`) were placed in
  `legacy/src/` beside their siblings. Whether any deserves promotion into the
  package is an open question this branch deliberately did not decide.
