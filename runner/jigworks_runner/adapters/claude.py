"""Claude CLI adapter over `claude -p --output-format stream-json`.

Built on the facts in docs/spikes/claude-stream-json.md:

- invocation: prompt first (the tool flags are variadic), `--verbose` is required, stdin closed;
- success = exit 0 and `result.is_error == false` (`result.subtype` alone is not a signal);
- usage = one UsageRecord per key of `result.modelUsage` (never from assistant events);
- a non-`allowed` `rate_limit_event` → `usage_limit`; an `is_error` result after a `rejected`
  rate limit is "paused by usage limit", not a failure;
- `assistant.error` (e.g. `authentication_failed`) → `error`; `permission_denials` → `agent_output`
  with `denied: true`.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..events import NodeContext, iso
from .base import AgentOptions, AgentResult

MAX_TEXT = 4000  # per agent_output block; the full transcript stays in claude's own session file


def build_command(prompt: str, options: AgentOptions, claude_bin: str = "claude") -> list[str]:
    cmd = [claude_bin, "-p", prompt, "--output-format", "stream-json", "--verbose", "--model", options.model]
    if options.setting_sources is not None:
        cmd += ["--setting-sources", options.setting_sources]
    for plugin in options.plugin_dirs:
        cmd += ["--plugin-dir", plugin]
    if options.effort:
        cmd += ["--effort", options.effort]
    if options.max_turns is not None:
        cmd += ["--max-turns", str(options.max_turns)]
    if options.resume_session_id:
        cmd += ["--resume", options.resume_session_id]
    if options.permission_mode:
        cmd += ["--permission-mode", options.permission_mode]
    # Variadic flags last, after the prompt (spike §1).
    if options.allowed_tools:
        cmd += ["--allowedTools", *options.allowed_tools]
    if options.disallowed_tools:
        cmd += ["--disallowedTools", *options.disallowed_tools]
    return cmd


def _clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + f"… [{len(text) - MAX_TEXT} chars clipped]"


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return json.dumps(content)


def _ts_from_unix(seconds: Any) -> str | None:
    try:
        return iso(datetime.fromtimestamp(int(seconds), UTC))
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass
class StreamParser:
    """Turns stream-json lines into RunEvents (through `ctx`) and an AgentResult."""

    ctx: NodeContext
    include_thinking: bool = False
    session_id: str | None = None
    result_event: dict[str, Any] | None = None
    assistant_error: str | None = None
    last_rate_limit: dict[str, Any] | None = None
    bad_lines: int = 0
    _texts: list[str] = field(default_factory=list)

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            self.bad_lines += 1
            return
        kind = msg.get("type")
        if kind == "system" and msg.get("subtype") == "init":
            self.session_id = msg.get("session_id") or self.session_id
        elif kind == "assistant":
            self._assistant(msg)
        elif kind == "user":
            self._user(msg)
        elif kind == "rate_limit_event":
            self._rate_limit(msg.get("rate_limit_info") or {})
        elif kind == "result":
            self.result_event = msg
            self.session_id = msg.get("session_id") or self.session_id
        # system/thinking_tokens, hook events and anything unknown: ignored (spike §8).

    def _out(self, payload: dict[str, Any]) -> None:
        if self.session_id:
            payload.setdefault("sessionId", self.session_id)
        self.ctx.emit("agent_output", agentOutput=payload)

    def _assistant(self, msg: dict[str, Any]) -> None:
        if msg.get("error"):
            self.assistant_error = str(msg["error"])
        message = msg.get("message") or {}
        mid = message.get("id")
        for block in message.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                self._texts.append(block.get("text", ""))
                self._out({"block": "text", "messageId": mid, "text": _clip(block.get("text", ""))})
            elif btype == "tool_use":
                tool = {"id": block.get("id", ""), "name": block.get("name", ""), "input": block.get("input") or {}}
                self._out({"block": "tool_use", "messageId": mid, "tool": tool})
            elif btype == "thinking" and self.include_thinking:
                self._out({"block": "thinking", "messageId": mid, "text": _clip(block.get("thinking", ""))})

    def _user(self, msg: dict[str, Any]) -> None:
        for item in (msg.get("message") or {}).get("content") or []:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                self._out(
                    {
                        "block": "tool_result",
                        "toolUseId": item.get("tool_use_id", ""),
                        "isError": bool(item.get("is_error", False)),
                        "text": _clip(_tool_result_text(item.get("content", ""))),
                    }
                )

    def _rate_limit(self, info: dict[str, Any]) -> None:
        status = info.get("status")
        if status not in ("allowed", "allowed_warning", "rejected"):
            return
        payload: dict[str, Any] = {"status": status}
        if info.get("rateLimitType"):
            payload["rateLimitType"] = str(info["rateLimitType"])
        resets = _ts_from_unix(info.get("resetsAt"))
        if resets:
            payload["resetsAt"] = resets
        self.last_rate_limit = payload
        if status == "allowed_warning":
            self.ctx.emit("usage_limit", usageLimit={**payload, "paused": False})
        # `rejected` is reported in finish(): only then do we know if the call was paused.

    def finish(self, exit_code: int | None, stderr: str = "") -> AgentResult:
        res = self.result_event
        result = AgentResult(status="failed", session_id=self.session_id, exit_code=exit_code)
        result.text = (res or {}).get("result") or "\n".join(t for t in self._texts if t)
        if res:
            result.num_turns = res.get("num_turns")
            result.cli_cost_usd = res.get("total_cost_usd")
            at = self.ctx.sink.now()
            for model, mu in (res.get("modelUsage") or {}).items():
                record = {
                    "runId": self.ctx.sink.run_id,
                    "node": self.ctx.node,
                    "attempt": self.ctx.attempt,
                    "model": model,
                    "adapter": "claude",
                    "input": int(mu.get("inputTokens", 0)),
                    "output": int(mu.get("outputTokens", 0)),
                    "cache_write": int(mu.get("cacheCreationInputTokens", 0)),
                    "cache_read": int(mu.get("cacheReadInputTokens", 0)),
                    "at": at,
                }
                if self.session_id:
                    record["sessionId"] = self.session_id
                if mu.get("costUSD") is not None:
                    record["cliCostUsd"] = float(mu["costUSD"])
                result.usage.append(record)
                self.ctx.emit("usage", model=model, usage=record)
            for denial in res.get("permission_denials") or []:
                tool = {
                    "id": denial.get("tool_use_id", ""),
                    "name": denial.get("tool_name", ""),
                    "input": denial.get("tool_input") or {},
                }
                result.denials.append(tool)
                self._out({"block": "tool_use", "tool": tool, "denied": True})

        is_error = res is None or bool(res.get("is_error")) or (exit_code not in (0, None))
        limited = self.last_rate_limit is not None and self.last_rate_limit["status"] == "rejected"

        if limited:
            paused = is_error
            result.usage_limit = {**self.last_rate_limit, "paused": paused}
            self.ctx.emit(
                "usage_limit",
                usageLimit=result.usage_limit,
                runStatus="paused_usage_limit" if paused else None,
            )
        if not is_error:
            result.status = "succeeded"
            return result
        if limited:
            result.status = "usage_limit"
            resets = self.last_rate_limit.get("resetsAt")
            result.error = {
                "code": "usage_limit",
                "message": "Claude usage limit reached" + (f"; resumes after {resets}." if resets else "."),
                "retryable": True,
            }
        elif self.assistant_error:
            result.error = {
                "code": self.assistant_error,
                "message": result.text or self.assistant_error,
                "retryable": False,
            }
        elif res is not None and res.get("subtype") == "error_max_turns":
            errors = res.get("errors") or []
            result.error = {"code": "max_turns", "message": "; ".join(errors) or "maximum turns reached", "retryable": False}
        elif res is None:
            tail = stderr.strip().splitlines()[-3:]
            result.error = {
                "code": "agent_failed",
                "message": f"claude exited {exit_code} without a result event" + (f": {' | '.join(tail)}" if tail else ""),
                "retryable": False,
            }
        else:
            errors = res.get("errors") or []
            result.error = {
                "code": "agent_failed",
                "message": "; ".join(map(str, errors)) or result.text or f"claude exited {exit_code}",
                "retryable": False,
            }
        self.ctx.emit("error", error=result.error)
        return result


class ClaudeAdapter:
    name = "claude"

    def __init__(self, claude_bin: str = "claude", env: dict[str, str] | None = None) -> None:
        self.claude_bin = claude_bin
        self.env = env

    def command(self, prompt: str, options: AgentOptions) -> list[str]:
        return build_command(prompt, options, self.claude_bin)

    def run(self, prompt: str, cwd: Path, options: AgentOptions, ctx: NodeContext) -> AgentResult:
        parser = StreamParser(ctx, include_thinking=options.include_thinking)
        try:
            proc = subprocess.Popen(
                self.command(prompt, options),
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,  # spike §1: otherwise claude waits 3 s for stdin
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.env,
            )
        except FileNotFoundError as exc:
            error = {"code": "agent_failed", "message": f"claude CLI not found: {exc}", "retryable": False}
            ctx.emit("error", error=error)
            return AgentResult(status="failed", error=error)
        assert proc.stdout is not None and proc.stderr is not None
        for line in proc.stdout:
            parser.feed(line)
        stderr = proc.stderr.read()
        try:
            code = proc.wait(timeout=options.timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait()
        return parser.finish(code, stderr)


def parse_lines(lines: Iterable[str], ctx: NodeContext, exit_code: int = 0, include_thinking: bool = False) -> AgentResult:
    """Replay recorded stream-json (tests, fixtures) without a process."""
    parser = StreamParser(ctx, include_thinking=include_thinking)
    for line in lines:
        parser.feed(line)
    return parser.finish(exit_code)


@dataclass(frozen=True)
class AuthStatus:
    logged_in: bool
    auth_method: str | None
    subscription_type: str | None
    exit_code: int


def auth_status(claude_bin: str = "claude", timeout_s: float = 15) -> AuthStatus:
    """Login preflight (spike §5): `claude auth status --json`; costs nothing.
    Only `authMethod` / `subscriptionType` are kept; email and org are dropped here."""
    try:
        proc = subprocess.run(
            [claude_bin, "auth", "status", "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return AuthStatus(False, None, None, -1)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        data = {}
    return AuthStatus(
        logged_in=proc.returncode == 0 and data.get("loggedIn") is True,
        auth_method=data.get("authMethod"),
        subscription_type=data.get("subscriptionType"),
        exit_code=proc.returncode,
    )
