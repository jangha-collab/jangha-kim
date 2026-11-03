---
name: newsletter-ko
description: 식품·라이프스타일 뉴스 브리핑 뉴스레터를 오늘 날짜로 새로 만들어 10MB 이하 PDF로 낸다. 사용자가 직접 부를 때만 실행한다.
disable-model-invocation: true
argument-hint: "[YYYY-MM-DD, 비우면 오늘]"
allowed-tools: Bash(python3 newsletter/build.py *) Bash(date *) Bash(tail *) Bash(ls *) Bash(cat *) Read Write WebSearch WebFetch
---

# 식품 뉴스 브리핑 뉴스레터 생성

## 오늘 정보

- 발행일: !`date +%F`
- 요청 인자: $ARGUMENTS (비어 있으면 위 발행일)
- 최근 발행 기록: !`tail -n 3 newsletter/archive.jsonl 2>/dev/null || echo "(이전 호 기록 없음)"`
- 비즈니스 섹션 입력 파일: !`ls newsletter/inputs 2>/dev/null || echo "(입력 폴더 없음)"`

## 원본 뉴스레터의 성격 (이 틀을 지킨다)

- 목적: 정보 → 신뢰 → 거래. 뉴스로 구독자를 모으고, 구독자가 고객사 CRM 자료로 다시 쓸 수 있게 한다.
- 선택 기준: 단순 사건 보도가 아니라 **구조 변화**와 **인사이트**가 보이는 기사.
- 기사 6건의 주제 배분: 소비 트렌드 1(메인) / 외식·프랜차이즈 2 / 유통·물류 1 / 소비·무역 지표 1 / AI·플랫폼 1.
- 기사 건당 순서: 제목 → 출처·일시·기자 → 핵심 요약 → 발행인 분석(구조 변화, 식품·외식 영향, 사업기회) → 한 문장 결론.
- 문체: 1인칭("저는", "제 판단으로는"). 숫자는 기사에서 확인된 것만 쓰고, 해석은 "가설"이라고 밝힌다. 효능·치료를 암시하는 표현은 쓰지 않는다.
- 사업기회 연결 축: 과재고 유동화, 외식업체 공동구매, 상품 큐레이션, 시장 데이터 축적.

## 순서

1. **검색**: WebSearch로 주제별 최근 3일 이내 국내 기사를 찾는다. 주요 경제·식품·유통 매체를 우선한다. `archive.jsonl`에 있는 URL은 쓰지 않는다.
2. **확인**: 고른 6건은 WebFetch로 본문을 읽어 제목·출처·일시·기자·핵심 수치를 확인한다. 읽지 못한 기사는 쓰지 않고 다른 기사로 바꾼다.
3. **작성**: 아래 형식의 JSON을 `newsletter/out/issue-<발행일>.json`에 쓴다. 기사 원문을 그대로 옮기지 않고 요약하며, 출처 링크를 단다.
4. **빌드**: `python3 newsletter/build.py newsletter/out/issue-<발행일>.json`
5. **확인**: 종료 코드 0이고 용량 10MB 이하인지 본다. 종료 코드 3(용량·쪽 수)이면 분량을 조정해 다시 빌드한다.
6. 결과 PDF 경로, 용량, 쪽 수, 고른 기사 목록을 한국어로 보고한다.

## issue JSON 형식

```json
{
  "date": "YYYY-MM-DD",
  "intro": ["오늘 호의 한 줄 소개 (선택, 0~3개)"],
  "articles": [
    {
      "tag": "소비 트렌드",
      "title": "기사 제목",
      "source": "매체명",
      "published": "2026.11.04 09:00",
      "reporter": "기자명 (모르면 생략)",
      "url": "https://...",
      "summary": ["핵심 요약 3~4개"],
      "analysis": [
        { "heading": "1. 구조 변화", "body": "문단. 줄바꿈은 \\n" },
        { "heading": "2. 식품·외식산업에 미치는 영향", "body": "..." },
        { "heading": "3. 사업기회", "body": "..." }
      ],
      "conclusion": "한 문장 결론"
    }
  ]
}
```

## 하지 않는 것

- 비즈니스 섹션(재고, 신상품, 공급사, M&A, 미팅 소식)은 **지어내지 않는다.** 발행인이 `newsletter/inputs/<발행일>.md`에 `## 제목` 블록으로 적어 둔 것만 빌드가 읽는다. 없으면 그 섹션은 빠진다.
- 배포 인원, 작업 시간·투입 가치 같은 발행인 수치는 만들지 않는다 (`newsletter/config.json`의 값만 쓴다).
- 기사 전문 복제 금지. 요약과 출처 링크만 싣는다.
- 읽지 못한 기사의 내용을 추측해서 쓰지 않는다.
