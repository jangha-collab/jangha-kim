# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 이 저장소가 무엇인가

Claude Code 자동화 설정(훅·슬래시 명령어·서브에이전트)을 바로 쓸 수 있는 형태로 모아 둔 한국어 저장소다. 애플리케이션 코드나 빌드 시스템은 없고, `.claude/` 아래의 셸 스크립트·마크다운·JSON이 전부다. `README.md`가 설계 의도와 사용법을 설명하는 정본이며, 설정을 바꾸면 README도 같이 맞춰야 한다 (`@docs-ko` 에이전트가 그 일을 맡는다). `docs/`에는 코드와 무관한 업무 문서(사업계획서 등)를 둔다.

## 검증 명령

빌드 시스템은 없다. 차단 훅에는 시험이 있고, 훅을 고친 뒤에는 반드시 돌린다. 다른 훅은 stdin JSON을 흉내 내어 직접 실행해 확인한다.

```bash
# 차단 훅 시험 (실패만 출력, -v 는 전체 출력). 실패가 0개여야 한다
python3 .claude/hooks/tests/test_block_dangerous.py

export CLAUDE_PROJECT_DIR="$PWD"

# 차단되어야 함 → permissionDecision: deny JSON 출력
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' \
  | .claude/hooks/block-dangerous.sh | jq .

# 통과해야 함 → 출력 없음, 종료 코드 0
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' | .claude/hooks/block-dangerous.sh

# settings.json 구조 검증
jq -e '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[] | .command' .claude/settings.json
jq -e '.extraKnownMarketplaces.ruflo.source.repo == "ruvnet/ruflo" and .enabledPlugins["ruflo-core@ruflo"] == true' .claude/settings.json

# ruflo 플러그인이 설치·활성 상태인지 확인 (ruflo-core@ruflo 가 enabled 로 보여야 한다)
claude plugin list

# 스킬 본문의 !`명령`은 종료 코드 0이어야 한다. 하나씩 터미널에서 실행해 확인
git log --oneline origin/main..HEAD 2>/dev/null || echo "(origin/main을 찾을 수 없음)"
```

훅 전체를 우회 시도까지 포함해 점검하려면 `hook-auditor` 에이전트에 위임한다.

## 구조와 동작 원리

`.claude/settings.json`이 세 훅을 등록한다. 세 스크립트가 서로 다른 패턴을 대표하므로 새 훅은 가장 가까운 것을 본뜬다.

같은 파일의 `extraKnownMarketplaces`·`enabledPlugins`는 [ruvnet/ruflo](https://github.com/ruvnet/ruflo) 마켓플레이스와 그 기본 플러그인 `ruflo-core`를 프로젝트 범위로 켠다. 이 항목은 `claude plugin marketplace add ruvnet/ruflo --scope project`, `claude plugin install ruflo-core@ruflo --scope project`가 쓴 결과이므로 손으로 고치지 말고 같은 CLI(`claude plugin ...`에 `--scope project`)로 바꾼다. `npx ruflo init`는 `.claude/`와 `CLAUDE.md`를 덮어쓰므로 쓰지 않는다. 플러그인 훅은 이 저장소 훅과 같은 이벤트에서 함께 실행되지만 차단은 하지 않는다.

| 스크립트                           | 이벤트 / 매처                                        | 역할                                                                                                                 |
| ---------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `.claude/hooks/block-dangerous.sh` | `PreToolUse` / `Bash`                                | 진입점. 본체 `block_dangerous.py`가 명령을 셸처럼 해석해 위험 명령이면 `permissionDecision: deny` JSON을 출력해 차단 |
| `.claude/hooks/log-tool-use.sh`    | `PreToolUse` / `Bash\|Write\|Edit\|Read\|Glob\|Grep` | 호출 내역을 `.claude/logs/tool-use.jsonl`(gitignore)에 한 줄 JSON으로 기록                                           |
| `.claude/hooks/format-file.sh`     | `PostToolUse` / `Write\|Edit`                        | 쓰여진 파일을 prettier로 포맷. 실패해도 `exit 0`                                                                     |

훅 스크립트 공통 규약:

- 셸 훅의 입력은 `jq -r`로 파싱하고 결과는 반드시 따옴표로 감싼 변수에 담는다. `xargs`로 넘기지 않는다. 따옴표·heredoc까지 해석해야 하는 차단 훅만 예외로 파이썬(3.9 이상)을 쓴다.
- 차단은 `hookSpecificOutput.permissionDecision = "deny"` JSON 출력으로 한다. 종료 코드 2 방식은 쓰지 않는다.
- 차단하지 않을 때는 아무것도 출력하지 않고 `exit 0`.
- 차단 훅은 명령을 셸처럼 해석해 **실제로 실행될 명령만** 검사한다. 따옴표 안의 글자, 주석, 따옴표 heredoc 본문은 막지 않지만 `$(...)`, `bash -c`, `eval` 안쪽은 검사한다. 따옴표나 괄호 짝이 맞지 않는 명령은 막는다.
- 이 훅은 이 저장소에서 일하는 Claude 자신과 서브에이전트에도 적용된다. 위험 명령을 시험하려면 Bash에 직접 치지 말고 `.claude/hooks/tests/`의 사례 파일에 추가한 뒤 시험 스크립트로 돌린다.
- `format-file.sh` 때문에 `.md`, `.json`, `.yml` 등을 Write/Edit하면 prettier가 즉시 재포맷한다. 편집 직후 내용을 다시 읽어야 하면 그 점을 감안한다.

슬래시 명령어(`.claude/skills/<이름>/SKILL.md`):

- `commit-ko`, `new-hook`은 부작용이 있어 `disable-model-invocation: true`. 사용자가 직접 부를 때만 실행한다.
- `pr-ko`, `explain-ko`는 Claude가 알아서 호출해도 된다.
- 본문의 `` !`명령` ``은 호출 즉시 실행되며 0이 아닌 코드로 끝나면 명령어 전체가 실패한다. 실패 가능한 명령에는 `|| echo "..."`를 붙인다. `allowed-tools`에 그 명령이 허용되어 있어야 한다.
- 내장 명령(`/review`, `/commit`, `/init`, `/doctor`)과 이름을 겹치지 않게 한다.

서브에이전트(`.claude/agents/<이름>.md`):

- `hook-auditor`(훅 점검, 보고만), `log-analyst`(로그 집계, haiku), `docs-ko`(마크다운만 수정). 각 파일 본문 끝에 보고 형식이 정해져 있으므로 바꿀 때 형식을 유지한다.
- `tools`는 도구 이름 단위로만 제한된다(`Bash(git *)` 같은 범위 지정 불가). 더 세밀한 제한은 훅으로 한다.
- 에이전트는 메인 대화를 보지 못하므로 위임 지시문에 필요한 정보를 모두 담는다.

## 문서 언어

README, 스킬, 에이전트 본문, 커밋 메시지, PR 설명은 모두 한국어다. 새로 추가하는 파일도 같은 언어로 쓴다.
