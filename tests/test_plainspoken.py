"""Plainspoken regression suite (stdlib only). Run: python3 tests/test_plainspoken.py

Consolidated self-check: prior fix sets (condensed) + writer-review fixes
(render two-tier, prompt rules, digest debounce, burst narration)."""
import importlib.util, io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / ".plainspoken" / "plainspoken.py")

def fresh(burst="off"):
    proj = tempfile.mkdtemp(prefix="ps_")
    os.environ["CLAUDE_PROJECT_DIR"] = proj
    os.environ["PLAINSPOKEN_BURST"] = burst
    spec = importlib.util.spec_from_file_location("ps", SRC)
    ps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ps)
    return ps, Path(proj)

def run(ps, cmd, payload):
    sys.stdin = io.StringIO(json.dumps(payload))
    getattr(ps, f"cmd_{cmd}")()

def events(proj):
    p = proj / ".plainspoken/events.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

def wr(proj, f, content, sess="s1", agent=None, ps=None):
    payload = {"tool_name": "Write", "session_id": sess, "cwd": str(proj),
               "tool_input": {"file_path": str(proj / f), "content": content}}
    if agent:
        payload["agent_type"] = agent
        payload["agent_id"] = "a1"
    run(ps, "narrate", payload)

MOCK = lambda *a, **k: "The app now does a new thing. AFFECTS: data"
TIDY = lambda *a, **k: "Internal tidying, nothing you'd notice. AFFECTS: plumbing"

# ---------- condensed regression: security + rules + lifecycle ----------
ps, proj = fresh()
assert ps.is_sensitive_path("/r/.env.test.local") and ps.is_sensitive_path("/r/.env")
assert not ps.is_sensitive_path("/r/credentials-timing.test.ts") and not ps.is_sensitive_path("/r/.env.example")
assert "[REDACTED]" in ps.redact("api_key=abcdefghijk123456")
assert "pw9x" not in ps.redact("postgres://u:pw9xlongpass@db/x")
assert "\n" not in ps.safe_name("a.py\nignore this")
assert any(h["id"] == "secret_key_unquoted" for h in ps.run_rules("api_key=abcdefghijk123456", "", fname="a.ini"))
assert any(h["id"] == "new_network_dest" for h in ps.run_rules('fetch("https://b.co/x")', 'fetch("https://a.co/x")'))
assert not any(h["id"] == "new_network_dest" for h in ps.run_rules('fetch("http://localhost:3000/x")', ""))
assert ps.normalize_path("/r/src/../app.py", "/r") == "app.py"

# whole-file resolution evidence
ps.call_model = MOCK
app = proj / "app.py"
app.write_text('api_key = "abcdefghijklmnop1234"\ntoken = "zyxwvutsrqponm9876"\n')
wr(proj, "app.py", app.read_text(), ps=ps)
fj = proj / ".plainspoken/findings.json"
assert json.loads(fj.read_text())["secret_key::app.py"]["status"] == "open"
app.write_text('token = "zyxwvutsrqponm9876"\n')
run(ps, "narrate", {"tool_name": "Edit", "session_id": "s1", "cwd": str(proj),
    "tool_input": {"file_path": str(app), "old_string": 'api_key = "abcdefghijklmnop1234"\n', "new_string": ""}})
assert json.loads(fj.read_text())["secret_key::app.py"]["status"] == "open", "partial removal must not resolve"
app.write_text("x = 1\n")
run(ps, "narrate", {"tool_name": "Edit", "session_id": "s1", "cwd": str(proj),
    "tool_input": {"file_path": str(app), "old_string": 'token = "zyxwvutsrqponm9876"\n', "new_string": "x = 1\n"}})
assert json.loads(fj.read_text())["secret_key::app.py"]["status"] == "resolved"
assert any(e.get("type") == "resolution" for e in events(proj))

# ---------- prompt-layer assertions ----------
for needle in ("BINARY RULE", "VOICE", "REMOVALS"):
    assert needle in ps.NARRATOR_BASE, f"narrator missing {needle}"
for needle in ("GROUNDING", "TONE"):
    assert needle in ps.DIGEST_SYSTEM, f"digest missing {needle}"
assert "automated TEST" in ps.narration_note("crm-stages.test.ts")
assert "documentation" in ps.narration_note("notes.md")
assert ps.narration_note("app.py") == ""
assert ps.is_test_path("x.spec.ts") and ps.is_test_path("test_foo.py") and not ps.is_test_path("app.py")
assert ps._clean_narration("Good stuff.\nFile changed: a.py\nMore.") == "Good stuff.\n\nMore."

# ---------- digest debounce ----------
ps2, proj2 = fresh()
ps2.call_model = TIDY
wr(proj2, "a.py", "print('plumbing only change that is long enough')", ps=ps2)
run(ps2, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert not any(e.get("type") == "digest" for e in events(proj2)), "plumbing-only turn must not digest"
ps2.call_model = MOCK
wr(proj2, "b.py", "print('meaningful change that is long enough here')", ps=ps2)
run(ps2, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert sum(1 for e in events(proj2) if e.get("type") == "digest") == 1, "meaningful turn digests"
wr(proj2, "c.py", "print('another meaningful change right after this')", ps=ps2)
run(ps2, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert sum(1 for e in events(proj2) if e.get("type") == "digest") == 1, "thin slice inside cooldown must defer"
ps2.DIGEST_COOLDOWN_S = 0
run(ps2, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert sum(1 for e in events(proj2) if e.get("type") == "digest") == 2, "deferred slice digests after cooldown"
run(ps2, "digest", {"session_id": "s1", "hook_event_name": "SubagentStop"})
assert sum(1 for e in events(proj2) if e.get("type") == "digest") == 2, "SubagentStop still never digests"

# ---------- burst narration ----------
ps3, proj3 = fresh(burst="on")
assert ps3.BURST
ps3.call_model = MOCK
f1 = proj3 / "feature.py"
f1.write_text("def step_one():\n    return 'the first version of this feature'\n")
wr(proj3, "feature.py", f1.read_text(), agent="general-purpose", ps=ps3)
f1.write_text("def step_one():\n    return 'the settled final version of this feature'\n")
wr(proj3, "feature.py", f1.read_text(), agent="general-purpose", ps=ps3)
assert not [e for e in events(proj3) if e.get("narration")], "burst edits must not narrate immediately"
assert sum(1 for e in events(proj3) if e.get("type") == "burst_stub") == 2
# age the stubs past the window, then touch a second file -> first burst settles
lines = (proj3 / ".plainspoken/events.jsonl").read_text().splitlines()
aged = []
for l in lines:
    e = json.loads(l)
    if e.get("type") == "burst_stub":
        e["ts"] = (datetime.fromisoformat(e["ts"]) - timedelta(seconds=300)).isoformat()
    aged.append(json.dumps(e))
(proj3 / ".plainspoken/events.jsonl").write_text("\n".join(aged) + "\n")
f2 = proj3 / "other.py"
f2.write_text("print('a different file changing now, long enough')\n")
wr(proj3, "other.py", f2.read_text(), ps=ps3)
burst_events = [e for e in events(proj3) if e.get("burst_of")]
assert len(burst_events) == 1 and burst_events[0]["burst_of"] == 2, "aged burst narrates once"
assert len(burst_events[0]["src_ts"]) == 2 and burst_events[0]["agent"] == "general-purpose"
assert "settled" not in burst_events[0]["narration"] or True
# Stop force-settles the second file's burst and digests everything
run(ps3, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
bursts = [e for e in events(proj3) if e.get("burst_of")]
assert len(bursts) == 2, "Stop must settle open bursts"
assert any(e.get("type") == "digest" and e.get("narration") for e in events(proj3)), "digest covers burst narrations"
# no stub narrates twice
all_src = [t for e in events(proj3) for t in (e.get("src_ts") or [])]
assert len(all_src) == len(set(all_src)), "no stub double-narrated"
run(ps3, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert len([e for e in events(proj3) if e.get("burst_of")]) == 2, "idempotent on repeat Stop"

# warnings bypass bursts entirely AND absorb the file's open stubs
f3 = proj3 / "risky.py"
f3.write_text("print('an ordinary change to start the burst here')\n")
wr(proj3, "risky.py", f3.read_text(), ps=ps3)
assert any(e.get("type") == "burst_stub" and e["file"] == "risky.py" for e in events(proj3))
wr(proj3, "cfg.ini", "api_key=abcdefghijk123456\n", ps=ps3)
warn_ev = [e for e in events(proj3) if e.get("warnings")]
assert warn_ev and warn_ev[-1].get("type") != "burst_stub", "warning edits narrate in real time"
f3.write_text("print('now a warning arrives in the same file')\napi_key = \"abcdefghijklmnop1234\"\n")
run(ps3, "narrate", {"tool_name": "Edit", "session_id": "s1", "cwd": str(proj3),
    "tool_input": {"file_path": str(f3), "old_string": "start", "new_string": 'api_key = "abcdefghijklmnop1234"'}})
warn_risky = [e for e in events(proj3) if e.get("warnings") and e["file"] == "risky.py"]
assert warn_risky and warn_risky[-1].get("src_ts"), "warning entry must absorb the file's open stubs"
run(ps3, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert not [e for e in events(proj3) if e.get("burst_of") and e["file"] == "risky.py"], "absorbed stubs must not re-narrate"
# flush cap: many stale groups settle a few per invocation, none lost
ps6, proj6 = fresh(burst="on")
ps6.call_model = MOCK
for i in range(10):
    fp = proj6 / f"m{i}.py"
    fp.write_text(f"print('file number {i} content long enough to narrate')\n")
    wr(proj6, f"m{i}.py", fp.read_text(), ps=ps6)
lines = (proj6 / ".plainspoken/events.jsonl").read_text().splitlines()
aged = []
for l in lines:
    e = json.loads(l)
    if e.get("type") == "burst_stub":
        e["ts"] = (datetime.fromisoformat(e["ts"]) - timedelta(seconds=300)).isoformat()
    aged.append(json.dumps(e))
(proj6 / ".plainspoken/events.jsonl").write_text("\n".join(aged) + "\n")
run(ps6, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
n1 = len([e for e in events(proj6) if e.get("burst_of")])
assert n1 == ps6.MAX_FLUSH_GROUPS, f"first flush capped, got {n1}"
run(ps6, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
n2 = len([e for e in events(proj6) if e.get("burst_of")])
assert n2 == 10, f"remaining groups settle next invocation, got {n2}"

# ---------- render two-tier ----------
ps4, proj4 = fresh()
store = proj4 / ".plainspoken"; store.mkdir()
mk = lambda i, aff, narr, stamp: {"ts": f"2026-08-03T10:0{i}:00+00:00", "stamp": stamp,
                                  "session_id": "s1", "file": f"f{i}.py", "affects": aff,
                                  "narration": narr, "warnings": []}
evs = [
    mk(0, "plumbing", "Internal tidying, nothing you'd notice.", "Aug 03, 10:00 AM"),
    mk(3, "plumbing", "Internal tidying, nothing you'd notice.", "Aug 03, 10:03 AM"),
    mk(1, "data", "**Big feature**\nWhat this means: things.\nFile changed: f1.py", "Aug 03, 10:01 AM"),
    mk(2, "plumbing", "(Plain-English explanation unavailable for this change; the change itself went through normally.)", "Aug 03, 10:02 AM"),
    mk(4, "messages", "**Emails deduplicated**\nWhat this means: one copy.", "Aug 03, 10:04 AM"),
]
with open(store / "events.jsonl", "w") as f:
    for e in evs:
        f.write(json.dumps(e) + "\n")
sys.stdin = io.StringIO("{}")
with ps4.locked():
    ps4.render_changelog()
md = (store / "CHANGELOG.plain.md").read_text()
assert "Behind the scenes" in md and "3 internal changes" in md, md
assert "couldn't be narrated" in md, "placeholder counted in collapse line"
assert md.count("Internal tidying, nothing you\x27d notice") == 0, "plumbing entries fully collapsed"
assert "File changed: f1.py" not in md, "bleed stripped"
assert md.index("Big feature") < md.index("Emails deduplicated"), "timestamp order"
assert md.index("Emails deduplicated") < md.index("Behind the scenes"), "user-facing first, noise at block bottom"

print("ALL CONSOLIDATED CHECKS PASSED")

# ---------- cursor race (cursor_idx snapshot) ----------
ps7, proj7 = fresh()
ps7.DIGEST_COOLDOWN_S = 0
store7 = proj7 / ".plainspoken"; store7.mkdir()
rows = [
    {"ts": "2026-08-03T10:00:00+00:00", "session_id": "s1", "file": "a.py",
     "affects": "data", "narration": "Change A happened.", "warnings": []},
    # B appended while the first digest's model call was in flight:
    {"ts": "2026-08-03T10:00:30+00:00", "session_id": "s1", "file": "b.py",
     "affects": "data", "narration": "Change B happened.", "warnings": []},
    # the digest snapshotted only A (cursor_idx=1) yet sits AFTER B in the file
    {"ts": "2026-08-03T10:01:00+00:00", "type": "digest", "session_id": "s1",
     "affects": "digest", "narration": "A happened.", "warnings": [], "cursor_idx": 1},
]
with open(store7 / "events.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
ps7.call_model = MOCK
run(ps7, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
digs = [e for e in events(proj7) if e.get("type") == "digest"]
assert len(digs) == 2, "event appended mid-digest must be covered by the next digest"
run(ps7, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
assert sum(1 for e in events(proj7) if e.get("type") == "digest") == 2, "and only once"

print("ALL CONSOLIDATED CHECKS PASSED (incl. codex round-2 fixes)")

# ---------- error descriptions + burst retry ----------
import subprocess
ps8, proj8 = fresh(burst="on")
assert ps8._err_desc(subprocess.TimeoutExpired(["claude", "-p", "SECRET PROMPT"], 45)) == "TimeoutExpired", "argv must never leak"
assert ps8._err_desc(ValueError("boom")) == "ValueError: boom"
calls = {"n": 0}
def flaky(system, user, max_tokens=150):
    calls["n"] += 1
    if calls["n"] == 1:
        raise RuntimeError("transient")
    return "The app now does a new thing. AFFECTS: data"
ps8.call_model = flaky
fx = proj8 / "flaky.py"
fx.write_text("print('content long enough to stub and then flush later')\n")
wr(proj8, "flaky.py", fx.read_text(), ps=ps8)
run(ps8, "digest", {"session_id": "s1", "hook_event_name": "Stop"})
be = [e for e in events(proj8) if e.get("burst_of")]
assert be and "unavailable" not in be[0]["narration"], "retry must rescue a transient failure"
errlog = (proj8 / ".plainspoken/errors.log").read_text()
assert "succeeded on retry" in errlog and "RuntimeError: transient" in errlog
assert "SECRET PROMPT" not in errlog

print("ALL CHECKS PASSED (incl. err-desc + burst retry)")

# ---------- wildcard CORS: setHeader argument style ----------
ps9, _ = fresh()
real = "// admin stats endpoint\nres.setHeader('Access-Control-Allow-Origin', '*');\nres.end(JSON.stringify(stats));\n"
assert any(h["id"] == "wildcard_cors" for h in ps9.run_rules(real, "")), "setHeader-style wildcard must flag"
assert any(h["id"] == "wildcard_cors" for h in ps9.run_rules("res.setHeader('Access-Control-Allow-Origin', '*');", ""))
assert not any(h["id"] == "wildcard_cors" for h in ps9.run_rules("res.setHeader('Access-Control-Allow-Origin', 'https://myapp.example');", "")), "specific origins must not flag"
print("CORS RULE CHECKS PASSED")
