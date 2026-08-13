"""An offline provider.

No network, no key, deterministic output. It exists so that the agent loop,
the interfaces and the test suite can all be exercised on a machine with no
model access at all -- and so a new user can see the shape of the workflow
before deciding which provider to sign up for.

It is not a model. It recognises a few intents and answers with real, valid
notation rather than pretending to be clever.
"""

from __future__ import annotations

import hashlib
import json
import re

from ..base import Provider
from ..types import CompletionRequest, CompletionResponse, ToolCall, Usage

TEMPLATE = """**TRACK: {title}**
[MetaData]
key: {key} | tempo: {tempo} | swing: 0% | subdivision: 8th
time: 4/4 | mood: {mood}

[V1] (Verse - 4 Bars)
Chords: | {c1} . . . | {c2} . . . | {c3} . . . | {c4} . . . |
Melody: | {m1} . {m2} {m3} | {m4} . {m3} {m2} | {m1} . {m2} {m4} | {m3} . {m2} {m1} |

[CH] (Chorus - 4 Bars)
Chords: | {c3} . . . | {c4} . . . | {c1} . . . | {c2} . . . |
Melody: | {m4} . {m3} {m2} | {m3} . {m2} {m1} | {m4} . {m4} {m3} | {m2} . {m1} . |
"""

PALETTES = {
    "minor": {
        "key": "Am",
        "chords": ["Am", "F", "C", "G"],
        "melody": ["A4", "C5", "E5", "G4"],
        "mood": "Reflective",
    },
    "major": {
        "key": "C",
        "chords": ["C", "G", "Am", "F"],
        "melody": ["C5", "E5", "G5", "A4"],
        "mood": "Bright",
    },
    "blues": {
        "key": "G",
        "chords": ["G7", "C7", "G7", "D7"],
        "melody": ["G4", "Bb4", "D5", "F5"],
        "mood": "Loose",
    },
}


class EchoProvider(Provider):
    """Deterministic stand-in for a model."""

    def describe(self) -> str:
        return "offline stub (no model)"

    def _palette(self, prompt: str) -> dict:
        lowered = prompt.lower()
        if "blues" in lowered or "swing" in lowered:
            return PALETTES["blues"]
        if any(word in lowered for word in ("sad", "minor", "dark", "melancholy", "slow")):
            return PALETTES["minor"]
        return PALETTES["major"]

    def _compose(self, prompt: str) -> str:
        palette = self._palette(prompt)
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        tempo = 70 + int(digest[:2], 16) % 70
        title_match = re.search(r"(?:called|titled|named)\s+[\"']?([\w \-]{3,40})", prompt, re.IGNORECASE)
        title = (title_match.group(1).strip() if title_match else "Offline Sketch").title()
        return TEMPLATE.format(
            title=title,
            key=palette["key"],
            tempo=tempo,
            mood=palette["mood"],
            c1=palette["chords"][0], c2=palette["chords"][1],
            c3=palette["chords"][2], c4=palette["chords"][3],
            m1=palette["melody"][0], m2=palette["melody"][1],
            m3=palette["melody"][2], m4=palette["melody"][3],
        )

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        prompt = "\n".join(
            message.content for message in request.messages if message.role in ("user", "system")
        )
        last_user = next(
            (message.content for message in reversed(request.messages) if message.role == "user"), ""
        )

        # If a write tool is on offer and nothing has been written yet, use it.
        already_wrote = any(
            call.name in {"write_score", "write_file"}
            for message in request.messages
            for call in message.tool_calls
        )
        tool_names = {tool.name for tool in request.tools}
        if not already_wrote and "write_score" in tool_names:
            return CompletionResponse(
                text="",
                tool_calls=[
                    ToolCall(
                        id="echo-1",
                        name="write_score",
                        arguments={
                            "path": "offline-sketch.tap",
                            "content": self._compose(last_user or prompt),
                        },
                    )
                ],
                model="echo",
                provider=self.id,
                usage=Usage(),
                finish_reason="tool_calls",
            )

        if request.json_mode:
            text = json.dumps(
                {
                    "summary": "offline stub reply",
                    "notes": "Connect a provider with `tapscript setup` for real answers.",
                }
            )
        else:
            text = (
                "Running without a model provider, so this is the offline stub.\n\n"
                + self._compose(last_user or prompt)
                + "\nRun `tapscript setup` to connect a real provider."
            )

        return CompletionResponse(
            text=text,
            model="echo",
            provider=self.id,
            usage=Usage(),
            finish_reason="stop",
        )

    def check(self) -> tuple[bool, str]:
        return True, "offline stub is always available"
