---
name: new-hook
description: X할 때마다 자동으로 Y를 하라는 요청을 이 저장소의 훅 규칙에 맞는 스크립트와 settings.json 등록으로 만든다. 사용자가 /new-hook 으로 직접 호출할 때만 실행한다.
argument-hint: "<언제> <무엇을> (예: 파이썬 파일 수정 후 ruff 실행)"
disable-model-invocation: true
allowed-tools: Read Write Edit Bash(jq *) Bash(chmod *) Bash(ls *)
---

# 새 훅 만들기

요청: $ARGUMENTS

## 현재 등록된 훅

!`jq '.hooks | to_entries | map({event: .key, matchers: [.value[].matcher]})' .claude/settings.json`

## 기존 훅 스크립트

!`ls .claude/hooks`

## 할 일

1. 요청이 비어 있으면 "언제 무엇을 할지 알려 주세요"라고만 답한다.
2. 요청을 이벤트와 매처로 옮긴다.
   - 도구 실행 전, 막아야 함 → `PreToolUse`
   - 도구 실행 후 → `PostToolUse`
   - 응답을 마칠 때 → `Stop`
   - 사용자가 프롬프트를 보낼 때 → `UserPromptSubmit`
   - 매처는 도구 이름 정규식이다. 예: `Bash`, `Write|Edit`
3. 같은 이벤트와 매처의 훅이 이미 있으면 덮어쓰지 말고 사용자에게 유지, 교체, 추가 중 무엇을 원하는지 묻는다.
4. `.claude/hooks/<이름>.sh`에 스크립트를 쓴다. 기존 스크립트와 같은 규칙을 따른다.
   - 첫 줄 `#!/usr/bin/env bash`, 그 아래 한국어 주석으로 이벤트와 목적.
   - stdin JSON은 `jq -r`로 읽고 따옴표 친 변수에 담는다.
   - 차단할 때는 `permissionDecision: "deny"` JSON을 출력하고 `exit 0`.
   - 후처리 훅은 실패해도 `exit 0`으로 끝나 Claude의 작업을 막지 않는다.
5. `chmod +x`로 실행 권한을 준다.
6. 등록 전에 가짜 입력을 파이프로 넣어 시험한다. 결과를 사용자에게 보여 준다.
7. `.claude/settings.json`의 기존 배열에 항목을 **추가**한다. 기존 항목은 지우지 않는다.
   명령은 `"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/<이름>.sh"` 형식으로 쓴다.
8. `jq -e`로 settings.json이 올바른지 확인한다.
9. 무엇을 만들었는지, 어떻게 끄는지(`/hooks`)를 짧게 보고한다.
