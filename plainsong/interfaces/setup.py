"""The setup wizard.

Its job is to get from a fresh clone to a working model connection in under a
minute, and to be honest about the fact that no connection is also a working
state -- the compiler does not need one.
"""

from __future__ import annotations

import getpass

from ..llm.catalog import load_catalog
from ..llm.credentials import mask, resolve_key, store_key
from ..llm.registry import auto_select, build_provider, provider_status
from ..llm.types import ProviderError
from ..runtime.capabilities import probe
from ..runtime.config import Config

SUGGESTED = ("anthropic", "openai", "deepseek", "openrouter", "gemini", "xai", "groq", "ollama")


def run_setup(config: Config, out, provider_id: str = "", non_interactive: bool = False) -> int:
    report = probe(refresh=True)
    catalog = load_catalog(config.paths)

    out.head("plainsong setup")
    out.say()
    out.say("The compiler works with no setup at all:")
    out.dim("    plainsong new song.song && plainsong compile song.song --play")
    out.say()
    out.say("Connecting a model adds the agent, which writes and revises notation for you.")
    out.say()

    if report.has("host_agent"):
        host = report.detail("host_agent")
        out.ok(f"running inside {host}")
        out.dim("  the `host` provider can borrow that agent's model -- no API key needed")
        out.say()

    already = [status for status in provider_status(config.paths) if status.configured and status.source]
    if already:
        out.head("already available")
        out.table([(status.info.id, status.info.label[:34], status.source) for status in already])
        out.say()

    chosen = provider_id.strip().lower()

    if not chosen and non_interactive:
        chosen = auto_select(config.paths, report)
        out.dim(f"choosing {chosen} automatically")

    if not chosen:
        if not _interactive():
            chosen = auto_select(config.paths, report)
            out.dim(f"not a terminal, so choosing {chosen} automatically")
        else:
            chosen = _ask_provider(catalog, out)
            if not chosen:
                out.say()
                out.dim("nothing changed. The compiler is ready to use.")
                return 0

    info = catalog.get(chosen)
    if info is None:
        out.fail(f"unknown provider: {chosen}")
        out.dim("see `plainsong providers` for the list")
        return 1

    api_key = ""
    if info.needs_key:
        existing = resolve_key(info, paths=config.paths)
        if existing and not _interactive():
            api_key = existing
        elif existing:
            out.say(f"{info.label} already has a key ({mask(existing)}).")
            if not _confirm("Replace it?", default=False):
                api_key = existing
        if not api_key:
            if not _interactive():
                out.fail(f"{info.label} needs an API key and this is not an interactive terminal")
                out.dim(f"set {' or '.join(info.env)} in the environment instead")
                return 1
            if info.docs:
                out.dim(f"get a key from {info.docs}")
            api_key = getpass.getpass(f"{info.label} API key: ").strip()
            if not api_key:
                out.fail("no key entered")
                return 1
            store_key(info.id, api_key, config.paths)
            out.ok(f"key stored in {config.paths.secrets_file}")

    model = info.default_model
    if _interactive() and info.models and not non_interactive:
        out.say()
        out.say(f"models for {info.label}:")
        for index, name in enumerate(info.models, start=1):
            marker = " (default)" if name == info.default_model else ""
            out.say(f"  {index}. {name}{marker}")
        answer = input("model [enter for the default]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(info.models):
            model = info.models[int(answer) - 1]
        elif answer:
            model = answer

    if info.id == "host":
        model = "host"
        if _interactive() and not non_interactive:
            out.say()
            out.say("How should plainsong reach your agent?")
            out.say("  1. run a command (claude -p, openclaw run, ollama run ...)")
            out.say("  2. exchange files in the bridge directory")
            answer = input("choice [2]: ").strip() or "2"
            if answer == "1":
                command = input("command: ").strip()
                if command:
                    config.set("llm", "host_command", command)
                    config.set("llm", "host_mode", "command")
            else:
                config.set("llm", "host_mode", "file")
                out.dim(f"  requests will appear in {config.paths.bridge_dir}/requests")
                out.dim("  see docs/host-bridge.md for the protocol")

    config.set("llm", "provider", info.id)
    config.set("llm", "model", model)
    saved = config.save()

    out.say()
    out.ok(f"provider: {info.label}")
    out.ok(f"model: {model}")
    out.dim(f"saved to {saved}")

    out.say()
    out.say("checking the connection ...")
    try:
        provider = build_provider(
            info.id,
            model=model,
            paths=config.paths,
            host_command=config.get("llm", "host_command", ""),
            host_mode=config.get("llm", "host_mode", ""),
        )
    except ProviderError as exc:
        out.fail(str(exc))
        return 1

    ok, detail = provider.check()
    if ok:
        out.ok(detail)
        out.say()
        out.say("try it:")
        out.dim('    plainsong agent "write a slow waltz in D minor"')
        return 0

    out.warn(detail)
    out.dim("the settings were saved; fix the problem above and run `plainsong providers --check`")
    return 1


def _interactive() -> bool:
    import sys

    return sys.stdin.isatty() and sys.stdout.isatty()


def _confirm(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not answer:
        return default
    return answer.startswith("y")


def _ask_provider(catalog, out) -> str:
    out.head("providers")
    options = [catalog[name] for name in SUGGESTED if name in catalog]
    for index, info in enumerate(options, start=1):
        note = "no key needed" if not info.needs_key else (info.docs or "")
        out.say(f"  {index}. {info.label:<24} {note}")
    out.say(f"  {len(options) + 1}. something else (see `plainsong providers`)")
    out.say("  0. skip -- use the compiler without a model")
    out.say()
    try:
        answer = input("choose [0]: ").strip() or "0"
    except (EOFError, KeyboardInterrupt):
        return ""
    if answer == "0":
        return ""
    if answer.isdigit():
        index = int(answer)
        if 1 <= index <= len(options):
            return options[index - 1].id
        if index == len(options) + 1:
            return input("provider id: ").strip().lower()
    return answer.lower()
