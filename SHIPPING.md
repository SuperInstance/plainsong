# Shipping audit

State of the branch as of `3487a35`. Items are struck through as they close. Written from inspection, not memory --
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

412 tests, 7 specs, ruff clean.

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

### S1. `docs/mcp.md` and `docs/ensemble.md` are unreviewed — AUDITED, two fixes outstanding

Written by the agent that built the feature and never checked against what it
actually built. The agent was killed by a spend limit before its own final
verification pass, so its documentation is the least-trustworthy artefact in
the tree.

Audited. Two things to fix: `ensemble.md`'s rebase example shows 3 of the 7
fields actually returned, and the `record_decision` tool is not documented.
Everything else checked out, including all 16 feature names and the protocol
version negotiation.

### S2. `ensemble.py` and `server.py` have not been read end to end

The protocol behaviour is now verified by handshake and the locking was read
closely while fixing two bugs in it. The rest -- merge determinism, the log,
part validation, resource templates -- has been tested but not read.

### S3. `render/backends.py` is untested — CLOSED

The fluidsynth, ffmpeg, playback and MIDI-port wrappers have no test. They all
shell out and all claim to degrade gracefully; none of that is proven. Lower
risk than it sounds, because the built-in path never touches them.

**Closed** by 44 tests with the tools mocked absent. Writing them found that
`BackendResult` had no `__bool__`, so every failure was truthy.

### S4. Two different things are called "ensemble"

`tapscript stage` analyses what each listener on a stage hears. The MCP
`ensemble_*` tools manage a shared multi-agent session. Unrelated concepts,
same word, both user-facing. Worth renaming one before the vocabulary sets.

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
