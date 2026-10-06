#!/usr/bin/env bash
# PreToolUse(Bash) 훅: 위험한 셸 명령을 실행 전에 차단한다.
# stdin으로 {"tool_name":"Bash","tool_input":{"command":"..."}} JSON을 받는다.
# 차단 시 permissionDecision=deny JSON을 출력하면 Claude Code가 도구 호출을 거부한다.
set -u

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
[ -z "$cmd" ] && exit 0

deny() {
  jq -n --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

# 1) 루트/홈 전체 삭제
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])rm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[[:space:]]+(/|~|\$HOME)(/?\*)?([[:space:]]|$)'; then
  deny "차단됨: 루트/홈 디렉터리 전체 삭제(rm -rf /, ~)는 허용되지 않습니다."
fi

# 2) 기본 브랜치로 강제 푸시
if printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push[^;&|]*(--force|-f)[^;&|]*[[:space:]](main|master)([[:space:]]|$)' \
   || printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push[^;&|]*[[:space:]](main|master)[^;&|]*(--force|[[:space:]]-f)([[:space:]]|$)'; then
  deny "차단됨: main/master 브랜치로의 강제 푸시(--force)는 허용되지 않습니다."
fi

# 3) 추적되지 않은 파일/변경 사항을 통째로 날리는 명령
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git[[:space:]]+(clean[[:space:]]+-[a-zA-Z]*f|reset[[:space:]]+--hard)'; then
  deny "차단됨: git clean -f / git reset --hard 는 작업 내용을 잃을 수 있어 허용되지 않습니다."
fi

# 4) 블록 디바이스/파일시스템 파괴
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])(mkfs(\.[a-z0-9]+)?|dd[[:space:]]+[^;&|]*of=/dev/)'; then
  deny "차단됨: 디스크/파일시스템을 파괴하는 명령은 허용되지 않습니다."
fi

exit 0
