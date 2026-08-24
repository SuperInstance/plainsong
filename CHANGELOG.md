# Changelog

Notable changes, newest first. Dates are ISO 8601.

## Unreleased

### `plainsong mcp` is deprecated

`plainsong-mcp` 1.0.0 is on PyPI, so for the first time there is somewhere to
send people. `plainsong mcp` still works and will keep working until 2.0; it now
warns and names the replacement.

That duplication has already cost twice. A DNS-rebinding fix existed in this
copy and not the sibling for months -- in the copy people `pip install` for MCP.
Then the same eight lines got the same two things wrong in both, because the
second was a copy of the first. Neither repository could notice either time.

The notice goes to **stderr**, and that is not a detail. In stdio mode stdout
*is* the protocol: a deprecation line printed there would desynchronise every
client, turning a courtesy into an outage. `PLAINSONG_NO_DEPRECATION=1` silences
it. A test drives the real subprocess and parses every stdout line as JSON, so
the rule is enforced rather than remembered.


### `plainsong spec` called finding nothing a pass

It printed `no specs found` and exited **0**. That is the exact shape of the
fault it exists to catch: the spec files once sat in a top-level `specs/`
directory, outside the package, so every `pip install` shipped without them --
and every install, and every CI job that ran `plainsong spec`, read that zero
as a pass. The self-verification the whole design leans on was doing nothing,
loudly enough to print a warning and quietly enough that nobody's exit status
moved.

It exits 1 now, and says which of the two things happened: an install missing
its spec files, or a `--tag` nothing carries. This is a **behaviour change** --
a script that ran `plainsong spec` against an install with no specs and treated
0 as success will now see a failure, which is the point.

Found while building `tools/verify_release.py` (below): a wheel built with the
specs deliberately excluded still passed the packaging canary, because the
canary trusted the exit status. Verified directly -- that wheel carries zero
`spec_files` entries, and `plainsong spec` in a venv installed from it reports
`no specs found`.

### A release is now verified from outside the tree

Everything in `tests/` runs with the repository on `sys.path`, which is
structurally blind to packaging: the "no specs found" bug above lived through a
release with a fully green suite. `tools/verify_release.py` never imports
plainsong. It builds a wheel, installs it into a throwaway virtualenv outside
the source tree, and drives the console script from `/tmp` with `PYTHONPATH`
stripped, then repeats against what is actually on PyPI -- including driving
the MCP server with real JSON-RPC over stdio and checking that the sibling's
loopback re-export is the compiler's own function.

CI gains a `packaging` job running `--stage wheel`, so a data file that stops
being packaged fails a pull request rather than a release.

One trap it had to learn: setuptools copies the package into `build/lib` and
**reuses whatever is already there**, so a data file that has stopped being
packaged still reaches the wheel from the last build that did include it. A
broken package then verifies perfectly. The script clears `build/` and
`*.egg-info` before building for that reason.

## 1.4.0 — 2026-08-18

A minor rather than a patch: `plainsong.runtime.localhost` is a new public
module, and a `Host` header that was accepted before is refused now. Nothing
about notation changes -- 6,321 files compile to exactly the music they did in
1.0.0.

### The loopback check let a domain through, and there were two of it

Both local servers — `plainsong serve` and `plainsong mcp --http` — refuse a
request whose `Host` is not this machine. That is the guard against DNS
rebinding, and comparing `Origin` against `Host` does not replace it: point
`evil.example` at 127.0.0.1 and a page served from that domain sends both
headers reading `evil.example`, matching perfectly. What gives it away is the
name itself.

The name was matched with `name.startswith("127.")`. `127.evil.example` starts
with those characters, is registrable, and can be pointed anywhere — so the
test meant to recognise the 127/8 block admitted the exact attack the guard
exists to stop. An address is parsed as an address now, not compared as a
string.

The same eight lines also read a bracketed IPv6 `Host` wrongly. The brackets
are what separate the address from the port, so stripping the port first turned
`[::1]` — which is what a client sends when the port is the default — into
`":"`, and a loopback caller was refused.

Both faults were in both servers, because the second was a copy of the first.
There is now one `plainsong/runtime/localhost.py`, and `tests/test_localhost.py`
fails if a third appears. The rebinding refusal is pinned over a real socket on
both servers, with and without an `Origin` header — the `Host` check has to run
before `Origin` is read, since a non-browser client simply omits `Origin` and an
`Origin`-only guard then has nothing to say.

`bind_is_loopback` is separated from `host_is_local` in the same move, because
they are different questions: a request addressed to `0.0.0.0` is legitimate,
and a server *bound* to `0.0.0.0` is what the "anyone who can reach this port"
warning is for.

The sibling `SuperInstance/plainsong-mcp` carries its own copy and needs the
same fix.

### Every release run had failed, for a reason nobody had read

Five tags, four versions on PyPI, and zero GitHub Releases. 1.3.0 blamed this on
`skip-existing` and shipped a fix for it. That was the wrong diagnosis. Reading
the job logs rather than reasoning about them, all six runs died at the same
step with the same error:

```
invalid-publisher: valid token, but no corresponding publisher
environment: MISSING
```

No Trusted Publisher was ever configured on PyPI. Every version up there had
been uploaded by hand. `skip-existing` is still worth having — it is what makes
a re-run idempotent — but it was never the blocker, and the `test` and `build`
jobs passing in all six runs is what made the failure easy to keep mis-reading.

`docs/releasing.md` is rewritten around this. It had been describing a project
that "has never been published", still sending the reader to the *pending*
publisher page — which refuses a name that already exists rather than
redirecting — and telling them to publish the sibling "the same way" when the
sibling has no release workflow at all. It now says which of PyPI's two pages
applies when, that the claims printed in the error are exactly what the
publisher must match, and that `environment: MISSING` means leave the field
empty.

One consequence worth knowing: a re-run uses the workflow file **as it was at
the tag**. `v1.0.1`, `v1.1.0` and `v1.2.0` predate `skip-existing`, so those
three cannot be backfilled by re-running — they authenticate and then abort on
files already on PyPI. From `v1.3.0` on, a re-run completes.

### The demo has a URL

`docs/index.html` redirects the GitHub Pages root to the browser demo, so
"try it" is a link rather than "download this file and open it". `docs/.nojekyll`
stops Pages running the markdown through Jekyll.

**This needs Pages switched on** — Settings → Pages → Deploy from a branch →
`master` / `docs`. Until that is done the README's link 404s.

### Badges, and the links PyPI shows in its sidebar

Version, supported Pythons, CI, dependencies-none and licence. `[project.urls]`
gains Changelog, Issues and a direct link to `AGENTS.md`, which PyPI renders as
sidebar links and which cost nothing to keep accurate.

## 1.3.0 — 2026-08-18

A minor rather than a patch on two counts: `Meter.readable` and `theory.KEY_RE`
are new public names, and unreadable header values now produce diagnostics that
were not there before — which changes what `check` reports for anyone counting
warnings in CI. No notation changes: 6,321 files compile to exactly the music
they did in 1.0.0.

Also the release workflow passes `skip-existing`, so a run whose artifacts are
already on PyPI completes instead of dying on duplicates. That is what has been
blocking the GitHub Release notes for 1.0.1, 1.1.0 and 1.2.0.

### Header typos were swallowed in silence

`tempo: banana` compiled happily at 100. `time: 3-4` compiled at 4/4. `key: Zz`
sounded in C while a chart printed `Zz` over it. None of them said anything —
not on `compile`, not on `check`, and not on `info --verbose`, which documents
itself as showing every diagnostic.

Each still falls back to a default, which is right: a typo in a header should
not cost you the piece. What was wrong is falling back **without saying so**,
the same fault as `Xm9` compiling to a silent bar. Now:

```
warning: tempo 'banana' is not a number; using 100
warning: time '3-4' is not a metre; using 4/4
warning: key 'Zz' is not a key; sounding in C major
```

The key message names the *sounding* key rather than the text, because the
unreadable text is kept for display — so "using Zz major" would have been no
help at all.

The parsers do not raise on nonsense, so these could not simply catch an
exception. `theory.KEY_RE` and `Meter.readable` name each rule once and serve
both the parse and the question "will parsing work", rather than a second copy
of each pattern drifting from the first.

Found by a fresh agent installing from PyPI and typing plausible mistakes — a
test this project cannot run on itself, having long since stopped making
beginner errors. It immediately turned up a real one in the bundled songbook:
`time: 2/4 (Lassan) then 4/4 (Friska)` on the Hungarian Rhapsody, a human
annotation the metre field cannot express, silently becoming 4/4. The file is
left alone — changing the metre would change the music — and the warning now
says what was ignored.

### The README is the PyPI page, and its links did not work there

`pyproject.toml` sets `readme = "README.md"`, so that file *is* the project page.
Forty-four relative links and one relative image resolved on GitHub and 404'd on
PyPI, which is where a `pip install` user reads them. The page told people to
read a dozen documents none of which they could reach.

All absolute now, images through `raw.githubusercontent.com` because a `blob`
URL serves HTML rather than an image. `tests/test_readme_links.py` buys back the
guarantee absolute links lose: every URL into this repository is mapped to a path
and checked to exist, images must not use `blob`, and the version the README
claims must match the tree — it said "Version 1.0" while PyPI shipped 1.2.0.

The examples section also told pip users to compile `examples/…`, which the wheel
does not ship. It now says so, and points at the bundled library, which it does.

## 1.2.0 — 2026-08-18

A minor rather than a patch: `notation/merge.py`, `notation/lyrics.py` and
`render/chart.py` are new public modules, and `plainsong chart` and
`plainsong lyrics` are new commands. Nothing existing changes — all 6,321
fingerprinted files compile to exactly the music they did in 1.0.0, and lyric
binding is opt-in for that reason.

### Housekeeping: two rename leftovers, and documentation that had drifted

- **`examples/plainsong-4-tap-closing-time.song`** still carried `tap` from
  before the rename, as did `docs/traditions/03-the-tap-songbook.md`. Both
  renamed. The fingerprint is keyed on path, so its baseline was re-recorded —
  and proved inert the way the earlier renames were, by comparing the note-hash
  multiset across all 6,321 files: `b850e4729399e7e5068a13c0` before and after.
  Not one note moved.
- **The README claimed nine complete examples and ships eight.**
- **`SHIPPING.md` said 527 tests and 6,333 sources**; it is 667 and 6,340. It
  opens by saying every claim in it was checked against the working tree, so
  stale numbers make it lie about itself.
- **It also still listed the four-note chord cap as an open limitation** —
  `D9` sounds like `D7` — which 1.0.1 fixed. Corrected, with the measurement and
  the `core.voicing = "stack"` escape hatch.
- **Its claim about the browser demo was the pre-fix one**, describing note
  counts as the guard. Counting was exactly what failed to catch `.` and `-`
  being read as rests. Rewritten to describe what actually checks it now.
- `chart` and `merge` reached `CLAUDE.md`, `AGENTS.md` and
  `docs/architecture.md`, which described neither.

### A third-party MCP client has now connected

The long-standing caveat — *"the MCP server has never had a real MCP client
connect to it"* — is closed. Driven with the official `mcp` Python SDK 2.0.0
over stdio, as any client would: `initialize` returns `plainsong 1.1.0` on
protocol `2025-06-18`, and 27 tools, 9 resources and 2 prompts enumerate.
`compile_score` round-trips inline notation, a resource reads back, and a call
missing a required argument correctly returns `isError: true`.

**One thing worth knowing.** Notation the compiler cannot read returns
`isError: false`, with the failure in the *content* (`error: no sections
found`). The tool ran; the music did not compile. That is defensible under the
specification, which reserves `isError` for execution failures — but it means an
agent client has to read the diagnostics rather than the flag, which is the
"success is not evidence" trap `AGENTS.md` warns about, served over the wire.
Recorded rather than changed: altering `isError` semantics is a decision about
the protocol surface, not a tidy-up.

### A conflict between two agents is now decidable

`notation/merge.py` three-way merges two edits of one score. An edit occupies a
set of `(section, row, bar)` cells, and two edits conflict **exactly when those
sets intersect** — a decision procedure rather than a heuristic.

```python
from plainsong.notation.merge import merge
result = merge(base, mine, theirs)
result.ok           # False only when both sides wrote the same bar differently
result.conflicts    # ["section 1, melody, bar 1"] -- a coordinate, not a diff hunk
```

Two agents rewriting `@bass` and `Melody:` are not in conflict in any sense a
musician would recognise, and neither are two agents rewriting bars 1–4 and bars
5–8 of the same melody. **That second case is what the time matrix buys**: a
file-per-voice model can keep rows apart, but only a coordinate per bar can tell
that two edits to one row do not overlap.

Three things it gets right, each held by a test that fails when the rule is
removed:

- **Bars are numbered the way the arranger counts them.** A repeated row
  continues rather than restarting, so two `Melody:` rows are bars 0–3, not
  0–1 twice. Numbering per row would make two agents editing different bars
  look like one collision.
- **A removal is a change.** Otherwise deleting a row reads as no change at all,
  and the other side's edit to it is resurrected by a merge that believed nobody
  objected.
- **The base is required.** Without it, one agent's untouched copy of a row
  cannot be told from a deliberate revert, and a two-way diff silently undoes
  the other agent's work.

Writing the same thing on both sides is agreement, not collision. The merge
reasons about written tokens rather than arranged notes, so it never changes
anyone's music by rounding — and it does not claim the result is *good*: two
agents can write compatible bars that make poor harmony together, which is a
musical judgement and not a merge conflict.

Phase 4 of `proposals/02-the-voyage.md`.

### `plainsong chart` draws a chord chart as SVG

```bash
plainsong chart song.song -o chart.svg
```

A standalone file, so it commits to a repository and embeds with
`<img src="chart.svg">` — which is the only way a chart appears in markdown on a
platform we do not control, because GitHub strips a raw `<svg>`. That one fact
decides most of the design: no webfonts, no script, and the chart carries its
own background, since an `<img>` cannot inherit the host page's colour and a
transparent chart is black ink on black in a dark README. It honours
`prefers-color-scheme`, so it is legible either way.

**Text is measured and then declared.** Layout is computed in Python from a
width table shipped in the package, and each `<text>` carries `textLength` with
`lengthAdjust="spacingAndGlyphs"` — SVG geometry rather than styling, so the
browser fits the string to the width we planned for even with a substituted
font. `spacing` alone would not do: it adjusts the *n−1* gaps between
characters, so a one-character symbol like `C` has nothing to adjust.

**Bars are as wide as their contents.** Each symbol sits at `unit × width`, so
the next is clear only when `width × (next_unit − unit)` covers this symbol's
advance plus a gap; the largest such requirement across the chart gives the
width exactly, with no iteration. `| Cmaj7#11 Abm7b5 Db7alt Gbmaj9 |` and
`| C . . . |` do not need the same room.

**Accidentals are folded to ASCII.** Liberation Sans has U+266F ♯ and has
neither U+266D ♭ nor U+266E ♮ — the wrong half to lose for a songbook full of
flats and a parser that accepts `E7♭9`. `E7♭9` draws as `E7b9`.

Positions come from `Arrangement.grid` and nowhere else, so a chart cannot
disagree with the audio about when a chord arrives. Symbols are read from every
row rather than only `Chords:`, because in the relative dialect a row mixing
roman numerals with scale degrees reads as melody — a chart taking only the
chord row draws empty bars for a piece whose harmony is written plainly.

`tools/extract_font_widths.py` generates `render/fontmetrics.py` from a real
TrueType file using only `struct`, and measures the bold face separately: `m`,
`b` and `j` differ between the weights and those are what chord symbols are made
of. Measuring one weight and drawing the other makes `lengthAdjust` smear every
glyph.

It is a chord chart, not an engraver — no noteheads, no staff, no beaming. See
[docs/chart.md](docs/chart.md), which lists what it deliberately does not do.

Phase 3 of `proposals/02-the-voyage.md`.

### A syllable can be sung on its note

```plainsong
[V1] (Verse - 1 Bars)
Melody: | A4  .   C5  E5 |
Lyrics: | the tide came  |
```

`came` is written directly beneath `C5` and sounds two thirds of a beat after
it, because the melody row divided the bar into four and the lyric row into
three. Every other notation format binds syllables to notes; they disagree only
about the mechanism, and the counting mechanism ABC and LilyPond use is what
Plainsong already is.

```toml
[core]
lyrics = "bound"
```

`PLAINSONG_CORE_LYRICS` does it for one run. **The default is `independent`,
which is exactly what every existing file already does** — lyric events reach
the MIDI file as meta events, so binding changes output, and a change to how
existing notation compiles defaults to the old reading even when the new one is
better.

- **The barline resyncs.** Each bar's syllables bind to that bar's notes and
  nothing carries across a `|`. Too many syllables in a bar are reported and not
  sung, and the next bar is unaffected: a miscount costs one bar and recovers
  rather than shifting every remaining word in the song.
- **A held syllable needs no mark.** Fewer words than notes and the last word
  carries across them; `LyricEvent.duration` says how long.
- **Lyrics with no melody to bind to are kept where they were written** and
  reported. Dropping the words silently is the worst available answer.

**Padding is not melisma, and the plan was wrong about this.**
`proposals/02-the-voyage.md` proposed reading a sustain token in a lyric row as
a melisma, by analogy with ABC's `_`. The notation people actually write
disagrees:

```plainsong
[V1] (Verse - 1 Bars)
Melody: | Bb3 .   F4    .   |
Lyrics: | sing .   every .   |
```

Two words, two notes — the dots hold the *column* under a sustaining melody.
Read as melismas they would each consume a note and `every` would fall off the
end of the bar. So a sustain or rest token in a lyric row binds to nothing. The
rule follows the notation rather than the analogy. See
[docs/lyrics.md](docs/lyrics.md).

Phase 2 of `proposals/02-the-voyage.md`.

### `plainsong lyrics` shows which note each syllable is sung on

```
$ plainsong lyrics song.song
ok  6 syllable(s); 4 move when bound to their notes
    syllable        written at   sung at    held
    the                      0         0       2
    tide                1.3333         2       1   <- moves
    came                2.6667         3       1   <- moves
```

It exists for the same reason `chord --explain` does: guessing was cheaper than
checking, and that is how the misalignment went unnoticed. Both readings are
shown side by side so the difference is a fact rather than a claim. Syllables
are paired by position rather than by matching text, so a word that appears
twice in a song is not paired with the wrong one of itself.

### `plainsong info --verbose` was showing half the diagnostics it promised

Diagnostics come from two places, and the arranger's are the ones a reader most
needs: an unreadable chord becomes silence while *arranging*, not while parsing.
`transform.describe` arranged the score and then reported only the parser's
half, so a file whose one chord was `Xm9` reported `notes 0` and explained
nowhere.

This affected every consumer of `describe`, not just `info`.
`Arrangement.diagnostics` is already the union of both, and is now what gets
reported. This is the second time this exact fault has shipped — `cmd_check` had
it before — so it is recorded in `CLAUDE.md` rather than just fixed.

## 1.1.0 — 2026-08-17

A minor rather than a patch: `notation/timegrid.py` is a new public module and
`Arrangement.grid` a new public field. Nothing existing changes — all 6,321
fingerprinted files compile to exactly the music they did in 1.0.0.

### The browser demo cut every held note short

`.` and `-` were in the demo's `REST` set where the compiler has them in
`SUSTAIN`. They are the two most common tokens in the notation, and they hold
the note before them. Reading them as rests meant `| Am . . . |` played a
one-beat chord followed by three beats of silence instead of a chord lasting the
bar. Every sustained note on the landing page — the first thing anyone hears —
was cut to a single subdivision.

The demo/compiler parity test could not see it. It pins the **note count** each
preset produces, and a rest and a sustain produce the same count: they differ
only in how long the note before them lasts. Counts matched exactly, start to
finish. The page simply sounded wrong.

- Both token sets now match `notation/parser.py`, including the parenthesised
  forms (`(hold)`, `(rest)`, `(let ring)`) and the rule that any other
  `(direction)` holds what is sounding — none of which the page had at all.
- `tests/test_demo.py` compares both sets against the compiler's and pins the
  durations that follow from them. Restoring the old sets fails it.
- `tools/demo_differential.py` is new: it runs notation through the real page in
  a browser and through the compiler, and compares **pitch, start and duration**
  of every note across triplets, 3/4, 6/8, chord qualities, stacks, sustains,
  rests and repeated rows. CI cannot run it — the suite installs nothing and
  assumes no browser — so it is a manual check, and it reports six of the eight
  cases differing against the revision this fixes.

The general lesson is worth more than the fix: **a second implementation checked
by counting is not checked.** Counts are the property most likely to survive a
divergence.

### Every written token now has a position, whether or not it sounds

`Arrangement.grid` is a new `TimeGrid` (`notation/timegrid.py`) holding every
token in every row on one coordinate system. Nothing about compilation changes:
all 6,321 fingerprinted files compile to exactly the music they did.

Rows divide their bars independently, so vertical alignment means nothing to the
compiler. In

```
Melody: | A4  .   C5  E5 |
Lyrics: | the tide came  |
```

`came` is written directly beneath `C5` and sounds two thirds of a beat after
it. That was previously not merely unreported but *inexpressible* — there was no
coordinate in which the two could be compared. Now `C5` is at `unit 0.5`, `came`
at `unit 0.667`, and `grid.column(0, 0.5)` returns the chord and melody rows
without the lyric that appears to be standing in them.

`bar` and `unit` are derived in one function, so a lyric and a note cannot drift
apart by being computed in two places. Rests and sustains are recorded as well:
a token that makes no sound still occupies its column, because a renderer has to
leave room for it and a merge has to see it as taken.

This reports nothing and enforces nothing yet — `grid.disagreements()` is a
query. Uneven subdivision is legal and often deliberate; a held chord under a
running melody is two tokens against sixteen and there is nothing wrong with it.

Phase 1 of `proposals/02-the-voyage.md`.

### The demo shows you which characters are sounding

The page's playground had a text box and a piano roll sitting next to each
other, and nothing ever drew the line between them: a visitor had to infer that
the third `A4` they typed produced the third block moving in the canvas. That
inference is the whole idea of the notation, and it was left as an exercise.

Each token now lights up while the note it wrote is sounding — including the
`.` tokens the note is held across, so `Am . . .` illuminates as one thing and
you can see that the dots are part of the chord rather than events of their own.
A textarea cannot hold a styled span, so the same text is painted behind it in
identical metrics and lit there.

A silent preview sweeps the playhead once on load, so the page is visibly
something that plays before anything is clicked. It is canvas and CSS only and
never opens an `AudioContext`: nothing here can make a sound the visitor did not
ask for. It ends at the first interaction, and does not run under
`prefers-reduced-motion`.

On a phone the editor used to push the Play button below the fold, so the first
screen was a text box with no visible way to hear anything. The panel that makes
sound now comes first.

### Repeated lyric rows are verses — decided, not yet implemented

Every other notation format stacks repeated lyric rows as parallel verses;
Plainsong's rule is that a repeated row runs on in time. The plan proposed
inventing `Lyrics 2:` to have both. That was the wrong shape: run-on is a claim
about *time*, and once lyrics bind to notes they own no time for a second row to
follow on into, so the rule does not reach them and needs no exception.

> Every `Melody:` row in a section concatenates into one melodic stream. Each
> `Lyrics:` row is a verse sung over that whole stream.

No new syntax. Not one of the 6,321 `.song` files here has a section with more
than one `Lyrics:` row, and lyrics do not enter the fingerprint, so this can move
no note. It ships gated with the rest of lyric binding rather than on its own.

## 1.0.1 — 2026-08-17

Fixes to what 1.0.0 said about itself, and to a setting it documented but never
read. No notation changes: all 6,321 files in the repository compile to exactly
the music they did in 1.0.0.

### The voicing setting now exists

1.0.0 changed how chords with more than four notes are rendered — a genuinely
better default, arrived at by measurement — and shipped **no way to opt out**.
`docs/voicing.md` told readers to set `render.voicing`, `ArrangeOptions` carried
the field, and nothing anywhere read it from configuration. Anyone whose
recordings depended on the old rendering had no recourse, and anyone who
followed the documentation got silence.

- **`core.voicing` selects the strategy**, and `PLAINSONG_CORE_VOICING` sets it
  for a single run. `stack` restores the pre-1.0.0 rendering exactly.
- It lives in `[core]` beside `bar_fill`, because it decides which notes exist
  and therefore changes the MIDI, not merely the audio. `render.voicing` is
  still honoured so that the spelling 1.0.0 published is not ignored.
- **A value that is not a strategy is now reported.** It previously fell back to
  the default in silence, which is indistinguishable from having been obeyed —
  the same fault, one level down.

### The 1.0.0 notes described a bug that 1.0.0 had already fixed

The release carried a section headed *"Known, recorded rather than fixed"*
stating that `D9` sounds like `D7`. The commit that fixed exactly that shipped
in the same release. Users reading the changelog were told the opposite of what
the software does, and — more seriously — were not told that seventy-two files
in the bundled corpus had changed how they sound. That section has been replaced
with what actually happened, including the breaking-change notice it owed.

## 1.0.0 — 2026-08-17

A rebuild. One engine replaces the two that had drifted apart, and everything
that used to be compiled in — paths, model provider, rendering backend — is now
resolved at runtime. Chord symbols are read by a grammar rather than a table,
voicing keeps the note a symbol was written for, and the corpus is held to
compiling to the same music rather than merely to compiling.

### The corpus is held to compiling to the same music, not merely to compiling

- **`plainsong fingerprint`** hashes what notation compiles to — pitch,
  position, length, velocity and voice — so a change in the *sound* of existing
  files is visible. `--check` compares against a recorded baseline and names
  every file that moved; `--write` re-records one.
- **CI now runs it over all 6,321 files.** The gap it closes is not
  hypothetical: with every major seventh in the package flattened by a
  semitone, `plainsong check` reports `ok 6333 file(s) checked` and the
  `library.compat` spec passes, because both only ask whether notation still
  compiles. The fingerprint catches it — 235 files, all with identical note
  counts, so only the hash moves.
- It is a user-facing command rather than a test helper because anyone with a
  folder of `.song` files has the same problem and no access to our suite:
  fingerprint before an upgrade, fingerprint after, diff.

### Chords that name more notes than fit now keep the note that was named

**This changes how existing files sound.** Seventy-two files in the bundled
corpus render differently than they did before, and files outside this
repository containing ninths, elevenths, thirteenths or altered fifths will do
the same. If you need the old rendering, set `core.voicing = "stack"`.

- **The renderer used to discard extensions.** `arrange.Options.max_chord_notes`
  is 4 and the notes were taken from the bottom, so a five-note chord kept
  root-third-fifth-seventh and dropped whatever sat above — which is the one
  note that made the symbol worth writing. `D9` rendered as `D7`; `E7#9`, the
  chord an entire Hendrix record is built on, rendered as `E7`; `G7alt`
  rendered as four notes that are not a chord anybody would name.
- **A player thinning a voicing drops the fifth first and the root second**,
  because the third and the seventh are what identify the chord. Taking the
  bottom four does exactly the opposite.
- **Chosen by measurement, not by argument.** Five strategies scored over every
  chord in the repository, reproducible with `plainsong voicing --compare`. The
  first measurement was useless and is worth recording as a mistake: averaged
  over all 125,375 chord occurrences it read 99.4% against 99.9%, because 99.7%
  of the corpus is triads and sevenths where the cap never bites and every
  strategy agrees. Averaging over the cases where nothing happens hides the case
  where something does. Scored on the 277 occurrences where a note actually has
  to go, keeping the symbol's defining note rose from 50.1% to 94.4%.
- `plainsong voicing "C13"` shows what any symbol reduces to under each
  strategy, and why. See [docs/voicing.md](docs/voicing.md).

### Chord symbols are read by a grammar

- **Compound spellings work without being enumerated.** The chord parser held a
  table of about thirty spellings, so `C7b9` worked and `C7b9#11` did not --
  not because anyone disagreed about what the second one means, but because
  nobody had typed that combination in. Symbols are now parsed into a root, a
  core quality, a stack height and a list of modifications, and the notes are
  derived from those. `C7b9#11`, `F13#11`, `Bbmaj7#5`, `Cadd11`, `G7#11` and
  `C9sus4` all read now, and none of them appears in any table.
- **`C7M` is a major seventh.** Standard in Brazil, from *sétima maior*, and
  the largest single group of unreadable chords in the bundled songbook -- 39
  of them. `C7M` and `Cm7` differ only in the order of two characters and are
  different chords, so an `M` counts as a major seventh only when a `7`
  immediately precedes it.
- **`G7alt` reads, and subtracts rather than adds.** The altered scale contains
  no natural fifth and no natural ninth, so a chord that grew them would be the
  wrong chord. 35 occurrences, previously silence.
- **Capitalisation and Unicode no longer refuse a chord.** `EbMaj7` (22
  occurrences) failed on a capital M alone. `E7♭9` failed because the root
  accepted a Unicode flat and the suffix did not. Both triangles are accepted:
  `Δ` is U+0394 and `∆` is U+2206, they are indistinguishable on screen, and
  both are in real charts.
- **Three rules now hold that a table could not express.** An alteration
  displaces its natural form, so `C7b9` has a D♭ and no D. An extension implies
  the odd degrees below it except the eleventh over a major third, so `C13` is
  7-9-13 while `Cm13` keeps its eleventh and `C13#11` gets a raised one.
  Removing a note removes what depended on it, so `C9sus4` needs no special
  case -- with no third, the fourth is simply a note.
- **`plainsong chord SYMBOL --explain`** reads a symbol out loud: every degree,
  what bent it, the MIDI numbers, and what is deliberately absent. `--json`
  for anything parsing it. The absences matter as much as the notes; `C7alt`
  reports `no fifth`.
- Documented in `docs/chords.md`, and the table of accepted spellings in that
  document is held to parsing by a test, because a table of promises in prose
  does not fail to compile on its own.

  **Nothing that compiled before compiles differently.** Every chord token in
  the repository was parsed with both engines and compared: 181,276 identical,
  136 newly readable, 0 changed. That result is why the richer vocabulary is
  the default rather than something to opt into. It was not zero on the first
  attempt -- the diff caught `Bb-7` turning into a dominant, which would have
  moved 22 minor chords in this repository and sounded wrong without looking
  wrong. Warnings from `plainsong check` over every source fell from 185 to 87.

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

- Every path is derived from the environment, a project-local `.plainsong/`, or
  the platform convention. The hardcoded `~/.openclaw/workspace/output` and
  `/home/eileen/projects/plainsong` are gone, and a test fails if either
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
  Plainsong can borrow that agent's model instead of asking for a second API
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
  `plainsong stage` reports the spread at the conductor, at the audience, or
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

- `plainsong mcp` serves JSON-RPC 2.0 over stdio, and over loopback HTTP for
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
- A terminal interface (`plainsong tui`) built on curses.
- A web interface (`plainsong serve`) on loopback, refusing cross-origin
  requests, serving rendered files only from the output directory.
- All three call the same `compile_text`, so compiling cannot come to mean
  different things in different places.

### Checking itself

- `plainsong/spec_files/` states what the system promises and names the checks
  that prove it. `plainsong spec` runs them, `plainsong doctor` reports the
  host, and the build agent runs both to verify its own changes. The specs used
  to live beside the package in a top-level `specs/`; a wheel carries only what
  is under the package, so `plainsong spec` reported "no specs found" to
  everybody who installed rather than cloned — the self-verification the whole
  design leans on, quietly doing nothing for exactly the people least able to
  notice. They are packaged now, and a
  `kind = "command"` check substitutes `{python}` for the interpreter actually
  running instead of hardcoding `python3` — the old form broke in every
  virtualenv and pipx install, reporting "No module named plainsong" about a
  package that had installed correctly.
- `plainsong check` extracts fenced ```` ```plainsong ```` blocks out of
  markdown as well as `.song` files, with file:line reporting, and
  `tests/test_notation.py::TestDocumentedNotation` fails if a documented
  example stops compiling or stops making a sound. It also reports the
  arranger's diagnostics, not only the parser's — an unreadable chord becoming
  silence is found while arranging, and only the parser's side used to reach
  anyone.
- 527 tests, 7 specs, and a CI job that checks 6,333 sources: every `.song` file
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
- **Ships from inside the package.** `plainsong library` and
  `plainsong play stand-by-me` found nothing for anyone who had installed
  rather than cloned — the corpus lived under `docs/`, and a wheel carries only
  what is under the package. The same fault as the specs, the same fix: 3,824
  charts now live in `plainsong/songbook/` and ship. The remaining 2,484 stay
  in `docs/fakebook-archive/`, not packaged. The songbook's own explainer moved
  from inside the package to `docs/songbook.md` — it is documentation, and it
  followed the charts into `plainsong/` by accident when they were packaged.

### Documentation

- Three guides, each written by installing the built wheel into a clean venv
  and walking a beginner's, an arranger's and an integrator's path through it:
  `docs/tutorial-first-song.md`, `docs/tutorial-arranging.md` and
  `docs/integration.md`. Every notation example in all three is tagged
  ```` ```plainsong ````, so `check` compiles them and CI fails if a guide stops
  working.
- `docs/releasing.md` covers cutting a release: what must be inside the
  package and why, and how to verify a build from a clean venv outside the
  source tree. A test now fails if `pyproject.toml` and `plainsong/version.py`
  disagree on the version, since one feeds the wheel and the other feeds
  `--version`.
- `.github/workflows/release.yml`: tag → test → build → publish to PyPI via
  trusted publishing → GitHub release. The first step refuses a tag that
  disagrees with `plainsong/version.py`, because the tag is the only thing that
  says which version a release is and nothing in the tree knows about it — a
  `v1.1.0` tag on a tree still saying 1.0.0 would publish 1.0.0 under a release
  page claiming otherwise, and PyPI will not accept that filename twice to let
  you correct it.
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
  reads `"banana"` as B major, so `plainsong transpose song.song banana` quietly
  moved the whole score down a semitone, and `Z` reformatted it in place while
  appearing to work. `transform.transpose` now raises `TheoryError` for a target
  it cannot read, and the CLI, the web interface, the TUI and the agent tool all
  report it. Notation parsing is unchanged: a `Key:` header still falls back to
  C major as it always has, and every `.song` file in the repository parses
  identically. `plainsong spec` checks the refusal.
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
  through to a tool that writes files. The web interface and `plainsong/mcp/`
  (mirrored, since that copy still exists pending extraction to the sibling
  repository) now also require `Host` to name this machine; a rebound request
  always carries the attacker's hostname there, so it cannot satisfy both.

### Removed

- **`academy/` and `docs/academy/` are deleted.** Extending `plainsong check` to
  fenced markdown blocks found that fourteen of the seventeen documented
  examples in the repository compiled to zero notes, and they were not
  near-misses: the lesson on dynamics and velocity taught a bouncing-ball
  physics simulation, the lesson on reading notation taught variables and
  operators, and one exercise instructed the reader to build with a bytecode
  compiler that has never existed. `check` walked only `.song` files and the
  academy contains none, so aiming the check at it passed vacuously and was
  quoted as evidence. The material is deleted rather than repaired;
  `docs/tutorial-first-song.md`, `docs/tutorial-arranging.md` and
  `docs/integration.md` cover the same ground and are held to compiling by
  `tests/test_notation.py::TestDocumentedNotation`. The directory is also gone
  from `library.SEARCH_DIRECTORIES`, from CI, and from every documented `check`
  invocation.
- **20 MB of committed build output is gone.** `examples/` carried 23 generated
  `.mid` and `.wav` files in every clone — committed before `.gitignore` learned
  to ignore them, and git kept tracking them regardless. The 13 real `.song`
  examples and `examples/edge-cases/BUGS.md` stay; 20 MB down to 68 KB.

### Moved

- The previous engines, the image gallery, the MIDI studio, the fake book
  generator and the unrelated `src/` ports were archived in `legacy/`.
- The old `docs/01`–`04` describing the old system were archived in `legacy/docs/`.

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
