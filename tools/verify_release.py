#!/usr/bin/env python3
"""Verify a release from the outside, the way a user meets it.

Everything in `tests/` runs against the working tree, with the repository on
`sys.path` and every data file sitting where the source says it does. That is
the wrong shape for the failures releases actually have. The specs once lived
in a top-level `specs/` directory and `plainsong spec` reported "no specs
found" to everybody who installed rather than cloned -- the whole
self-verification story quietly doing nothing, with a green test suite. The
songbook had the same fault.

So this script never imports plainsong. It builds a wheel, installs it into a
throwaway virtualenv **outside the source tree**, and drives the console script
from `/tmp`, where nothing resolves out of the working directory by accident.
Then it does the same against whatever is actually on PyPI, which is a
different question: the tree can be right and the upload can be a version
behind.

    python3 tools/verify_release.py            # tree, wheel and PyPI
    python3 tools/verify_release.py --local    # skip the network
    python3 tools/verify_release.py --json

Exit status is 0 only if every check passed. Nothing here is skipped silently:
a check that cannot run says so and counts as a failure, because "we did not
look" and "we looked and it was fine" are the two things this script exists to
keep apart.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A tiny piece of notation with a chord row, a melody row and a lyric row, so a
# compile exercises the parser, the arranger and the MIDI writer rather than
# just proving the entry point exists.
NOTATION = """**TRACK: Release Check**
[MetaData]
key: C | tempo: 120 | time: 4/4

[Verse]
Chords: | C | Am | F | G |
Melody: | C4 E4 G4 E4 | A3 C4 E4 C4 | F3 A3 C4 A3 | G3 B3 D4 B3 |
"""


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append(Result(name, ok, detail))
        mark = "ok  " if ok else "FAIL"
        line = f"  {mark}  {name}"
        if detail:
            line += f"\n        {detail}"
        print(line, flush=True)
        return ok

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]


def run(command: list[str], cwd: Path | None = None, env: dict | None = None) -> tuple[int, str]:
    """Run a command with the source tree kept off the path.

    `PYTHONPATH` is stripped deliberately. Leaving it set is exactly how a
    packaging bug hides: the installed package imports, but the module that
    answers is the one in the checkout.
    """
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(env or {})
    try:
        finished = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return finished.returncode, (finished.stdout + finished.stderr).strip()


def make_venv(where: Path) -> Path:
    venv.create(where, with_pip=True, clear=True)
    binary = where / ("Scripts" if os.name == "nt" else "bin")
    return binary


# -- the checks ---------------------------------------------------------------


def check_tree(report: Report) -> None:
    """The working tree's own checks. These are the ones CI runs."""
    print("\nworking tree")
    python = sys.executable

    code, out = run([python, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT)
    report.check("test suite passes", code == 0, out.splitlines()[-1] if out else "")

    code, out = run([python, "-m", "plainsong", "spec"], cwd=ROOT)
    report.check("specs pass", code == 0, out.splitlines()[-1] if out else "")

    code, out = run(
        [python, "-m", "plainsong", "check", "docs", "examples", "plainsong/songbook", "README.md"],
        cwd=ROOT,
    )
    report.check("every documented example compiles", code == 0, out.splitlines()[-1] if out else "")

    code, out = run(
        [
            python, "-m", "plainsong", "fingerprint",
            "plainsong/songbook", "examples", "docs",
            "--check", "tests/corpus-fingerprint.txt",
        ],
        cwd=ROOT,
    )
    report.check(
        "the corpus compiles to exactly the recorded music",
        code == 0,
        out.splitlines()[-1] if out else "",
    )


def exercise(binary: Path, report: Report, label: str, expect_version: str | None) -> None:
    """Drive an installed plainsong from outside the source tree.

    Every command here runs with cwd=/tmp. That is the point: a data file the
    wheel forgot to carry is invisible from inside the checkout.
    """
    plainsong = binary / ("plainsong.exe" if os.name == "nt" else "plainsong")
    python = binary / ("python.exe" if os.name == "nt" else "python")
    outside = Path(tempfile.gettempdir())

    code, out = run([str(plainsong), "--version"], cwd=outside)
    version = out.split()[-1] if code == 0 and out else ""
    detail = out
    if expect_version:
        report.check(
            f"[{label}] reports version {expect_version}",
            code == 0 and version == expect_version,
            detail,
        )
    else:
        report.check(f"[{label}] runs and reports a version", code == 0, detail)

    # The packaging canary. `spec` reads the spec_files/ TOMLs out of the
    # installed package, so it fails loudly when package-data is wrong -- which
    # is the failure the test suite structurally cannot see.
    code, out = run([str(plainsong), "spec"], cwd=outside)
    report.check(
        f"[{label}] specs pass from the install (packaging canary)",
        code == 0,
        out.splitlines()[-1] if out else "",
    )

    # The songbook is package data too, and shipped for exactly this command.
    code, out = run([str(plainsong), "library", "--limit", "3"], cwd=outside)
    report.check(f"[{label}] the bundled songbook is present", code == 0, out.splitlines()[-1] if out else "")

    work = Path(tempfile.mkdtemp(prefix="plainsong-verify-"))
    try:
        source = work / "check.song"
        source.write_text(NOTATION, encoding="utf-8")

        code, out = run([str(plainsong), "compile", str(source), "-o", str(work / "out.mid")], cwd=outside)
        midi = work / "out.mid"
        report.check(
            f"[{label}] compiles notation to a MIDI file",
            code == 0 and midi.exists() and midi.stat().st_size > 0,
            out.splitlines()[-1] if out else "",
        )

        # A MIDI file is not proof of music -- an unreadable chord becomes a
        # rest and still writes a file. Read the note count back.
        #
        # `--json` is a global flag and has to precede the subcommand:
        # `plainsong --json info x`, not `plainsong info x --json`, which
        # argparse rejects outright. The count is `arrangement.notes`, the
        # total across tracks; the per-track counts live under
        # `arrangement.tracks[].notes`.
        code, out = run([str(plainsong), "--json", "info", str(source)], cwd=outside)
        notes = None
        if code == 0:
            try:
                notes = json.loads(out).get("arrangement", {}).get("notes")
            except (ValueError, AttributeError):
                notes = None
        report.check(
            f"[{label}] the compile actually produced notes",
            isinstance(notes, int) and notes > 0,
            f"arrangement.notes={notes}",
        )

        code, out = run([str(plainsong), "chart", str(source), "-o", str(work / "out.svg")], cwd=outside)
        svg = work / "out.svg"
        report.check(
            f"[{label}] renders a chord chart",
            code == 0 and svg.exists() and svg.read_text(encoding="utf-8").lstrip().startswith("<"),
            out.splitlines()[-1] if out else "",
        )

        code, out = run([str(plainsong), "transpose", str(source), "Dm"], cwd=outside)
        report.check(f"[{label}] transposes", code == 0, out.splitlines()[-1] if out else "")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # The security guard, read out of the installed package rather than the
    # tree. Both bugs this replaced were live in a shipped artifact.
    probe = (
        "from plainsong.runtime.localhost import host_is_local, bind_is_loopback;"
        "print(int(not host_is_local('127.evil.example')),"
        "int(host_is_local('[::1]')),"
        "int(host_is_local('127.0.0.1')),"
        "int(not host_is_local('evil.example')),"
        "int(not bind_is_loopback('0.0.0.0')),"
        "int(bind_is_loopback('::1')))"
    )
    code, out = run([str(python), "-c", probe], cwd=outside)
    report.check(
        f"[{label}] the DNS-rebinding guard is correct in the shipped package",
        code == 0 and out.strip() == "1 1 1 1 1 1",
        out,
    )


def check_wheel(report: Report) -> Path | None:
    """Build the tree and install the wheel somewhere clean."""
    print("\nbuilt wheel")
    dist = Path(tempfile.mkdtemp(prefix="plainsong-dist-"))
    code, out = run([sys.executable, "-m", "build", "--outdir", str(dist)], cwd=ROOT)
    wheels = sorted(dist.glob("*.whl"))
    if not report.check("wheel builds", code == 0 and bool(wheels), out.splitlines()[-1] if out else ""):
        return None

    home = Path(tempfile.mkdtemp(prefix="plainsong-venv-"))
    binary = make_venv(home)
    pip = binary / ("pip.exe" if os.name == "nt" else "pip")
    code, out = run([str(pip), "install", "--quiet", str(wheels[0])])
    if not report.check("the wheel installs into a clean venv", code == 0, out.splitlines()[-1] if out else ""):
        return None

    version = (ROOT / "plainsong" / "version.py").read_text(encoding="utf-8")
    expected = version.split('__version__ = "')[1].split('"')[0]
    exercise(binary, report, "wheel", expected)
    return home


def check_pypi(report: Report) -> None:
    """The same drill against what is actually published.

    The tree being right says nothing about the upload. Twice during this
    project's releases PyPI's JSON API reported an older version than `pip`
    then resolved, which is why this installs rather than asking.
    """
    print("\npublished on PyPI")
    home = Path(tempfile.mkdtemp(prefix="plainsong-pypi-"))
    binary = make_venv(home)
    pip = binary / ("pip.exe" if os.name == "nt" else "pip")

    code, out = run([str(pip), "install", "--quiet", "--upgrade", "plainsong"])
    if not report.check("plainsong installs from PyPI", code == 0, out.splitlines()[-1] if out else ""):
        return
    exercise(binary, report, "pypi", None)

    # The sibling. It depends on the compiler, so installing it also proves the
    # dependency floor resolves to something real.
    home = Path(tempfile.mkdtemp(prefix="plainsong-mcp-"))
    binary = make_venv(home)
    pip = binary / ("pip.exe" if os.name == "nt" else "pip")
    python = binary / ("python.exe" if os.name == "nt" else "python")

    code, out = run([str(pip), "install", "--quiet", "plainsong-mcp"])
    if not report.check("plainsong-mcp installs from PyPI", code == 0, out.splitlines()[-1] if out else ""):
        return

    # Drive the MCP server the way a third-party client does: real JSON-RPC
    # over stdio. `--list-tools` would prove less, being our own code path.
    messages = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        '{"protocolVersion":"2025-06-18","capabilities":{},'
        '"clientInfo":{"name":"verify","version":"1"}}}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    try:
        finished = subprocess.run(
            [str(python), "-m", "plainsong_mcp"],
            input=messages,
            cwd=tempfile.gettempdir(),
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        replies = [json.loads(line) for line in finished.stdout.splitlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001 - report whatever went wrong
        report.check("the MCP server answers a real client over stdio", False, f"{type(exc).__name__}: {exc}")
        return

    initialize = next((r for r in replies if r.get("id") == 1), {})
    listing = next((r for r in replies if r.get("id") == 2), {})
    served = initialize.get("result", {}).get("serverInfo", {})
    tools = listing.get("result", {}).get("tools", [])
    report.check(
        "the MCP server answers a real client over stdio",
        served.get("name") == "plainsong" and len(tools) > 0,
        f"server={served.get('name')} {served.get('version')} tools={len(tools)}",
    )

    # The two copies of the loopback check must agree, or one of them is wrong.
    probe = (
        "import plainsong_mcp.localhost as a, plainsong.runtime.localhost as b;"
        "cases=['127.evil.example','[::1]','[::1]:8765','0.0.0.0','evil.example',"
        "'localhost:8765','[::ffff:127.0.0.1]','127.0.0.1'];"
        "print(int(all(a.host_is_local(c)==b.host_is_local(c) for c in cases)),"
        "int(not a.host_is_local('127.evil.example')))"
    )
    code, out = run([str(python), "-c", probe], cwd=Path(tempfile.gettempdir()))
    report.check(
        "the sibling's loopback check agrees with the compiler's",
        code == 0 and out.strip() == "1 1",
        out,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--local", action="store_true", help="skip the checks that need the network")
    parser.add_argument("--json", action="store_true", help="machine-readable summary on stdout")
    args = parser.parse_args()

    report = Report()
    check_tree(report)
    check_wheel(report)
    if not args.local:
        check_pypi(report)

    passed = len(report.results) - len(report.failed)
    if args.json:
        print(json.dumps({
            "passed": passed,
            "failed": len(report.failed),
            "results": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in report.results],
        }, indent=2))
    else:
        print(f"\n{passed} passed, {len(report.failed)} failed")
        for failure in report.failed:
            print(f"  FAIL  {failure.name}\n        {failure.detail}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
