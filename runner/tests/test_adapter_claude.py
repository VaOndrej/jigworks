"""Claude adapter against the T00 recordings (runner/tests/fixtures/stream-json/). No live calls."""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jigworks_contracts as contracts
import pytest

from jigworks_runner.adapters import AgentOptions, ClaudeAdapter, auth_status, build_command, parse_lines
from jigworks_runner.events import EventSink, NodeContext
from jigworks_runner.pricing import PriceTable, UnknownPrice, cross_check

FIXTURES = Path(__file__).parent / "fixtures" / "stream-json"
PRICES = Path(contracts.__file__).resolve().parent.parent / "fixtures" / "prices.json"
T0 = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)


def lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


def ctx(node: str = "implement", attempt: int = 1) -> NodeContext:
    sink = EventSink(run_id="run_test_adapter", release="feature-development@1.3.0", clock=lambda: T0)
    return NodeContext(sink, node, attempt)


def kinds(c: NodeContext) -> list[str]:
    return [e["kind"] for e in c.sink.events]


def assert_all_valid(c: NodeContext) -> None:
    for i, event in enumerate(c.sink.events):
        assert contracts.validate("RunEvent", event) == [], event
        assert event["seq"] == i


def usage_limited_lines() -> list[str]:
    """Synthetic: the real limit cannot be triggered on demand (spike §5, "inferred").
    Built from plain.jsonl: rate limit rejected, assistant error, result is_error."""
    out = []
    for raw in lines("plain.jsonl"):
        msg = json.loads(raw)
        if msg["type"] == "rate_limit_event":
            msg["rate_limit_info"]["status"] = "rejected"
        if msg["type"] == "assistant":
            msg["error"] = "rate_limit"
        if msg["type"] == "result":
            msg["is_error"] = True
            msg["api_error_status"] = 429
        out.append(json.dumps(msg))
    return out


# --- command line --------------------------------------------------------------------------


def test_adapter_command_puts_prompt_before_variadic_flags():
    opts = AgentOptions(
        model="claude-sonnet-5",
        allowed_tools=("Read", "Edit", "Bash(uv run pytest:*)"),
        max_turns=12,
        resume_session_id="sess-1",
    )
    cmd = build_command("implement the spec", opts)
    assert cmd[:3] == ["claude", "-p", "implement the spec"]
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5"
    assert cmd[cmd.index("--setting-sources") + 1] == "project"
    assert cmd[cmd.index("--resume") + 1] == "sess-1"
    assert cmd[cmd.index("--max-turns") + 1] == "12"
    assert "--verbose" in cmd and cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert cmd[cmd.index("--allowedTools") :] == ["--allowedTools", "Read", "Edit", "Bash(uv run pytest:*)"]


def test_adapter_passes_the_effort_only_when_set():
    assert "--effort" not in build_command("p", AgentOptions(model="m"))
    cmd = build_command("p", AgentOptions(model="m", effort="medium"))
    assert cmd[cmd.index("--effort") + 1] == "medium"


def test_adapter_model_is_required_and_plan_mode_is_refused():
    with pytest.raises(ValueError, match="workflow release"):
        AgentOptions(model="")
    with pytest.raises(ValueError, match="plan mode"):
        AgentOptions(model="claude-sonnet-5", permission_mode="plan")
    cmd = build_command("p", AgentOptions(model="m", permission_mode="acceptEdits"))
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"


# --- recorded runs ---------------------------------------------------------------------------


def test_adapter_plain_run_succeeds_with_usage_per_model():
    c = ctx()
    result = parse_lines(lines("plain.jsonl"), c)
    assert result.ok and result.status == "succeeded"
    assert result.session_id == "7163b770-7bce-43f7-b6a6-20fdf9f7c23f"
    assert [u["model"] for u in result.usage] == ["claude-haiku-4-5-20251001"]
    u = result.usage[0]
    assert {k: u[k] for k in ("runId", "node", "attempt", "adapter")} == {
        "runId": "run_test_adapter", "node": "implement", "attempt": 1, "adapter": "claude"
    }
    assert all(contracts.validate("UsageRecord", r) == [] for r in result.usage)
    assert "usage" in kinds(c) and "agent_output" in kinds(c)
    assert "error" not in kinds(c) and "usage_limit" not in kinds(c)
    assert_all_valid(c)


def test_adapter_usage_comes_from_model_usage_not_assistant_events():
    raw = [json.loads(x) for x in lines("plain.jsonl")]
    final = next(m for m in raw if m["type"] == "result")["modelUsage"]
    result = parse_lines(lines("plain.jsonl"), ctx())
    for record in result.usage:
        mu = final[record["model"]]
        assert record["output"] == mu["outputTokens"]
        assert record["cache_write"] == mu["cacheCreationInputTokens"]
        assert record["cache_read"] == mu["cacheReadInputTokens"]
    streamed = [m["message"]["usage"]["output_tokens"] for m in raw if m["type"] == "assistant"]
    assert max(streamed) < result.usage[0]["output"], "streamed output_tokens are partial (spike §3)"


def test_adapter_passes_text_and_tool_calls_through_as_agent_output():
    c = ctx()
    result = parse_lines(lines("denied-tool.jsonl"), c)
    outputs = [e["agentOutput"] for e in c.sink.events if e["kind"] == "agent_output"]
    blocks = [o["block"] for o in outputs]
    assert "text" in blocks and "tool_use" in blocks and "tool_result" in blocks
    assert "thinking" not in blocks, "thinking is skipped by default"
    tool_use = next(o for o in outputs if o["block"] == "tool_use" and not o.get("denied"))
    assert tool_use["tool"]["name"] == "Bash"
    tool_result = next(o for o in outputs if o["block"] == "tool_result")
    assert tool_result["isError"] is True and tool_result["toolUseId"] == tool_use["tool"]["id"]
    assert all(e["node"] == "implement" for e in c.sink.events if e["kind"] == "agent_output")
    assert result.ok, "a denied tool call does not fail the run (spike §6)"
    assert_all_valid(c)


def test_adapter_marks_permission_denials():
    c = ctx()
    result = parse_lines(lines("denied-tool.jsonl"), c)
    assert [d["name"] for d in result.denials] == ["Bash"]
    denied = [e["agentOutput"] for e in c.sink.events if e["kind"] == "agent_output" and e["agentOutput"].get("denied")]
    assert len(denied) == 1 and denied[0]["tool"]["input"]["command"] == "echo hi > x.txt"


def test_adapter_thinking_can_be_included():
    c = ctx()
    parse_lines(lines("plain.jsonl"), c, include_thinking=True)
    assert any(e["agentOutput"]["block"] == "thinking" for e in c.sink.events if e["kind"] == "agent_output")
    assert_all_valid(c)


def test_adapter_resume_keeps_the_session():
    first = parse_lines(lines("resume-1.jsonl"), ctx("plan"))
    second = parse_lines(lines("resume-2.jsonl"), ctx("plan", attempt=2))
    assert first.session_id and first.session_id == second.session_id
    assert "PLUM-42" in second.text
    cmd = build_command("what was the codeword?", AgentOptions(model="haiku", resume_session_id=first.session_id))
    assert cmd[cmd.index("--resume") + 1] == first.session_id


def test_adapter_not_logged_in_is_an_error_not_a_success():
    c = ctx()
    result = parse_lines(lines("not-logged-in.jsonl"), c, exit_code=1)
    assert result.status == "failed"
    assert result.error["code"] == "authentication_failed"
    assert kinds(c)[-1] == "error"
    assert_all_valid(c)


def test_adapter_usage_limit_pauses_instead_of_crashing():
    c = ctx()
    result = parse_lines(usage_limited_lines(), c, exit_code=1)
    assert result.status == "usage_limit"
    assert result.usage_limit["status"] == "rejected" and result.usage_limit["paused"] is True
    assert result.usage_limit["rateLimitType"] == "five_hour"
    assert result.usage_limit["resetsAt"].endswith("Z")
    limit = next(e for e in c.sink.events if e["kind"] == "usage_limit")
    assert limit["runStatus"] == "paused_usage_limit"
    err = next(e for e in c.sink.events if e["kind"] == "error")
    assert err["error"]["code"] == "usage_limit" and err["error"]["retryable"] is True
    assert_all_valid(c)


def test_adapter_usage_limit_warning_is_reported_without_pausing():
    raw = [json.loads(x) for x in lines("plain.jsonl")]
    for m in raw:
        if m["type"] == "rate_limit_event":
            m["rate_limit_info"]["status"] = "allowed_warning"
    c = ctx()
    result = parse_lines([json.dumps(m) for m in raw], c)
    assert result.ok
    warning = next(e for e in c.sink.events if e["kind"] == "usage_limit")
    assert warning["usageLimit"] == {**warning["usageLimit"], "status": "allowed_warning", "paused": False}
    assert "runStatus" not in warning


def test_adapter_max_turns_is_a_failure():
    raw = [json.loads(x) for x in lines("plain.jsonl")]
    for m in raw:
        if m["type"] == "result":
            m.update(subtype="error_max_turns", is_error=True, errors=["Reached maximum number of turns (1)"])
    result = parse_lines([json.dumps(m) for m in raw], ctx(), exit_code=1)
    assert result.status == "failed" and result.error["code"] == "max_turns"


def test_adapter_crash_without_result_is_a_failure():
    c = ctx()
    result = parse_lines(lines("plain.jsonl")[:3] + ["not json"], c, exit_code=137)
    assert result.status == "failed" and result.error["code"] == "agent_failed"
    assert "137" in result.error["message"]
    assert_all_valid(c)


# --- cost -------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["plain.jsonl", "resume-1.jsonl", "resume-2.jsonl", "denied-tool.jsonl", "denied-plan.jsonl", "plan-mode.jsonl"])
def test_adapter_cost_from_price_table_matches_cli_cross_check(name):
    table = PriceTable.from_file(PRICES)
    result = parse_lines(lines(name), ctx())
    check = cross_check(table, result.usage)
    assert check["match"], check
    total = Decimal(str(result.cli_cost_usd))
    assert abs(check["ours"] - total) <= Decimal("0.000001")


def test_adapter_cost_prices_cache_tokens_separately():
    table = PriceTable.from_file(PRICES)
    base = {"model": "claude-haiku-4-5-20251001", "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "at": "2026-11-19T15:00:00Z"}
    assert table.cost({**base, "cache_write": 1_000_000}) == Decimal("2.0")
    assert table.cost({**base, "cache_read": 1_000_000}) == Decimal("0.1")
    assert table.cost({**base, "input": 1_000_000}) == Decimal("1.0")


def test_adapter_price_validity_picks_the_entry_valid_at_call_time():
    entries = [
        {"model": "m", "tokenType": t, "pricePerMtok": p, "validFrom": v}
        for t in ("input", "output", "cache_write", "cache_read")
        for p, v in ((1.0, "2026-01-01T00:00:00Z"), (2.0, "2026-06-01T00:00:00Z"))
    ]
    table = PriceTable(entries)
    usage = {"model": "m", "input": 1_000_000, "output": 0, "cache_write": 0, "cache_read": 0}
    assert table.cost(usage, at="2026-03-01T00:00:00Z") == Decimal("1.0")
    assert table.cost(usage, at="2026-07-01T00:00:00Z") == Decimal("2.0")
    with pytest.raises(UnknownPrice):
        table.cost(usage, at="2025-12-31T00:00:00Z")


# --- the real subprocess path, with a fake `claude` binary -----------------------------------


def fake_claude(tmp_path: Path, fixture: str, exit_code: int = 0) -> Path:
    script = tmp_path / "claude"
    argv_file = tmp_path / "argv.json"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"json.dump(sys.argv[1:], open({str(argv_file)!r}, 'w'))\n"
        f"sys.stdout.write(open({str(FIXTURES / fixture)!r}).read())\n"
        f"sys.exit({exit_code})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_adapter_runs_the_cli_with_closed_stdin(tmp_path):
    claude = fake_claude(tmp_path, "plain.jsonl")
    c = ctx()
    opts = AgentOptions(model="claude-haiku-4-5-20251001", allowed_tools=("Read",))
    result = ClaudeAdapter(claude_bin=str(claude)).run("say ok", tmp_path, opts, c)
    assert result.ok and result.exit_code == 0
    argv = json.loads((tmp_path / "argv.json").read_text())
    assert argv[:2] == ["-p", "say ok"] and argv[-2:] == ["--allowedTools", "Read"]
    assert_all_valid(c)


def test_adapter_cli_not_logged_in_exit_code(tmp_path):
    claude = fake_claude(tmp_path, "not-logged-in.jsonl", exit_code=1)
    result = ClaudeAdapter(claude_bin=str(claude)).run("x", tmp_path, AgentOptions(model="haiku"), ctx())
    assert result.status == "failed" and result.exit_code == 1 and result.error["code"] == "authentication_failed"


def test_adapter_missing_cli_is_an_error_event(tmp_path):
    c = ctx()
    result = ClaudeAdapter(claude_bin=str(tmp_path / "nope")).run("x", tmp_path, AgentOptions(model="haiku"), c)
    assert result.status == "failed" and kinds(c) == ["error"]


def test_adapter_auth_status_keeps_only_method_and_subscription(tmp_path):
    script = tmp_path / "claude"
    script.write_text(
        f"#!{sys.executable}\nimport json\n"
        "print(json.dumps({'loggedIn': True, 'authMethod': 'claude.ai', 'apiProvider': 'firstParty',"
        " 'email': 'someone@example.com', 'orgId': 'x', 'subscriptionType': 'max'}))\n"
    )
    script.chmod(0o755)
    status = auth_status(str(script))
    assert status.logged_in and status.auth_method == "claude.ai" and status.subscription_type == "max"
    assert "example.com" not in repr(status)
    script.write_text(f"#!{sys.executable}\nimport sys\nprint('{{\"loggedIn\": false, \"authMethod\": \"none\"}}')\nsys.exit(1)\n")
    assert auth_status(str(script)).logged_in is False


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("JIGWORKS_LIVE") != "1", reason="live run: set JIGWORKS_LIVE=1")
def test_adapter_live_smoke(tmp_path):
    status = auth_status()
    assert status.logged_in, "claude is not logged in"
    c = ctx()
    opts = AgentOptions(model="haiku", max_turns=1, allowed_tools=("Read",))
    result = ClaudeAdapter().run("Reply with the single word: ok", tmp_path, opts, c)
    assert result.ok, result.error
    assert result.usage and all(contracts.validate("UsageRecord", u) == [] for u in result.usage)
    assert_all_valid(c)
