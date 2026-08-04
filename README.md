# Plainspoken (working title)

Plain-English narration and safety flags for AI-generated code changes, built as a Claude Code hook. See PRD.md for the full product spec.

## What it does

- **Narrator**: plain-English explanations of the consequence of every change, appended to `.plainspoken/CHANGELOG.plain.md`. Rapid consecutive edits to the same file narrate ONCE as a settled outcome (burst narration) instead of one entry per keystroke. User-facing changes render in full; internal churn collapses into a one-line "Behind the scenes" summary per session block
- **Inspector**: a local rule engine checks every change for dangerous patterns (hardcoded secrets, removed auth, wildcard CORS, destructive database operations, and more). Hits get a plain-language warning pinned to the top of the changelog AND surfaced back into the Claude Code session so Claude itself relays the flag and offers the fix
- **Tutor**: when a session ends, a digest is written: what got built, the most important warning, and one concept worth understanding
- **Subagent coverage**: edits made by subagents (Task/Agent tool workers, including ones in isolated git worktrees) are narrated too, labeled "background helper" in the feed. Subagent completions never write digest fragments; only the main session's end does

Everything is local except the model calls (Claude Haiku via your API key).

## Install into a test project

1. Copy the two pieces into the target project root:
   - `.claude/settings.json` (or merge the `hooks` block into your existing one)
   - `.plainspoken/plainspoken.py`
2. Install the one dependency:
   ```
   pip install anthropic
   ```
3. Make sure `ANTHROPIC_API_KEY` is set in the environment Claude Code runs in.
4. Start a Claude Code session in the project and ask it to build something. Watch `.plainspoken/CHANGELOG.plain.md` fill up.

## Files it creates (all inside `.plainspoken/`)

| File | What it is |
|------|------------|
| events.jsonl | Append-only source of truth: every change, recap, and digest event |
| findings.json | Warning lifecycle state: open and resolved findings with timestamps |
| CHANGELOG.plain.md | The human-readable view, rebuilt in full from the two files above on every update. Open warnings pinned, recently resolved listed, then the feed |
| concepts.json | Tutor state: which concept areas keep coming up |
| errors.log | Handler errors (the hook always fails open and never blocks your session) |

If the markdown view ever looks wrong, rebuild it any time with:
```
python3 .plainspoken/plainspoken.py render
```

Warnings resolve themselves: when a later change removes the pattern that triggered a finding (or rewrites the file without it), the finding moves from Open warnings to Recently resolved automatically.

## Design notes

- The rule engine runs before any API call and only checks content that was ADDED by the change, so pre-existing issues do not re-flag on every edit.
- Any handler error exits 0 silently. Narration must never break the coding session.
- Warning severities: fire hazard (act now), worth fixing (soon), keep an eye on (informational).

## Settings (environment variables)

| Variable | Values | Effect |
|----------|--------|--------|
| PLAINSPOKEN_BACKEND | auto (default), api, cli | How narration calls the model. `api` uses the Anthropic API (needs ANTHROPIC_API_KEY, pay-as-you-go). `cli` shells out to `claude -p`, which runs on your Claude subscription with no API key or separate billing. `auto` uses the API when a key is set, otherwise the CLI |
| PLAINSPOKEN_DETAIL | brief, standard (default), full | How rich each change entry is: brief is two sentences; standard adds a headline, "what this means," and an analogy; full also adds a "worth knowing" note when there is one |
| PLAINSPOKEN_MODE | economy | Defers all narration to one batched call at session end (warnings still fire in real time). Batched entries are always brief. |
| PLAINSPOKEN_BURST | off | Disables burst narration, restoring one narration per edit. Bursts are ON by default (except in economy mode) |
| PLAINSPOKEN_BURST_WINDOW | seconds (default 120) | How long a file's burst must go quiet before it narrates. Bursts always settle at session Stop regardless |

Subscription-only users (no API key): it works out of the box via the CLI backend; narration just runs a bit slower per change and draws from your subscription usage limits. The `pip install anthropic` step is only needed for the API backend.

## Tuning ideas once it is running

- Add rules to the `RULES` list in plainspoken.py (id, severity, plain-English name, regex)
- Adjust `MAX_SNIPPET_CHARS` if narrations miss context on big files
- Add file-type filters if you want to skip narrating things like lockfiles or generated assets
