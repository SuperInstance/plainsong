# Arrival-centric timing

A score says a note is on beat four. Where does that happen?

- at the player's hands, when they act
- at the instrument, when it actually makes a sound
- at somebody's ear, when the sound gets there

Those are three different clocks. On a large platform they are tens of
milliseconds apart, which is more than an ensemble's tolerance for being out of
time, and the gaps are not the same for everyone. TapScript takes the third one
as the one you write in: **a written time is the moment the sound is meant to
reach the listener the piece is written for**. Everything else is solved
backwards from it.

This is what a good ensemble already does without discussing it. The timpanist
starts the stroke before the downbeat so the sound lands on it. The organist
anticipates further, because the pipe takes time to speak. Players at opposite
ends of a platform each hear the other as late, and both correctly trust the
stick over their own ears.

Nothing in this page happens unless a piece declares a `[Stage]` block. Without
one, a file compiles to exactly the bytes it always did.

## The three delays

    arrival = emission + speech + propagation + p_center

**Speech** is the instrument taking time to sound after the player acts. A
woodblock is instant. A piano hammer takes 5 to 15ms to reach the string. A
bowed entry runs from 12ms hacked out to 80ms for a swell. A large organ pipe
has to fill before it speaks at all, which is 50 to 200ms.

**Propagation** is distance over the speed of sound: 343 m/s at 20 degrees, or
2.9ms a metre. Twenty metres across a big platform is 58ms — longer than a
thirty-second note at 120bpm.

**p-centre** is the perceptual attack time: the ear places a note slightly
*into* its attack, not at its physical onset. A sung note is heard later than
its onset; a snare essentially at it. It is a real, measured effect, and it is
why two instruments whose onsets line up can still sound out of time.

Turn the equation around and you get what the compiler solves:

    emission = written_time - speech - propagation - p_center + feel

**Feel is not part of the correction.** It is a musical decision — negative
pushes ahead of the beat, positive lays back — and it is meant to be *heard*, so
it survives into the arrival instead of cancelling out. The correction makes an
ensemble sound together; the feel makes it sound like somebody. They are
separate in the notation and separate in the code.

## The `[Stage]` block

```
**TRACK: Processional**
[MetaData]
key: Dm | tempo: 96 | time: 4/4

[Stage]
listener: conductor
temperature: 20
@timpani:  pos 4,-6  | speech: percussion
@violin1:  pos -3,1  | speech: bowed | feel: -6ms
@horn:     pos 2,-4
@organ:    pos 0,-12 | speech: organ-large

[A] (4 bars)
@timpani  | d2 . . . | . . . . | d2 . . . | a1 . . . |
@violin1  | d5 e5 f5 g5 | a5 . . . | f5 e5 d5 c5 | d5 . . . |
@horn     | d4 . . . | f4 . . . | a4 . . . | d4 . . . |
@organ    | d3-a3-d4 . . . | . . . . | bb2-f3-bb3 . . . | a2-e3-a3 . . . |
```

`[Stage]` is a special section like `[MetaData]`. It is read, not played, and it
runs until the next header.

### Settings

| Line | Means |
|---|---|
| `listener: conductor` | whose ears the written times belong to |
| `temperature: 20` | degrees Celsius; sets the speed of sound |
| `compensate: off` | stop correcting, and hear what that does |
| `audience: 0,14` | move a named listener, in metres |

### Voices

`@name: pos 4,-6 | speech: brass | feel: -6ms`

- `pos x,y` in metres. The origin is the podium, **+y points towards the
  audience** and **+x is to the conductor's right**. So the first violins sit
  around `-3,1`, the timpani around `4,-6` and the organ well behind everyone at
  `0,-12`. Only the distances between things matter, so pacing the platform out
  roughly is enough. A voice with no position is treated as standing at the
  podium.
- `speech` names a profile (below) or gives a time: `speech: 40ms`. Leave it out
  and one is chosen from the voice's General MIDI program, so `@trumpet` and
  `@organ` are already sensible.
- `feel` is the musical deviation, in milliseconds: `feel: -6ms` sits ahead of
  the beat.
- `p-center: 20ms` overrides the perceptual attack time if you know better.

The same three can be written at the end of a player's note row, next to
`vel:` and `inst:`, when a whole block would be overkill:

```
@cello | c3 . g3 . | e3 . c3 . | pos: -2,3 | speech: bowed |
```

## Speech profiles

| Profile | Speech | p-centre | |
|---|---|---|---|
| `percussion` | 0 ms | 1 ms | stick on head: the reference everything else is late against |
| `mallet` | 2 ms | 4 ms | vibraphone, marimba, glockenspiel |
| `plucked` | 3 ms | 4 ms | guitar, harp, harpsichord, pizzicato |
| `electric` | 4 ms | 5 ms | electronic sources speak when told to |
| `plucked-bass` | 6 ms | 9 ms | low strings need a cycle or two before the pitch is there |
| `piano` | 8 ms | 6 ms | hammer travel after the key goes down |
| `bowed-short` | 12 ms | 8 ms | spiccato, martelé, a hard attack |
| `woodwind-flue` | 14 ms | 10 ms | flute and recorder |
| `woodwind` | 18 ms | 12 ms | oboe, clarinet, bassoon, saxophone |
| `brass` | 25 ms | 15 ms | tongued; a soft entry runs to 40ms |
| `reed-organ` | 35 ms | 20 ms | harmonium, accordion, harmonica |
| `bowed` | 45 ms | 25 ms | an ordinary détaché bow |
| `brass-soft` | 45 ms | 22 ms | a quiet horn entry, no tongue |
| `organ-small` | 45 ms | 25 ms | a chamber organ |
| `voice` | 45 ms | 30 ms | consonant to vowel |
| `bowed-section` | 60 ms | 32 ms | desks do not start together |
| `pad` | 80 ms | 45 ms | a synthesiser pad is as slow as its patch |
| `organ` | 90 ms | 40 ms | a church organ on ordinary stops |
| `organ-large` | 140 ms | 60 ms | large flue pipes have to fill before they speak |

Common spellings work too: `timpani`, `strings`, `arco`, `choir`, `flute`.

**These numbers are a model, not measurements.** They are the right order of
magnitude and they rank instruments correctly against each other, which is what
the solver needs. Your instrument in your room will differ, and a player can
change their own speech time by a factor of two with a different articulation.
When you know better, say so: `speech: 62ms`.

## Reference frames

`tapscript ensemble` and `tapscript compile` both take `--frame`:

| Frame | Means |
|---|---|
| `conductor` | at the podium |
| `audience` | the audience reference point, twelve metres out unless you move it |
| `player:violin1` | what that one player hears at their desk |
| `score` | no compensation at all: the naive behaviour, and the control |

The same performance has a different arrival pattern at each of them, and being
able to say so is the point of the whole feature:

```
$ tapscript ensemble processional.tap

Processional  --  4 voices at 96 bpm
written for conductor, listening at conductor, 20 C, sound at 343.21 m/s

what each player has to do, solved against conductor
  voice    pos    speech       distance  onset   travel  p-centre  act
  timpani  4,-6   percussion   7.2 m     0 ms    21 ms   1 ms      -22 ms
  horn     2,-4   brass        4.5 m     25 ms   13 ms   15 ms     -53 ms
  violin1  -3,1   bowed        3.2 m     45 ms   9 ms    25 ms     -85 ms
  organ    0,-12  organ-large  12.0 m    140 ms  35 ms   60 ms     -235 ms

what conductor hears, against the written beat
  spread 6 ms
  violin1    6 ms early

the same performance heard elsewhere
  audience                 spread 17 ms  (latest: organ 35 ms late)
  player:horn              spread 18 ms  (latest: violin1 5 ms late)
  player:organ             spread 59 ms  (latest: violin1 24 ms late)
  player:timpani           spread 35 ms  (latest: violin1 14 ms late)
  player:violin1           spread 23 ms  (latest: timpani 8 ms late)
```

Read the top block as instructions: the organist starts 235ms before the beat,
the timpanist 22ms, and everything lands on the podium within a millisecond.
The 6ms at the bottom is the violins' `feel: -6ms`, which is supposed to be
there.

Now stand behind the drums:

```
$ tapscript ensemble processional.tap --frame player:timpani

what player:timpani hears, against the written beat
  spread 35 ms
  timpani    21 ms early
  organ      14 ms early
  violin1    14 ms late
  horn       5 ms early

and against timpani's own sound, which is what that player judges by
  violin1    35 ms late
  horn       16 ms late
  organ      7 ms late
```

The timpanist genuinely hears the first violins a thirty-second note behind
their own stroke, and they are both right. That is the argument for watching
the stick.

`--json` works the same as everywhere else.

## MIDI carries emission, audio carries arrival

This trips people up, so it is worth being blunt about.

**A MIDI file gets emission times.** A MIDI file is an instruction to a player
or a sequencer, and what an instruction has to say is *when to act*. Open the
file above in a sequencer and the organ part sits a third of a beat ahead of the
timpani part, which is exactly what the organist has to do.

**An audio render gets arrival times.** A render is a recording of what one
listener hears, so a note goes where its sound reaches them. In the same piece
the organ and the timpani land on the same sample.

The two are the same file, seen from the two ends of the equation. On a piece
with no `[Stage]` block they are identical, because there is nothing between the
hands and the ear to model.

If the earliest player has to act before the piece starts — the organ, here,
needs 235ms of head start on bar one — the whole thing is pushed later by that
much, emissions and arrivals alike. Nothing inside the music moves; it just
begins a fraction of a beat in.

## Hearing the difference

Same file, two renders:

```
tapscript compile processional.tap --audio tight.wav
tapscript compile processional.tap --audio smeared.wav --no-compensate
```

`tight.wav` is what the podium hears when everybody has corrected for
themselves. `smeared.wav` is what it hears when nobody has: the organ lands
235ms late, the violins 73ms, the horn 53ms, the timpani 22ms, and a downbeat
that should be one event spreads over about a fifth of a second. You do not have
to squint at a waveform to hear it.

`compensate: off` in the `[Stage]` block does the same thing permanently.
`--frame score` is different again: it ignores the stage entirely and renders
what the compiler did before any of this existed.

## Conducting

A gesture is not learned per player. One thing goes out and the whole ensemble
reacts to it at once. So a gesture is defined on the **arrival** timeline — on
what the room is meant to hear — and each player's emission falls out of it:

```python
from tapscript.notation import arrange, parse
from tapscript.perform.conduct import Gesture, conduct

written = arrange(parse(text))
held_back = conduct(written, [Gesture(kind="rubato", amount=-0.25, span=8.0, shape="arch")])
```

| Kind | Does |
|---|---|
| `rubato` | bends the timeline: `amount=-0.25` is a quarter slower at the peak |
| `swell` | scales velocities |
| `lean` | scales note lengths without moving anything |

Shapes are `arch` (in and out again), `ramp`, `fall` and `step`, over `span`
beats from `start`.

The arrivals stay together through the gesture — that is the definition of it
being one gesture. The players' hands do not. Each player's lead is a fixed
number of milliseconds, and a beat is not: shorten the beats and that lead
becomes a bigger slice of one. Speeding up makes the organist anticipate by
much more of a beat, and the timpanist by only a little, because the organist's
lead was ten times bigger to begin with. Nobody wrote that rule down; it comes
out of solving in seconds and writing in beats.

## What it does not do

- The listener is a point, not a head. There is no stereo image, no head
  shadow, no interaural difference. Audio is mono anyway.
- No reflections, no reverberation, no absorption. Direct sound only.
- Speech times do not change with dynamic, register or articulation within a
  voice, though in a real player they do. One profile covers the whole part.
- The compensation is applied per voice, not per note. A player who has to
  anticipate more on a soft entry than a loud one is beyond this model.
- Nothing is inferred. A piece with no `[Stage]` block is left alone, forever.
