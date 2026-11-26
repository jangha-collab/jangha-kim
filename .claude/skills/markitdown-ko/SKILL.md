---
name: markitdown-ko
description: Word, PowerPoint, Excel, PDF 같은 문서 파일을 마크다운으로 바꿔 토큰을 아끼며 읽고 내용을 한국어로 정리한다. 사용자가 docx, pptx, xlsx, pdf 파일의 내용을 읽거나 요약해 달라고 할 때 사용한다.
argument-hint: "<문서 파일 경로> [궁금한 점]"
allowed-tools: Bash(markitdown *) Bash(command -v markitdown) Bash(mkdir -p .claude/logs/converted) Read
---

# 문서를 마크다운으로 바꿔 읽기

대상: $ARGUMENTS

markitdown 설치 여부: !`command -v markitdown || echo "(markitdown 미설치)"`

## 왜 하는가

docx, pptx, pdf를 그대로 읽히면 서식·레이아웃 정보 때문에 토큰이 많이 든다.
먼저 마크다운 텍스트로 바꾸면 제목, 목록, 표 같은 내용만 남아 같은 문서를 적은 토큰으로 읽을 수 있다.

## 할 일

1. 대상이 비어 있으면 "변환할 문서 파일 경로를 알려 주세요"라고만 답한다.
2. 위의 설치 여부가 `(markitdown 미설치)`이면 아래 안내만 하고 멈춘다. 설치는 직접 하지 않는다.
   - `pip install 'markitdown[all]'` 을 사용자가 직접 실행하도록 안내한다.
3. 첫 번째 인자를 파일 경로로 본다. 파일이 없으면 그렇다고 말한다. 지원 형식은 pdf, docx, pptx, xlsx, html, csv, json, 이미지 등이다.
4. 변환한다. 결과는 `.claude/logs/converted/` 아래에 `원본이름.md`로 저장한다(이 폴더는 git에 올라가지 않는다).
   - `mkdir -p .claude/logs/converted`
   - `markitdown "<원본 경로>" -o ".claude/logs/converted/<원본이름>.md"`
5. 변환 결과 파일을 Read로 읽는다. 매우 길면 필요한 부분만 `offset`과 `limit`으로 나눠 읽는다.
6. 나머지 인자(궁금한 점)가 있으면 그에 답하고, 없으면 아래 형식으로 정리한다.
   - **한 줄 요약**
   - **핵심 내용:** 3~5개 항목
   - **변환에서 빠진 것:** 이미지, 도형, 디자인처럼 마크다운으로 옮겨지지 않은 부분. 없으면 생략.
7. 원본 파일은 수정하거나 삭제하지 않는다.

## 주의

- 스캔본 PDF나 이미지 속 글자는 변환되지 않을 수 있다. 결과가 비어 있으면 그렇다고 알린다.
- 회사 문서는 로컬에서만 변환되며 외부로 보내지 않는다.
- 레이아웃이나 디자인 검토가 목적이면 마크다운 변환이 맞지 않으니 원본을 직접 보도록 안내한다.
