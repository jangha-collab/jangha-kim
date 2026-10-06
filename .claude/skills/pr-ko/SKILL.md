---
name: pr-ko
description: 현재 브랜치가 main 대비 무엇을 바꿨는지 읽고 한국어 PR 설명 초안을 쓴다. 사용자가 PR 설명이나 PR 본문 초안을 요청할 때 사용한다.
argument-hint: "[리뷰어에게 강조할 점]"
allowed-tools: Bash(git log *) Bash(git diff *) Bash(git branch *) Bash(echo *)
---

# 한국어 PR 설명 초안

## 브랜치 정보

- 현재 브랜치: !`git branch --show-current`
- main 이후 커밋: !`git log --oneline origin/main..HEAD 2>/dev/null || echo "(origin/main을 찾을 수 없음)"`
- 변경 파일: !`git diff --stat origin/main...HEAD 2>/dev/null || echo "(origin/main을 찾을 수 없음)"`

## 변경 내용

!`git diff origin/main...HEAD 2>/dev/null || echo "(origin/main을 찾을 수 없음)"`

## 강조할 점

$ARGUMENTS

## 할 일

변경 내용을 읽고 아래 구조의 PR 설명을 마크다운으로 출력한다. PR을 직접 만들지는 않는다.

```markdown
## 요약

(이 PR이 무엇을 왜 바꾸는지 2~3문장)

## 변경 사항

- (파일 또는 기능 단위로 한 줄씩)

## 검증

- (실행한 테스트나 확인 방법. 알 수 없으면 "확인 필요"라고 쓴다)

## 리뷰 포인트

- (리뷰어가 특히 봐야 할 부분. 강조할 점이 있으면 여기에 반영)
```

- 변경 내용에 없는 사실은 지어내지 않는다.
- origin/main을 찾을 수 없다고 나오면 초안 대신 그 사실을 알린다.
