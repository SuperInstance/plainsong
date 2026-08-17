# Shipping audit

State of the branch. Items are marked closed as they close, and the reasoning is
kept rather than deleted -- the fault each one describes is the reason a rule in
`CLAUDE.md` exists. Written from inspection, not memory: every claim below was
checked against the working tree.

## Verified

These have been proven, not assumed.

| Claim | How it was checked |
|---|---|
| MCP protocol is correct | Drove the stdio server with real JSON-RPC. `initialize` returns protocolVersion/capabilities/serverInfo; `notifications/initialized` correctly produces no response; unknown method gives `-32601`; malformed input gives `-32700`; `tools/call` returns content plus `isError`. 27 tools, 9 resources, 2 prompts enumerate. |
| Works on Python 3.10 | Hid `tomllib` entirely and ran the CLI (`info`, `compile`) and all specs through the fallback reader. |
| The TOML fallback matches the real one | Differential test: every TOML file in the repo plus 17 edge cases parsed by both readers and compared. |
| Arrival timing is arithmetically right | Hand-checked a three-voice stage: 14 m at 343.21 m/s is 40.8 ms, plus 140 ms pipe speech and 60 ms perceptual attack gives the organ's -241 ms. Spread is 0 ms at the podium and non-zero at every player's desk. |
| Notation compatibility held | 6,333 sources compile with 0 errors, including every fenced `plainsong` block in the prose. |
| No hidden dependencies | CI installs nothing on 4 Python versions x 3 operating systems. |
| No hardcoded paths | A test greps the package for `~/.openclaw`, `/home/eileen`, `/Users/`. |
| Nothing half-written | No TODO, FIXME, XXX, HACK or `NotImplementedError` anywhere in `plainsong/`. |
| The browser demo agrees with the compiler | `docs/demo/index.html` carries its own parser and arranger in JavaScript. It states the note count it produces for each preset, and `tests/test_demo.py` compiles the same notation with the real compiler and requires the same answer -- so a change to the arranger that moves a count fails CI rather than making the page quietly lie. |
| A wheel actually works | Built, installed into a clean venv outside the source tree, and exercised there. This is the only way the two packaging faults were visible: `plainsong spec` and `plainsong library` both did nothing for anyone who installed rather than cloned. |
| The new tests would catch a regression | Each guard was removed and the suite confirmed to go red: retryable statuses, the `[DONE]` stream terminator, the User-Agent and header merge, the same-origin refusal, the `/files/` basename and containment guards together, the null-byte guard, percent-decoding, the `MAX_BODY` limit, `ConnectorResult.__bool__`, the broken-connector skip, and the availability check in `run()`. |

527 tests, 7 specs, 6,333 sources checked including every fenced example in the
prose, ruff clean.

## Blockers

All closed. Kept here because the reasoning is the useful part.

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

`plainsong/interfaces/tui.py` is 429 lines. No test imports it. Its only spec
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

`plainsong stage` analyses what each listener on a stage hears. The MCP
`ensemble_*` tools manage a shared multi-agent session. Unrelated concepts,
same word, both user-facing.

**Closed.** The analysis is now `plainsong stage`, and the MCP server and
ensemble layer have moved to their own repository, `plainsong-mcp`.

### S6. Three surfaces had no tests at all — CLOSED

`interfaces/web/server.py` (343 lines), `llm/transport.py` (146) and
`connectors/` (289) were never executed by the suite. This is the same gap as
B3, and closing B3 immediately found a Windows bug, so it was worth closing
these too.

**Closed** by 102 tests. Two real defects came out of it:

- `transform.transpose` accepted a target that names no key. `parse_key` is
  forgiving by design and reads `"banana"` as B major, so a mistyped key
  silently moved a whole score by a semitone rather than failing. Now refused,
  with the refusal checked by `plainsong spec`.
- The web interface never percent-decoded `/files/`, so a rendered file with a
  space in its name 404'd. Latent for compile output, which is always slugged;
  live for what the TUI and the connectors write.

Worth recording: the first versions of the traversal, `MAX_BODY` and
same-origin tests all passed against a deliberately broken server. `urllib`
normalises `..` out of a path before the request is sent and recomputes
Content-Length from the body it was handed, so the guards were never reached
and the 404s came from elsewhere. They now go over a raw `http.client`
connection. A security test that has never seen the code fail is not evidence.

### B4. The academy teaches a language that does not exist — CLOSED

Found by extending `plainsong check` to markdown. Fourteen of the seventeen
fenced `plainsong` blocks in the repository compiled to **zero notes**, and they
are not near-misses — they are four unrelated invented languages:

- `academy/.../04-dynamics-and-velocity.md` taught a bouncing-ball physics
  simulation, `entity Orb { position, velocity, damping, maxSpeed }`, because
  something saw the word *velocity*.
- `academy/.../04-reading-notation.md` taught variables and operators,
  `let myNumber = 5; print myNumber + 2`, with exercises expecting answers like
  `7` and `30`.
- `academy/.../05-compile-and-listen.md` instructed the reader to build with
  `tapc listen.song -o listen.tbc` and run `tap run listen.tbc`. There is no
  bytecode compiler and never has been.
- Several lessons pointed at a server on `localhost:5557`.
- `01-chord-progressions.md` used `prog "X" { chord C func:T beat:2 }`.

**Closed by deletion.** The entire `academy/` and `docs/academy/` directories
have been removed. Three genuine tutorials now cover the same ground:
`docs/tutorial-first-song.md`, `docs/tutorial-arranging.md`, and
`docs/integration.md`. All references to academy in build checks, library
searches, documentation and CI have been removed.

### B5. The fakebook shipped melody and lyrics for in-copyright songs — CLOSED

1,902 of the 6,309 `.song` files carried both a `Melody:` row and a `Lyrics:`
row. The policy this project documents is full melody plus lyrics only for
public-domain works, chord charts otherwise.

It was not being met, and it could not be enforced per title:
`hindi/folk-traditional/tere-bina-jiya-jaye-na.song` carried a full melody and
three verses of lyrics for a 1979 R. D. Burman / Gulzar film song. The
directory name is what defeated the policy — it is filed under
`folk-traditional`, and it is not folk. Nothing in the files records
provenance, so no rule could separate the public-domain works from the rest.

**Closed** by stripping the set to chord charts: 41,990 rows removed from 6,309
files, across `plainsong/songbook/` (3,824 files, packaged) and
`docs/fakebook-archive/` (2,484, not packaged). Neither directory now contains
a single `Melody:` or `Lyrics:` row — checked, not assumed. A chord progression
is not protectable expression; a tune and its words are.

The stripping is whitelist-based rather than blacklist-based. The first attempt
matched `Melody:` and `Lyrics:` literally and missed `Melody (8th):` and bare
lyric lines carrying no row label at all. Policy and rationale are in
`docs/songbook.md`.

Two side effects worth knowing: the ~3,800 bar-count warnings this corpus was
famous for came from those rows and are now 2, and the directory moved inside
the package — kept in `docs/`, it was invisible to anyone who installed rather
than cloned.

### S5. Windows lock contention — SETTLED

Two fixes landed (release no longer raises; acquisition treats a delete-pending
`PermissionError` as contention). `test_the_manifest_survives_a_crowd` now
passes on Windows across 3.10 through 3.13.

## Known limitations -- ship with these, documented

- The built-in synthesiser is a preview renderer. Mono, approximate timbres.
  fluidsynth with a soundfont is the quality path.
- The host bridge cannot stream and reports no token usage.
- The bundled songbook is generated material. It
  parses; it is not all well written.
- The TUI needs `curses`, which stock Python on Windows does not ship. It
  reports this and points at `windows-curses` or the web interface. Found by
  the new TUI tests running on Windows CI for the first time.
- The MCP server has never had a real MCP client connect to it. The protocol is
  verified by hand-driven JSON-RPC, which is strong evidence but not the same
  thing as Claude Desktop or an SDK client connecting.
- **The renderer discards chord extensions.** `arrange.Options.max_chord_notes`
  is 4 and the notes are taken from the bottom, so a five-note chord keeps
  root-third-fifth-seventh and drops what sat above. `D9` sounds like `D7`;
  `E7#9` sounds like `E7`; `G7alt` renders as four notes that are not a chord
  anybody would name. 459 occurrences, 0.3% of the corpus, concentrated
  entirely in the chords where the dropped note is the whole point. The cap is
  defensible; taking the bottom four is not — a player drops the fifth first,
  then the root, because the third and seventh carry the identity. Left alone
  because fixing it changes how existing files sound, and that wants its own
  reviewed diff rather than a ride along with a parser change.
- **`plainsong/mcp/` also exists in `SuperInstance/plainsong-mcp`.** The one
  open violation of "one of everything", and it is temporary: the extraction
  happened while this branch was in review. Until the copy here is removed, a
  change to one must be made to the other or they drift — precisely the failure
  the rule exists to prevent.

## Not blocking, worth knowing

- `master` has been red on its own older workflow since before this branch, for
  reasons unrelated to it.
- **Dialect auto-detection fails on a relative-dialect file, and it looks like
  corrupt source.** `examples/plainsong-4-tap-closing-time.song` is written in
  the relative dialect -- `I`, `IV`, `vi` as roman-numeral chords and `1 . 3 |
  5 . . |` as scale degrees. `dialect: auto` reads it as absolute, so every
  scale degree becomes an unreadable token: 42 notes and 51 warnings. Told
  `--dialect relative` explicitly, the same file yields **111 notes**. The
  melody is real and the detector is wrong.
  This is worth more than the warning count suggests, because of how it nearly
  went. An agent asked to clear the warnings read the bare digits as generation
  artefacts and replaced all 51 with rests. The note count stayed at 42, every
  test passed, the fingerprint moved by exactly the one file it was supposed
  to, and the warnings went to zero -- a clean bill of health for an edit that
  deleted a tune. Reverted. **A warning that a parser cannot read something is
  evidence about the parser at least as often as about the file.**
- **`legacy/` is not dead, and was nearly deleted for being quiet.** It was
  removed on the strength of two documents saying it could go and nothing
  outside it importing it. Both were true and both were beside the point: a
  commit landed on master the next day adding real work to
  `legacy/scripts/gallery_v5.py`, an image-generation studio that shares this
  repository and has nothing to do with the compiler. The directory is
  restored. Absence of imports measures coupling; it says nothing about whether
  anybody is working in there. `git log` says that, and it was never consulted.
- **Three Rust-to-Python ports remain parked and undecided.**
  `counterpoint_analyzer`, `genome` and `tradition_dna` arrived on master
  mid-session and sit in `legacy/src/` beside their siblings. Whether any
  deserves promotion into the package is still an open question this branch
  deliberately did not answer.
