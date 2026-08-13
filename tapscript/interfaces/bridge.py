"""The host-agent side of the bridge.

When tapscript is configured with the ``host`` provider in file mode, it drops
a request into the bridge directory and waits. These commands are how the
surrounding agent -- or a person -- answers it.

    tapscript bridge list              # what is waiting
    tapscript bridge answer <id> --text "..."
    tapscript bridge watch             # print requests as they arrive
"""

from __future__ import annotations

import json
import time

from ..llm.providers.host import pending_bridge_requests, write_bridge_response
from ..runtime.config import Config


def run_bridge(args, config: Config, out) -> int:
    bridge_dir = config.paths.bridge_dir
    action = args.action

    if action == "status":
        waiting = pending_bridge_requests(bridge_dir)
        out.data({"bridge_dir": str(bridge_dir), "pending": len(waiting)})
        out.head("host bridge")
        out.table(
            [
                ("directory", str(bridge_dir)),
                ("requests", str(bridge_dir / "requests")),
                ("responses", str(bridge_dir / "responses")),
                ("waiting", str(len(waiting))),
                ("mode", str(config.get("llm", "host_mode", "file"))),
                ("command", str(config.get("llm", "host_command", "") or "(none)")),
            ]
        )
        out.say()
        out.dim("protocol: docs/host-bridge.md")
        return 0

    if action == "list":
        waiting = pending_bridge_requests(bridge_dir)
        out.data(waiting)
        if not waiting:
            out.say("nothing waiting")
            return 0
        for item in waiting:
            out.head(item.get("id", "?"))
            prompt = str(item.get("prompt", ""))
            out.say(prompt[:2000])
            out.say()
        return 0

    if action == "answer":
        if not args.request_id:
            out.fail("usage: tapscript bridge answer <request-id> --text '...'")
            return 2
        text = args.text
        if not text:
            import sys

            text = sys.stdin.read()
        if not text.strip():
            out.fail("no reply text given")
            return 2
        target = write_bridge_response(bridge_dir, args.request_id, text)
        out.ok(f"answered {args.request_id}")
        out.dim(str(target))
        return 0

    if action == "watch":
        out.dim(f"watching {bridge_dir / 'requests'} -- ctrl-c to stop")
        seen: set[str] = set()
        try:
            while True:
                for item in pending_bridge_requests(bridge_dir):
                    request_id = str(item.get("id", ""))
                    if request_id in seen:
                        continue
                    seen.add(request_id)
                    print(json.dumps(item, indent=2))
                    print(f"\n# answer with: tapscript bridge answer {request_id} --text '...'\n")
                time.sleep(0.5)
        except KeyboardInterrupt:
            out.say()
            return 0

    out.fail(f"unknown action: {action}")
    return 2


def check_importable() -> tuple[bool, str]:
    return True, "bridge commands available"
