# Changelog

Notable changes, newest first. Dates are ISO 8601.

## Unreleased

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

### Fixed

- **A transpose target that names no key is refused.** `parse_key` is forgiving
  on purpose — a hand-typed `Key:` header must not stop a file loading — but it
  reads `"banana"` as B major, so `tapscript transpose song.tap banana` quietly
  moved the whole score down a semitone, and `Z` reformatted it in place while
  appearing to work. `transform.transpose` now raises `TheoryError` for a target
  it cannot read, and the CLI, the web interface, the TUI and the agent tool all
  report it. Notation parsing is unchanged: a `Key:` header still falls back to
  C major as it always has, and all 6,322 `.tap` files in the repository parse
  identically. `tapscript spec` checks the refusal.
- **The web interface percent-decodes `/files/`.** A rendered file whose name
  contained a space arrived as `my%20song.wav` and was served as a 404. Names
  produced by `slugify` were never affected, which is why this went unseen; the
  TUI and the connectors write names that are not slugged. A null byte in the
  name is now a 404 rather than an unhandled `ValueError`.

### Tests

- The web interface, the HTTP transport and the connector layer had no tests at
  all. They now have 102 between them, taking the suite to 514.
- The traversal, body-limit and same-origin tests drive the server over a raw
  connection. Sent through `urllib` they proved nothing: the client normalises
  `..` out of the path before the request leaves the process, and recomputes
  Content-Length from the body it was actually given, so neither guard was ever
  reached. Removing either guard now fails the suite.

## 1.0.0 — 2026-08-13

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
- A terminal interface (`tapscript tui`) built on curses.
- A web interface (`tapscript serve`) on loopback, refusing cross-origin
  requests, serving rendered files only from the output directory.
- All three call the same `compile_text`, so compiling cannot come to mean
  different things in different places.

### Checking itself

- `specs/` states what the system promises and names the checks that prove it.
  `tapscript spec` runs them, `tapscript doctor` reports the host, and the build
  agent runs both to verify its own changes.
- 333 tests, plus a CI job that parses all 6,322 `.tap` files in the repository.

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
- `docs/fakebook/` is generated material and carries about 3,800 bar-count
  warnings. It parses; it is not all well written.
