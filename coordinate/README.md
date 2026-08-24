# coordinate

**Scheduling backwards from when an effect should land.**

One file, standard library only, MIT. Copy it next to whatever needs it.

Most scheduling says when to *act*. This says when the effect should *arrive*,
and solves backwards for when each participant has to move:

```
act    = intent·scale + shift − alignment·(actuation + lead + reference_delay + bias)
effect = act + actuation + lead + bias + observed_delay
```

## Staged for extraction

This directory lives inside `SuperInstance/plainsong` for now because that is
where the idea was built and tested, and where the proof that the extraction is
inert can actually run. **It is destined for its own repository** and is not
part of the `plainsong` wheel — nothing under `plainsong/` imports it yet.

## Why the two delay terms must not be collapsed

`reference_delay` is the transport delay the plan was **compensated for**.
`observed_delay` is the delay **actually experienced** by whoever is watching
now.

When they are equal the correction cancels exactly and the effect lands where
it was written. When they differ it does not, and the residue is real. It is
why `spread` — the gap between the earliest and latest effect — is zero at the
point you tuned for and non-zero everywhere else, and why a coordinated group
needs a conductor rather than mutual listening.

Collapse those two into one variable and the model becomes symmetric,
self-consistent, and a description of nothing.

## `intent` survives compensation; `lead` does not

Swing is meant to be heard. A deliberate lead into a turn is meant to happen.
So `intent` moves the effect and is *not* solved away, while `lead` moves only
the action and *is* compensated. They look identical in the arithmetic and are
opposites in meaning, which is exactly why they are separate fields.

## The same three quantities, three domains

| | Orchestra | Boat helm | Camera / avatar cue |
|---|---|---|---|
| `actuation` | the instrument speaking | valve lag + hydraulic slew | rig acceleration, render lead |
| `bias` | habitual drag | linkage backlash | fixed pipeline stage |
| `reference_delay` | distance to the podium | conditions the autopilot was tuned in | the timing the sequence was cut against |
| `observed_delay` | distance to this listener | loaded, in current, in a seaway | this machine, this frame rate |
| `alignment` | ensemble discipline | trust in calibration right now | degraded mode |
| `intent` | swing, rubato | deliberate lead into a turn | an intentionally late reveal |
| `spread` | smear of a chord | **how far from tuning conditions you are** | cue drift across channels |

That middle column is the one worth dwelling on. An autopilot tuned in flat
water at one speed is running with a `reference_delay` that no longer matches
its `observed_delay` once the boat is loaded or in a seaway. `spread` turns
that mismatch into a number you can put on a screen.

## Proving a change is safe

`test_equivalence.py` drives this and `plainsong.perform.solve` with the same
inputs and requires **bit-identical** results across ~4,000 combinations —
`assertEqual`, not `assertAlmostEqual`, because a reordered sum is a different
implementation even when it is close, and close is what accumulates.

That is not a formality. Reordering one addition in `solve_one` — same terms,
same value mathematically — fails 1,803 of those cases.

```bash
cd coordinate && python3 test_equivalence.py
```

## What is deliberately not here

- **No I/O, no configuration, no logging.** It computes offsets in seconds.
- **No medium baked in.** `delay_for(distance, speed)` defaults to sound in air
  and takes any speed. Where there is no distance at all, set the delays
  directly and never call it.
- **No opinion about what a participant is.** A player, a steering pump, a
  camera rig, an agent waiting on a message.
