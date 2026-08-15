# Specs

A spec is a short TOML file stating something the system is supposed to do and
naming the checks that prove it.

```bash
tapscript spec              # run them
tapscript spec --list       # what exists
tapscript spec --tag fast   # a subset
tapscript doctor --specs    # host report and specs together
```

```
  ok    core.notation      Notation parses, arranges and survives a round trip
  ok    core.providers     A model can be reached however the user has one
  ok    core.render        A clean checkout renders MIDI and audio with nothing installed
  ok    core.interfaces    Every interface starts
  ok    library.compat     Existing notation still compiles

  5 passed, 0 failed, 0 skipped
```

## Why they exist separately from the tests

The test suite is for people changing the code. Specs are for three readers at
once:

- **A user**, finding out which part of their install is not working, on their
  machine, with their optional dependencies.
- **The build agent**, which runs them after each change it makes. A change it
  cannot verify is a change it should not claim to have made.
- **A contributor**, who adds the spec for a capability before the capability.

They run anywhere, including from an installed package where the tests are not
present.

## Writing one

```toml
[spec]
id = "studio.midi-out"
title = "The studio synth receives MIDI"
why = """
This install exists to drive hardware. If the port is gone, everything else
working is beside the point.
"""
tags = ["integration"]

[[check]]
id = "port-present"
kind = "capability"
run = "midi_ports"

[[check]]
id = "smoke"
kind = "python"
run = "mypackage.checks:send_a_note"
optional = true
requires = "midi_ports"
```

Repository specs live in `specs/`. Ones the build agent writes while tailoring an
install go in `<workspace>/specs/`, and per-user ones in `<config-dir>/specs/`.
All three are picked up.

### Check kinds

| `kind` | `run` is | Passes when |
|---|---|---|
| `python` | `module:function` | the function returns true, or `(True, detail)` |
| `command` | a command line | it exits zero, and `expect` appears in the output if set |
| `capability` | a capability name | `tapscript doctor` reports it present |
| `file` | a path | the file exists |

`requires` names a capability that must be present for the check to mean
anything; without it the check is skipped. `optional = true` makes a skip count
as a pass, which is how a spec covering hardware you do not have stays green
instead of shouting at you.

A Python check returns `(ok, detail)`, must not need a network, and must not
write outside a temporary directory. The ones that ship are in
`tapscript/selfcheck.py` and are worth reading before writing your own.

## In CI

`tapscript spec` exits non-zero if any spec fails, so it works as a build step.
The repository's own CI runs it on every supported Python version and operating
system before the test suite, with nothing installed — which is what keeps the
"works with no dependencies" claim from quietly becoming false.
