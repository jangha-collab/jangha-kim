#!/usr/bin/env bash
# PreToolUse(모든 도구) 훅: 도구 호출 전에 호출 내역을 JSONL로 기록한다.
# 기록 파일: $CLAUDE_PROJECT_DIR/.claude/logs/tool-use.jsonl (gitignore 됨)
set -u

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
log_dir="$root/.claude/logs"
mkdir -p "$log_dir" 2>/dev/null || exit 0

jq -c --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{
  ts: $ts,
  event: (.hook_event_name // "PreToolUse"),
  tool: .tool_name,
  command: (.tool_input.command // null),
  file: (.tool_input.file_path // null)
}' >> "$log_dir/tool-use.jsonl" 2>/dev/null

exit 0
