"""Provider adapters, the catalogue and credential resolution.

Adapters are tested against recorded payload shapes rather than live services:
what matters is that a provider's wire format is translated correctly in both
directions, and that is checkable offline.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tapscript.llm import build_provider, load_catalog, mask, provider_status
from tapscript.llm.catalog import ProviderInfo
from tapscript.llm.credentials import forget_key, resolve_key, store_key
from tapscript.llm.providers import ADAPTERS
from tapscript.llm.providers.anthropic import AnthropicProvider
from tapscript.llm.providers.gemini import GeminiProvider
from tapscript.llm.providers.host import _parse_reply, _render_prompt
from tapscript.llm.providers.openai_compat import OpenAICompatibleProvider
from tapscript.llm.registry import auto_select
from tapscript.llm.types import CompletionRequest, Message, ProviderError, ToolCall, ToolSpec
from tapscript.runtime.paths import Paths

TOOL = ToolSpec(
    name="write_score",
    description="write notation",
    parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)

CONVERSATION = [
    Message.system("be helpful"),
    Message.user("write a waltz"),
    Message.assistant("", [ToolCall(id="call_1", name="write_score", arguments={"path": "a.tap"})]),
    Message.tool("call_1", "wrote a.tap"),
]


def info_for(api: str, **kwargs) -> ProviderInfo:
    return ProviderInfo(id=f"test-{api}", label="Test", api=api, base_url="https://example.test/v1", **kwargs)


class TestCatalogue(unittest.TestCase):
    def test_every_entry_has_an_adapter(self):
        for info in load_catalog().values():
            self.assertIn(info.api, ADAPTERS, f"{info.id} has no adapter")

    def test_expected_providers_are_present(self):
        catalog = load_catalog()
        for name in ("anthropic", "openai", "deepseek", "openrouter", "xai", "gemini", "ollama", "host", "echo"):
            self.assertIn(name, catalog)

    def test_local_providers_need_no_key(self):
        catalog = load_catalog()
        for name in ("ollama", "lmstudio", "host", "echo"):
            self.assertFalse(catalog[name].needs_key, f"{name} should not require a key")

    def test_status_lists_everything(self):
        statuses = provider_status()
        self.assertEqual(len(statuses), len(load_catalog()))

    def test_extra_providers_can_be_added_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory) / "config"
            config_dir.mkdir()
            (config_dir / "providers.json").write_text(
                json.dumps(
                    {
                        "providers": {
                            "housemodel": {
                                "label": "House model",
                                "api": "openai",
                                "base_url": "http://10.0.0.5:8000/v1",
                                "default_model": "house-7b",
                                "api_key_optional": True,
                            }
                        }
                    }
                )
            )
            with mock.patch.dict(os.environ, {"TAPSCRIPT_CONFIG_DIR": str(config_dir)}):
                catalog = load_catalog(Paths())
            self.assertIn("housemodel", catalog)
            self.assertEqual(catalog["housemodel"].base_url, "http://10.0.0.5:8000/v1")


class TestCredentials(unittest.TestCase):
    def test_environment_wins(self):
        info = load_catalog()["deepseek"]
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-key"}):
            self.assertEqual(resolve_key(info), "env-key")

    def test_explicit_beats_environment(self):
        info = load_catalog()["deepseek"]
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-key"}):
            self.assertEqual(resolve_key(info, "explicit"), "explicit")

    def test_store_and_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"TAPSCRIPT_CONFIG_DIR": directory}, clear=False):
                paths = Paths()
                info = ProviderInfo(id="fake", label="Fake", env=["FAKE_KEY_NOT_SET"])
                store_key("fake", "sk-secret", paths)
                self.assertEqual(resolve_key(info, paths=paths), "sk-secret")
                self.assertTrue(forget_key("fake", paths))
                self.assertEqual(resolve_key(info, paths=paths), "")

    @unittest.skipIf(os.name == "nt", "POSIX permission bits do not apply on Windows")
    def test_stored_keys_are_not_world_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"TAPSCRIPT_CONFIG_DIR": directory}, clear=False):
                path = store_key("fake", "sk-secret", Paths())
            self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_mask_hides_the_middle(self):
        self.assertEqual(mask("sk-1234567890ab"), "sk-1...90ab")
        self.assertNotIn("567890", mask("sk-1234567890ab"))


class TestOpenAIAdapter(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAICompatibleProvider(info_for("openai"), api_key="k", model="m")

    def test_payload_shape(self):
        payload = self.provider._payload(CompletionRequest(messages=CONVERSATION, tools=[TOOL]))
        self.assertEqual(payload["model"], "m")
        self.assertEqual(payload["tools"][0]["function"]["name"], "write_score")
        roles = [message["role"] for message in payload["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "tool"])
        self.assertEqual(
            json.loads(payload["messages"][2]["tool_calls"][0]["function"]["arguments"]),
            {"path": "a.tap"},
        )
        self.assertEqual(payload["messages"][3]["tool_call_id"], "call_1")

    def test_auth_header(self):
        self.assertEqual(self.provider._headers()["Authorization"], "Bearer k")

    def test_alternate_auth_header(self):
        provider = OpenAICompatibleProvider(info_for("openai", auth_header="api-key"), api_key="k")
        self.assertEqual(provider._headers()["api-key"], "k")

    def test_response_parsing(self):
        payload = {
            "model": "m",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "on it",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {"name": "write_score", "arguments": '{"path": "b.tap"}'},
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        }
        with mock.patch("tapscript.llm.providers.openai_compat.request_json", return_value=payload):
            response = self.provider.complete(CompletionRequest(messages=CONVERSATION))
        self.assertEqual(response.text, "on it")
        self.assertEqual(response.tool_calls[0].arguments, {"path": "b.tap"})
        self.assertEqual(response.usage.total, 16)

    def test_malformed_tool_arguments_do_not_crash(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [{"id": "c1", "function": {"name": "x", "arguments": "not json"}}],
                    }
                }
            ]
        }
        with mock.patch("tapscript.llm.providers.openai_compat.request_json", return_value=payload):
            response = self.provider.complete(CompletionRequest(messages=CONVERSATION))
        self.assertEqual(response.tool_calls[0].arguments, {"_raw": "not json"})

    def test_empty_choices_raises_a_clear_error(self):
        with mock.patch("tapscript.llm.providers.openai_compat.request_json", return_value={"choices": []}):
            with self.assertRaises(ProviderError):
                self.provider.complete(CompletionRequest(messages=CONVERSATION))


class TestAnthropicAdapter(unittest.TestCase):
    def setUp(self):
        self.provider = AnthropicProvider(info_for("anthropic"), api_key="k", model="claude")

    def test_system_prompt_is_hoisted(self):
        payload = self.provider._payload(CompletionRequest(messages=CONVERSATION, tools=[TOOL]))
        self.assertEqual(payload["system"], "be helpful")
        self.assertNotIn("system", [message["role"] for message in payload["messages"]])

    def test_tool_use_and_result_blocks(self):
        payload = self.provider._payload(CompletionRequest(messages=CONVERSATION))
        assistant = payload["messages"][1]
        self.assertEqual(assistant["content"][0]["type"], "tool_use")
        result = payload["messages"][2]
        self.assertEqual(result["role"], "user")
        self.assertEqual(result["content"][0]["type"], "tool_result")
        self.assertEqual(result["content"][0]["tool_use_id"], "call_1")

    def test_tool_schema_uses_input_schema(self):
        payload = self.provider._payload(CompletionRequest(messages=CONVERSATION, tools=[TOOL]))
        self.assertIn("input_schema", payload["tools"][0])

    def test_response_parsing(self):
        payload = {
            "model": "claude",
            "stop_reason": "tool_use",
            "content": [
                {"type": "text", "text": "writing"},
                {"type": "tool_use", "id": "t1", "name": "write_score", "input": {"path": "c.tap"}},
            ],
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }
        with mock.patch("tapscript.llm.providers.anthropic.request_json", return_value=payload):
            response = self.provider.complete(CompletionRequest(messages=CONVERSATION))
        self.assertEqual(response.text, "writing")
        self.assertEqual(response.tool_calls[0].name, "write_score")
        self.assertEqual(response.usage.input_tokens, 7)


class TestGeminiAdapter(unittest.TestCase):
    def setUp(self):
        self.provider = GeminiProvider(info_for("gemini"), api_key="k", model="gemini-2.5-flash")

    def test_roles_are_renamed(self):
        _system, contents = self.provider._convert(CONVERSATION)
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[1]["role"], "model")

    def test_unsupported_schema_keywords_are_dropped(self):
        spec = ToolSpec(
            name="t",
            description="d",
            parameters={
                "type": "object",
                "additionalProperties": False,
                "title": "ignored",
                "properties": {"a": {"type": "string", "default": "x"}},
            },
        )
        schema = spec.as_gemini()["parameters"]
        self.assertNotIn("additionalProperties", schema)
        self.assertNotIn("title", schema)
        self.assertNotIn("default", schema["properties"]["a"])

    def test_response_parsing(self):
        payload = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "hello"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
        }
        with mock.patch("tapscript.llm.providers.gemini.request_json", return_value=payload):
            response = self.provider.complete(CompletionRequest(messages=CONVERSATION))
        self.assertEqual(response.text, "hello")
        self.assertEqual(response.usage.output_tokens, 2)

    def test_blocked_prompt_raises(self):
        payload = {"promptFeedback": {"blockReason": "SAFETY"}}
        with mock.patch("tapscript.llm.providers.gemini.request_json", return_value=payload):
            with self.assertRaises(ProviderError) as caught:
                self.provider.complete(CompletionRequest(messages=CONVERSATION))
        self.assertIn("SAFETY", str(caught.exception))


class TestHostBridge(unittest.TestCase):
    def test_prompt_includes_tools_and_history(self):
        prompt = _render_prompt(CompletionRequest(messages=CONVERSATION, tools=[TOOL]))
        self.assertIn("be helpful", prompt)
        self.assertIn("write a waltz", prompt)
        self.assertIn("write_score", prompt)
        self.assertIn("Tool result", prompt)

    def test_reply_forms(self):
        self.assertEqual(_parse_reply('{"text": "hello"}'), ("hello", []))
        self.assertEqual(_parse_reply("just prose"), ("just prose", []))
        text, calls = _parse_reply('{"tool": "write_score", "arguments": {"path": "x.tap"}}')
        self.assertEqual(text, "")
        self.assertEqual(calls[0].name, "write_score")
        self.assertEqual(calls[0].arguments["path"], "x.tap")

    def test_fenced_reply(self):
        text, _calls = _parse_reply('```json\n{"text": "fenced"}\n```')
        self.assertEqual(text, "fenced")

    def test_command_mode_runs_a_subprocess(self):
        provider = build_provider(
            "host", host_mode="command", host_command="/bin/echo hello-from-host"
        )
        response = provider.complete(CompletionRequest(messages=[Message.user("hi")]))
        self.assertIn("hello-from-host", response.text)


class TestEchoProvider(unittest.TestCase):
    def test_always_available(self):
        ok, _detail = build_provider("echo").check()
        self.assertTrue(ok)

    def test_produces_valid_notation(self):
        from tapscript.notation import parse

        provider = build_provider("echo")
        response = provider.complete(
            CompletionRequest(messages=[Message.user("something sad in a minor key")])
        )
        notation = response.text.split("Running without a model provider, so this is the offline stub.")[-1]
        score = parse(notation)
        self.assertFalse(score.has_errors, [d.message for d in score.errors()])

    def test_calls_write_score_when_offered(self):
        provider = build_provider("echo")
        response = provider.complete(
            CompletionRequest(messages=[Message.user("write something")], tools=[TOOL])
        )
        self.assertEqual(response.tool_calls[0].name, "write_score")


class TestRegistry(unittest.TestCase):
    def test_unknown_provider_is_explained(self):
        with self.assertRaises(ProviderError) as caught:
            build_provider("nope")
        self.assertIn("available", str(caught.exception))

    def test_missing_key_is_explained(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as directory:
                os.environ["TAPSCRIPT_CONFIG_DIR"] = directory
                with self.assertRaises(ProviderError) as caught:
                    build_provider("openai")
        message = str(caught.exception)
        self.assertIn("OPENAI_API_KEY", message)
        self.assertIn("tapscript setup", message)

    def test_auto_select_prefers_a_configured_key(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"TAPSCRIPT_CONFIG_DIR": directory, "DEEPSEEK_API_KEY": "x"}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(auto_select(Paths()), "deepseek")

    def test_auto_select_falls_back_to_the_host_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"TAPSCRIPT_CONFIG_DIR": directory, "TAPSCRIPT_HOST_AGENT": "claude-code"}
            with mock.patch.dict(os.environ, env, clear=True):
                from tapscript.runtime.capabilities import probe

                self.assertEqual(auto_select(Paths(), probe(refresh=True)), "host")


if __name__ == "__main__":
    unittest.main()
