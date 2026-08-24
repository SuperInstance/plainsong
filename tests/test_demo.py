"""The browser demo is a second implementation, so it can drift.

`docs/demo/index.html` carries its own parser, arranger and MIDI writer in
JavaScript, because the demo has to run with nothing installed. That is a
deliberate exception to "one of everything", and the thing it risks is exactly
what the rule exists to prevent: the page quietly disagreeing with the compiler
it advertises.

CI has no JavaScript runtime, so this cannot run the page. What it can do is
hold the page's own claims against the reference implementation. The page states
the note count it produces for each preset; these tests compile the same
notation with the real compiler and require the same answer. A change to the
arranger that moves a count fails here, which is the reminder to re-check the
demo rather than let it rot.
"""

from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path

from plainsong.notation import arrange, chordsymbol, parse
from plainsong.notation.arrange import ArrangeOptions
from plainsong.notation.theory import LETTER_PC

PAGE = Path(__file__).resolve().parent.parent / "docs" / "demo" / "index.html"


def _presets() -> dict[str, str]:
    """The notation the page ships, read out of its PRESETS object."""
    text = PAGE.read_text(encoding="utf-8")
    block = re.search(r"const PRESETS=\{(.*`)\};", text, re.S)
    assert block, "could not find the PRESETS object in the demo page"
    return dict(re.findall(r"(\w+):`(.*?)`", block.group(1), re.S))


def _claimed() -> dict[str, int]:
    text = PAGE.read_text(encoding="utf-8")
    block = re.search(r'<script type="application/json" id="parity">(.*?)</script>', text, re.S)
    assert block, "the demo page carries no parity block"
    return json.loads(block.group(1))


class TestDemoParity(unittest.TestCase):
    def test_the_page_exists_and_is_self_contained(self):
        """No external fetch: the demo must work offline, from a file:// URL."""
        text = PAGE.read_text(encoding="utf-8")
        for forbidden in ("<script src=", '<link rel="stylesheet"', "@import", "fetch(", "XMLHttpRequest"):
            self.assertNotIn(forbidden, text, f"the demo reaches outside itself: {forbidden}")

    def test_every_preset_is_valid_notation(self):
        for name, notation in _presets().items():
            with self.subTest(preset=name):
                score = parse(notation)
                self.assertEqual([d.format() for d in score.errors()], [], name)

    def test_the_note_counts_the_page_claims_are_the_ones_we_produce(self):
        """If this fails, the compiler moved and the demo now misreports it."""
        presets, claimed = _presets(), _claimed()
        self.assertEqual(sorted(presets), sorted(claimed), "a preset has no claimed count")
        for name, notation in presets.items():
            with self.subTest(preset=name):
                arrangement = arrange(parse(notation), ArrangeOptions(humanize=False))
                self.assertEqual(
                    arrangement.note_count,
                    claimed[name],
                    f"{name}: the page says {claimed[name]} notes, the compiler makes "
                    f"{arrangement.note_count}",
                )


class TestDemoTokenClasses(unittest.TestCase):
    """Which tokens hold a note and which end it.

    This is the gap that let a real bug sit on the landing page. The demo had
    `.` and `-` in its REST set where the compiler has them in SUSTAIN, so
    `| Am . . . |` played a one-beat chord followed by three beats of silence
    instead of a chord lasting the bar. Every held note on the front door was
    cut to a single subdivision.

    The parity test above could not see it, because a rest and a sustain produce
    the *same number of notes* -- they differ only in how long the note before
    them lasts. Counts were identical; the page simply sounded wrong. So these
    tests pin the sets and the durations that follow from them.
    """

    def _js_set(self, name: str) -> set[str]:
        text = PAGE.read_text(encoding="utf-8")
        block = re.search(rf"const {name}=new Set\(\[(.*?)\]\);", text, re.S)
        assert block, f"could not find the demo's {name} set"
        return set(ast.literal_eval("[" + block.group(1).replace('"', '"') + "]"))

    def test_sustain_tokens_match_the_compiler(self):
        from plainsong.notation.parser import SUSTAIN_TOKENS

        self.assertEqual(self._js_set("SUSTAIN"), set(SUSTAIN_TOKENS))

    def test_rest_tokens_match_the_compiler(self):
        from plainsong.notation.parser import REST_TOKENS

        self.assertEqual(self._js_set("REST"), set(REST_TOKENS))

    def test_the_two_sets_do_not_overlap(self):
        self.assertEqual(self._js_set("SUSTAIN") & self._js_set("REST"), set())

    def test_a_dot_holds_the_note_rather_than_ending_it(self):
        """The behavioural statement of the same thing, in the compiler that
        the demo has to agree with. If this ever changes, the demo's sets and
        the sentence in `docs/demo/index.html` about them both need revisiting."""
        arrangement = arrange(
            parse(
                "**TRACK: Hold**\n[MetaData]\nkey: C | tempo: 60 | time: 4/4\n\n"
                "[V1] (Verse - 1 Bars)\nChords: | Am . . . |\n"
            ),
            ArrangeOptions(humanize=False),
        )
        durations = {round(n.duration, 6) for t in arrangement.tracks for n in t.notes}
        self.assertEqual(durations, {4.0}, "`.` should hold the chord for the whole bar")

    def test_the_preset_durations_are_what_the_page_should_reproduce(self):
        """A duration fingerprint for each preset. The demo is a second
        implementation of this arithmetic; pinning only note counts left it free
        to disagree about length, and it did."""
        for name, notation in _presets().items():
            with self.subTest(preset=name):
                arrangement = arrange(parse(notation), ArrangeOptions(humanize=False))
                total = sum(n.duration for t in arrangement.tracks for n in t.notes)
                self.assertGreater(
                    total,
                    arrangement.note_count * 0.9,
                    f"{name}: notes averaging under a beat suggests sustains are being read as rests",
                )


class _ShadowChordError(Exception):
    """Raised by the shadow parser below, mirroring the demo's ChordSymbolError."""


_REST_LIKE = {".", "-", "_", "rest", "x", "~", "..", "hold"}
_ROOT_RE = re.compile(r"^([A-Ga-g])([#b]*)")
_DEGREE_RE = re.compile(r"^(\d{1,2})")
_ACCIDENTAL_SHIFT = {"b": -1, "#": 1}
_ALTER_SHIFT = {"b": -1, "#": 1, "-": -1, "+": 1}

#: Symbols the vocabulary was rewritten to accept. If any of these silently
#: stop parsing again, that is exactly the regression this file exists to
#: catch -- see the module docstring and docs/chords.md.
VOCABULARY = (
    "CM7",
    "C7M",
    "G7alt",
    "C7alt",
    "C13",
    "Cadd9",
    "C7b9",
    "C7b9#11",
    "C13#11",
    "C6/9",
    "Cø",
    "CΔ",
    # Extra coverage beyond the twelve named in the task, exercising the
    # rules docs/chords.md calls out explicitly (the eleventh-over-a-major-
    # third exception, alteration displacing the natural form, sus dropping
    # the third, the Brazilian 7M, the two triangles, ASCII vs Unicode
    # accidentals, and the historically-regressed `Bb-7`/`C-9` spellings).
    "Cm13",
    "CmMaj7",
    "Bbmaj7#5",
    "C11",
    "Csus4",
    "C9sus4",
    "Cm7b5",
    "EbMaj7",
    "G7#9",
    "F#dim7",
    "GbΔ",
    "Bb-7",
    "C-9",
    "C5",
    "Csus2",
    "F13#11",
    "E7♭9",
)


def _preset_chord_tokens() -> set[str]:
    """Every chord symbol the page's own presets actually contain."""
    tokens: set[str] = set()
    for notation in _presets().values():
        for line in notation.splitlines():
            head, _, body = line.strip().partition(":")
            if head.strip().lower() not in ("chords", "chord"):
                continue
            for bar in body.split("|"):
                for token in bar.split():
                    if re.match(r"(?i)^vel\s*$", token):
                        continue
                    if token.lower() not in _REST_LIKE:
                        tokens.add(token)
    return tokens


def _js_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _extract_core_aliases(text: str) -> dict[str, str]:
    block = _js_block(text, "const CORE_ALIASES=new Map([", "\n]);")
    return dict(ast.literal_eval("[" + block + "]"))


def _extract_seventh_implied(text: str) -> set[str]:
    block = _js_block(text, "const SEVENTH_IMPLIED=new Set([", "]);")
    return set(ast.literal_eval("[" + block + "]"))


def _extract_alt(text: str) -> tuple[list[tuple[int, int]], list[int]]:
    degrees = _js_block(text, "const ALT_DEGREES=[", "];")
    removes = _js_block(text, "const ALT_REMOVES=[", "];")
    return (
        [tuple(pair) for pair in ast.literal_eval("[" + degrees + "]")],
        list(ast.literal_eval("[" + removes + "]")),
    )


def _extract_degree_semitones(text: str) -> dict[int, int]:
    block = _js_block(text, "const DEGREE_SEMITONES={", "};")
    return {int(k): int(v) for k, v in re.findall(r"(\d+):(-?\d+)", block)}


def _extract_cores(text: str) -> dict[str, dict]:
    block = _js_block(text, "const CORES={", "\n};")
    quoted = re.sub(r"(\w+):", r'"\1":', block)
    quoted = quoted.replace("null", "None").replace("true", "True").replace("false", "False")
    data = ast.literal_eval("{" + quoted + "}")
    return {
        name: {
            "third": fields["third"],
            "fifth": fields["fifth"],
            "seventh": fields["seventh"],
            "major_third": fields["majorThird"],
            "fixed": tuple(sorted(tuple(pair) for pair in fields["fixed"])),
        }
        for name, fields in data.items()
    }


def _extract_unicode_fold(text: str) -> dict[str, str]:
    block = _js_block(text, "const UNICODE_FOLD={", "};")
    return ast.literal_eval("{" + block + "}")


def _shadow_tables(text: str) -> dict:
    """Every table the demo's chord grammar reads, pulled out of the page
    itself rather than hand-copied -- so a table edited on one side and not
    the other fails here instead of silently drifting."""
    core_aliases = _extract_core_aliases(text)
    return {
        "core_scan": sorted(core_aliases.items(), key=lambda pair: -len(pair[0])),
        "seventh_implied": _extract_seventh_implied(text),
        "cores": _extract_cores(text),
        "degree_semitones": _extract_degree_semitones(text),
        "alt_degrees": _extract_alt(text)[0],
        "alt_removes": _extract_alt(text)[1],
        "unicode_fold": _extract_unicode_fold(text),
    }


def _fold_degree(d: int) -> int:
    return {2: 9, 4: 11}.get(d, d)


def _leading_accidental(text: str) -> tuple[int, str]:
    if text[:1] in ("b", "#"):
        return _ACCIDENTAL_SHIFT[text[0]], text[1:]
    return 0, text


def _shadow_normalise(text: str, unicode_fold: dict[str, str]) -> str:
    for source, target in unicode_fold.items():
        text = text.replace(source, target)
    return text


def _shadow_split_bass(text: str) -> tuple[str, str | None]:
    if "/" not in text:
        return text, None
    head, _, tail = text.rpartition("/")
    if _ROOT_RE.match(tail.strip()):
        return head, tail.strip()
    return head + tail, None


def _shadow_scan_root(text: str) -> tuple[int, str] | None:
    match = _ROOT_RE.match(text)
    if not match:
        return None
    letter, accidentals = match.groups()
    shift = sum(_ACCIDENTAL_SHIFT[c] for c in accidentals)
    return (LETTER_PC[letter.upper()] + shift) % 12, text[match.end() :]


def _shadow_scan_suffix(suffix: str, original: str, tables: dict):
    core_name, stack, seventh_kind, alt = None, 0, None, False
    mods: list[tuple[str, int, int]] = []
    rest = suffix
    while rest:
        if rest[:3].lower() == "alt":
            alt = True
            rest = rest[3:]
            if rest[:4].lower() == "ered":
                rest = rest[4:]
            continue

        matched = False
        for word, op in (("add", "add"), ("omit", "omit"), ("no", "omit")):
            if rest[: len(word)].lower() == word:
                shift, tail = _leading_accidental(rest[len(word) :])
                dm = _DEGREE_RE.match(tail)
                if dm:
                    mods.append((op, _fold_degree(int(dm.group(1))), shift))
                    rest = tail[dm.end() :]
                    matched = True
                    break
        if matched:
            continue

        signed = rest[:1] in ("-", "+") and rest[1:2].isdigit() and core_name is not None
        if rest[:1] in ("b", "#") or signed:
            shift = _ALTER_SHIFT[rest[0]]
            dm = _DEGREE_RE.match(rest[1:])
            if dm:
                mods.append(("alter", _fold_degree(int(dm.group(1))), shift))
                rest = rest[1 + dm.end() :]
                continue

        if rest[:2] == "69":
            mods.append(("add", 6, 0))
            mods.append(("add", 9, 0))
            rest = rest[2:]
            continue

        dm = _DEGREE_RE.match(rest)
        if dm:
            value = int(dm.group(1))
            tail = rest[dm.end() :]
            if value == 5 and core_name is None and not tail:
                core_name = "power"
                rest = tail
                continue
            if value == 7 and tail[:1] in ("M", "m"):
                seventh_kind = "maj" if tail[0] == "M" else "min"
                stack = max(stack, 7)
                rest = tail[1:]
                continue
            if value == 6:
                mods.append(("add", 6, 0))
                rest = tail
                if tail[:1] == "9":
                    mods.append(("add", 9, 0))
                    rest = tail[1:]
                continue
            if value in (2, 4) and core_name is None:
                mods.append(("add", _fold_degree(value), 0))
                rest = tail
                continue
            if value in (5, 7, 9, 11, 13):
                stack = max(stack, value)
                rest = tail
                continue
            raise _ShadowChordError(f"unreadable degree {value} in {original!r}")

        hit = False
        for alias, name in tables["core_scan"]:
            seg = rest[: len(alias)]
            if seg == alias or (len(alias) > 1 and seg.lower() == alias.lower()):
                if core_name is None:
                    core_name = name
                elif core_name == "min" and name == "maj":
                    core_name = "minmaj"
                elif core_name == "maj" and name == "min":
                    core_name = "minmaj"
                elif name in ("sus4", "sus2"):
                    mods.append(("omit", 3, 0))
                    mods.append(("add", 11 if name == "sus4" else 9, 0))
                else:
                    core_name = name
                if alias in tables["seventh_implied"]:
                    stack = max(stack, 7)
                rest = rest[len(alias) :]
                hit = True
                break
        if not hit:
            raise _ShadowChordError(f"unreadable chord quality {suffix!r} in {original!r}")

    return _shadow_resolve_core(core_name, stack, seventh_kind, alt), stack, mods, alt


def _shadow_resolve_core(core_name, stack, seventh_kind, alt):
    if core_name is None:
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
        return core_name
    if seventh_kind == "maj":
        return "maj"
    if seventh_kind == "min":
        return "dom"
    return core_name


def _shadow_build(core_name, stack, mods, alt, tables):
    core = tables["cores"][core_name]
    degree_semitones = tables["degree_semitones"]
    degrees: dict[int, int] = {1: 0}
    if core["third"] is not None:
        degrees[3] = core["third"]
    if core["fifth"] is not None:
        degrees[5] = core["fifth"]
    for degree, offset in core["fixed"]:
        degrees[degree] = offset

    if alt:
        stack = max(stack, 7)
    if core_name in ("halfdim", "dim") and stack == 0:
        stack = 7 if core_name == "halfdim" else stack

    if stack >= 7:
        degrees[7] = core["seventh"]
        for degree in (9, 11, 13):
            if degree > stack:
                break
            if degree == 11 and degree < stack and core["major_third"] and 3 in degrees:
                continue
            degrees[degree] = degree_semitones[degree]
        if stack == 11 and core["major_third"] and 3 in degrees:
            degrees.pop(3, None)

    if alt:
        for degree in tables["alt_removes"]:
            degrees.pop(degree, None)
        degrees.pop(9, None)
        degrees[9] = tables["alt_degrees"][0][1]
        degrees[11] = 18
        degrees[13] = 20

    for operation, degree, shift in mods:
        if operation == "omit":
            degrees.pop(degree, None)
        elif operation == "add":
            degrees[degree] = degree_semitones[degree] + shift
        elif operation == "alter":
            if degree in (5, 3) or degree in degrees:
                degrees[degree] = degree_semitones[degree] + shift
            else:
                degrees[degree] = degree_semitones[degree] + shift
                if degree >= 9 and 7 not in degrees:
                    degrees[7] = tables["cores"][core_name]["seventh"]
    return degrees


def _shadow_parse(token: str, tables: dict) -> tuple[int, dict[int, int], int | None]:
    """A Python transliteration of the demo's `parseChordSymbol`, run against
    tables extracted live from the page. Independent of chordsymbol.py: it
    reproduces the demo's own algorithm rather than calling the reference
    implementation, so the two can be compared without comparing a function
    to itself."""
    original = token.strip()
    if not original:
        raise _ShadowChordError("empty chord")
    text = _shadow_normalise(original, tables["unicode_fold"])
    head, bass_text = _shadow_split_bass(text)
    root = _shadow_scan_root(head)
    if root is None:
        raise _ShadowChordError(f"no chord root in {head!r}")
    root_pc, suffix = root
    bass_pc = None
    if bass_text:
        bass = _shadow_scan_root(bass_text)
        if bass is None:
            raise _ShadowChordError(f"no chord root in {bass_text!r}")
        bass_pc = bass[0]
    suffix = re.sub(r"[()\s,]", "", suffix)
    core_name, stack, mods, alt = _shadow_scan_suffix(suffix, original, tables)
    degrees = _shadow_build(core_name, stack, mods, alt, tables)
    return root_pc, degrees, bass_pc


class TestDemoChordVocabulary(unittest.TestCase):
    """The 18-entry QUALITIES table that used to sit here is exactly what let
    `CM7`, `alt`, `13` and friends compile to silence: real spellings simply
    were not in the table, and nothing said so. The replacement is a JS port
    of plainsong/notation/chordsymbol.py's grammar. These tests hold the
    port to two standards: its lookup tables must equal the Python module's
    tables exactly (the table is where the old bug actually lived), and its
    parsing algorithm, run against those tables, must agree with the real
    grammar note-for-note across the twelve symbols the task named plus
    everything the page's own presets already contain.
    """

    @classmethod
    def setUpClass(cls):
        cls.text = PAGE.read_text(encoding="utf-8")

    def test_core_aliases_match_the_python_grammar(self):
        self.assertEqual(_extract_core_aliases(self.text), dict(chordsymbol.CORE_ALIASES))

    def test_seventh_implied_matches_the_python_grammar(self):
        self.assertEqual(_extract_seventh_implied(self.text), set(chordsymbol.SEVENTH_IMPLIED))

    def test_alt_tables_match_the_python_grammar(self):
        degrees, removes = _extract_alt(self.text)
        self.assertEqual(degrees, list(chordsymbol.ALT_DEGREES))
        self.assertEqual(removes, list(chordsymbol.ALT_REMOVES))

    def test_degree_semitones_match_the_python_grammar(self):
        self.assertEqual(_extract_degree_semitones(self.text), dict(chordsymbol.DEGREE_SEMITONES))

    def test_cores_match_the_python_grammar(self):
        expected = {
            name: {
                "third": core.third,
                "fifth": core.fifth,
                "seventh": core.seventh,
                "major_third": core.major_third,
                "fixed": tuple(sorted(core.fixed)),
            }
            for name, core in chordsymbol.CORES.items()
        }
        self.assertEqual(_extract_cores(self.text), expected)

    def test_the_demo_reads_every_symbol_the_python_grammar_reads(self):
        """The behavioural half of the guard: run the same tokens through the
        real grammar and through the demo's own algorithm (fed the demo's own
        tables) and require an identical degree map every time."""
        tables = _shadow_tables(self.text)
        vocabulary = sorted(set(VOCABULARY) | _preset_chord_tokens())
        self.assertGreaterEqual(len(vocabulary), 12 + len(_preset_chord_tokens()))
        for token in vocabulary:
            with self.subTest(token=token):
                real = chordsymbol.parse_symbol(token)
                try:
                    shadow_root, shadow_degrees, shadow_bass = _shadow_parse(token, tables)
                except _ShadowChordError as exc:
                    self.fail(
                        f"the demo's grammar refuses {token!r} ({exc}) but the reference "
                        f"compiler reads it as {dict(sorted(real.degrees.items()))}"
                    )
                self.assertEqual(shadow_root, real.root_pc, token)
                self.assertEqual(shadow_degrees, dict(real.degrees), token)
                self.assertEqual(shadow_bass, real.bass_pc, token)


if __name__ == "__main__":
    unittest.main()
