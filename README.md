# Claude Code 훅(Hooks): "X가 일어날 때마다 자동으로 Y"

Claude Code는 특정 **이벤트**가 발생할 때 셸 명령을 자동으로 실행하는 **훅(hook)** 을 지원합니다.
"파일을 쓸 때마다 포맷해 줘", "위험한 명령은 막아 줘" 같은 자동화는 메모리(CLAUDE.md)로는
보장되지 않습니다. 모델이 기억해서 해 주는 것이 아니라, **하네스가 반드시 실행**하도록
`settings.json`에 훅으로 등록해야 합니다.

이 저장소는 세 가지 대표 패턴을 바로 쓸 수 있는 형태로 담고 있습니다.

| 패턴                                  | 이벤트        | 매처                                  | 스크립트                           |
| ------------------------------------- | ------------- | ------------------------------------- | ---------------------------------- |
| 도구 호출 **전** 자동 실행 + **차단** | `PreToolUse`  | `Bash`                                | `.claude/hooks/block-dangerous.sh` |
| 도구 호출 **전** 자동 실행 (기록)     | `PreToolUse`  | `Bash\|Write\|Edit\|Read\|Glob\|Grep` | `.claude/hooks/log-tool-use.sh`    |
| 도구 호출 **후** 자동 실행 (포맷)     | `PostToolUse` | `Write\|Edit`                         | `.claude/hooks/format-file.sh`     |

## 파일 구성

```
.claude/
├── settings.json          # 훅 등록 (팀 공유, git 커밋)
├── hooks/
│   ├── block-dangerous.sh # rm -rf /, main 강제 푸시, reset --hard 등 차단
│   ├── log-tool-use.sh    # 모든 도구 호출을 .claude/logs/tool-use.jsonl 에 기록
│   └── format-file.sh     # Write/Edit 직후 prettier 로 자동 포맷
└── logs/                  # 훅이 만드는 로그 (gitignore 됨)
```

## 동작 원리

### 1. 이벤트와 매처

`settings.json`의 `hooks` 아래에 **이벤트 이름 → 매처 → 명령 목록** 구조로 등록합니다.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/block-dangerous.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/format-file.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

- `matcher`는 도구 이름에 대한 정규식입니다. `Write|Edit`처럼 여러 도구를 묶을 수 있습니다.
- `$CLAUDE_PROJECT_DIR`는 Claude Code가 훅 실행 시 넣어 주는 프로젝트 루트 경로입니다.
  어느 디렉터리에서 세션을 열어도 같은 스크립트를 가리킵니다.

자주 쓰는 이벤트:

| 이벤트                       | 시점                        | 차단 가능                                     |
| ---------------------------- | --------------------------- | --------------------------------------------- |
| `PreToolUse`                 | 도구 실행 직전              | 가능 (`permissionDecision: "deny"`)           |
| `PostToolUse`                | 도구가 성공한 직후          | 결과를 되돌릴 수는 없고, 모델에 피드백만 가능 |
| `PostToolUseFailure`         | 도구가 실패한 직후          | -                                             |
| `UserPromptSubmit`           | 사용자가 프롬프트를 보낼 때 | 가능                                          |
| `Stop`                       | Claude가 응답을 마칠 때     | 가능 (계속 작업하도록 되돌림)                 |
| `SessionStart`               | 세션 시작                   | -                                             |
| `PreCompact` / `PostCompact` | 컨텍스트 압축 전후          | -                                             |

### 2. 훅이 받는 입력 (stdin JSON)

훅 스크립트는 stdin으로 JSON 하나를 받습니다.

```json
{
  "session_id": "abc123",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": { "command": "rm -rf ./build" },
  "tool_response": { "filePath": "..." }
}
```

- `tool_input`은 도구에 넘어가는 인자 그대로입니다. Bash는 `.tool_input.command`, Write/Edit는 `.tool_input.file_path`.
- `tool_response`는 `PostToolUse`에서만 들어옵니다.
- 파싱은 `jq -r`로 하고, 결과는 반드시 **따옴표로 감싼 변수**에 담습니다.
  `| xargs`로 넘기면 경로에 공백이 있을 때 깨집니다.

### 3. 차단하는 방법 (PreToolUse)

스크립트가 아래 JSON을 stdout으로 내면 도구 호출이 거부되고, 이유가 모델에게 전달됩니다.

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "차단됨: main 브랜치로의 강제 푸시는 허용되지 않습니다."
  }
}
```

- `permissionDecision`은 `allow` / `deny` / `ask` 중 하나입니다. `ask`는 사용자에게 확인창을 띄웁니다.
- 아무것도 출력하지 않고 종료 코드 0으로 끝나면 평소처럼 진행됩니다.
- 종료 코드 2로 끝내고 stderr에 메시지를 쓰는 방식도 차단으로 동작하지만, JSON 출력이 더 명확합니다.

`block-dangerous.sh`는 다음을 막습니다.

| 차단 대상             | 예시                                                        |
| --------------------- | ----------------------------------------------------------- |
| 루트/홈 전체 삭제     | `rm -rf /`, `rm -rf ~`, `sudo rm -fr /*`                    |
| 기본 브랜치 강제 푸시 | `git push --force origin main`, `git push origin master -f` |
| 작업 내용 유실        | `git reset --hard`, `git clean -f`                          |
| 디스크 파괴           | `mkfs.*`, `dd ... of=/dev/...`                              |

`rm -rf ./build`, `git push --force origin feature/x`, `git clean -n` 같은 일상적인 명령은 통과합니다.

> 주의: 매처는 **명령 문자열 전체**를 봅니다. 문자열 안에 패턴이 들어 있기만 해도
> (예: 테스트용 heredoc) 차단됩니다. 이것은 의도된 보수적 동작입니다.

### 4. 후처리하는 방법 (PostToolUse)

`format-file.sh`는 파일 경로를 꺼내 확장자를 확인한 뒤 `prettier --write`를 실행합니다.

- 실패해도 `exit 0`으로 끝나므로 Claude의 작업을 막지 않습니다.
- prettier 3는 `.gitignore`된 경로를 조용히 건너뜁니다. `.claude/logs/` 안의 파일은 포맷되지 않습니다.
- 모델에게 무언가 알려 주고 싶다면 `hookSpecificOutput.additionalContext`에 문자열을 담아 출력하세요.

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "prettier가 src/app.ts 를 다시 포맷했습니다. 파일을 다시 읽으세요."
  }
}
```

### 5. 기록하는 방법 (PreToolUse, 모든 도구)

`log-tool-use.sh`는 호출 시각·이벤트·도구 이름·명령·파일 경로를 한 줄 JSON으로 남깁니다.

```json
{
  "ts": "2026-10-06T09:42:13Z",
  "event": "PreToolUse",
  "tool": "Bash",
  "command": "ls",
  "file": null
}
```

## 직접 검증하기

훅은 조용히 성공하면 UI에 아무것도 보이지 않습니다. 등록 뒤에는 stdin을 흉내 내어 바로 확인하세요.

```bash
export CLAUDE_PROJECT_DIR="$PWD"

# 차단되어야 함 → permissionDecision: deny
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' \
  | .claude/hooks/block-dangerous.sh | jq .

# 통과해야 함 → 출력 없음
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' \
  | .claude/hooks/block-dangerous.sh

# settings.json 구조 검증 (종료 코드 0이면 정상)
jq -e '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[] | .command' .claude/settings.json
```

## 수정·비활성화

- `/hooks` 명령으로 현재 등록된 훅을 보고 편집할 수 있습니다.
- 세션 중에 `.claude/settings.json`을 바꾸면 보통 바로 반영됩니다. 반영되지 않으면 `/hooks`를 한 번 열거나 세션을 재시작하세요.
- 개인만 쓸 훅은 `.claude/settings.local.json`(gitignore 됨)에, 모든 프로젝트에 적용할 훅은 `~/.claude/settings.json`에 넣습니다.
- `"disableAllHooks": true`를 설정하면 모든 훅이 꺼집니다.

## 자주 쓰는 변형

| 하고 싶은 것               | 이벤트 / 매처                 | 명령 예시                                                                      |
| -------------------------- | ----------------------------- | ------------------------------------------------------------------------------ |
| 코드 수정 후 테스트 실행   | `PostToolUse` / `Write\|Edit` | `jq -r '.tool_input.file_path' \| grep -E '\.(ts\|js)$' && npm test \|\| true` |
| 특정 디렉터리 편집 금지    | `PreToolUse` / `Write\|Edit`  | 경로가 `secrets/`로 시작하면 `deny` 출력                                       |
| 응답 종료 전 git 상태 확인 | `Stop` / 없음                 | 커밋 안 된 변경이 있으면 `{"decision":"block","reason":"..."}` 출력            |
| 압축 전 보존할 내용 묻기   | `PreCompact` / `auto`         | 보존 항목을 `additionalContext`로 출력                                         |
| 모델 판단으로 차단         | `PreToolUse` / `Bash`         | `{"type":"prompt","prompt":"이 명령이 안전한가? $ARGUMENTS"}`                  |
