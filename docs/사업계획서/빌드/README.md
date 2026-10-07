# 문서 재생성 방법

`docs/사업계획서/`의 Word와 PPT는 같은 폴더의 마크다운과 이 폴더의 스크립트로 만든다. 내용을 고칠 때는 마크다운(Word)과 `build_ppt.py`(PPT)를 수정한 뒤 아래 명령으로 다시 만든다.

필요한 도구는 pandoc, python-pptx, lxml이다.

## Word

표의 물결표(~)가 취소선으로 해석되지 않도록 `gfm-strikeout`을 쓴다.

```bash
N=docs/사업계획서/2026-10_스마트경찰경광등_사업계획서
pandoc "$N.md" -f gfm-strikeout -t docx --reference-doc=docs/사업계획서/빌드/ref3.docx \
  --resource-path=docs/사업계획서/빌드/images -o "$N.docx"
python3 docs/사업계획서/빌드/postdocx.py "$N.docx"
```

개발계획 과제제안서도 같은 방식이다. 파일 이름만 `2026-10_스마트경찰경광등_개발계획_과제제안서`로 바꾼다.

## PPT

`MClavis 양식_PPT 가로.pptx` 원본 템플릿이 필요하다. 저장소에는 넣지 않았으므로 직접 지정한다.

```bash
python3 docs/사업계획서/빌드/build_ppt.py "<MClavis 양식_PPT 가로.pptx 경로>" /tmp/out.pptx
python3 docs/사업계획서/빌드/post_ppt.py /tmp/out.pptx docs/사업계획서/2026-10_스마트경찰경광등_사업계획_과제제안.pptx
```

`post_ppt.py`는 템플릿에 남은 샘플 날짜를 작성 당일로 바꾼다. 표지 날짜(`26/10/06`)는 `build_ppt.py` 안의 값을 직접 고친다.

## 이미지

`images/`에 PPT와 Word에 쓰는 이미지가 있다.

- 해외 제품 사진 4점(VITRONIC, Ekin, Hikvision, GET): 각 제조사의 발표자료·리플릿·브로슈어·매뉴얼에서 가져왔다. Dahua iPatrol은 이미지 자료가 없다. 외부 제출 전 사용 허락을 확인한다.
- 국내 규격서 사진 5점(쏘나타, 렉스턴, 싼타페, 통합디바이스, 경기북부 자율방범대 경광등): 나눔컴퍼니 규격서와 입찰요청서에서 가져왔다.
- 특허 도면 4점: 엠클라비스 경광등 특허 조사(2026.4)에 수록된 공개 도면이다.
- `fig_overseas_products.jpg`, `fig_domestic_specs.jpg`: 위 사진을 묶어 Word 문서에 넣는 합성 그림이다.

사진을 바꾸거나 추가하려면 같은 폴더에 파일을 두고 `build_ppt.py`의 해당 슬라이드 코드(`pcells`, `cells`, `spec_imgs`)를 고친다.
