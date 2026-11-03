#!/usr/bin/env python3
"""뉴스레터 호(issue JSON)를 PDF로 만든다.

사용법:
  python3 newsletter/build.py <issue.json> [--out-dir DIR] [--inputs-dir DIR] [--dry-run]

하는 일:
  1. issue JSON 검증 (기사 수, 필수 항목, https 출처 링크)
  2. archive.jsonl 과 대조해 이미 쓴 기사 URL 중복 차단
  3. 비즈니스 섹션 입력(inputs/YYYY-MM-DD.md)이 있으면 읽고, 없으면 섹션 생략
  4. HTML -> PDF(render_pdf.js) -> 압축(Ghostscript, 없으면 pypdf)
  5. 용량(config.max_mb)과 쪽 수(config.target_pages) 확인
  6. 통과하면 archive.jsonl 에 기록 (--dry-run 이면 기록하지 않음)

종료 코드: 0 성공 / 1 검증 실패 / 2 사용법 오류 / 3 용량·쪽 수 기준 미달
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTICLE_REQUIRED = ["tag", "title", "source", "published", "url", "summary", "analysis", "conclusion"]


def fail(msg, code=1):
    print(f"오류: {msg}", file=sys.stderr)
    sys.exit(code)


def esc(text):
    return html.escape(str(text), quote=True)


def paragraphs(text):
    return "".join(f"<p>{esc(p)}</p>" for p in str(text).split("\n") if p.strip())


def load_archive(path):
    urls = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                urls.update(json.loads(line).get("urls", []))
    return urls


def validate(issue, cfg, used_urls):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(issue.get("date", ""))):
        fail("date 는 YYYY-MM-DD 형식이어야 합니다")
    arts = issue.get("articles", [])
    if len(arts) != cfg["article_count"]:
        fail(f"기사는 정확히 {cfg['article_count']}건이어야 합니다 (현재 {len(arts)}건)")
    seen = set()
    for i, a in enumerate(arts, 1):
        for key in ARTICLE_REQUIRED:
            if not a.get(key):
                fail(f"기사 {i}번에 '{key}' 가 비어 있습니다")
        if not str(a["url"]).startswith("https://"):
            fail(f"기사 {i}번 url 은 https 링크여야 합니다")
        if a["url"] in used_urls:
            fail(f"기사 {i}번은 이전 호에 이미 실었습니다: {a['url']}")
        if a["url"] in seen:
            fail(f"기사 {i}번 url 이 같은 호 안에서 중복됩니다")
        seen.add(a["url"])
        for sec in a["analysis"]:
            if not sec.get("heading") or not sec.get("body"):
                fail(f"기사 {i}번 analysis 항목은 heading 과 body 가 모두 필요합니다")
    return list(seen)


def read_business(inputs_dir, date):
    """'## 제목' 으로 시작하는 블록 목록을 읽는다. 파일이 없으면 빈 목록."""
    path = inputs_dir / f"{date}.md"
    if not path.exists():
        return []
    items = []
    for block in re.split(r"(?m)^## +", path.read_text(encoding="utf-8")):
        block = block.strip()
        if not block:
            continue
        title, _, body = block.partition("\n")
        items.append({"title": title.strip(), "body": body.strip()})
    return items


def render_html(issue, cfg, business):
    quote = cfg["quotes"][int(issue["date"].replace("-", "")) % len(cfg["quotes"])]
    subs = f" · 배포 {cfg['subscribers']:,}명" if cfg.get("subscribers") else ""
    parts = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>",
        f"<title>{esc(cfg['title'])} {esc(issue['date'])}</title>",
        f"<style>:root{{--font:{cfg['font_stack']}}}\n{(HERE / 'style.css').read_text(encoding='utf-8')}</style>",
        "</head><body>",
        f"<div class='date'>작성일 : {esc(issue['date'].replace('-', '.'))}{esc(subs)}</div>",
        f"<h1>{esc(cfg['title'])}</h1>",
        f"<div class='slogan'>{esc(cfg['slogan'])}</div>",
        f"<div class='quote'>{esc(quote)}</div>",
    ]
    if issue.get("intro"):
        parts.append("<div class='intro'><ul>" + "".join(f"<li>{esc(x)}</li>" for x in issue["intro"]) + "</ul></div>")
    parts.append("<h2>오늘의 뉴스</h2>")
    for a in issue["articles"]:
        reporter = f" · 기자 : {esc(a['reporter'])}" if a.get("reporter") else ""
        parts += [
            "<div class='article'>",
            f"<span class='tag'>{esc(a['tag'])}</span>",
            f"<h3 style='font-size:13pt;margin-top:0'>{esc(a['title'])}</h3>",
            f"<div class='meta'>출처 : {esc(a['source'])} · 일시 : {esc(a['published'])}{reporter}<br>"
            f"<a href='{esc(a['url'])}'>{esc(a['url'])}</a></div>",
            "<ul class='summary'>" + "".join(f"<li>{esc(s)}</li>" for s in a["summary"]) + "</ul>",
            "<div class='analysis'>",
        ]
        for sec in a["analysis"]:
            parts.append(f"<h3>{esc(sec['heading'])}</h3>{paragraphs(sec['body'])}")
        parts += ["</div>", f"<div class='conclusion'>{esc(a['conclusion'])}</div>", "</div>"]
    if business:
        parts.append("<div class='business'><h2>비즈니스 섹션</h2>")
        for b in business:
            parts.append(f"<div class='biz-item'><h3>{esc(b['title'])}</h3>{paragraphs(b['body'])}</div>")
        parts.append("</div>")
    parts.append("<div class='note'>기사 원문은 각 출처 링크에서 확인하세요. 본 자료의 분석은 발행인의 가설이며 투자·계약의 근거가 아닙니다.</div>")
    parts.append("</body></html>")
    return "".join(parts)


def page_count(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def compress(src, dst, max_bytes):
    """src -> dst. 용량 한도를 넘으면 더 강한 설정으로 다시 시도한다."""
    if shutil.which("gs"):
        for preset in ("/ebook", "/screen"):
            subprocess.run(
                ["gs", "-sDEVICE=pdfwrite", f"-dPDFSETTINGS={preset}", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                 f"-sOutputFile={dst}", str(src)], check=True)
            if dst.stat().st_size <= max_bytes:
                return "ghostscript" + preset
        return "ghostscript/screen"
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(str(src)))
    for page in writer.pages:
        page.compress_content_streams()
    try:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except TypeError:  # 구버전 pypdf
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    with open(dst, "wb") as f:
        writer.write(f)
    return "pypdf"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("issue")
    ap.add_argument("--out-dir", default=str(HERE / "out"))
    ap.add_argument("--inputs-dir", default=str(HERE / "inputs"))
    ap.add_argument("--archive", default=str(HERE / "archive.jsonl"))
    ap.add_argument("--dry-run", action="store_true", help="archive.jsonl 에 기록하지 않는다")
    args = ap.parse_args()

    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    issue = json.loads(Path(args.issue).read_text(encoding="utf-8"))
    archive = Path(args.archive)
    urls = validate(issue, cfg, load_archive(archive))
    business = read_business(Path(args.inputs_dir), issue["date"])

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"뉴스레터(식품관련 {issue['date'][2:].replace('-', '')})"
    html_path, raw_pdf, final_pdf = out / f"{stem}.html", out / f"{stem}.raw.pdf", out / f"{stem}.pdf"
    html_path.write_text(render_html(issue, cfg, business), encoding="utf-8")

    subprocess.run(["node", str(HERE / "render_pdf.js"), str(html_path), str(raw_pdf)], check=True, cwd=HERE)
    method = compress(raw_pdf, final_pdf, int(cfg["max_mb"] * 1024 * 1024))
    raw_pdf.unlink()

    size_mb = final_pdf.stat().st_size / 1024 / 1024
    pages = page_count(final_pdf)
    print(f"산출물: {final_pdf}")
    print(f"용량: {size_mb:.2f}MB (한도 {cfg['max_mb']}MB, 압축: {method}) / 쪽 수: {pages}")
    print(f"비즈니스 섹션: {'있음 ' + str(len(business)) + '건' if business else '입력 없음, 생략'}")

    if size_mb > cfg["max_mb"]:
        fail(f"용량이 {cfg['max_mb']}MB 를 넘습니다", 3)
    target = cfg.get("target_pages")
    if target and abs(pages - target) > cfg.get("pages_tolerance", 1):
        fail(f"쪽 수 {pages} 가 목표 {target}±{cfg.get('pages_tolerance', 1)} 를 벗어납니다", 3)

    if not args.dry_run:
        with archive.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": issue["date"], "urls": urls}, ensure_ascii=False) + "\n")
        print(f"archive 기록: {archive}")


if __name__ == "__main__":
    main()
