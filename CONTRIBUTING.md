# Contributing

## Getting set up

```bash
git clone https://github.com/SuperInstance/tapscript-studio
cd tapscript-studio
python3 -m tapscript doctor
```

There is nothing to install. If you want the linter and pytest:

```bash
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
python3 -m tapscript spec                        # the system's own checks
python3 -m unittest discover -s tests -v         # the test suite
python3 -m tapscript check docs examples academy # the notation library still parses
ruff check tapscript tests                       # if you installed it
```

The first two also run in CI on Python 3.10 through 3.13, on Linux, macOS and
Windows, with nothing installed.

## The one rule that matters

**The core must keep working with the standard library alone.**

A clone with no `pip install` has to parse, compile, write MIDI, synthesise
audio, serve the web interface and talk to a model API. An import of NumPy,
`requests`, `pretty_midi` or anything else at module scope in `tapscript/`
breaks that, and CI will catch it.

Optional accelerators are welcome. Probe for them in
`runtime/capabilities.py`, import them inside the function that uses them, and
make sure the fallback produces the same result more slowly.

## Where things belong

| Change | Goes in |
|---|---|
| A new chord quality, scale or pitch spelling | `notation/theory.py` |
| How a row is read | `notation/parser.py` |
| When a note sounds | `notation/arrange.py` |
| A new instrument sound | `render/voices.py` |
| A model service that speaks an existing wire format | `llm/catalog.json` — data, not code |
| A model service with its own wire format | `llm/providers/`, then `ADAPTERS` |
| A new agent capability | `agent/tools.py` |
| A way out to another system | `connectors/builtin.py`, or a plugin |

If you find yourself copying a table between two files, stop. The version this
replaced kept four copies of the General MIDI programs and they had all drifted.

## Changing the notation

The notation is used by several thousand files in this repository and by files
we cannot see. A change to it needs:

1. A spec that fails before the change and passes after.
2. `tapscript check docs examples academy` still clean.
3. A note in `CHANGELOG.md` under the right heading.

If existing notation would parse differently after your change, that is a
breaking change even when the new reading is better. Put it behind a setting,
default to the old behaviour, and say when the default will move.

## Adding a spec

New capabilities want a spec, not only a test — see [docs/specs.md](docs/specs.md).
The spec is what tells a user whether the thing works on *their* machine, and
what the build agent uses to check its own work.

## Tests

`unittest` from the standard library, so they run anywhere. pytest runs them too
if you prefer it.

Test what a caller can observe, not how it is implemented. `test_render.py`
parses the MIDI bytes back out and checks that every note is switched off;
that is the kind of test that survives a refactor and catches a real bug.

Three tests exist because they caught real bugs. Please do not delete them:

- `test_no_home_directory_is_hardcoded` — the previous version wrote everything
  into one contributor's home directory.
- `test_tokens_divide_the_bar` — the previous parser dropped notes past the
  sixteenth token in a bar.
- `test_tool_results_are_fed_back` — the agent loop once handed providers a
  reference to a list it was still appending to.

## Style

`ruff` with the settings in `pyproject.toml`; 108 columns.

Comments should say why, not what. A comment explaining a subtraction is noise;
a comment explaining why the subtraction is one greater than it looks is the
reason the next person does not "fix" it.

Docstrings on modules and public functions. Say what it does and what it will
not do.

## Documentation

If a change alters what a user types or sees, update `docs/`. The docs are
written for someone who has the problem in front of them, not for someone
admiring the design — keep the tone plain, skip the adjectives, and prefer a
worked example over a description of one.

## Reporting a bug

Include the output of:

```bash
tapscript doctor
tapscript --version
```

and, if it involves notation, the smallest file that shows the problem.
`tapscript info yourfile.tap --verbose` prints every diagnostic, which is often
the answer on its own.

## Reporting a security issue

Do not open a public issue. The web interface binds to loopback and refuses
cross-origin requests by default; if you have found a way around that, or a path
traversal, or a way to make the agent write outside its workspace, please report
it privately to the repository owner.
