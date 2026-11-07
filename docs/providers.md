---
title: Model providers
description: How to run JJV on public model APIs with your own keys, and how to send several models' answers through the panel.
status: draft
updated: 2026-11-06
---

# Model providers

This page is optional. Native JJV needs none of it: `python -m jjv.cli review ...` runs on the Claude Agent SDK, with no settings file or provider keys. See [Ways to run JJV](../README.md#ways-to-run-jjv).

The harness assumes nothing about who runs it. Every provider, Claude included, is reached through its public API with your own key. Nothing here has run against a live provider yet; the tests use simulated replies.

## Setup

1. Copy the settings file: `cp docs/providers.example.json ~/.jjv/providers.json`.
2. Fill in a model name and the price per million tokens for each provider you use. Prices are required, because these APIs report tokens rather than dollars, so a spending limit cannot work without them. Check them against each provider's price list.
3. Put keys in your environment, never in the settings file: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`.
4. Run `pip install -r requirements-live.txt`.

## Ask several models, then run the panel

```bash
python -m jjv.cli review plan.md --panel "Thinkers Panel" \
  --consult claude,openai,xai,gemini --consult-usd 2
```

Each model answers first. Their answers are shuffled, labeled "Model 1", "Model 2", and added to the subject, so the Judges can weigh them without knowing the brand. The panel then runs as usual. A run saves `<run id>.opinions.json` beside its record, with each model's words and label. If the worst case would pass `--consult-usd`, nothing is sent.

Your content goes to every provider you name, under that provider's terms.

## Run the Judges on a provider

```bash
python -m jjv.cli review plan.md --panel "Thinkers Panel" --judge-provider openai
```

Without `--judge-provider`, Judges run on the local Claude Agent SDK, as before. `--repo` works only with that backend, because the guard that keeps file tools inside a repository is built on its hooks. Judges on a provider use one model for the whole panel, and read only the subject.

## Add another service

Any service that speaks the OpenAI chat format needs only settings:

```json
{"local": {"format": "openai", "model": "my-model", "api_key_env": "MY_KEY",
           "base_url": "http://localhost:8080/v1/chat/completions",
           "usd_per_mtok_in": 0.01, "usd_per_mtok_out": 0.01}}
```

`base_url` must be https, except on localhost, so a key is not sent in the clear. Optional fields are `limit_field`, the name of the service's output limit, and `max_output_tokens`.

## MCP server

The server lets Claude Code, Claude Desktop and other MCP clients call JJV. It runs on your machine over stdio:

```bash
pip install -r requirements-live.txt
python -m jjv.mcp_server
```

Most clients take a command and its environment, for example:

```json
{"mcpServers": {"jjv": {"command": "/path/to/.venv/bin/python",
                        "args": ["-m", "jjv.mcp_server"],
                        "cwd": "/path/to/judge_jury_voter",
                        "env": {"JJV_MCP_PAID": "0"}}}}
```

**Free tools** never call a model: `list_panels`, `list_archetypes`, `list_providers`, `get_limits`, `get_run`, `explain_run`, and `settle`, which replays the bargain on a saved run at a different budget.

**Paid tools** are `review` and `generate`. An AI client would be choosing when to spend, so they are off unless you set `JJV_MCP_PAID=1`. Each returns a job id at once, and `get_run` reports progress. `review` takes `consult_models` to ask several providers first.

| Setting | Default | Meaning |
|---|---|---|
| `JJV_MCP_DEFAULT_USD` | 1 | Limit for a run that names none |
| `JJV_MCP_MAX_USD` | 5 | Most any one run may be given |
| `JJV_MCP_TOTAL_USD` | 20 | Most the server may commit before it restarts |
| `JJV_MCP_MAX_JOBS` | 2 | Runs at once |
| `JJV_MCP_REPOS` | none | `name=/path` pairs Judges may read |
| `JJV_JUDGE_PROVIDER` | none | Run Judges on this provider |
| `JJV_PROVIDERS_FILE` | `~/.jjv/providers.json` | Models and prices |
| `JJV_STORE` | `~/.jjv/runs` | Run records |

A client cannot change these. Limits are soft, because a model call in flight finishes, so a run can pass its limit somewhat. The total allowance resets when the server restarts. Links from a client must resolve to public addresses, though a name that changes address between the check and the fetch can still get past this. Findings can quote the subject, so a client should treat them as data, not instructions.

## For developers

`jjv/harness.py` is the layer the CLI uses, and it is where an MCP server or web view should connect: `load_providers`, `consult`, `with_opinions` and `make_backend`. Each backend has the same `ask(Request) -> Reply`, so it can be passed to `Orchestrator`.
