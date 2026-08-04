# Product Requirements Document: Plainspoken (working title)

**Version:** 0.3
**Author:** Elias Bou Zeid
**Date:** July 30, 2026
**Status:** Working draft; reflects the built MVP starter plus trust-boundary hardening (tranche 1: redaction, injection defenses, deterministic fallbacks) and the event-sourced storage layer with warning lifecycle (tranche 2). Next planned tranche: burst narration.

---

## 1. Overview

Plainspoken is a Claude Code companion that translates AI-generated code changes into plain, consequence-oriented English for non-technical builders ("vibe coders"). It runs invisibly inside the coding session via Claude Code hooks, narrates every accepted change, flags dangerous ones, and gradually teaches the user how their own app works.

The personality of the product: the friend who reads the contract before you sign it.

## 2. Problem Statement

AI coding tools have made software creation accessible to people who have never written code. These builders:

- Accept edits and generated files without understanding what they do
- Cannot distinguish a cosmetic change from one that exposes their database
- Have no mental model of their own application (what data it stores, who can access it, what services it talks to)
- Learn nothing from the process, so they remain dependent and vulnerable

Existing tools (diff summarizers, PR review bots, security scanners) are all written for developers. They describe mechanics ("refactored auth middleware to use JWT validation") rather than consequences ("your app now remembers who is logged in"). No product currently serves the comprehension and safety needs of the non-technical builder at the moment the change happens.

## 3. Target User

**Primary persona: The Vibe Coder**

- Non-engineer building a real project with Claude Code (or similar)
- Smart, capable, motivated, but has never read code
- Examples: a founder prototyping a SaaS idea, a small business owner building an internal tool, a designer shipping a portfolio app
- Accepts most AI suggestions on trust
- Fears: breaking the app, leaking customer data, getting hacked, looking foolish
- Wants: confidence, awareness, and slow, painless learning

**Secondary persona: The Semi-Technical Reviewer**

- A slightly more technical friend, cofounder, or consultant who periodically checks in on the vibe coder's project and wants a fast, readable history of what changed and what to worry about.

## 4. Goals

1. Every accepted code change gets a one-to-two sentence plain-English explanation focused on consequences, not mechanics
2. Dangerous changes are flagged immediately in language a non-engineer acts on
3. Over time, the user builds an accurate mental model of their own app without studying
4. Zero workflow friction: no new tool to open, no approval clicks, no configuration beyond initial install

## 5. Non-Goals (v1)

- Supporting IDEs or agents other than Claude Code
- Blocking or reverting changes (narrate and warn only; the user stays in control)
- Multi-user, teams, auth, billing, or any hosted service
- Replacing real security review for production applications
- Explaining code the user wrote themselves (scope is AI-generated changes)

## 6. Product Principles

1. **Consequences, never mechanics.** "Your app can now email users" beats "integrated the Resend SDK."
2. **Silence is a feature.** The inspector speaks only when something is wrong. No noise, no cry-wolf fatigue.
3. **Meet them in their world.** Analogies from everyday life (rooms, doors, locks, mail) over programming vocabulary.
4. **Teach by osmosis.** Learning emerges from the user's own project history, never from a curriculum.
5. **Local and private by default, with an explicit trust boundary.** Plainspoken stores its history locally. When narration is enabled, selected and redacted portions of changes are sent to the configured model provider. Plainspoken never intentionally sends detected credentials, sensitive files (environment files, keys, credential stores), or unchanged surrounding content, and its error logs never contain raw hook payloads. Changed content is always treated as untrusted data at the model boundary, never as instructions.
6. **Respect what the user already brought.** Explain the machine's decisions, not the human's. Never define a well-known service the user chose themselves (Stripe, Google sign-in, an email provider); spend the words on what is non-obvious: what the app handles versus the service, what the app knows or never sees, what could surprise them later. This is the difference between a helpful narrator and a condescending one, and it is the product's single biggest tone risk.
7. **Detail must earn its place.** Every sentence in an entry should tell the user something they did not already know. Optional sections (analogies, "worth knowing" notes) appear only when genuinely non-obvious; padding trains users to skim, and a skimmed safety product is a failed one.

## 7. Feature Requirements

### Layer 1: The Narrator (always on)

| ID | Requirement | Priority |
|----|-------------|----------|
| N1 | Fire on every successful Edit or Write tool call in Claude Code via a PostToolUse hook | P0 |
| N2 | Generate a plain-English explanation of the change using a fast, cheap model (Claude Haiku) | P0 |
| N3 | Explanation must describe user-visible or data-level consequences, never implementation mechanics | P0 |
| N4 | Append each entry to a human-readable log (CHANGELOG.plain.md) and a structured log (events.jsonl) in the project | P0 |
| N5 | Include a plain-language "affects" tag per entry: looks, data, access, money, messages, speed, plumbing | P1 |
| N6 | Three detail levels via PLAINSPOKEN_DETAIL (brief / standard / full): brief is two sentences; standard adds a headline, "what this means," and a conditional analogy; full adds a conditional "worth knowing" note. Output token caps scale with level (150/300/500). Default: standard | P0 (built) |
| N7 | Pre-API skip filter: lockfiles, images, minified assets, whitespace-only edits, and changes under a meaningful-size threshold are logged locally without a model call | P0 (built) |
| N8 | Economy mode via PLAINSPOKEN_MODE=economy: no per-change API calls; raw change stubs accumulate and one batched call at session end narrates everything (brief format). Inspector warnings still fire in real time | P0 (built) |
| N9 | Batch rapid successive edits to the same file within a short window into one narration (default mode) | P2 |

### Layer 2: The Inspector (speaks only when needed)

| ID | Requirement | Priority |
|----|-------------|----------|
| I1 | Run deterministic rule checks on every change before any LLM call (regex/AST-lite, no API cost) | P0 |
| I2 | Rule set v1: hardcoded secrets and API keys, credentials in code, disabled or removed auth checks, wildcard CORS, SQL string concatenation, destructive database operations, new external network destinations, new dependencies | P0 |
| I3 | On rule hit, run a second LLM pass to write the warning in plain language with a concrete "what could happen" and "what to ask Claude to do" | P0 |
| I4 | Warnings are visually distinct in the log (pinned section at top of CHANGELOG.plain.md) and surfaced back into the Claude Code session as hook output context | P0 |
| I5 | Severity levels: "stop and check" (act now), "fix soon", "for awareness". Severity and certainty are separate concepts: warnings state what the rule confirmed versus what is inferred, and context-dependent findings say so ("this appears to remove a check; Plainspoken cannot confirm another one covers it") | P0 (built: labels; certainty language: prompt-level) |
| I6 | LLM-based semantic check for risks rules cannot catch (e.g. authorization logic that looks present but is wrong) | P2 (never allowed to block; see open question 1) |
| I7 | Redaction before any model call: secret-shaped content (matched credentials, cloud keys, payment keys, private key blocks) is replaced with typed placeholders in everything that leaves the machine, including economy-mode stubs. Secret-class findings NEVER reach the model at all; their warnings are built entirely from controlled rule text. Files with sensitive paths (.env, key files, credential stores) never have content sent to the model | P0 (built) |
| I8 | Prompt-injection defense: changed content is delimited and declared untrusted data in both prompts; the additionalContext fed back into the Claude Code session uses ONLY controlled template text (never model prose, never file content), so nothing injectable can ride that channel | P0 (built) |
| I9 | Deterministic fallback: every rule carries a controlled plain-language "ask Claude this" line, and a template warning is emitted whenever the model call fails, so an API outage can never silence a confirmed finding. Narration failures likewise preserve the event with a placeholder instead of dropping it | P0 (built) |

### Layer 3: The Tutor (slow burn)

| ID | Requirement | Priority |
|----|-------------|----------|
| T1 | On session end (Stop hook), generate a session digest: what got built, what changed, one thing worth understanding | P0 |
| T2 | Track recurring concepts across sessions in a local concepts.json (e.g. "authentication touched 5 times") | P1 |
| T3 | When a concept crosses a repetition threshold, include a two-minute plain-English explainer of how it works in this specific project | P1 |
| T4 | Maintain a growing "Your App, Explained" document: a living plain-language description of the whole application | P2 |

### Layer 4: The Map (future, post-MVP)

A visual "floor plan" of the app rendered from a maintained JSON model: pages/screens, data stores, external services, and access boundaries. Changes highlight on the map. Explicitly out of scope for MVP; the JSON model (appmodel.json) may be stubbed early since Layers 1-3 can populate it incrementally.

## 8. Architecture

### 8.1 Components

1. **Hook config** (.claude/settings.json in the target project): registers PostToolUse and Stop hooks
2. **Hook handler script** (plainspoken.py): a single Python script invoked by Claude Code; receives event JSON on stdin
3. **Rule engine**: pure-Python checks inside the handler, no network required
4. **Model client**: calls the Anthropic API (claude-haiku-4-5) using ANTHROPIC_API_KEY from the environment
5. **Local store** (.plainspoken/ directory in the project):
   - events.jsonl: structured record of every narrated change
   - CHANGELOG.plain.md: the human-readable feed, warnings pinned at top
   - concepts.json: tutor state
   - appmodel.json: stub for the future map

### 8.2 Event flow

```
Claude Code accepts an Edit/Write
        |
        v
PostToolUse hook fires, JSON on stdin
  (tool_name, tool_input incl. file_path and
   old/new content, session_id, cwd)
        |
        v
plainspoken.py narrate
  1. Extract change (old_string/new_string for Edit,
     content for Write), cap size
  2. Run rule engine (offline, instant)
  3. Call Haiku: narration (+ warning copy if rules hit)
  4. Append to events.jsonl and CHANGELOG.plain.md
  5. If warning: emit additionalContext back to the
     session so Claude itself sees the flag
        |
        v
User keeps working; log accumulates silently

On session end: Stop hook -> plainspoken.py digest
  -> session summary appended, concepts.json updated
```

### 8.3 Key decisions

- **Language: Python 3**, stdlib plus the anthropic package. Widely available, easy for others to install.
- **Change source: tool_input, not git.** The hook payload already contains old and new content, so the tool works even in projects without git. Git diff is a fallback enhancement.
- **Fail open.** Any handler error exits 0 silently and logs to .plainspoken/errors.log. The narrator must never break or slow the user's coding session. Hook timeout set to 30s; API calls capped shorter.
- **Cost posture (built).** Four stacked measures: (1) skip filter kills noise before any API call; (2) the deterministic rule engine gates the expensive inspector prompt; (3) snippets send only the change (BEFORE trimmed to 600 chars, AFTER capped at 3,000) with per-call output caps; (4) economy mode collapses a whole session's narration into one batched call, leaving only rule-triggered warnings real-time. System prompts are intentionally below prompt-caching minimums; brevity is the caching strategy.
- **Settings surface.** Two environment variables: PLAINSPOKEN_DETAIL (brief/standard/full) and PLAINSPOKEN_MODE (economy). No config file until users ask for one.

## 9. Prompt Design (summary)

**Narrator system prompt core rules:**

- Audience has never read code; never use programming vocabulary (no "function," "endpoint," "middleware," "refactor")
- Describe what the app can now do, show, store, or allow that it could not before, or what behavior changed
- Never define or explain a well-known service the user chose (payment platforms, email services, sign-in providers); explain only the non-obvious division of responsibility: what the app does versus the service, what the app knows or never sees, what could surprise them later
- Analogies ("How it works" section) appear only when the mechanism is genuinely non-obvious to a non-engineer (e.g. data persistence: yes; a new page existing: no)
- If the change is purely internal housekeeping, say so in under ten words ("Internal tidying, nothing you'd notice.")
- Structured formats by detail level (see N6); no code in replies; every reply ends with an AFFECTS tag for the events log
- Never praise the change or reassure; describe neutrally

**Inspector prompt core rules:**

- Structure: what happened, what could go wrong in concrete real-world terms, exactly what to paste back to Claude to fix it
- Threat described as a scenario ("anyone who finds your site address could download your customer list"), never as a CVE or jargon term
- No hedging language that buries the severity

Full prompt text lives in the handler script and is versioned with it.

## 10. UX Surfaces (MVP)

1. **CHANGELOG.plain.md**: the product, for now. Warnings pinned at top, then a reverse-chronological feed grouped by session. Rendered nicely by any markdown viewer, and Claude Code can display it on request.
2. **In-session context**: warnings flow back into the Claude Code conversation via hook output, so the assistant itself acknowledges the flag and can offer the fix immediately.
3. **Terminal status line**: hook statusMessage shows a subtle "Narrating change..." so the user knows it is alive.

Post-MVP: localhost dashboard reading events.jsonl (feed, filters by "affects" tag, the map).

## 11. Milestones

**M1: Narrator (target: 1 evening)**
Hook config plus handler; every edit produces a plain-English line in CHANGELOG.plain.md. Success: a non-technical friend reads the log of a session and can accurately say what got built.

**M2: Inspector (target: 1 week)**
Rule engine with the v1 rule set plus plain-language warning generation and in-session surfacing. Success: seeded test project with 10 planted issues; 8+ flagged with zero false alarms on a clean session.

**M3: Tutor (target: 2-3 weeks)**
Stop-hook session digests and concept tracking. Success: after five sessions, the digest history reads like a coherent story of the project.

**M4: Package (target: 1 month)**
One-command install script, README, publish on GitHub. Success: a stranger installs it in under five minutes.

## 12. Success Metrics (side-project honest)

- You personally leave it enabled on your own projects after week two
- One real vibe coder uses it for a week and can explain their own app's data flow afterward
- Inspector catches at least one genuine issue in the wild
- Users become accurately informed, not overconfident: a user can describe a change without becoming more confident than the evidence supports. Wrong confidence is worse than admitted uncertainty
- GitHub stars are a bonus, not the goal

## 12.5 Adopted Roadmap (from external review, in order)

1. **Tranche 1 (built):** pre-model redaction, sensitive-path exclusion, prompt-injection defenses, controlled additionalContext, deterministic warning and narration fallbacks, severity rename
2. **Tranche 2 (built):** events.jsonl is the append-only source of truth; CHANGELOG.plain.md is a rendered view rebuilt in full from events + findings on every update (no in-place markdown surgery). Warning lifecycle: stable finding identity (rule + file), dedup of repeat hits (refresh last_seen, never duplicate), resolution on positive evidence only (an edit whose removed content matched the rule while the replacement does not, or a full-file rewrite without the pattern), resolved findings move to a "Recently resolved" list, and the pinned section shows only open findings. Atomic writes (temp + rename), cross-process file locking, malformed-line recovery on the event log, and a manual `render` command to rebuild the view
3. **Tranche 3:** burst narration promoted from N9: group ordinary edits by file relationship, time window, and task boundary; narrate the burst once; warnings stay immediate. Drop the per-edit status message; show status only for warnings, delays, or ill health
4. **Deferred to packaging (M4):** install/doctor/disable/uninstall commands, rebuild-view command, evaluation fixture suite, edge cases (existing hook configs, nested repos, concurrent sessions, rate limits). Legitimate, but adopting them now turns a side project into a product team; gate on two weeks of personal daily use first
5. **Explicitly rejected for now:** none of the review was wrong; items above are sequenced, not dismissed

## 13. Risks and Open Questions

| Risk | Mitigation |
|------|------------|
| Narration noise: LLM-heavy sessions make hundreds of edits | Built: skip filter and economy mode. Remaining: same-file debounce (N9) |
| Wall-of-text feed: at full detail a 30-edit session stops getting read | v1.1 idea: collapse the feed by feature using the affects tags and file grouping ("everything related to signups") |
| Condescension: explaining things the user already knows erodes trust as fast as false alarms | Built: known-service rule and conditional sections in the narrator prompt; validate in real testing |
| Prompt injection: file content manipulating the narrator, or riding additionalContext into the session | Built: untrusted-data framing and delimiters in both prompts; additionalContext restricted to controlled template text |
| Secret leakage: the tool sending detected credentials to the API while warning about them | Built: redaction of all outbound content, template-only warnings for secret findings, sensitive-path exclusion |
| Stale pinned warnings: fixed issues remain pinned, eroding trust | Built: warning lifecycle with dedup and evidence-based resolution; the rendered view shows only open findings |
| False alarms erode trust faster than anything | Rules tuned conservative; "keep an eye on" tier absorbs uncertainty; track false-positive rate on own projects |
| Hook latency annoys the user | Async pattern: write a stub entry instantly, fill narration in background; hard timeout with fail-open (built: fail-open, 30s cap) |
| Anthropic changes hook schema | Pin behavior to documented schema; handler validates input and fails open |
| Users without an API key | Document clearly; explore whether a prompt-type hook can cover narration without a separate key (open question) |
| Naming | "Plainspoken" is a placeholder; explore the contract-reading-friend space |

Open questions:

1. Should warnings ever block (PreToolUse exit 2) in a strict mode, or is narrate-and-warn always the right posture for this audience?
2. Does the narration language need localization early (vibe coding is global)?
3. Is the appmodel.json worth populating from day one so the map arrives "for free" later?

## 14. Future Directions

- Feed collapse by feature: group entries via affects tags and file relationships so a long session reads as a few feature stories instead of thirty entries
- The visual floor-plan map (Layer 4) as a localhost dashboard
- Support for Cursor, Windsurf, and other agents via their extension points
- A weekly email-style digest for the Semi-Technical Reviewer persona
- Shareable "app inspection report" export (leans into the home-inspection framing, natural ForgeLabs crossover)
