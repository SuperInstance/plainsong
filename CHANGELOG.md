# Changelog

Notable changes, newest first. Dates are ISO 8601.

## 1.0.0 — 2026-08-15

A rebuild. One engine replaces the two that had drifted apart, and everything
that used to be compiled in — paths, model provider, rendering backend — is now
resolved at runtime.

### The compiler

- **One engine, both notations.** The labelled dialect (`Chords:`, `Melody:`,
  `@player`, scientific pitch) and the older relative one (roman numerals and
  scale degrees) are read by the same parser and compile through the same
  arranger.
- **Parsing and arranging are separate.** The parser builds a structural score
  and keeps tokens as written; the arranger decides timing. Transposition is
  parse, rewrite, emit — so it now moves the chord row, which the previous
  engine skipped.
- **A bar is one bar long.** Tokens in a bar divide it, so twelve tokens are
  triplets and a seventeenth cannot spill into the next bar. Fixes BUG-1 and
  BUG-2 in `examples/edge-cases/BUGS.md`. The old behaviour is available as
  `core.bar_fill = "grid"`, and reports every token it drops.
- **Repeated rows follow on.** Two `Melody:` rows in one section are eight bars,
  not four played twice. Rows of different kinds still sound together.
- **Time signatures are honoured**, including `3/4` and `6/8`.
- **Duration-by-spacing** (`C4~~~`) works in both dialects. It previously
  existed in only one engine.
- **Unclassifiable rows are reported, not guessed at.** The old heuristic could
  drop a melody silently if too few of its tokens looked like digits.
- **An unreadable chord or pitch token now warns instead of silently becoming a
  rest.** `Xm9` used to compile "ok, 0 warnings" and produce a bar of nothing;
  the arranger now reports what it could not read, with a hint about what
  chords and pitches look like.
- Slot positions are computed from the bar start rather than accumulated, so
  timing cannot drift over a long piece.

### No dependencies

- MIDI writing and audio synthesis are written against the standard library. A
  clone with nothing installed compiles and produces sound. CI proves it on
  Python 3.10–3.13 across Linux, macOS and Windows with no install step.
- NumPy, fluidsynth, ffmpeg, mido and an audio player are detected at runtime
  and used when present. None is required.

### Portability

- Every path is derived from the environment, a project-local `.tapscript/`, or
  the platform convention. The hardcoded `~/.openclaw/workspace/output` and
  `/home/eileen/projects/tapscript-studio` are gone, and a test fails if either
  kind of path comes back.
- Layered configuration: defaults, user file, project file, environment, flags.
- Ports are configurable. The two engines both hardcoded 5557 and could not run
  together.

### Models

- **Any provider.** Anthropic, OpenAI, DeepSeek, OpenRouter, xAI, Gemini, Groq,
  Mistral, Together, Fireworks, Cerebras, Azure, Ollama, LM Studio, vLLM and
  anything else OpenAI-shaped. Providers are catalogue entries, so adding one is
  a JSON file.
- **Host bridge.** Running inside Claude Code, openclaw or a similar agent,
  TapScript can borrow that agent's model instead of asking for a second API
  key — by subprocess, by a documented file handshake, or over stdio.
- **Offline stub.** `--provider echo` returns valid notation with no network, so
  the agent loop and the interfaces can be used and tested with no connection.
- Keys are read from the environment or a separate credentials file that is
  never mixed into shareable configuration. `DEEPSEEK_API_KEY` is no longer
  found by grepping `~/.bashrc`.

### The agent

- A composer agent that writes and revises notation, and a build agent that
  probes the host and tailors the install to it.
- Twenty-seven tools, sandboxed to a workspace. Notation is parsed before it
  is written, so invalid notation never reaches disk.
- Runs are bounded by a step budget and emit events, which is how the CLI shows
  progress and the web interface shows what happened.

### Arrival-centric timing

- **A written time is when the sound should reach the listener**, not when the
  player acts. Declare a `[Stage]` and the solver works backwards for each
  voice: `emission = arrival - speech - propagation - p_center + feel`, where
  speech is the instrument taking time to sound, propagation is distance over
  the speed of sound, and p_center is the ear placing the note slightly into
  the attack. A large organ pipe 14 m from the podium has its key pressed
  241 ms early so that it speaks on the beat.
- **Every listener hears something different**, and the analysis says so.
  `tapscript stage` reports the spread at the conductor, at the audience, or
  at any named player's desk. At the podium a compensated ensemble is together;
  at the second violin's chair the timpani are late. That is why an orchestra
  watches instead of listening.
- **Conducting is one transform over the whole ensemble.** `conduct` consumes
  the directive schema from fleet-jepa-midi unchanged, so the two systems speak
  the same language. The Time/Feel family is implemented; anything else is read
  and reported rather than silently ignored.
- `anticipate` and `push_forward` are different operations and the model can
  tell them apart: anticipate moves the hands and leaves the arrival on the
  beat, push_forward moves the arrival itself. A correction versus an
  intention.
- **Inert without a `[Stage]`.** A file that declares no stage compiles to
  byte-identical output. Instrument speech profiles are a model, not
  measurements, and say so.

### The Model Context Protocol server

- `tapscript mcp` serves JSON-RPC 2.0 over stdio, and over loopback HTTP for
  remote and multi-agent setups. Any MCP-capable client can drive the whole
  system without shelling out to the CLI.
- Tools are enumerated from the existing registry, so a tool added anywhere in
  the codebase appears automatically rather than being maintained twice.
  Resources cover the library, sessions, specs and capabilities; prompts expose
  the composer and builder roles.
- `analyze_features` computes the sixteen per-bar features fleet-jepa-midi
  perceives, which lets a bandleader read a written score and makes the
  repository's notation usable as a labelled corpus.

### The ensemble layer

- Many agents, one score. A session gives each agent a voice to own, so the
  common case is conflict-free by construction. Writes carry the version they
  were made against; a stale write is refused and handed the current state to
  rebase onto, because a lock cannot be held across a model call that takes
  seconds.
- Parts are validated as notation before they are accepted, so invalid notation
  never lands. Writes are atomic, the merge is deterministic, and every change
  appends to a log a joining agent can read to find out what has happened.

### Interfaces

- A CLI with nineteen commands, `--json` on all of them, and useful exit codes.
  `check` and `transpose` were the two holdouts — `check` emitted nothing under
  `--json` and `transpose` printed raw notation, so a caller piping either into
  a parser got garbage. `info --verbose` shows every diagnostic, as documented.
- A terminal interface (`tapscript tui`) built on curses.
- A web interface (`tapscript serve`) on loopback, refusing cross-origin
  requests, serving rendered files only from the output directory.
- All three call the same `compile_text`, so compiling cannot come to mean
  different things in different places.

### Checking itself

- `tapscript/spec_files/` states what the system promises and names the checks
  that prove it. `tapscript spec` runs them, `tapscript doctor` reports the
  host, and the build agent runs both to verify its own changes. The specs used
  to live beside the package in a top-level `specs/`; a wheel carries only what
  is under the package, so `tapscript spec` printed "no specs found" to every
  `pip install` user rather than to nobody. They are packaged now, and a
  `kind = "command"` check substitutes `{python}` for the interpreter actually
  running instead of hardcoding `python3` — the old form broke in every
  virtualenv and pipx install, reporting "No module named tapscript" about a
  package that had installed correctly.
- `tapscript check` extracts fenced ```` ```tapscript ```` blocks out of
  markdown as well as `.tap` files, with file:line reporting, and
  `tests/test_notation.py::TestDocumentedNotation` fails if a documented
  example stops compiling or stops making a sound. It also reports the
  arranger's diagnostics, not only the parser's — an unreadable chord becoming
  silence is found while arranging, and only the parser's side used to reach
  anyone.
- 527 tests, 7 specs, and a CI job that checks 6,333 sources: every `.tap` file
  in the repository plus every fenced example in the prose.

### The songbook

- **Chord charts only.** Melody and lyric rows are stripped: 41,990 rows
  removed from 6,309 files, chords and structure kept. The documented policy
  has always been full melody plus lyrics only for public-domain works, and it
  could not be enforced per title — nothing recorded provenance, and the genre
  directories lie (a 1979 R. D. Burman film song was filed under
  `hindi/folk-traditional`). The reduction is universal rather than
  adjudicated: a chord progression is not protectable expression, a tune and
  its words are.
- **Ships from inside the package.** `tapscript library` and
  `tapscript play stand-by-me` found nothing for anyone who had installed
  rather than cloned — the corpus lived under `docs/`, and a wheel carries only
  what is under the package. The same fault as the specs, the same fix: 3,824
  charts now live in `tapscript/songbook/` and ship. The remaining 2,484 stay
  in `docs/fakebook-archive/`, not packaged. The songbook's own explainer moved
  from inside the package to `docs/songbook.md` — it is documentation, and it
  followed the charts into `tapscript/` by accident when they were packaged.

### Documentation

- Three guides, each written by installing the built wheel into a clean venv
  and walking a beginner's, an arranger's and an integrator's path through it:
  `docs/tutorial-first-song.md`, `docs/tutorial-arranging.md` and
  `docs/integration.md`. Every notation example in all three is tagged
  ```` ```tapscript ````, so `check` compiles them and CI fails if a guide stops
  working.
- `docs/releasing.md` covers cutting a release: what must be inside the
  package and why, and how to verify a build from a clean venv outside the
  source tree. A test now fails if `pyproject.toml` and `tapscript/version.py`
  disagree on the version, since one feeds the wheel and the other feeds
  `--version`.
- `.github/workflows/release.yml`: tag → test → build → publish to PyPI via
  trusted publishing → GitHub release.
- **A browser demo that compiles for real**, at `docs/demo/index.html`: a
  parser, arranger, MIDI writer and WebAudio player in one self-contained file
  with no network, no build step and no dependencies. It is a second
  implementation of the notation, which "one of everything" exists to prevent,
  so it is guarded rather than trusted — checked against the reference compiler
  on fourteen cases (triplets, 3/4, 6/8, chord qualities, stacks, sustains,
  repeated rows, real songbook files) and it agrees note-for-note. CI has no
  JavaScript runtime, so `tests/test_demo.py` holds the page's own claims
  against the Python compiler instead: the page states the note count it
  produces for each preset, and a change to the arranger that moves a count now
  fails there rather than leaving the page quietly lying. The page also
  includes a stage simulation — drag a listener between the podium and the
  ensemble to hear the same performance arrive 0 ms apart or 51 ms apart,
  depending where you stand — offline WAV rendering, a chord generator built
  from real harmony, and share links that carry the song in the URL fragment
  rather than storing it anywhere.

### Fixed

- **A transpose target that names no key is refused.** `parse_key` is forgiving
  on purpose — a hand-typed `Key:` header must not stop a file loading — but it
  reads `"banana"` as B major, so `tapscript transpose song.tap banana` quietly
  moved the whole score down a semitone, and `Z` reformatted it in place while
  appearing to work. `transform.transpose` now raises `TheoryError` for a target
  it cannot read, and the CLI, the web interface, the TUI and the agent tool all
  report it. Notation parsing is unchanged: a `Key:` header still falls back to
  C major as it always has, and every `.tap` file in the repository parses
  identically. `tapscript spec` checks the refusal.
- **The web interface percent-decodes `/files/`.** A rendered file whose name
  contained a space arrived as `my%20song.wav` and was served as a 404. Names
  produced by `slugify` were never affected, which is why this went unseen; the
  TUI and the connectors write names that are not slugged. A null byte in the
  name is now a 404 rather than an unhandled `ValueError`.
- **Transposing no longer grows every `@player` row by a bar.** `_format_row`
  closed a barred row with `|` and then appended ` | vel: 70`, so the emitted
  text read `... | | vel: 70`. Reading that back saw the empty cell as a real
  bar, so each transpose pushed the row one bar further out of step with its
  section — and the section then warned that its rows disagreed about their
  length, which read as the user's mistake rather than the tool's. Two tests
  hold the invariant: repeated transposition holds every row at its original
  width, and emitted text parses back to the shape it came from.

### Security

- **The DNS-rebinding hole is closed in both local servers.** Comparing
  `Origin` against `Host` alone is defeated by rebinding: point `evil.example`
  at 127.0.0.1, and a page served from that domain sends `Origin` and `Host`
  both reading `evil.example` — they match, and the check waved the request
  through to a tool that writes files. The web interface and `tapscript/mcp/`
  (mirrored, since that copy still exists pending extraction to the sibling
  repository) now also require `Host` to name this machine; a rebound request
  always carries the attacker's hostname there, so it cannot satisfy both.

### Removed

- **`academy/` and `docs/academy/` are deleted.** Extending `tapscript check` to
  fenced markdown blocks found that fourteen of the seventeen documented
  examples in the repository compiled to zero notes, and they were not
  near-misses: the lesson on dynamics and velocity taught a bouncing-ball
  physics simulation, the lesson on reading notation taught variables and
  operators, and one exercise instructed the reader to build with a bytecode
  compiler that has never existed. `check` walked only `.tap` files and the
  academy contains none, so aiming the check at it passed vacuously and was
  quoted as evidence. The material is deleted rather than repaired;
  `docs/tutorial-first-song.md`, `docs/tutorial-arranging.md` and
  `docs/integration.md` cover the same ground and are held to compiling by
  `tests/test_notation.py::TestDocumentedNotation`. The directory is also gone
  from `library.SEARCH_DIRECTORIES`, from CI, and from every documented `check`
  invocation.
- **20 MB of committed build output is gone.** `examples/` carried 23 generated
  `.mid` and `.wav` files in every clone — committed before `.gitignore` learned
  to ignore them, and git kept tracking them regardless. The 13 real `.tap`
  examples and `examples/edge-cases/BUGS.md` stay; 20 MB down to 68 KB.

### Moved

- The previous engines, the image gallery, the MIDI studio, the fake book
  generator and the unrelated `src/` ports are in `legacy/`. Nothing imports
  them, nothing tests them, and the directory can be deleted.
- The old `docs/01`–`04` describe the old system and moved to `legacy/docs/`.

### Known limitations

- The built-in synthesiser is a preview renderer, not an instrument library.
  Install fluidsynth and a soundfont for accurate timbres.
- Audio is mono.
- The host bridge cannot stream and reports no token usage.
- The MCP server's protocol is verified by hand-driven JSON-RPC. No third-party
  MCP client has connected to it yet.
- `EbMaj7`, `G7alt` and `CM7` are legitimate spellings the chord parser does not
  accept, and it has been silently dropping them rather than warning — found by
  turning on the unreadable-token warning above and running it over the
  songbook. Still open; changing chord parsing wants its own spec and changelog
  entry.
- `docs/fakebook-archive/` is generated material not included in the package
  and carries bar-count warnings. It parses; it is not all well written.
