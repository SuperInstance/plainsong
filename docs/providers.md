# Providers

A provider is wherever your model comes from. Plainsong treats that as
configuration, not as a dependency: the same agent code runs against a hosted
API, a server on your laptop, or the agent that launched you.

The compiler never calls a provider. If you only want to turn notation into
sound, you can skip this page entirely.

## Connecting one

```bash
plainsong setup
```

Pick from the list, paste a key, and it makes a test call before saving. To skip
the questions:

```bash
plainsong setup deepseek          # a specific provider
plainsong setup -y                # accept whatever is already detected
```

## What is in the catalogue

```bash
plainsong providers               # everything, and whether it is ready
plainsong providers --check       # make a real call with the current settings
```

| Provider | id | Key from |
|---|---|---|
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` |
| xAI (Grok) | `xai` | `XAI_API_KEY` or `GROK_API_KEY` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| Groq | `groq` | `GROQ_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |
| Together | `together` | `TOGETHER_API_KEY` |
| Fireworks | `fireworks` | `FIREWORKS_API_KEY` |
| Cerebras | `cerebras` | `CEREBRAS_API_KEY` |
| Azure OpenAI | `azure` | `AZURE_OPENAI_API_KEY` + a base URL |
| Ollama | `ollama` | nothing — local |
| LM Studio | `lmstudio` | nothing — local |
| vLLM, llama.cpp, anything OpenAI-shaped | `vllm` | optional |
| The agent you are already running inside | `host` | nothing — see [host-bridge.md](host-bridge.md) |
| Offline stub | `echo` | nothing — no network |

`echo` is not a model. It returns valid notation deterministically so the agent
loop, the interfaces and the tests can run with no connection at all. It is what
gets used if nothing else is available, and it says so.

## Where keys come from

In order:

1. A key passed on the command line.
2. The environment variable(s) the catalogue lists for that provider.
3. `credentials.toml` in your config directory, written by `plainsong setup`.

Keys are never written into `config.toml`, which is meant to be shareable and is
often committed. The credentials file is separate and is created readable only
by you.

```bash
plainsong config path            # where config.toml lives
plainsong doctor                 # shows which source each key came from
```

## Choosing without configuring

With no provider set, one is chosen at the moment you need it:

1. Any provider whose key is already in your environment.
2. The host agent, if Plainsong can tell it is running inside one.
3. A local server that is actually listening — Ollama, LM Studio, vLLM.
4. The offline stub.

Nothing hard-fails for want of a model. `plainsong doctor` prints what
auto-selection would pick right now.

## Overriding per run

```bash
plainsong agent --provider ollama --model qwen2.5 "write a jig"
PLAINSONG_PROVIDER=groq plainsong agent "..."
```

## Adding a provider

Most services speak the OpenAI chat-completions shape. Adding one of those is a
data change — drop a `providers.json` into your config directory:

```json
{
  "providers": {
    "housemodel": {
      "label": "House model",
      "api": "openai",
      "base_url": "http://10.0.0.5:8000/v1",
      "env": ["HOUSE_API_KEY"],
      "api_key_optional": true,
      "default_model": "house-7b",
      "models": ["house-7b", "house-34b"],
      "local": true
    }
  }
}
```

It appears in `plainsong providers` immediately. No code, no release.

Fields:

| Field | Meaning |
|---|---|
| `api` | Which wire format: `openai`, `anthropic`, `gemini`, `host`, `echo` |
| `base_url` | Endpoint root, without a trailing slash |
| `env` | Environment variables to look in for a key, in order |
| `api_key_optional` | True for local servers that accept anything |
| `needs_base_url` | True when the URL must be supplied per install, as with Azure |
| `auth_header` | Defaults to `Authorization: Bearer`; Azure uses `api-key` |
| `headers` | Extra headers sent with every request |
| `query_params` | Appended to the URL, such as an API version |
| `tools`, `streaming` | Whether the service supports them |

A service with a genuinely different wire format needs an adapter — about 120
lines, see `plainsong/llm/providers/`. Register it in `ADAPTERS` and it becomes
available to every catalogue entry naming that shape.

## What an adapter has to do

Adapters translate to and from one neutral set of types (`plainsong/llm/types.py`)
so that nothing above them cares which service answered:

- messages with roles, including tool calls and tool results
- tools described in JSON Schema
- a reply carrying text, tool calls, a finish reason and token usage
- errors that say which provider failed, whether retrying is worth it, and what
  the user should do about it

Retries with backoff, timeouts and proxy support live in the shared transport,
not in each adapter.

## Cost and privacy

Plainsong sends the model your prompt, the notation it is working on, and the
results of the tools it calls — which can include file contents from the
workspace. If that matters, use a local provider (`ollama`, `lmstudio`, `vllm`)
or none. Nothing is sent anywhere unless you run the agent.
