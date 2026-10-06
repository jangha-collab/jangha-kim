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
├── skills/                # /명령어로 부르는 프롬프트 템플릿 (아래 "슬래시 명령어" 참고)
│   ├── commit-ko/SKILL.md
│   ├── pr-ko/SKILL.md
│   ├── explain-ko/SKILL.md
│   └── new-hook/SKILL.md
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

# 슬래시 명령어: 자주 쓰는 프롬프트를 `/이름`으로 호출

훅이 "이벤트가 일어나면 자동으로" 실행된다면, 슬래시 명령어는 "내가 부를 때" 실행되는 프롬프트 템플릿입니다.
매번 같은 지시를 길게 타이핑하는 대신 `.claude/skills/<이름>/SKILL.md`에 한 번 적어 두고 `/이름`으로 부릅니다.
이 폴더는 git에 커밋되므로 팀 전체가 같은 명령어를 씁니다.

## 이 저장소의 명령어

| 명령어        | 하는 일                                                         | Claude가 알아서 호출 |
| ------------- | --------------------------------------------------------------- | -------------------- |
| `/commit-ko`  | 스테이징된 변경을 읽고 한국어 커밋 메시지를 써서 커밋           | 안 함 (직접 호출만)  |
| `/pr-ko`      | main 대비 변경을 읽고 한국어 PR 설명 초안 출력                  | 함                   |
| `/explain-ko` | 파일·함수·설정을 개발자가 아닌 사람도 알 수 있게 설명           | 함                   |
| `/new-hook`   | "X할 때마다 Y" 요청을 훅 스크립트와 settings.json 등록으로 생성 | 안 함 (직접 호출만)  |

사용 예:

```
/commit-ko 로그인 버그 수정 건
/pr-ko 보안 관련 변경이 있으니 꼼꼼히 봐 주세요
/explain-ko .claude/hooks/block-dangerous.sh
/new-hook 파이썬 파일 수정 후 ruff 실행
```

## SKILL.md 구조

```markdown
---
name: 명령어-이름 # /명령어-이름 으로 호출. 생략하면 폴더 이름
description: 무엇을, 언제 쓰는지 # Claude가 알아서 호출할지 판단하는 근거
argument-hint: "<인자 설명>" # / 입력 시 자동완성에 표시
disable-model-invocation: true # 직접 호출만 허용 (커밋처럼 부작용 있는 작업)
allowed-tools: Bash(git diff *) Read # 이 명령 실행 중 확인 없이 허용할 도구
---

# 본문은 Claude에게 주는 지시입니다

- 사용자가 / 뒤에 붙인 글자: $ARGUMENTS
- 공백으로 나눈 n번째 인자: $0, $1, $2 ...
- 실행 시점의 명령 결과를 끼워 넣기: !`git status --short`
```

알아 둘 점:

- **`!` 명령은 호출 즉시 실행**되고, 결과가 프롬프트에 들어간 상태로 Claude가 읽습니다.
  `allowed-tools`에 그 명령이 허용되어 있어야 합니다.
- **`!` 명령이 0이 아닌 코드로 끝나면 명령어 전체가 실패**합니다.
  실패할 수 있는 명령에는 `|| echo "..."`처럼 대체 출력을 붙이세요. `/pr-ko`가 그 예입니다.
- **부작용이 있는 명령어**(커밋, 배포, 설정 변경)는 `disable-model-invocation: true`로
  직접 부를 때만 실행되게 하세요.
- **내장 명령과 이름이 겹치지 않게** 하세요. `/review`, `/commit`, `/init`, `/doctor` 등은 이미 있습니다.
- `description`에 `"`로 시작하는 문장을 쓰면 YAML이 깨집니다. 따옴표로 감싸려면 문장 전체를 감싸세요.
- `.claude/skills/`를 수정하면 실행 중인 세션에도 바로 반영됩니다.

## 새 명령어 만들기

1. `.claude/skills/<이름>/SKILL.md`를 만듭니다. 위 구조를 복사해 고칩니다.
2. 본문의 `!` 명령을 터미널에서 한 번씩 직접 실행해 종료 코드가 0인지 확인합니다.
3. Claude Code에서 `/` 를 입력해 목록에 보이는지 확인하고 호출해 봅니다.
4. 나만 쓸 명령어는 `~/.claude/skills/`에 두면 모든 프로젝트에서 쓸 수 있습니다.
