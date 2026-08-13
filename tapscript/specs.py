"""Specs: a machine-readable definition of what "working" means.

A spec is a small TOML file stating an outcome the system is supposed to
deliver and the checks that prove it. Three things read them:

* ``tapscript doctor --specs`` -- tells a user what is and is not working.
* The build agent -- runs them after each change, so it can tell whether the
  change helped, and undo it when it did not.
* Contributors -- adding a capability means adding a spec that fails first.

Specs live in ``specs/`` in the repository and in ``<workspace>/specs`` for
ones the build agent writes while tailoring an install.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .runtime.capabilities import CapabilityReport, probe
from .runtime.paths import Paths, default_paths

CHECK_KINDS = ("python", "command", "capability", "file")


@dataclass
class CheckResult:
    """The outcome of one check."""

    id: str
    ok: bool
    detail: str = ""
    skipped: bool = False
    elapsed: float = 0.0

    @property
    def status(self) -> str:
        if self.skipped:
            return "skip"
        return "pass" if self.ok else "FAIL"


@dataclass
class Check:
    """One way of proving part of a spec."""

    id: str
    kind: str = "python"
    run: str = ""
    requires: str = ""
    expect: str = ""
    optional: bool = False
    description: str = ""

    def execute(self, paths: Paths, report: CapabilityReport) -> CheckResult:
        started = time.perf_counter()
        try:
            ok, detail = self._execute(paths, report)
            skipped = detail.startswith("skipped:")
        except Exception as exc:
            ok, detail, skipped = False, f"{type(exc).__name__}: {exc}", False
        return CheckResult(
            id=self.id,
            ok=ok or (skipped and self.optional),
            detail=detail,
            skipped=skipped,
            elapsed=time.perf_counter() - started,
        )

    def _execute(self, paths: Paths, report: CapabilityReport) -> tuple[bool, str]:
        if self.requires and not report.has(self.requires):
            return (self.optional, f"skipped: needs {self.requires}")

        if self.kind == "capability":
            target = self.run or self.requires
            capability = report.get(target)
            if capability is None:
                return False, f"no such capability: {target}"
            return capability.present, capability.detail or ("present" if capability.present else "absent")

        if self.kind == "file":
            candidates = [Path(self.run), (paths.project_root or Path.cwd()) / self.run]
            for candidate in candidates:
                if candidate.exists():
                    return True, str(candidate)
            return False, f"missing: {self.run}"

        if self.kind == "command":
            argv = self.run.split()
            if not argv:
                return False, "no command given"
            if not shutil.which(argv[0]):
                return (self.optional, f"skipped: {argv[0]} is not installed")
            completed = subprocess.run(
                argv, capture_output=True, timeout=300, check=False,
                cwd=str(paths.project_root or Path.cwd()),
            )
            output = (completed.stdout or completed.stderr).decode("utf-8", "replace").strip()
            tail = output.splitlines()[-1] if output else ""
            if self.expect and self.expect not in output:
                return False, f"expected {self.expect!r} in output; got {tail[:160]}"
            return completed.returncode == 0, tail[:200]

        # kind == "python": "module.path:function", returning (ok, detail) or a bool.
        target = self.run
        module_name, _, attribute = target.partition(":")
        if not module_name or not attribute:
            return False, f"malformed target: {target!r} (expected module:function)"
        module = importlib.import_module(module_name)
        function: Callable[..., Any] = getattr(module, attribute)
        outcome = function()
        if isinstance(outcome, tuple) and len(outcome) == 2:
            return bool(outcome[0]), str(outcome[1])
        return bool(outcome), ""


@dataclass
class Spec:
    """One outcome the system promises, and how to prove it."""

    id: str
    title: str
    why: str = ""
    tags: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    source: Path | None = None

    def verify(self, paths: Paths | None = None, report: CapabilityReport | None = None) -> "SpecResult":
        paths = paths or default_paths()
        report = report or probe()
        results = [check.execute(paths, report) for check in self.checks]
        return SpecResult(spec=self, checks=results)


@dataclass
class SpecResult:
    """How a spec fared."""

    spec: Spec
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.ok]

    @property
    def status(self) -> str:
        if self.ok:
            return "pass" if not all(check.skipped for check in self.checks) else "skip"
        return "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.spec.id,
            "title": self.spec.title,
            "status": self.status,
            "checks": [
                {"id": check.id, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
        }


def _load_spec_file(path: Path) -> Spec | None:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    header = data.get("spec", {})
    spec_id = header.get("id") or path.stem
    checks = []
    for index, raw in enumerate(data.get("check", []), start=1):
        checks.append(
            Check(
                id=raw.get("id", f"{spec_id}-{index}"),
                kind=raw.get("kind", "python"),
                run=raw.get("run", ""),
                requires=raw.get("requires", ""),
                expect=raw.get("expect", ""),
                optional=bool(raw.get("optional", False)),
                description=raw.get("description", ""),
            )
        )
    return Spec(
        id=spec_id,
        title=header.get("title", spec_id),
        why=header.get("why", ""),
        tags=list(header.get("tags", [])),
        checks=checks,
        source=path,
    )


def spec_directories(paths: Paths | None = None) -> list[Path]:
    paths = paths or default_paths()
    directories = []
    if paths.project_root:
        directories.append(paths.project_root / "specs")
    directories.append(paths.workspace / "specs")
    directories.append(paths.config_dir / "specs")
    return [directory for directory in directories if directory.is_dir()]


def load_specs(paths: Paths | None = None, tag: str = "") -> list[Spec]:
    """Every spec visible from here, repository first."""
    specs: dict[str, Spec] = {}
    for directory in spec_directories(paths):
        for path in sorted(directory.glob("*.toml")):
            spec = _load_spec_file(path)
            if spec and (not tag or tag in spec.tags):
                specs[spec.id] = spec
    return list(specs.values())


def verify_all(
    paths: Paths | None = None,
    tag: str = "",
    report: CapabilityReport | None = None,
) -> list[SpecResult]:
    paths = paths or default_paths()
    report = report or probe()
    return [spec.verify(paths, report) for spec in load_specs(paths, tag)]


def format_results(results: list[SpecResult], verbose: bool = False) -> str:
    """A compact report suitable for a terminal."""
    lines: list[str] = []
    symbols = {"pass": "ok  ", "FAIL": "FAIL", "skip": "skip"}
    for result in results:
        lines.append(f"  {symbols.get(result.status, '?')}  {result.spec.id:<28} {result.spec.title}")
        for check in result.checks:
            if verbose or not check.ok:
                detail = f" -- {check.detail}" if check.detail else ""
                lines.append(f"         {check.status:<5} {check.id}{detail}")
    passed = sum(1 for result in results if result.status == "pass")
    failed = sum(1 for result in results if result.status == "FAIL")
    skipped = sum(1 for result in results if result.status == "skip")
    lines.append(f"\n  {passed} passed, {failed} failed, {skipped} skipped")
    return "\n".join(lines)
