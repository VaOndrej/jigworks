#!/usr/bin/env bash
# T00 spike: reproduce the facts about `claude -p --output-format stream-json`
# that the runner (T04), the contracts (T02) and the analytics depend on.
#
# Usage:
#   bash scripts/spike-claude.sh            # run all checks (5 small paid calls, haiku)
#   bash scripts/spike-claude.sh --record   # also rewrite the scrubbed fixtures in
#                                           # runner/tests/fixtures/stream-json/
#
# Requires: claude (logged in), jq, python3. Findings: docs/spikes/claude-stream-json.md
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$REPO/runner/tests/fixtures/stream-json"
RECORD=0
[[ "${1:-}" == "--record" ]] && RECORD=1

WORK="$(mktemp -d "${TMPDIR:-/tmp}/jigworks-spike.XXXXXX")"
RAW="$WORK/raw"
SANDBOX="$WORK/sandbox"
EMPTY_CFG="$WORK/empty-config"
mkdir -p "$RAW" "$SANDBOX" "$EMPTY_CFG"
echo "raw transcripts: $RAW"

FAILS=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILS=$((FAILS + 1)); }
check() { # check "<description>" <jq filter that must yield true> <file>
  if jq -e -s "$2" "$3" >/dev/null 2>&1; then pass "$1"; else fail "$1"; fi
}

# Isolate from the user's global hooks/plugins/skills; keep auth (OAuth works here,
# unlike --bare, which accepts only ANTHROPIC_API_KEY).
CLAUDE=(claude -p --output-format stream-json --verbose --model haiku --setting-sources project)

cd "$SANDBOX"
echo "claude version: $(claude --version)"

# --- (d) login check without starting a task --------------------------------
status_json="$(claude auth status --json)"; status_rc=$?
if [[ $status_rc -eq 0 ]] && jq -e '.loggedIn == true' <<<"$status_json" >/dev/null; then
  pass "auth status: loggedIn=true, exit 0, authMethod=$(jq -r .authMethod <<<"$status_json"), subscriptionType=$(jq -r '.subscriptionType // "n/a"' <<<"$status_json")"
else
  fail "auth status: expected loggedIn=true and exit 0"
fi
# Values used only for scrubbing; never printed.
SCRUB_EMAIL="$(jq -r '.email // empty' <<<"$status_json")"
SCRUB_ORG="$(jq -r '.orgId // empty' <<<"$status_json")"

set +e
empty_json="$(env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR="$EMPTY_CFG" claude auth status --json)"; empty_rc=$?
env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR="$EMPTY_CFG" "${CLAUDE[@]}" --max-turns 1 \
  "reply with the word ok" </dev/null >"$RAW/not-logged-in.jsonl" 2>"$RAW/not-logged-in.err"; nolog_rc=$?
set -e
if [[ $empty_rc -eq 1 ]] && jq -e '.loggedIn == false and .authMethod == "none"' <<<"$empty_json" >/dev/null; then
  pass "auth status with empty CLAUDE_CONFIG_DIR: loggedIn=false, authMethod=none, exit 1"
else
  fail "auth status with empty config: expected loggedIn=false and exit 1 (got exit $empty_rc)"
fi
[[ $nolog_rc -eq 1 ]] && pass "not-logged-in run exits 1" || fail "not-logged-in run exit code $nolog_rc (expected 1)"
check "not-logged-in run: init.apiKeySource=none, assistant.error=authentication_failed, result.is_error=true, cost 0" \
  '(map(select(.type=="system" and .subtype=="init"))[0].apiKeySource == "none")
   and (map(select(.type=="assistant"))[0].error == "authentication_failed")
   and (map(select(.type=="result"))[0] | .is_error == true and .subtype == "success" and .total_cost_usd == 0)' \
  "$RAW/not-logged-in.jsonl"

# --- (a) plain run: usage, cost, session, model -----------------------------
"${CLAUDE[@]}" --max-turns 1 "reply with the word ok" </dev/null >"$RAW/plain.jsonl"
P="$RAW/plain.jsonl"
check "plain: system/init has session_id, model, apiKeySource, claude_code_version" \
  'map(select(.type=="system" and .subtype=="init"))[0] | (.session_id|type=="string") and (.model|type=="string") and has("apiKeySource") and has("claude_code_version")' "$P"
check "plain: every assistant event has message.usage.{input_tokens,output_tokens,cache_creation_input_tokens,cache_read_input_tokens}" \
  'map(select(.type=="assistant") | .message.usage | has("input_tokens") and has("output_tokens") and has("cache_creation_input_tokens") and has("cache_read_input_tokens")) | all' "$P"
check "plain: one API message is split into several assistant events with the same message.id (dedupe needed)" \
  '(map(select(.type=="assistant"))|length) > (map(select(.type=="assistant")|.message.id)|unique|length)' "$P"
check "plain: result has total_cost_usd, session_id, usage.* and modelUsage.<model>.{inputTokens,outputTokens,cacheReadInputTokens,cacheCreationInputTokens,costUSD}" \
  'map(select(.type=="result"))[0] | (.total_cost_usd|type=="number") and (.session_id|type=="string")
   and (.usage|has("input_tokens") and has("output_tokens") and has("cache_creation_input_tokens") and has("cache_read_input_tokens"))
   and (.modelUsage|to_entries|map(.value|has("inputTokens") and has("outputTokens") and has("cacheReadInputTokens") and has("cacheCreationInputTokens") and has("costUSD"))|all)' "$P"
check "plain: total_cost_usd == sum(modelUsage[].costUSD)" \
  'map(select(.type=="result"))[0] | ((.total_cost_usd - ([.modelUsage[].costUSD]|add)) | fabs) < 1e-9' "$P"
check "plain: final output_tokens >= streamed assistant output_tokens (streamed values are partial)" \
  '(map(select(.type=="result"))[0].usage.output_tokens) >= (map(select(.type=="assistant")|.message.usage.output_tokens)|max)' "$P"
check "plain: rate_limit_event with rate_limit_info.{status,resetsAt,rateLimitType}" \
  'map(select(.type=="rate_limit_event"))[0].rate_limit_info | has("status") and has("resetsAt") and has("rateLimitType")' "$P"
echo "      models: init=$(jq -r 'select(.subtype=="init").model' "$P"), modelUsage=$(jq -c 'select(.type=="result").modelUsage|keys' "$P"), rate_limit=$(jq -c 'select(.type=="rate_limit_event").rate_limit_info|{status,rateLimitType}' "$P")"

# --- (b) --resume continues the session -------------------------------------
# Tools are disabled (--tools "") so the second run can only know the codeword from the
# resumed context; with tools on, "remember" makes the agent write Claude Code auto-memory.
"${CLAUDE[@]}" --max-turns 1 "The codeword for this conversation is PLUM-42. Reply with just: ok" \
  --tools "" </dev/null >"$RAW/resume-1.jsonl"
SID="$(jq -r 'select(.type=="result").session_id' "$RAW/resume-1.jsonl")"
"${CLAUDE[@]}" --max-turns 1 --resume "$SID" "What was the codeword? Reply with the codeword only." \
  --tools "" </dev/null >"$RAW/resume-2.jsonl"
if [[ "$(jq -r 'select(.type=="result").session_id' "$RAW/resume-2.jsonl")" == "$SID" ]]; then
  pass "resume: second run reports the same session_id"
else
  fail "resume: session_id changed"
fi
check "resume: second run recalls PLUM-42 from the first" \
  'map(select(.type=="result"))[0].result | test("PLUM-42")' "$RAW/resume-2.jsonl"
echo "      cost per invocation: resume-1=$(jq -r 'select(.type=="result").total_cost_usd' "$RAW/resume-1.jsonl") resume-2=$(jq -r 'select(.type=="result").total_cost_usd' "$RAW/resume-2.jsonl")"

# --- (c) --allowedTools and --permission-mode denials ------------------------
# NOTE: --allowedTools is variadic; the prompt must come before it (or it is swallowed).
rm -f x.txt y.txt
"${CLAUDE[@]}" --max-turns 3 \
  "Use the Bash tool to run exactly: echo hi > x.txt . Do not use any other tool. If it is denied, reply DENIED." \
  --allowedTools Read </dev/null >"$RAW/denied-tool.jsonl"
D="$RAW/denied-tool.jsonl"
[[ ! -e x.txt ]] && pass "allowedTools=Read: x.txt was not created" || fail "allowedTools=Read: x.txt exists"
check "allowedTools=Read: result.permission_denials[] has tool_name=Bash with tool_use_id and tool_input" \
  'map(select(.type=="result"))[0].permission_denials | map(select(.tool_name=="Bash" and has("tool_use_id") and has("tool_input"))) | length >= 1' "$D"
check "allowedTools=Read: the denied tool_use gets a user tool_result with is_error=true" \
  '[.[] | select(.type=="user") | .message.content[]? | select(.type=="tool_result" and .is_error==true)] | length >= 1' "$D"
check "allowedTools=Read: denial is not a run error (result.is_error=false, subtype=success)" \
  'map(select(.type=="result"))[0] | .is_error == false and .subtype == "success"' "$D"

# Plan mode is erratic (it may try Write, write its own plan file, or search for
# ExitPlanMode until max turns, which exits 1), so its exit code is recorded, not fatal.
set +e
"${CLAUDE[@]}" --max-turns 3 --permission-mode plan \
  "Use the Write tool to create y.txt containing hi. If it is denied, reply DENIED." </dev/null >"$RAW/denied-plan.jsonl"
plan_rc=$?
set -e
DP="$RAW/denied-plan.jsonl"
echo "      plan-mode exit=$plan_rc result=$(jq -c 'select(.type=="result")|{subtype,is_error,terminal_reason}' "$DP")"
[[ ! -e y.txt ]] && pass "permission-mode=plan: y.txt was not created" || fail "permission-mode=plan: y.txt exists"
check "permission-mode=plan: init.permissionMode=plan" \
  'map(select(.subtype=="init"))[0].permissionMode == "plan"' "$DP"
# Not asserted: in plan mode the model sometimes tries Write (-> permission_denials, like
# allowedTools) and sometimes only writes its own plan file under ~/.claude/plans/.
echo "      plan-mode denials (non-deterministic): $(jq -c 'select(.type=="result").permission_denials|map(.tool_name)' "$DP")"
echo "      plan-mode models: init=$(jq -r 'select(.subtype=="init").model' "$DP"), assistant=$(jq -r 'select(.type=="assistant").message.model' "$DP" | sort -u | paste -sd, -), modelUsage=$(jq -c 'select(.type=="result").modelUsage|keys' "$DP")"

# --- record scrubbed fixtures -------------------------------------------------
if [[ $RECORD -eq 1 ]]; then
  mkdir -p "$FIXTURES"
  # raw name:fixture name. denied-plan.jsonl in the fixtures is a curated run in which
  # plan mode did deny Write; a re-record writes plan mode to plan-mode.jsonl instead.
  for pair in plain:plain resume-1:resume-1 resume-2:resume-2 denied-tool:denied-tool \
              denied-plan:plan-mode not-logged-in:not-logged-in; do
    SCRUB_EMAIL="$SCRUB_EMAIL" SCRUB_ORG="$SCRUB_ORG" SCRUB_WORK="$WORK" python3 -I - \
      "$RAW/${pair%%:*}.jsonl" "$FIXTURES/${pair##*:}.jsonl" <<'PY'
import json, os, re, sys, getpass
src, dst = sys.argv[1], sys.argv[2]
home = os.path.expanduser("~")
user = getpass.getuser()
email, org, work = os.environ["SCRUB_EMAIL"], os.environ["SCRUB_ORG"], os.environ["SCRUB_WORK"]
real_work = os.path.realpath(work)
work = os.path.normpath(work)  # $TMPDIR often ends in "/", giving "T//jigworks-spike..."
def esc(p):  # Claude Code's dash-escaped project dir form
    return re.sub(r"[^A-Za-z0-9]", "-", p)
pairs = [(real_work, "/work"), (work, "/work"), (esc(real_work), "-work"), (esc(work), "-work"),
         (home, "/home/user"), (esc(home), "-home-user")]
def scrub_str(s):
    for a, b in pairs:
        if a:
            s = s.replace(a, b)
    for secret, repl in ((email, "user@example.com"), (org, "00000000-0000-0000-0000-000000000000")):
        if secret:
            s = s.replace(secret, repl)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "user@example.com", s)
    return s.replace(user, "user")
def walk(v, key=None):
    if key == "signature" and isinstance(v, str):
        return "REDACTED"  # the thinking signature embeds account data (base64)
    if key == "mcp_servers" and isinstance(v, list):
        return []  # lists the user's connected claude.ai connectors; not ours to publish
    if isinstance(v, dict):
        return {k: walk(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [walk(x) for x in v]
    if isinstance(v, str):
        return scrub_str(v)
    return v
with open(src) as f, open(dst, "w") as out:
    for line in f:
        if line.strip():
            out.write(json.dumps(walk(json.loads(line)), ensure_ascii=False) + "\n")
PY
  done
  leak=0
  for needle in "$(whoami)" "$SCRUB_EMAIL" "$SCRUB_ORG" "@gmail"; do
    [[ -n "$needle" ]] && grep -rqiF -- "$needle" "$FIXTURES" && leak=1
  done
  [[ $leak -eq 0 ]] && pass "fixtures written to runner/tests/fixtures/stream-json/ and contain no user name, email or org id" \
                    || fail "fixtures contain personal data"
fi

echo
if [[ $FAILS -eq 0 ]]; then echo "ALL CHECKS PASSED"; exit 0; else echo "$FAILS CHECK(S) FAILED"; exit 1; fi
