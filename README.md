# Segundo Cerebro

A single-user personal assistant ("second brain"). You talk to it on
**Telegram**; it captures and retrieves notes in an **Obsidian** vault
that lives on an always-on AWS server. The vault syncs to your local
Obsidian, so anything the bot writes shows up on your machine within
minutes — and anything you edit locally flows back.

Built with **LangGraph** to orchestrate a small set of agents, **Claude**
as the model, and an evaluation harness that gates changes to the router.

> The design document ([`DISEÑO.md`](./DISEÑO.md), in Spanish) is the
> source of truth for architecture decisions and their rationale.

---

## What it does

You send a message; a **Router** (Claude Haiku) classifies the intent and
routes it to one node:

| You send… | Intent | What happens |
|---|---|---|
| *"save this idea: use a webhook instead of polling"* | `capturar` | The **Archivista** (Claude Sonnet) picks a title and tags, writes `00-inbox/use-a-webhook-instead-of-polling.md` with front-matter, and indexes it for semantic search. |
| *"what had I saved about webhooks?"* | `consultar` | The **Bibliotecario** (Sonnet, **read-only**) runs semantic search (Chroma + Voyage embeddings) and answers with the relevant notes — it finds them even if you used different words. |
| *"buy bread next time you go to the supermarket"* | `tarea` | The **Tareas** node adds `- [ ] bread` to `20-tareas/compras.md`. *"already bought the bread"* checks it off. |
| *"remind me to call the bank on Tuesday at 10"* | `recordatorio` | The **Recordatorio** node resolves the time (in your timezone) and schedules it. On Tuesday at 10, the bot messages you. Recurring works too: *"every Monday remind me to send the invoice"*. |
| a **photo** (compressed or "sent as file") | `imagen` | The webhook downloads it to `30-imagenes/`, Claude vision writes a note with a description + a transcription of any visible text + an embedded link, and indexes it. |
| a **voice note** | — | Groq (Whisper) transcribes it; the text then flows through the graph exactly as if typed. |
| something unclear (*"ok"*, *"hey"*) | `ambiguo` | It asks you to rephrase instead of guessing. |

### Proactive behaviour

The bot doesn't only respond — a background loop in the app process does:

- **Reminders** fire at their time (recurring ones reschedule themselves).
- **Morning briefing**: once a day (default 8 AM local), a short message
  with what's due today and your open task lists. If there's nothing, it
  stays quiet.
- **Weekly digest** (default Monday 9 AM): the **Digestor** walks the
  vault and sends a recap — what you captured this week (synthesised by
  Claude), what's been aging in the inbox, the state of your lists. It
  also drops the recap as a note in `90-sistema/`.

### Commands (no LLM tokens)

`/ayuda` · `/estado` · `/costos` (stub) ·
`/corregir <intent>` — reclassify the last message and feed the eval set ·
`/recordatorios` · `/cancelar <id>` ·
`/lista` · `/lista <name>` ·
`/reindexar` — force a search-index sync ·
`/digest` — run the weekly recap now

---

## Architecture

```
Telegram ──> FastAPI webhook ──> auth (chat id + secret token)
                                      │
                                      ▼
                          LangGraph graph (SQLite checkpointer)
                                      │
        Router (Haiku) ── classifies ─┤
                                      ├─ capturar / imagen ─> Archivista (Sonnet)
                                      ├─ consultar          ─> Bibliotecario (Sonnet, read-only)
                                      ├─ tarea              ─> Tareas
                                      ├─ recordatorio       ─> Recordatorio
                                      └─ comando / ambiguo  ─> direct reply

        Budget brake: every run stops at 15 graph steps or 50k tokens
        and returns a partial summary.

Background loops (same process, no EventBridge):
  • proactive: reminders + morning briefing + weekly digest, every 60s
  • reindex: keep Chroma in sync with the vault, every ~5 min
```

| Layer | Choice |
|---|---|
| Orchestration | LangGraph, typed state with Pydantic |
| Model | Claude — Haiku (`claude-haiku-4-5`) for the Router, Sonnet for everything else and vision |
| Interface | FastAPI + a single Telegram webhook |
| Vault access | A **custom MCP server** (`src/mcp_obsidian/`), spoken to over stdio as a subprocess |
| Semantic search | Chroma (embedded) + Voyage AI embeddings (`voyage-3.5-lite`) |
| Audio | Groq `whisper-large-v3-turbo` (Claude's API doesn't take audio) |
| Short-term memory | LangGraph checkpointer over SQLite — lets a run pause (human-in-the-loop) and resume in a later message |
| Device sync | Syncthing (server ⇄ local Obsidian), P2P and end-to-end encrypted |
| Infra | One EC2 instance (Amazon Linux, Docker Compose: app + Caddy + Syncthing), Caddy terminates HTTPS via `sslip.io` + Let's Encrypt |
| CI/CD | GitHub Actions — lint + type-check + tests on every push; deploy to the instance on push to `main`, authenticated with **OIDC** (no static AWS keys) |

### The vault

```
00-inbox/     everything captured lands here first
10-notas/     permanent notes
20-tareas/    one note per list, markdown checkboxes  (compras.md, farmacia.md, …)
30-imagenes/  the original photo + a .md note with its description/transcription
90-sistema/   logs and system state (weekly digests, reminders.jsonl, …)
```

---

## Design principles

- **Fewest agents that cover the use cases.** Each extra agent is more
  tokens, more latency, more surface for error. New nodes only get added
  when the evaluation shows the current graph mishandles something.
- **Safety enforced in code, not prompts.** The Archivista has no delete
  or overwrite tool; the Bibliotecario has no write tool at all. A prompt
  can be argued with; a missing function can't.
- **Everything external is mocked in tests.** No test spends money or
  needs the network. The one deliberate exception is the router eval.
- **All state that matters lives in the vault** (as markdown or small
  JSONL files), so it syncs to your devices and you can read or edit it
  in Obsidian — no separate database.

---

## Evaluation

The Router is the node everything depends on, so it has a regression
gate. `tests/eval/mensajes.jsonl` holds ~30 labelled messages;
`tests/eval/evaluar.py` runs each one through the **real** Router and
scores accuracy against `tests/eval/baseline.json`. A run fails if
accuracy drops more than 5 points below the baseline.

It runs in CI (`.github/workflows/eval.yml`) on any PR that touches the
router, its prompt, or the state schema — and on demand. It costs a few
cents per run, so it needs `ANTHROPIC_API_KEY` as a repository secret.

```bash
uv run --env-file .env python -m tests.eval.evaluar
uv run --env-file .env python -m tests.eval.evaluar --actualizar-baseline
```

The set grows from real usage: `/corregir` in Telegram writes each
correction to the vault, and `tests/eval/incorporar.py` merges those in.

---

## Running locally

Python 3.12, managed with [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras --dev
cp .env.example .env      # then fill in the values
uv run ruff check .
uv run mypy
uv run pytest             # ~95 tests, all mocked
```

To run the bot against a real Telegram bot you need a public HTTPS URL
for the webhook (ngrok or similar for local dev). See `.env.example` for
every variable; the essentials are `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
`GROQ_API_KEY`, the three `TELEGRAM_*` values, and the vault/index paths.

## Deployment

`infra/template.yaml` (CloudFormation) provisions the EC2 instance, the
elastic IP, the ECR repository, the IAM roles, and the GitHub OIDC
provider. Secrets live in **AWS SSM Parameter Store** as `SecureString`
under `/segundo-cerebro/`, never in the repo. Access to the instance is
via **SSM Run Command** — there is no SSH.

Push to `main` → GitHub Actions runs the test job, then builds the image,
pushes it to ECR, and tells the instance (over SSM) to re-authenticate to
ECR, pull, and restart.

---

## Privacy

This is a personal assistant, so data does leave the machine — a
conscious trade-off, documented in `DISEÑO.md` §Parte 7:

- **Claude (Anthropic)** sees each message, each photo, and — for the
  weekly digest — a batch of note titles and snippets.
- **Voyage AI** sees the text of every note (to compute embeddings).
- **Groq** sees the audio of every voice note.
- **Telegram** carries every message (bot chats are not end-to-end
  encrypted).

The vault itself stays on your EC2 instance (EBS, encrypted at rest) and
on your own devices via Syncthing; no third party sees the vault as a
whole. Secrets are in SSM, and CI uses OIDC rather than stored keys.

Only one Telegram chat is authorised — any other sender is ignored
silently, without logging the content.

---

## Status

Phases 0–13 are done and running in production 24/7; the weekly Digestor
is the current addition. Known gaps and next steps are tracked in
`DISEÑO.md` (roadmap section) — notably a citations mode for the
Bibliotecario, real cost tracking for `/costos`, and Google Calendar
integration.
