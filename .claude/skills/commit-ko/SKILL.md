---
name: commit-ko
description: 스테이징된 변경을 읽고 한국어 커밋 메시지를 작성해 커밋한다. 사용자가 /commit-ko 로 직접 호출할 때만 실행한다.
argument-hint: "[메시지에 반영할 메모]"
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(git commit *)
---

# 한국어 커밋 메시지 작성 후 커밋

## 현재 상태

- 작업 트리: !`git status --short`
- 스테이징된 파일: !`git diff --cached --stat`
- 최근 커밋 (스타일 참고용): !`git log --oneline -5`

## 스테이징된 변경 내용

!`git diff --cached`

## 사용자 메모

$ARGUMENTS

## 할 일

1. 스테이징된 변경이 비어 있으면 커밋하지 말고 "스테이징된 변경이 없습니다"라고만 알린다.
   `git add`로 아무 파일이나 스테이징하지 않는다.
2. 변경 내용을 읽고 아래 형식으로 커밋 메시지를 쓴다.
   - 첫 줄: 무엇을 왜 바꿨는지 50자 이내 한국어 한 문장. 마침표 없음.
   - 빈 줄 하나.
   - 본문: 주요 변경을 `- `로 시작하는 항목 2~5개. 각 항목은 한 문장.
   - 사용자 메모가 있으면 메시지에 반영한다.
3. `git commit -F -`에 heredoc으로 메시지를 넘겨 커밋한다.
4. 커밋 해시와 첫 줄을 보고한다. 푸시는 하지 않는다.
