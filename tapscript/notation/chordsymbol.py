"""Chord symbols, read as a grammar rather than looked up in a table.

The engine this replaced held a dictionary of about thirty spellings. Every
symbol anyone might write had to appear in it, so `C7b9` worked and `C7b9#11`
did not -- not because anybody disagreed about what the second one means, but
because nobody had typed that particular combination into the table. The 6,308
charts in this repository contain 102 chords it could not read, and none of them
are exotic: `G7alt`, `EbMaj7`, and `C7M`, which is simply how Brazil writes a
major seventh.

So this module measures nothing point by point. A symbol is parsed into a small
number of decisions -- a root, a core quality, how far up to stack, and a list
of modifications -- and the notes are *derived* from those. Compound spellings
come free, because nothing enumerates them.

    C7b9#11   ->  core=dom, stack to 7, alter 9 flat, alter 11 sharp
    F13#11    ->  core=dom, stack to 13, alter 11 sharp
    Bbmaj7#5  ->  core=maj, stack to 7, alter 5 sharp

The representation is a **degree map**: scale degree (1, 3, 5, 7, 9, 11, 13)
onto its offset in semitones from the root. Degrees are the fixed points; the
offsets are what bends. Writing it this way is what makes the rules below
expressible at all, because every one of them is a statement about a degree
rather than about a chord.

Three rules do the bending, and they are the whole reason a table cannot do
this job:

**A named alteration displaces its natural form.** `C7b9` has a Db and no D.
The alteration is not an extra note, it is the same degree moved. This falls
out of the degree map for free -- writing offset 13 at degree 9 overwrites
offset 14 -- which is the main argument for the representation.

**An extension implies the odd degrees below it, except the eleventh on a
chord with a major third.** `C13` means 7, 9 and 13, not 7, 9, 11 and 13,
because a natural 11 sits a semitone above the major 3rd and fights it. Ask for
`C13#11` and you get it, because a raised 11 is a whole tone above the 3rd and
does not fight. This exception is the single most-cited rule in chord-scale
teaching and the one a naive stacker always gets wrong.

**Removing a note removes what depended on it.** `sus4` takes out the third,
which means the eleventh-avoidance rule no longer applies -- the 11 and the 4
are the same degree, and with no third to clash with there is nothing to avoid.
`C9sus4` is therefore a perfectly ordinary chord and needs no special case.

What this module deliberately does *not* do is choose a voicing. It answers
"which degrees sound", not "at which octaves". Register, spacing and omission
are a separate decision with a separate set of rules, because they depend on
the instrument and the texture rather than on the symbol. See `voicing.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "ChordSymbolError",
    "ParsedChord",
    "parse_symbol",
    "CORES",
    "DEGREE_SEMITONES",
]


class ChordSymbolError(ValueError):
    """A chord symbol that cannot be read."""


# --- the fixed points ------------------------------------------------------
#
# Degrees, and where each one sits when nothing has bent it. These are diatonic
# major-scale distances: the 9th is a major second up an octave, the 11th a
# perfect fourth, the 13th a major sixth. Everything else in this file is
# expressed as a departure from this row.

DEGREE_SEMITONES: dict[int, int] = {
    1: 0,
    2: 2,    # only ever reached through sus2 or add2; folded onto 9 elsewhere
    3: 4,
    4: 5,    # likewise sus4 / add4, folded onto 11
    5: 7,
    6: 9,    # a sixth is a sixth, not a thirteenth: it sits below the seventh
    7: 11,
    9: 14,
    11: 17,
    13: 21,
}

# The odd degrees, in the order an extension walks up through them.
STACK_ORDER: tuple[int, ...] = (7, 9, 11, 13)


@dataclass(frozen=True)
class Core:
    """A chord's skeleton, before anything is stacked or bent.

    `third`, `fifth` and `seventh` are semitone offsets, or None for a degree
    this core does not have. `seventh` is what the core uses when a symbol asks
    for a seventh or higher without saying which kind -- a bare `C9` wants a
    minor seventh because its core is dominant, while `Cmaj9` wants a major one.
    """

    name: str
    third: int | None
    fifth: int | None
    seventh: int
    #: True when the core carries a major third, which is what makes a natural
    #: 11th an avoid note. Minor and sus chords set this False and are therefore
    #: allowed their natural 11.
    major_third: bool = False
    #: Degrees this core adds outright, beyond third and fifth.
    fixed: tuple[tuple[int, int], ...] = ()


# --- the cores -------------------------------------------------------------
#
# Eight skeletons. Everything a symbol can say is one of these plus a stack
# height plus a list of bends. If you are adding a chord family, this is very
# likely the only table you need to touch -- add a core here and a spelling in
# CORE_ALIASES below, and every extension and alteration works on it already.

CORES: dict[str, Core] = {
    # Major triad. Its seventh is major, which is why `Cmaj9` gets a B natural.
    "maj": Core("maj", third=4, fifth=7, seventh=11, major_third=True),
    # Dominant. Identical skeleton to major; the difference is entirely which
    # seventh it reaches for, and that difference is the whole of tonal harmony.
    "dom": Core("dom", third=4, fifth=7, seventh=10, major_third=True),
    "min": Core("min", third=3, fifth=7, seventh=10),
    # Minor with a major seventh. A separate core rather than a modifier,
    # because `CmMaj7` names it directly and the stack has to know.
    "minmaj": Core("minmaj", third=3, fifth=7, seventh=11),
    # Half-diminished: a minor seventh over a diminished triad. Written m7b5
    # about as often as it is written with the slashed circle.
    "halfdim": Core("halfdim", third=3, fifth=6, seventh=10),
    # Fully diminished. Its seventh is diminished -- nine semitones, enharmonic
    # with a sixth, which is why the chord is symmetric and why `Cdim7`,
    # `Ebdim7`, `Gbdim7` and `Adim7` are four spellings of one sound.
    "dim": Core("dim", third=3, fifth=6, seventh=9),
    "aug": Core("aug", third=4, fifth=8, seventh=10, major_third=True),
    # Suspensions replace the third rather than colouring it. No third means no
    # 11th-avoidance, which is why `C9sus4` needs no special handling.
    "sus4": Core("sus4", third=None, fifth=7, seventh=10, fixed=((11, 5),)),
    "sus2": Core("sus2", third=None, fifth=7, seventh=10, fixed=((9, 2),)),
    # Root and fifth. The "power chord", and also how a chart says "no quality
    # implied, play the shell".
    "power": Core("power", third=None, fifth=7, seventh=10),
}


# --- spellings -------------------------------------------------------------
#
# What people actually write, mapped onto a core. Order does not matter here;
# the scanner tries longest-first, so `maj` cannot be eaten by `ma`.
#
# Adding a spelling is a one-line change and needs no other edit. Adding one
# that starts with a digit (Brazil's `7M`) is handled by the scanner, not here.

CORE_ALIASES: dict[str, str] = {
    # major
    "maj": "maj", "major": "maj", "ma": "maj", "mj": "maj", "M": "maj",
    "Δ": "maj", "∆": "maj", "^": "maj",
    # minor. `-` is the Real Book's spelling and is very common.
    "m": "min", "min": "min", "mi": "min", "minor": "min", "-": "min",
    "moll": "min",
    # diminished
    "dim": "dim", "o": "dim", "°": "dim", "º": "dim",
    # half-diminished
    "ø": "halfdim", "Ø": "halfdim", "halfdim": "halfdim", "h": "halfdim",
    # augmented
    "aug": "aug", "+": "aug",
    # suspended
    "sus": "sus4", "sus4": "sus4", "sus2": "sus2",
    # no third
    "5": "power", "no3": "power", "omit3": "power",
}

#: Longest first, so a scan cannot stop early on a prefix.
_CORE_SCAN: tuple[tuple[str, str], ...] = tuple(
    sorted(CORE_ALIASES.items(), key=lambda pair: -len(pair[0]))
)

#: Spellings that mean the seventh chord even when no 7 is written.
#:
#: `GbΔ` is a major seventh and `Cø` is half-diminished seventh -- both are
#: written bare constantly, and both mean the four-note chord. This is a
#: property of the *spelling*, not of the core: `CM` and `Cmaj` are triads
#: while `CΔ` is not, so it cannot live in CORES.
SEVENTH_IMPLIED: frozenset[str] = frozenset({"Δ", "∆", "^", "ø", "Ø", "halfdim"})

# What `alt` means. A dominant with every degree that can be altered, altered,
# and -- the part a table always misses -- the natural fifth and natural ninth
# *removed*. `C7alt` is not a dominant with things added; it is a dominant with
# its middle replaced. The scale is the seventh mode of Db melodic minor, which
# contains no G and no D.
#
# Both the b9 and the #9 are named. A player picks one, or voices both; the
# symbol licenses either, and refusing to choose here is the honest reading.
ALT_DEGREES: tuple[tuple[int, int], ...] = ((9, 13), (9, 15), (11, 18), (13, 20))
ALT_REMOVES: tuple[int, ...] = (5,)


# --- accidentals -----------------------------------------------------------

_UNICODE = {
    "♭": "b", "♯": "#", "𝄫": "bb", "𝄪": "##",
    "−": "-", "–": "-", "—": "-",   # minus signs that are not hyphens
    "＃": "#",
}

_ACCIDENTAL_SHIFT = {"b": -1, "#": 1}


def _normalise(text: str) -> str:
    """Fold the many ways of typing the same mark onto one way.

    The two triangles are worth a word. `Δ` is U+0394 GREEK CAPITAL LETTER
    DELTA and `∆` is U+2206 INCREMENT. They are indistinguishable on screen,
    both are in real chord charts, and a parser that knows only one of them
    fails on half its input for a reason nobody can see by looking.
    """
    for source, target in _UNICODE.items():
        text = text.replace(source, target)
    return text


# --- the parse -------------------------------------------------------------

_ROOT_RE = re.compile(r"^([A-Ga-g])((?:[#b])*)")
_DEGREE_RE = re.compile(r"^(\d{1,2})")


@dataclass
class ParsedChord:
    """A chord symbol, read.

    `degrees` maps scale degree onto semitones above the root. It is the whole
    answer: `intervals()` is just its sorted values. Nothing downstream needs
    to know which alias was typed.
    """

    root_pc: int
    core: str
    degrees: dict[int, int] = field(default_factory=dict)
    bass_pc: int | None = None
    text: str = ""
    #: Everything after the root and before any slash bass, exactly as written.
    #: The transposer re-emits this untouched, which is what lets a symbol the
    #: quality names cannot express survive being moved to another key.
    suffix: str = ""
    #: Degrees the symbol licensed but did not require -- the second of `alt`'s
    #: two ninths, for instance. A voicer may use these; a plain stack ignores
    #: them, so a chord never gets both a b9 and a #9 unless something asks.
    optional: dict[int, tuple[int, ...]] = field(default_factory=dict)

    def intervals(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.degrees.values())))

    def pitch_classes(self) -> tuple[int, ...]:
        return tuple(sorted({(self.root_pc + offset) % 12 for offset in self.degrees.values()}))

    def has(self, degree: int) -> bool:
        return degree in self.degrees


def _scan_root(text: str) -> tuple[int, str]:
    from .theory import LETTER_PC

    match = _ROOT_RE.match(text)
    if not match:
        raise ChordSymbolError(f"no chord root in {text!r}")
    letter, accidentals = match.groups()
    shift = sum(_ACCIDENTAL_SHIFT[character] for character in accidentals)
    return (LETTER_PC[letter.upper()] + shift) % 12, text[match.end():]


def _split_bass(text: str) -> tuple[str, str | None]:
    """Separate a slash bass, without mistaking `6/9` for one.

    `C6/9` is a single quality -- a sixth chord with a ninth -- and the slash
    is punctuation, not an inversion. The test is simply whether what follows
    the slash names a note.
    """
    if "/" not in text:
        return text, None
    head, _, tail = text.rpartition("/")
    if _ROOT_RE.match(tail.strip()):
        return head, tail.strip()
    return head + tail, None


def parse_symbol(token: str) -> ParsedChord:
    """Read a chord symbol into a degree map.

    Raises :class:`ChordSymbolError` when the symbol cannot be read. Being
    refused is the point: an unreadable token used to become a rest, so a
    mistyped chord compiled to a bar of nothing and reported success.
    """
    original = token.strip()
    if not original:
        raise ChordSymbolError("empty chord")

    text = _normalise(original)
    text, bass_text = _split_bass(text)
    root_pc, suffix = _scan_root(text)
    bass_pc = _scan_root(bass_text)[0] if bass_text else None
    # Taken before the brackets and spaces come out, so a transpose re-emits
    # `C7(b13)` as `D7(b13)` rather than quietly reformatting it.
    written_suffix = _written_suffix(original)

    # Brackets carry no meaning of their own -- `C7(b9)` and `C7b9` are the
    # same chord -- so they come out before the scan rather than being tracked.
    suffix = suffix.replace("(", "").replace(")", "").replace(" ", "").replace(",", "")

    core_name, stack, mods, alt = _scan_suffix(suffix, original)
    degrees = _build(core_name, stack, mods, alt)
    optional: dict[int, tuple[int, ...]] = {}
    if alt:
        # The ninth that was not chosen stays available without sounding.
        optional[9] = (13, 15)

    return ParsedChord(
        root_pc=root_pc,
        core=core_name,
        degrees=degrees,
        bass_pc=bass_pc,
        text=original,
        suffix=written_suffix,
        optional=optional,
    )


def _written_suffix(token: str) -> str:
    """Everything after the root, as typed, with any slash bass removed.

    Splitting on the last slash is not enough: `C6/9` has a slash and no bass,
    and taking the head of that split loses the ninth. The same test decides it
    here as decides it during parsing -- does what follows the slash name a
    note -- so the two cannot drift apart.
    """
    text = token.strip()
    head, _bass = _split_bass(_normalise(text))
    match = _ROOT_RE.match(head)
    return head[match.end():] if match else head


# A modification: what to do, to which degree, and by how much.
#   ("alter", 9, -1)  -> b9, displacing the natural 9
#   ("add",  11, +1)  -> add a #11 without implying anything below it
#   ("omit",  5,  0)  -> take the fifth out
Modification = tuple[str, int, int]


def _scan_suffix(suffix: str, original: str) -> tuple[str, int, list[Modification], bool]:
    """Walk the suffix left to right, one construct at a time.

    Left to right rather than one large regular expression, because the
    constructs genuinely are a sequence and a regex over all of them stops
    being readable long before it stops being wrong.
    """
    core_name: str | None = None
    stack = 0
    mods: list[Modification] = []
    alt = False
    seventh_kind: str | None = None
    rest = suffix

    while rest:
        # `alt`: a whole vocabulary in three letters.
        if rest[:3].lower() == "alt":
            alt = True
            rest = rest[3:]
            if rest[:4].lower() == "ered":
                rest = rest[4:]
            continue

        # add / omit / no
        matched = False
        for word, operation in (("add", "add"), ("omit", "omit"), ("no", "omit")):
            if rest[: len(word)].lower() == word:
                tail = rest[len(word):]
                shift, tail = _leading_accidental(tail)
                degree_match = _DEGREE_RE.match(tail)
                if degree_match:
                    degree = int(degree_match.group(1))
                    mods.append((operation, _fold(degree), shift))
                    rest = tail[degree_match.end():]
                    matched = True
                    break
        if matched:
            continue

        # A bare accidental in front of a number is an alteration: b9, #11, b13.
        #
        # `-5` and `+5` are the older spellings of `b5` and `#5`. But `-` is
        # also how the Real Book writes minor, and `C-7`, `C-9`, `C-11` and
        # `C-13` are all minor chords -- never flattened degrees. So a minus
        # reads as an accidental only once a quality has already been named.
        # Reading it the other way turned 22 minor chords in this repository
        # into dominants: a chart that sounds wrong without looking wrong.
        #
        # An earlier version also excluded a 7 explicitly. Removing that clause
        # changed no behaviour and failed no test, because the check below
        # already covers every real spelling -- so it went, rather than sit
        # there looking load-bearing and tempting someone to trade the real
        # guard for it.
        signed = rest[0] in "-+" and rest[1:2].isdigit() and core_name is not None
        if rest[0] in "b#" or signed:
            shift = {"b": -1, "#": 1, "-": -1, "+": 1}[rest[0]]
            degree_match = _DEGREE_RE.match(rest[1:])
            if degree_match:
                degree = int(degree_match.group(1))
                mods.append(("alter", _fold(degree), shift))
                rest = rest[1 + degree_match.end():]
                continue

        # A number: either how far to stack, or a sixth, or -- when it is
        # immediately followed by a major-seventh marker -- Brazil's `7M`.
        #
        # `69` is scanned before the general number rule, because a greedy
        # two-digit match reads it as the sixty-ninth degree. `C6/9` arrives
        # here as `69`, the slash having been dropped as punctuation.
        if rest[:2] == "69":
            mods.append(("add", 6, 0))
            mods.append(("add", 9, 0))
            rest = rest[2:]
            continue
        degree_match = _DEGREE_RE.match(rest)
        if degree_match:
            value = int(degree_match.group(1))
            tail = rest[degree_match.end():]
            if value == 5 and core_name is None and not tail:
                # A bare `C5`: root and fifth, no third. Anywhere else a 5 is
                # either a stack height nobody writes or part of `b5`/`#5`,
                # both of which were handled above.
                core_name = "power"
                rest = tail
                continue
            if value == 7 and tail[:1] in ("M", "m"):
                # `C7M` is a major seventh (sétima maior) and `C7m` a minor one.
                # Only after a 7 -- `Cm7` must never be read this way, which is
                # why this test lives here and not in the alias table.
                seventh_kind = "maj" if tail[0] == "M" else "min"
                stack = max(stack, 7)
                rest = tail[1:]
                continue
            if value == 6:
                # A sixth sits below the seventh and does not imply one.
                mods.append(("add", 6, 0))
                rest = tail
                # `6/9` and `69` both mean the ninth comes too.
                if tail[:1] == "9":
                    mods.append(("add", 9, 0))
                    rest = tail[1:]
                continue
            if value in (2, 4) and core_name is None:
                # A bare `C2` or `C4`. Both readings are in the wild -- sus and
                # add -- and no authority settles it. Taken as an add, because
                # that keeps the third, and losing a third silently is the
                # worse failure. `Csus2` and `Csus4` say the other thing.
                mods.append(("add", _fold(value), 0))
                rest = tail
                continue
            if value in (5, 7, 9, 11, 13):
                stack = max(stack, value)
                rest = tail
                continue
            raise ChordSymbolError(f"unreadable degree {value} in {original!r}")

        # A core spelling.
        for alias, name in _CORE_SCAN:
            if rest[: len(alias)] == alias or (
                len(alias) > 1 and rest[: len(alias)].lower() == alias.lower()
            ):
                # `M` and `m` differ only by case and mean opposite things, so
                # single-character aliases are matched case-sensitively and
                # longer words are not -- which is what lets `Maj7` through
                # while keeping `CM7` a major seventh and `Cm7` a minor one.
                if core_name is None:
                    core_name = name
                elif core_name == "min" and name == "maj":
                    core_name = "minmaj"       # CmMaj7, C-Δ7
                elif core_name == "maj" and name == "min":
                    core_name = "minmaj"
                elif name in ("sus4", "sus2"):
                    mods.append(("omit", 3, 0))
                    mods.append(("add", 11 if name == "sus4" else 9, 0))
                else:
                    core_name = name
                if alias in SEVENTH_IMPLIED:
                    stack = max(stack, 7)
                rest = rest[len(alias):]
                break
        else:
            raise ChordSymbolError(f"unreadable chord quality {suffix!r} in {original!r}")

    resolved = _resolve_core(core_name, stack, seventh_kind, alt)
    return resolved, stack, mods, alt


def _leading_accidental(text: str) -> tuple[int, str]:
    if text[:1] in ("b", "#"):
        return _ACCIDENTAL_SHIFT[text[0]], text[1:]
    return 0, text


def _fold(degree: int) -> int:
    """A 2 is a 9 and a 4 is an 11, once they are above the third."""
    return {2: 9, 4: 11}.get(degree, degree)


def _resolve_core(core_name: str | None, stack: int, seventh_kind: str | None, alt: bool) -> str:
    """Decide which skeleton a symbol meant, given what it said and did not say.

    The interesting case is the bare number. `C7` names no quality at all, and
    it means a dominant -- the one place in this notation where saying nothing
    means something specific. `Cmaj7` and `C7M` say otherwise explicitly.
    """
    if core_name is None:
        # `C7M` names its seventh and nothing else, so the seventh decides.
        # This test has to come before the bare-number one below, or Brazil's
        # major seventh reads as a dominant -- which was the single largest
        # group of unreadable chords in the corpus this replaced.
        if seventh_kind == "maj":
            return "maj"
        if alt or stack >= 7 or seventh_kind == "min":
            return "dom"
        return "maj"
    if core_name == "maj" and seventh_kind == "min":
        return "dom"
    if core_name == "min" and seventh_kind == "maj":
        return "minmaj"
    if core_name == "maj" and stack >= 7 and seventh_kind is None:
        return "maj"
    if core_name in ("dim", "halfdim", "aug", "sus4", "sus2", "power", "min", "minmaj"):
        # `Caug7` and `C+7` want a minor seventh; `CaugMaj7` is spelled out.
        return core_name
    if seventh_kind == "maj":
        return "maj"
    if seventh_kind == "min":
        return "dom"
    return core_name


def _build(core_name: str, stack: int, mods: list[Modification], alt: bool) -> dict[int, int]:
    """Turn the decisions into a degree map. This is where the rules bend."""
    core = CORES[core_name]
    degrees: dict[int, int] = {1: 0}
    if core.third is not None:
        degrees[3] = core.third
    if core.fifth is not None:
        degrees[5] = core.fifth
    for degree, offset in core.fixed:
        degrees[degree] = offset

    if alt:
        stack = max(stack, 7)
    if core.name in ("halfdim", "dim") and stack == 0:
        # The slashed circle is written for the four-note chord far more often
        # than for the triad -- `Cø` means `Cø7` to anyone reading a chart.
        # A plain `Cdim` does mean the triad, so only half-diminished is
        # promoted here; `dim` is listed for the shared branch below.
        stack = 7 if core.name == "halfdim" else stack

    # Stack the odd degrees up to the requested height.
    if stack >= 7:
        degrees[7] = core.seventh
        for degree in STACK_ORDER[1:]:
            if degree > stack:
                break
            if degree == 11 and degree < stack and core.major_third and 3 in degrees:
                # The rule that a table cannot express. A natural 11 is a
                # semitone above a major third and fights it, so a symbol that
                # merely stacks *past* it does not get one -- `C13` is 7, 9, 13.
                #
                # `degree < stack` is what confines this to the implication.
                # When 11 is the height actually asked for, `C11`, the player
                # is naming the eleventh on purpose and gets it; convention
                # then drops the third instead, which is handled below.
                continue
            degrees[degree] = DEGREE_SEMITONES[degree]
        if stack == 11 and core.major_third and 3 in degrees:
            # `C11` in the wild is C-G-Bb-D-F: the third goes, not the
            # eleventh. It is the same resolution as the rule above -- the two
            # notes cannot both stay -- reached from the other side.
            degrees.pop(3, None)

    if alt:
        for degree in ALT_REMOVES:
            degrees.pop(degree, None)
        degrees.pop(9, None)
        # One ninth sounds; `optional` carries the other.
        degrees[9] = ALT_DEGREES[0][1]
        degrees[11] = 18
        degrees[13] = 20

    for operation, degree, shift in mods:
        if operation == "omit":
            degrees.pop(degree, None)
        elif operation == "add":
            degrees[degree] = DEGREE_SEMITONES[degree] + shift
        elif operation == "alter":
            if degree in (5, 3) or degree in degrees:
                # Altering a degree that is present moves it. Altering one that
                # is not present -- `C7b9` on a chord stacked only to 7 --
                # introduces it, because that is plainly what was meant.
                degrees[degree] = DEGREE_SEMITONES[degree] + shift
            else:
                degrees[degree] = DEGREE_SEMITONES[degree] + shift
                if degree >= 9 and 7 not in degrees:
                    degrees[7] = CORES[core_name].seventh

    return degrees
