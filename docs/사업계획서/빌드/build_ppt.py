import math, re, sys
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.oxml.ns import qn
from lxml import etree

TEMPLATE, OUT = sys.argv[1], sys.argv[2]
FONT = "Noto Sans KR"
NAVY = RGBColor(0x1F, 0x3A, 0x93)
BLUE = RGBColor(0x2E, 0x75, 0xB6)
INK = RGBColor(0x22, 0x22, 0x22)
GRAY = RGBColor(0x59, 0x59, 0x59)
TINT = RGBColor(0xEE, 0xF3, 0xFA)
LINE = RGBColor(0xBF, 0xBF, 0xBF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

L = 365760
W = 12192000 - 2 * L
R = L + W
BOT = 6330000
WARN = []

prs = Presentation(TEMPLATE)

# ---- keep cover (slide 1), drop sample slide 2 --------------------------------
ids = list(prs.slides._sldIdLst)
for sid in ids[1:]:
    prs.part.drop_rel(sid.rId)
    prs.slides._sldIdLst.remove(sid)


# ---- helpers -------------------------------------------------------------------
def style_run(run, size, bold=False, color=INK, italic=False):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color
    f.name = FONT
    rPr = run._r.get_or_add_rPr()
    rPr.set("lang", "ko-KR")
    for tag in ("a:ea", "a:cs"):
        for e in rPr.findall(qn(tag)):
            rPr.remove(e)
    for tag in ("a:ea", "a:cs"):
        e = etree.SubElement(rPr, qn(tag))
        e.set("typeface", FONT)


def add_runs(p, text, size, bold=False, color=INK):
    for part in re.split(r"(\*\*.+?\*\*)", text):
        if not part:
            continue
        b = bold
        if part.startswith("**") and part.endswith("**"):
            part, b = part[2:-2], True
        r = p.add_run()
        r.text = part
        style_run(r, size, b, color)


def set_bullet(p):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", "200000")
    pPr.set("indent", "-200000")
    for tag in ("a:buNone", "a:buChar", "a:buFont"):
        for e in pPr.findall(qn(tag)):
            pPr.remove(e)
    bf = etree.SubElement(pPr, qn("a:buFont"))
    bf.set("typeface", "Arial")
    bc = etree.SubElement(pPr, qn("a:buChar"))
    bc.set("char", "•")


def text_w(text, size):
    """Rough text width in EMU."""
    t = re.sub(r"\*\*", "", text)
    em = 0.0
    for ch in t:
        o = ord(ch)
        if o >= 0x2E80:
            em += 1.0
        elif ch == " ":
            em += 0.32
        elif ch.isdigit():
            em += 0.58
        else:
            em += 0.56
    return em * size * 12700


def est_lines(text, width, size):
    total = 0
    for seg in text.split("\n"):
        w = text_w(seg, size)
        total += max(1, math.ceil(w / max(width, 1) * 1.06))
    return total


def est_h(text, width, size, spacing=1.32):
    return int(est_lines(text, width, size) * size * spacing * 12700)


def tbox(slide, x, y, w, h, paras, size=12, color=INK, bold=False, bullet=False,
         align=None, anchor=MSO_ANCHOR.TOP, margin=0, space=4):
    sh = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = sh.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(margin)
    tf.vertical_anchor = anchor
    first = True
    need = 0
    for item in paras:
        opts = {}
        if isinstance(item, tuple):
            item, opts = item
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        sz = opts.get("size", size)
        bl = opts.get("bullet", bullet)
        p.space_after = Pt(opts.get("space", space))
        if opts.get("align", align) is not None:
            p.alignment = opts.get("align", align)
        add_runs(p, item, sz, opts.get("bold", bold), opts.get("color", color))
        if bl:
            set_bullet(p)
        aw = w - 2 * margin - (200000 if bl else 0)
        need += est_h(item, aw, sz) + int(opts.get("space", space) * 12700)
    if need > h + 60000:
        WARN.append(f"textbox may overflow: need {need} > {h}: {paras[0] if not isinstance(paras[0], tuple) else paras[0][0]}"[:140])
    return sh


def card(slide, x, y, w, h, fill=TINT, radius=0.04):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
    sh.adjustments[0] = radius
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def label_shape(slide, shape_type, x, y, w, h, text, size, fill=NAVY, color=WHITE, bold=True,
                align=PP_ALIGN.CENTER, line=None):
    sh = slide.shapes.add_shape(shape_type, Emu(x), Emu(y), Emu(w), Emu(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(1)
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(70000)
    tf.margin_top = tf.margin_bottom = Emu(30000)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, seg in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        add_runs(p, seg, size, bold, color)
    return sh


def new_slide(title, lead=None, notes=None):
    s = prs.slides.add_slide(prs.slide_layouts[1])
    tf = s.shapes.title.text_frame
    tf.text = title
    for r in tf.paragraphs[0].runs:
        style_run(r, 20, True, INK)
    if len(title) > 40:
        WARN.append("long title: " + title)
    if lead:
        tbox(s, L, 640000, W, 420000, [lead], size=16, color=NAVY, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def set_cell_border(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for e in tcPr.findall(qn(tag)):
            tcPr.remove(e)
    for i, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
        ln = etree.Element(qn(tag))
        ln.set("w", "6350")
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        sf = etree.SubElement(ln, qn("a:solidFill"))
        c = etree.SubElement(sf, qn("a:srgbClr"))
        c.set("val", "BFBFBF")
        tcPr.insert(i, ln)


def add_table(slide, x, y, colw, rows, size=10.5, hdr=True, bold_first_col=False,
              fills=None, aligns=None, min_row=300000, hdr_size=None, max_bottom=BOT):
    w = sum(colw)
    pad = 70000
    heights = []
    for ri, row in enumerate(rows):
        hmax = min_row
        for ci, txt in enumerate(row):
            sz = (hdr_size or size) if (hdr and ri == 0) else size
            hh = est_h(txt, colw[ci] - 2 * pad, sz) + 90000
            hmax = max(hmax, hh)
        heights.append(hmax)
    total = sum(heights)
    global LAST_TABLE_ROWS
    LAST_TABLE_ROWS = [(y + sum(heights[:i]), heights[i]) for i in range(len(heights))]
    gs = slide.shapes.add_table(len(rows), len(colw), Emu(x), Emu(y), Emu(w), Emu(total))
    tbl = gs.table
    tblPr = tbl._tbl.tblPr
    for a in ("firstRow", "bandRow", "firstCol", "lastRow", "lastCol", "bandCol"):
        if a in tblPr.attrib:
            del tblPr.attrib[a]
    for e in tblPr.findall(qn("a:tableStyleId")):
        tblPr.remove(e)
    for ci, cw in enumerate(colw):
        tbl.columns[ci].width = Emu(cw)
    for ri, row in enumerate(rows):
        tbl.rows[ri].height = Emu(heights[ri])
        for ci, txt in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.margin_left = cell.margin_right = Emu(pad)
            cell.margin_top = cell.margin_bottom = Emu(40000)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            is_h = hdr and ri == 0
            cell.fill.solid()
            if is_h:
                cell.fill.fore_color.rgb = NAVY
            elif fills and fills.get((ri, ci)) is not None:
                cell.fill.fore_color.rgb = fills[(ri, ci)]
            else:
                cell.fill.fore_color.rgb = WHITE
            set_cell_border(cell)
            tf = cell.text_frame
            tf.word_wrap = True
            for li, seg in enumerate(txt.split("\n")):
                p = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
                if aligns and aligns[ci] is not None:
                    p.alignment = aligns[ci]
                if is_h:
                    add_runs(p, seg, hdr_size or size, True, WHITE)
                else:
                    add_runs(p, seg, size, bold_first_col and ci == 0, INK)
    if y + total > max_bottom + 20000:
        WARN.append(f"table bottom {y+total} > {max_bottom}: {rows[0][0]}")
    return y + total


def set_chart_fonts(chart, size=11):
    chart.font.size = Pt(size)
    chart.font.name = FONT
    chart.font.color.rgb = INK
    cs = chart._chartSpace
    for d in cs.iter(qn("a:defRPr")):
        if d.find(qn("a:ea")) is None:
            lat = d.find(qn("a:latin"))
            ea = etree.Element(qn("a:ea"))
            ea.set("typeface", FONT)
            if lat is not None:
                lat.addnext(ea)
            else:
                d.append(ea)


def bar_chart(slide, x, y, w, h, title, cats, series, colors=None, fmt="0.0", maxv=None,
              legend=False, size=11, horizontal=False):
    cd = CategoryChartData()
    cd.categories = cats
    for name, vals in series:
        cd.add_series(name, vals)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    gf = slide.shapes.add_chart(kind, Emu(x), Emu(y), Emu(w), Emu(h), cd)
    ch = gf.chart
    ch.has_title = True
    ch.chart_title.text_frame.text = title
    for r in ch.chart_title.text_frame.paragraphs[0].runs:
        style_run(r, size + 1, True, INK)
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = fmt
    dl.number_format_is_linked = False
    dl.font.size = Pt(size)
    dl.font.name = FONT
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    cols = colors or [NAVY, BLUE]
    for i, s in enumerate(plot.series):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = cols[i % len(cols)]
        s.invert_if_negative = False
    va = ch.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = RGBColor(0xE3, 0xE3, 0xE3)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(size - 1)
    va.tick_labels.font.color.rgb = GRAY
    if maxv is not None:
        va.maximum_scale = maxv
    ch.category_axis.tick_labels.font.size = Pt(size)
    ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    ch.category_axis.format.line.color.rgb = LINE
    set_chart_fonts(ch, size)
    return gf


# ================================================================================
# 1. cover
# ================================================================================
cover = prs.slides[0]


def font_only(run):
    f = run.font
    f.name = FONT
    rPr = run._r.get_or_add_rPr()
    rPr.set("lang", "ko-KR")
    for tag in ("a:ea", "a:cs"):
        for e in rPr.findall(qn(tag)):
            rPr.remove(e)
    for tag in ("a:ea", "a:cs"):
        e = etree.SubElement(rPr, qn(tag))
        e.set("typeface", FONT)


for sh in cover.shapes:
    if sh.name.startswith("제목"):
        p = sh.text_frame.paragraphs[0]
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        r = p.add_run()
        r.text = "스마트 경찰 경광등 사업계획 및 R&D 과제 제안"
        font_only(r)
    elif sh.name.startswith("부제목"):
        paras = sh.text_frame.paragraphs
        paras[0].runs[0].text = __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Seoul")).strftime("%y/%m/%d")
        for pp in paras:
            for r in pp.runs:
                font_only(r)
cover.notes_slide.notes_text_frame.text = (
    "내부 검토용 초안. 사업계획서(docx)와 개발계획 과제제안서(docx)의 핵심을 슬라이드로 옮긴 자료입니다. "
    "과제 금액·일정과 언론 보도 수치는 원문 확인 전 값이므로 25장을 함께 보세요.")

# ================================================================================
# 2. summary
# ================================================================================
s = new_slide("핵심 요약", "레이더 일체형 스마트 경광등으로 경찰청 직납 구조를 만든다",
              "근거: 2024 경찰청 종합쇼핑몰 납품요구 내역(나눔컴퍼니 137건) 분석, 사업계획서 0장 요약.")
rows = [
    ("현재 구조", "순찰차 경광등은 특장업체의 패키지용품으로 납품되어 당사는 경찰청과 직접 계약이 없다."),
    ("진입 방향", "24GHz 레이더를 경광등에 내장해 레이더 기반 교통안전·단속 장비로 품목을 재정의한다."),
    ("직납 경로", "교통단속장비 2번째 공급사, 혁신제품 수의계약, 종합쇼핑몰 단품 등록 순으로 진입한다."),
    ("재원", "정부 R&D 5.5억 원(구매연계형 기준)을 중심으로 1억 원 이상 과제를 2건 이상 병행 신청한다."),
]
y = 1200000
for i, (h, b) in enumerate(rows):
    label_shape(s, MSO_SHAPE.OVAL, L, y + 60000, 420000, 420000, str(i + 1), 16)
    tbox(s, L + 560000, y, 6500000, 1150000, [(h, {"size": 16, "bold": True, "color": NAVY, "space": 3}), (b, {"size": 14})])
    y += 1220000
stats = [("연 50~60억 원", "순찰차 경광등 신규 수요 (당사 가정)"),
         ("7.3억 원 · 24개월", "정부 5.5억 원 + 자부담 1.8억 원"),
         ("TRL 4 → 8", "순찰차 10대 · 3개월 현장 실증")]
y = 1200000
for big, small in stats:
    card(s, 7600000, y, R - 7600000, 1500000)
    tbox(s, 7600000 + 220000, y + 200000, R - 7600000 - 440000, 1100000,
         [(big, {"size": 28, "bold": True, "color": NAVY, "space": 4}), (small, {"size": 14, "color": GRAY})])
    y += 1650000

# ================================================================================
# 3. why now
# ================================================================================
s = new_slide("왜 지금인가: 세 가지 흐름이 겹친다", "해외는 이미 출시했고, 국내 현장은 준비됐으며, 당사는 핵심 기술이 있다",
              "근거: 당사 5사 경광등 비교표(2025.10), 전세계 동향(2025.10), 특허 조사(2026.4), 경찰청 보도, 2026 ITS 세계총회 출품 자료.")
cols = [
    ("해외", ["VITRONIC은 2021년 폴란드에 102대를 납품했고 2026.3 Intertraffic에서 재소개",
              "Ekin, Hikvision, Dahua, GET도 같은 개념의 제품 출시",
              "경쟁축이 속도 정확도에서 통합 플랫폼으로 이동",
              "국내에는 국산 경광등 일체형 제품이 없음"]),
    ("국내", ["순찰차 탑재형 과속단속 2022.3 본격 운영, 암행순찰차 중심",
              "2025 LED 전광판이 붙은 5세대 리프트 경광등 도입",
              "2035년 신규 경찰차 100% 전기·수소차 전환, 특장 재설계 시기",
              "연평균 신규 경찰차 약 1,908대"]),
    ("당사", ["24GHz 레이더 MCRT-100N/R, 경찰 속도규격 충족",
              "단속장비사 완제품에 이미 탑재·공급",
              "2026 ITS 세계총회에 완제품 출품, 부품에서 완제품으로 전환 결정",
              "남은 과제는 이동 플랫폼 신호처리와 경광등 일체 설계"]),
]
cw = (W - 2 * 200000) // 3
for i, (h, bl) in enumerate(cols):
    x = L + i * (cw + 200000)
    card(s, x, 1250000, cw, 4950000)
    tbox(s, x + 220000, 1400000, cw - 440000, 400000, [(h, {"size": 18, "bold": True, "color": NAVY})])
    tbox(s, x + 220000, 1950000, cw - 440000, 4100000, bl, size=15, bullet=True, space=14)

# ================================================================================
# 4. global comparison
# ================================================================================
s = new_slide("글로벌 5사 비교: 경쟁축은 통합성", "라이트바가 이동식 종합 단속 플랫폼으로 바뀌는 중이다",
              "출처: 엠클라비스 '5사 경광등 비교표'(2025.10.31), '경광등 관련 특허 조사'(2026.4). 공개 자료 기준이며 일부 수치는 미확인.")
rows = [["업체 · 제품", "핵심 구성", "포지셔닝"],
        ["VITRONIC Poliscan Enforcement Bar", "번호판 인식 + 레이더 속도단속 + 영상증거, 최대 5차선, 4G", "정확한 단속·증거성, 2021년 폴란드 102대 납품"],
        ["Ekin Patrol G2", "번호판 + 속도 + 주차관리 + 360° 영상, 최대 7차선, 약 20kg", "올인원, 미국 2,500만 달러 투자"],
        ["Hikvision Intelligent Light Bar", "77GHz 레이더(128 타깃), 최대 320km/h, 중앙 증거관리", "레이더 + 증거관리"],
        ["GET Group ADHAM Light Bar", "번호판 + 360° + 얼굴인식 + 속도 레이더, 관제 연동", "보안·관제 통합"],
        ["Dahua iPatrol Smart Light Bar", "360° + 정밀 레이더 + AI 위반·불법주차 탐지", "모바일 스마트 허브"]]
yb = add_table(s, L, 1200000, [3300000, 5000000, 3160480], rows, size=12, bold_first_col=True, min_row=520000)
card(s, L, yb + 200000, W, 1650000)
tbox(s, L + 220000, yb + 300000, W - 440000, 1500000, [
    "**시사점 ①** 경쟁이 속도 정확도에서 다기능 통합성으로 옮겨갔다.",
    "**시사점 ②** 통합 라이트바 구조 특허(US9002313B2)는 2026.8.30 만료되어 구조는 자유 실시가 가능하다.",
    "**시사점 ③** Ekin 3건은 2034~2040년 유효하다. 번호판·얼굴 인식을 넣지 않은 T2로 회피 설계하고 한국 출원 여부를 확인한다."],
    size=13, space=6)

# ================================================================================
# 4-2. patent drawings of overseas products
# ================================================================================
import os
from PIL import Image as _PILImage

IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")


def fit_picture(slide, path, x, y, w, h, name):
    with _PILImage.open(path) as im:
        iw, ih = im.size
    sc = min(w / iw, h / ih)
    pw, ph = int(iw * sc), int(ih * sc)
    pic = slide.shapes.add_picture(path, Emu(x + (w - pw) // 2), Emu(y + (h - ph) // 2), Emu(pw), Emu(ph))
    pic.name = name
    return pic


s = new_slide("해외 제품 사진: 센서를 경광등에 내장", "해외 제품은 센서를 경광등 안에 넣은 일체형이며 VITRONIC은 대량 납품 실적이 있다",
              "사진과 사양은 각 제조사 자료에서 가져왔다. VITRONIC 발표자료(Walter Planer, ASECAP Days 2024.5), Ekin Patrol G2 사용자 매뉴얼(V1.0.241120), "
              "Hikvision Intelligent Light Bar 리플릿(2023), GET Group ADHAM 브로슈어. 폴란드 사례: 재무부 e-TOLL 이동 단속차 70대(마킹 운송차, Enforcement Bar 2기)와 "
              "32대(비마킹 승용차, 1기), 2021년 1월 계약, 6~11월 납품. 번호판 인식률 99%와 98%. Dahua iPatrol은 이미지 자료가 없어 제외했다. "
              "제조사 사진은 외부 제출 전 사용 허락 확인이 필요하다.")
pcells = [
    ("VITRONIC_EnforcementBar.jpg", "VITRONIC Poliscan Enforcement Bar",
     ["4면 360° 단속, 주행·정차 중 운용", "번호판 인식 98~99%, 최대 250km/h 판독", "2021년 폴란드 재무부 102대 납품"], "VITRONIC 발표자료 2024.5"),
    ("Ekin_PatrolG2.jpg", "Ekin Patrol G2",
     ["플러그 앤 플레이, DC 12V·360W", "웹 화면에서 번호·속도·위치·증거 사진 확인", "관련 미국 특허 3건(6장 도면)"], "Ekin Patrol G2 매뉴얼 V1.0.241120"),
    ("Hikvision_IntelligentLightBar.jpg", "Hikvision Light Bar iDS-TVJ860-IR",
     ["전·후면 8MP, 좌·우 5MP 카메라", "77GHz 레이더 320km/h, 128 타깃, 5차로", "DC 12~14V, GPS·4G·Wi-Fi 연동"], "Hikvision 리플릿 2023"),
    ("GET_ADHAM.jpg", "GET Group ADHAM Smart Patrol",
     ["번호판 인식·360° 감시·얼굴인식·속도 레이더 통합", "관제센터 블랙리스트 연동, GPS 기록", "경찰 표준 경광 구성 준수"], "GET Group ADHAM 브로슈어"),
]
pw = (W - 200000) // 2
ph = 2300000
for i, (img, ttl, bl, src) in enumerate(pcells):
    x = L + (i % 2) * (pw + 200000)
    y = 1200000 + (i // 2) * (ph + 150000)
    card(s, x, y, pw, ph)
    card(s, x + 120000, y + 120000, 2900000, ph - 240000, fill=WHITE, radius=0.03)
    fit_picture(s, os.path.join(IMG_DIR, img), x + 160000, y + 160000, 2820000, ph - 320000, "제품 사진 " + ttl)
    tbox(s, x + 3150000, y + 150000, pw - 3270000, ph - 300000,
         [(ttl, {"size": 14, "bold": True, "color": NAVY, "space": 6})] +
         [(t, {"size": 11, "bullet": True, "space": 4}) for t in bl] +
         [(src, {"size": 10, "color": GRAY})], size=11)
tbox(s, L, 6030000, W, 260000,
     ["출처: 각 제조사 자료. Dahua iPatrol은 이미지 자료가 없어 제외했다. 외부 제출 전 제조사 사진의 사용 허락을 확인해야 한다."],
     size=10, color=GRAY)

s = new_slide("해외 제품의 일체형 구조: 공개 특허 도면", "해외 제조사는 경광등 하우징 안에 센서를 넣는 구조를 이미 특허로 확보했다",
              "도면은 엠클라비스 '경광등 관련 특허 조사'(2026.4)에 수록된 각 특허의 공개 도면이다. 제품 사진이 아니며, VITRONIC·Hikvision·GET·Dahua는 "
              "조사한 특허 도면이 없어 제외했다. 제조사 사이트에 접속할 수 없어 제품 사진은 넣지 못했다. 권리 상태: US9002313B2 2026.8.30 만료, "
              "US9791766B2 2034.1, US9928737B2 2034.12, US10946793B1 2040.4 만료 예정(특허 조사 기준).")
cells = [
    ("US9002313B2_FederalSignal.png", "Federal Signal · US9002313B2",
     "경광등 하우징 안에 레이더·카메라·번호판 인식·GPS·통신 모듈을 선택 탑재", "2026.8.30 만료, 구조 자유 실시", "그림: 하우징 내부 구성"),
    ("US9791766B2_Ekin.png", "Ekin · US9791766B2",
     "복수 카메라와 LED, 경광등을 한 몸체로 묶은 차량 장착형 장치", "2034.1까지 유효", "그림: 라이트바 외형"),
    ("US10946793B1_Ekin.png", "Ekin · US10946793B1",
     "순찰차에 후장착하는 스마트 라이트바, 센서 결과로 위협을 평가해 경고", "2040.4까지 유효", "그림: 순찰차 장착 형태"),
    ("US9928737B2_Ekin.png", "Ekin · US9928737B2",
     "번호판 인식과 레이더 속도정보를 연계하는 차량 탑재형 구조", "2034.12까지 유효", "그림: 라이트바 구조"),
]
cwid = (W - 200000) // 2
chei = 2300000
for i, (img, ttl, desc, stat, cap) in enumerate(cells):
    x = L + (i % 2) * (cwid + 200000)
    y = 1200000 + (i // 2) * (chei + 150000)
    card(s, x, y, cwid, chei)
    bgbox = card(s, x + 120000, y + 120000, 2900000, chei - 240000, fill=WHITE, radius=0.03)
    fit_picture(s, os.path.join(IMG_DIR, img), x + 160000, y + 160000, 2820000, chei - 320000, "특허 도면 " + ttl)
    tbox(s, x + 3150000, y + 150000, cwid - 3270000, chei - 300000, [
        (ttl, {"size": 14, "bold": True, "color": NAVY, "space": 6}),
        (desc, {"size": 12, "space": 6}),
        ("권리 상태: " + stat, {"size": 11, "color": GRAY, "space": 3}),
        (cap, {"size": 11, "color": GRAY})], size=12)
tbox(s, L, 6030000, W, 260000,
     ["출처: 엠클라비스 경광등 특허 조사(2026.4) 수록 공개 도면. 제품 사진이 아니며 VITRONIC·Hikvision·GET·Dahua는 조사한 특허 도면이 없어 제외했다."],
     size=10, color=GRAY)

# ================================================================================
# 5. police need table
# ================================================================================
s = new_slide("현장 경찰관이 필요로 하는 이유 5가지", "경찰관 선호도 조사는 찾지 못했다. 아래는 필요의 근거이며 선호는 실증에서 검증한다",
              "근거 수준은 보도 수치의 신뢰도와 제품과의 직접성으로 판단. 수치는 검색 요약 기준이며 원문 대조가 필요함. 출처 목록은 26장.")
rows = [["번호", "경찰관이 선호할 이유(가설)", "핵심 근거", "근거 수준"],
        ["1", "사고 처리 중 뒤에서 오는 차량이 가장 무섭다", "고속도로순찰 업무 중 교통사고로 다치거나 숨진 경찰관 5년간 34명, 2026년 1월 사고 수습 중 경찰관 사망", "강함"],
        ["2", "2차사고는 한 번 나면 치명적이다", "2차사고 치사율이 일반사고의 약 5~6.5배, 2026년 1~5월 고속도로 2차사고 사망자 급증", "강함"],
        ["3", "경찰이 이미 경광등으로 안전을 해결해 왔다", "2014년 순직 사고를 계기로 리프트 경광등 개발, 2015년 188대 투입 후 일선 호평 보도", "중간"],
        ["4", "일반 순찰차도 주행 중 단속하고 싶다", "탑재형 단속 시범 중 과속 사고 82%·사망 89% 감소(경찰청 발표), 사망사고 69.8%가 단속장비 없는 구간", "중간"],
        ["5", "해외 경찰도 같은 문제를 장비로 풀고 있다", "미국 경찰 순직 원인 1위가 차량 관련(2014~2016년 35~38%), 해외 5사가 라이트바에 센서 통합", "중간"]]
yb = add_table(s, L, 1200000, [700000, 3600000, 5760480, 1400000], rows, size=13, min_row=760000,
               aligns=[PP_ALIGN.CENTER, None, None, PP_ALIGN.CENTER])
tbox(s, L, yb + 150000, W, 400000,
     ["수치는 모두 언론 보도 기준이며 원문 사이트에 접속하지 못해 검색 요약으로 확인했다. 제안서에 인용하기 전에 원문 대조가 필요하다."],
     size=12, color=GRAY)

# ================================================================================
# 6. charts
# ================================================================================
s = new_slide("근거 ①②: 2차사고 피해와 치사율", "사고를 수습하는 경찰관이 치사율이 높은 2차사고에 가장 가까이 노출된다",
              "출처: 네이트뉴스 2026.1.10(5년 34명 보도, 연도별 부상 33명), 전북일보 2025.9.1(한국도로공사 치사율 54.3% 대 8.4%, 6.5배), "
              "YTN 2026.7.9(최근 3년 5배), 파이낸셜뉴스 2026.6.24(2026년 1~5월 고속도로 사망자 52.4% 증가). 모두 검색 요약 기준.")
bar_chart(s, L, 1200000, 5500000, 3500000, "고속도로순찰 업무 중 교통사고 부상 경찰관(명)",
          ["2021", "2022", "2023", "2024", "2025"], [("부상 경찰관", (3, 12, 5, 10, 3))], fmt="0", maxv=15)
bar_chart(s, 6200000, 1200000, R - 6200000, 3500000, "고속도로 사고 치사율(%)",
          ["일반사고", "2차사고"], [("치사율", (8.4, 54.3))], colors=[BLUE], fmt="0.0", maxv=65)
tbox(s, L, 4800000, W, 700000, [
    "출처: 네이트뉴스 2026.1.10(5년간 34명, 연도별은 부상 33명 보도), 전북일보 2025.9.1(한국도로공사 기준, 6.5배). "
    "최근 3년 기준 5배(YTN 2026.7.9) 보도도 있어 제안서에는 한 출처만 인용한다."], size=10, color=GRAY)
card(s, L, 5450000, W, 800000)
tbox(s, L + 220000, 5500000, W - 440000, 700000, [
    "2026년 1월 서해안고속도로에서 사고를 수습하던 경찰관과 견인차 기사가 숨졌다. 2026년 1~5월 고속도로 2차사고 사망자도 급증했다."],
    size=12, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================================
# 7. timeline
# ================================================================================
s = new_slide("리프트 경광등 호평에서 다음 단계로", "경찰은 안전을 이유로 경광등에 투자해 왔고, 다음 단계는 감지하는 경광등이다",
              "출처: 머니투데이 2015.2.12, 한국일보 2015.2.11, 충청투데이(리프트 경광등), 경향신문 2022.3.3(탑재형 단속), "
              "경찰청 2024 종합쇼핑몰 납품요구(181대·89대). 2014년 개발 계기는 출처 재확인 필요.")
nodes = [("2014", "여주 경감 순직을 계기로 리프트 경광등 개발 추진(출처 재확인 필요)"),
         ("2015", "방향표시 리프트 경광등 순찰차 188대 투입, 전방 3~4km 가시, 일선 호평"),
         ("2022", "순찰차 탑재형 과속단속 본격 운영, 시범 중 과속 사고·사망 감소 발표"),
         ("2024", "전기 다목적 순찰차 181대, 고속순찰차 89대에 리프트 경광등 납품"),
         ("2025", "후면 LED 전광판이 붙은 5세대 도입"),
         ("다음", "감지하는 경광등: 후방 접근 경보와 주행 중 속도 검지")]
cw = W // 6
ln = s.shapes.add_connector(1, Emu(L + cw // 2), Emu(1650000), Emu(L + 5 * cw + cw // 2), Emu(1650000))
ln.line.color.rgb = LINE
ln.line.width = Pt(2)
for i, (yr, tx) in enumerate(nodes):
    x = L + i * cw
    last = i == len(nodes) - 1
    label_shape(s, MSO_SHAPE.OVAL, x + cw // 2 - 480000, 1270000, 960000, 760000, yr, 13,
                fill=BLUE if last else NAVY)
    tbox(s, x + 60000, 2250000, cw - 120000, 2200000, [tx], size=13, align=PP_ALIGN.LEFT)
card(s, L, 4700000, W, 1500000)
tbox(s, L + 250000, 4800000, W - 500000, 1300000, [
    ("현재 경광등의 한계", {"size": 16, "bold": True, "color": NAVY, "space": 4}),
    "경광등은 경고를 표출할 뿐 접근하는 차량이 위험한지 감지하지 못한다. 본 제품은 이 한계를 메운다."],
    size=15, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================================
# 8. procurement structure
# ================================================================================
s = new_slide("현재 조달 구조: 경광등은 차량 패키지의 일부", "수요기관은 특장업체를 고를 뿐 경광등 브랜드를 고르지 않는다",
              "출처: 경찰청(수요기관코드 1320000) 종합쇼핑몰 납품요구 물품 내역 2024, ㈜나눔컴퍼니 137건, 나눔컴퍼니 차량별 규격서(NN-EXPC 6.3.5, 4.1.2). 경광등 실제 제조사는 확인하지 못했다(보도는 국제산업·현도산업 거론). "
              "경광등 패키지 비중: 전기다목적순찰차 건 총 125.7억 원 중 8.87억 원.")
dx, dw = L, 6400000
steps8 = [("1", "수요 발생·공고", "경찰청이 순찰차 특장 개조와 경광등 설치를 공고한다"),
          ("2", "계약·수주", "조달청 종합쇼핑몰(제3자단가계약)에서 ㈜나눔컴퍼니가 수주한다"),
          ("3", "완성차 공급", "현대자동차 등 완성차를 특장업체가 받는다"),
          ("4", "특장 개조·장착", "리프트·장방향 경광등, 사인보드, 앰프, 통합컨트롤러를 단다. 규격서상 경광등 공급자는 나눔컴퍼니"),
          ("5", "구조변경 승인·실차 검사", "교통안전공단이 기술검토, 제원, 최대안전경사각도를 측정한다"),
          ("6", "최종 납품·정산", "경찰서에 인도하고 대금을 받는다. 규격은 경찰청 순찰차 사양서 기준")]
sy = 1230000
for n_, h_, d_ in steps8:
    card(s, dx, sy, dw, 660000)
    label_shape(s, MSO_SHAPE.OVAL, dx + 90000, sy + 110000, 440000, 440000, n_, 14, fill=NAVY if n_ in ("4", "5") else BLUE)
    tbox(s, dx + 640000, sy + 40000, dw - 740000, 600000, [("**" + h_ + "**  " + d_, {"size": 12})], anchor=MSO_ANCHOR.MIDDLE)
    sy += 720000
tbox(s, dx, sy + 40000, dw, 700000, [
    "경광등만 따로 사야 할 이유, 곧 레이더 기반 단속·안전 기능이 있어야 직납이 가능하다. 4~5단계가 우리 제품이 맞춰야 할 관문이다."],
    size=12, color=INK)
tx = 7100000
rows = [["2024년 납품요구", "수량", "단가", "금액"],
        ["전기다목적순찰차\n리프트경광등 외 2종", "181대", "490만 원", "8.87억 원"],
        ["고속순찰차\n리프트경광등 설치", "89대", "370만 원", "3.29억 원"],
        ["암행순찰차\n그릴경광등 외 2종", "26대", "80만 원", "2,080만 원"],
        ["상용 순찰차\n리프트경광등 외 3종", "2대", "695만 원", "1,390만 원"]]
yb = add_table(s, tx, 1250000, [1900000, 750000, 900000, R - tx - 3550000], rows, size=12, min_row=640000,
               aligns=[None, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT])
tbox(s, tx, yb + 200000, R - tx, 1500000, [
    "경광등 패키지는 차량 가액의 약 7%다.",
    ("출처: 경찰청 종합쇼핑몰 납품요구 물품 내역(2024, ㈜나눔컴퍼니 137건)", {"size": 10, "color": GRAY})],
    size=14, space=6)

# ================================================================================
# 8-2. vehicle-specific light bar specifications
# ================================================================================
s = new_slide("차량별 경광등 규격서: 맞춰야 할 조건", "규격서에는 이미 스마트 장치를 연동할 자리가 있다",
              "출처: ㈜나눔컴퍼니 순찰차 규격서 3종(NN-CARP115 식별 25204397, NN-EXPC 24547105, NN-COPC 25479810), 순찰차 공용 통합디바이스 외 2종 규격서(24857805), "
              "경기북부 자율방범대 경광등 입찰요청서(규격서). 작성 연도는 문서에 없어 확인하지 못했다. 구조변경·실차 검사: 규격서 4.1.2. 순찰차 사양서(경찰청 장비운영과): NN-EXPC 6.3.5.")
rows = [["사진", "차종·규격", "경광등과 연동 장치", "크기·전기·검사"],
        ["", "쏘나타 순찰차\nNN-CARP115", "리프트 경광등에 사인보드(전광판) 내장, 경광등 안 앰프, 앞좌석 통합 컨트롤 박스", "리프트 경광등 전기 공급·작동 자체검사, 교통안전공단 실차 검사"],
        ["", "렉스턴 고속도로순찰차\nNN-EXPC", "장방향 경광등을 FRP 에어스포일러 위에, 통합컨트롤러(7~9인치, LTE·GPS), 접이식 사인보드", "경광등 1,250×296×167mm, 앰프 100W, 정차(P) 시 후방 경음기만 작동"],
        ["", "싼타페 다목적 순찰차\nNN-COPC", "전면 루프 장방향 경광등, 앰프 내장, 컨트롤박스 위치는 수요처 협의", "경광등 1,250×307×73mm, 앰프·스피커 100W급 이상"],
        ["", "순찰차 공용 통합디바이스\n식별번호 24857805", "8인치 이상 태블릿, USB 연동, 멀티캠 외 스마트 특수장치 통합 제어", "레이더 모듈을 연결할 규격상 자리"],
        ["", "경기북부 자율방범대 입찰\n경광등 단품 32대", "청색 장방형 LED, 신규 21대·교체 11대, 구조변경 포함, 경기도 내 업체 한정", "1,200×306×127mm, IPX4, DC 12V(10~15V), A/S 1년"]]
yb = add_table(s, L, 1150000, [1500000, 2300000, 3900000, R - L - 7700000], rows, size=11, bold_first_col=False, min_row=720000)
spec_imgs = ["KR_Sonata_NN-CARP115.jpg", "KR_Rexton_NN-EXPC.jpg", "KR_Santafe_NN-COPC.jpg", "KR_IntegratedDevice.jpg", "KR_Gyeonggi_lightbar.jpg"]
for (rt, rh), im_ in zip(LAST_TABLE_ROWS[1:], spec_imgs):
    fit_picture(s, os.path.join(IMG_DIR, im_), L + 70000, rt + 50000, 1360000, rh - 100000, "규격서 사진 " + im_)
card(s, L, yb + 130000, W, 6330000 - yb - 130000)
tbox(s, L + 200000, yb + 180000, W - 400000, 6330000 - yb - 230000, [
    "**시사점** 통합디바이스·통합컨트롤러가 스마트 장치 연동을 이미 규정하므로 레이더 모듈을 이 규격에 맞춰 공급한다. "
    "정차(P) 시 후방 경음기만 켜지는 규격은 T2의 후방 경보와 방향이 같다. 길이 1,200~1,300mm, DC 12V 안에서 설계하고 구조변경 승인과 실차 검사를 일정에 넣는다."],
    size=12, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================================
# 9. paths
# ================================================================================
s = new_slide("직납 경로 4가지와 규격 반영 경로", "실적이 없어도 열려 있는 경로부터 밟고, 쇼핑몰은 마지막에 정착한다",
              "근거: 조달청 다수공급자계약 요건(세부품명 거래실례 3건·품목 1건, 특수관계인 거래 불인정), 혁신제품 지정(최대 6년 수의계약). 2026 신청 창구는 상반기 1/30~3/5, 하반기 7/10~8/10.")
rows = [["경로", "방식", "요건", "평가"],
        ["A. 종합쇼핑몰 단품 등록", "수요기관이 쇼핑몰에서 직접 선택", "세부품명 거래실례 3건 이상, 직접생산, KC", "실적 선행 필요, 3단계 목표"],
        ["B. 혁신제품 지정", "최대 6년 수의계약, 조달청 시범구매", "R&D 성과 5년 이내 등, 상·하반기 신청", "최우선, 실적 없이 직납 가능"],
        ["C. 우수제품 지정", "수의계약", "특허·신기술 + 품질 인증", "2단계에서 병행"],
        ["D. 경찰청 교통단속장비 구매", "교통국·시도청 물품구매", "경찰 규격 적합, 단속 정보의 TCS 연계", "현 공급사 1개, 2번째 공급사 수요"],
        ["E. 순찰차 규격 반영", "나눔컴퍼니 통합디바이스 규격과 경찰청 순찰차 사양서에 레이더 연동 반영", "USB 연동 규격 정합, 구조변경 승인, 실차 검사", "가장 빠른 진입, 직납은 아님"]]
yb = add_table(s, L, 1200000, [2900000, 3000000, 3300000, 2260480], rows, size=12, bold_first_col=True, min_row=560000)
card(s, L, yb + 200000, W, 1250000)
tbox(s, L + 250000, yb + 250000, W - 500000, 1150000, [
    ("추천 순서", {"size": 16, "bold": True, "color": NAVY, "space": 4}),
    "D(2027 실적·실증)  →  B(2028 혁신제품)  →  A(2029 종합쇼핑몰)",
    "병행: E로 특장업체·완성차에 레이더 모듈을 공급해 현금흐름과 거래실례를 확보한다."],
    size=13, space=5)

# ================================================================================
# 10. product line-up
# ================================================================================
s = new_slide("제품 개념: 레이더 일체형 스마트 경광등 3개 라인업", "주력은 T2이며 T1은 시장 진입용, T3는 단속 확장용이다",
              "사업계획서 3.1장. 카메라·번호판 인식(T3)은 파트너 협력을 전제로 하며 T2까지는 영상 저장과 식별을 하지 않는다.")
lines = [("T1 기본형", "3단계",
          ["LED 리프트·장방형 경광등과 사이렌앰프 통합 제어(ODM 기반)", "경찰 규격 준수", "용도: 일반 교체 수요, 종합쇼핑몰 단품 진입"]),
         ("T2 레이더형 (주력)", "1~2단계",
          ["T1 + 전·후면 24GHz 레이더 + 제어기 + 운전석 표시기", "영상 저장·식별 없음", "용도: 순찰차·고속순찰대 2차사고 예방, 과속 알림"]),
         ("T3 단속형", "2~3단계",
          ["T2 + 카메라(번호판 인식, 파트너) + LTE + 경찰청 TCS 연계", "차량탑재형 교통단속장비 규격", "용도: 암행순찰차·고속순찰대 단속"])]
cw = (W - 2 * 200000) // 3
for i, (nm, when, bl) in enumerate(lines):
    x = L + i * (cw + 200000)
    card(s, x, 1250000, cw, 4950000)
    label_shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x + 150000, 1400000, cw - 300000, 600000, nm, 16,
                fill=NAVY if i == 1 else BLUE)
    tbox(s, x + 220000, 2200000, cw - 440000, 3300000, bl, size=15, bullet=True, space=12)
    tbox(s, x + 220000, 5600000, cw - 440000, 450000, [f"진입 시점: {when}"], size=14, bold=True, color=NAVY)

# ================================================================================
# 11. features + specs
# ================================================================================
s = new_slide("핵심 기능과 목표 규격(T2)", "후방 접근 경고와 주행 중 속도 검지를 경광등 하나로 처리한다",
              "목표 규격은 MCRT-100N/R 규격에서 가져온 초안이며 주행 중 성능은 아직 검증되지 않은 목표값이다. 개념 시제품으로 실측한 뒤 확정한다.")
feats = ["**후방 접근 경보**: 80m 이내 접근 차량의 속도·거리로 위험을 판단해 경광·사이렌·전광판을 자동 전환",
         "**주행 중 속도 검지**: 자차 속도로 보정해 전방 차량 절대속도를 산출, 임계 초과 시 알림",
         "**전광판 자동 연동**: 정차·리프트 상승·후방 위험 상태에 따라 메시지 자동 전환",
         "**자가진단·원격관리**: 레이더·LED·앰프 상태를 점검해 관제 서버에 보고",
         "**전기차 대응**: 저전력(60W 이하)·경량(25kg 이하), 레이더 고장 시에도 경광은 독립 동작",
         "**규격 호환**: 기존 장방향 경광등 치수(길이 1,200~1,300mm)와 DC 12V, 통합디바이스 USB 연동을 따른다"]
tbox(s, L, 1200000, 5600000, 5000000, feats, size=14, bullet=True, space=14)
rows = [["항목", "목표"],
        ["레이더", "24.05~24.25GHz FMCW, 전·후면 각 1기"],
        ["속도 측정", "0~250km/h, 정지 ±1km/h, 주행 ±3%"],
        ["검지 범위", "전방 5~100m, 후방 5~80m, 수평 ±33°"],
        ["외형", "길이 1,200~1,300mm, 폭 300mm 안팎, 높이 73~167mm 범위(초안)"],
        ["전원·중량", "DC 12V(10~15V), 60W 이하, 25kg 이하(경광 포함)"],
        ["환경", "IP67, -30~+65℃"],
        ["인증", "KC EMC, 전파, 구조변경 승인·교통안전공단 실차 검사"]]
add_table(s, 6300000, 1200000, [1500000, R - 6300000 - 1500000], rows, size=12, bold_first_col=True, min_row=560000)

# ================================================================================
# 12. scope split
# ================================================================================
s = new_slide("개발 범위: 재사용·신규·외부로 나눠 확장을 최소화", "새로 만드는 것은 신호처리와 통합 설계에 한정한다",
              "사업계획서 3.4장, 6.1장. 신규 인력은 하드웨어·기구 1명, 과제관리·인증 1명으로 제한.")
cols = [("재사용", ["레이더 하드웨어·펌웨어(MCRT-100N/R, 빔폭만 조정)", "차량감지제어기·VDU 플랫폼", "자가진단·관제 S/W"]),
        ("신규 개발 (핵심)", ["이동 플랫폼 신호처리", "자차 속도 보정, 정지 클러터 제거", "다중 표적 추적, 후방 위험도 산출"]),
        ("외부 · 협력", ["경광등 광학·하우징·리프트: ODM 협력사", "사이렌앰프·스피커: 규격품 구매", "카메라·번호판 인식(T3): 파트너", "통합디바이스 연동: 나눔컴퍼니와 규격 협의", "인증·시험: 외부 시험기관"])]
cw = (W - 2 * 200000) // 3
for i, (h, bl) in enumerate(cols):
    x = L + i * (cw + 200000)
    card(s, x, 1250000, cw, 3900000)
    label_shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x + 150000, 1400000, cw - 300000, 550000, h, 15,
                fill=NAVY if i == 1 else BLUE)
    tbox(s, x + 220000, 2150000, cw - 440000, 2900000, bl, size=14, bullet=True, space=9)
card(s, L, 5350000, W, 850000)
tbox(s, L + 250000, 5400000, W - 500000, 750000, [
    "인력: 기존 연구 인력 중심에 신규 2명(하드웨어·기구, 과제관리·인증)만 충원한다. 경광등 광학·양산은 협력사가 맡는다."],
    size=14, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================================
# 13. roadmap
# ================================================================================
s = new_slide("사업 로드맵: 4단계로 직납을 정착시킨다", "수요처 구매동의서와 현장 실증을 먼저 확보하고 혁신제품으로 넘어간다",
              "사업계획서 4.1장. 시범구매 30대와 직납 300대는 당사 목표(가정)이며 경찰청 확인이 필요하다.")
st = [("0단계", "2026.10~12 준비", ["경찰 현장 인터뷰 5건 이상", "수요처 구매동의서 협의", "특허 FTO, 선행 특허 출원 준비", "ODM·카메라 파트너 확약", "나눔컴퍼니 통합디바이스 연동 협의"]),
      ("1단계", "2027 개발·과제", ["정부 R&D 1~2건 선정", "시제품 10대(TRL 6)", "시도경찰청 5~10대 시범 장착", "KPEX 출품"]),
      ("2단계", "2028 실증·지정", ["현장 실증(TRL 8)", "혁신제품 지정 신청", "시범구매 30대 내외", "T3 단속형 시제품"]),
      ("3단계", "2029~ 직납 정착", ["수의계약으로 시도청 직납 연 300대", "종합쇼핑몰 단품 등록", "T1 기본형으로 교체 수요 진입", "2030년 이후 연 1,000대"])]
cw = (W - 3 * 160000) // 4
for i, (a, b, bl) in enumerate(st):
    x = L + i * (cw + 160000)
    label_shape(s, MSO_SHAPE.PENTAGON, x, 1250000, cw, 800000, f"{a}\n{b}", 14, fill=NAVY if i % 2 == 0 else BLUE,
                align=PP_ALIGN.LEFT)
    card(s, x, 2200000, cw, 3050000)
    tbox(s, x + 160000, 2350000, cw - 320000, 2800000, bl, size=13, bullet=True, space=8)
card(s, L, 5450000, W, 750000)
tbox(s, L + 250000, 5480000, W - 500000, 690000, [
    "목표 직납 구조: ① 교통단속장비 2번째 공급사(2027~)  ② 혁신제품 수의계약·시범구매(2028~)  ③ 종합쇼핑몰(2029~)"],
    size=14, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================================
# 14. revenue assumption
# ================================================================================
s = new_slide("매출 목표(가정): 2029년 직납 첫해 흑자 전환", "수치는 모두 당사 가정이며 경찰청 물량과 직납 단가는 확인되지 않았다",
              "사업계획서 7장. T2 600만 원, T3 1,500만 원, 레이더 모듈 160만 원(현 공급가) 가정. 손익분기는 2028년 시범구매 시점.")
bar_chart(s, L, 1200000, 6900000, 4600000, "사업 매출과 영업손익(억 원)",
          ["2027", "2028", "2029", "2030"],
          [("사업 매출", (3.0, 5.8, 21.0, 39.0)), ("영업손익", (-0.8, 0.6, 6.0, 12.5))],
          colors=[NAVY, BLUE], fmt="0.0", legend=True, maxv=45)
card(s, 7500000, 1200000, R - 7500000, 4600000)
tbox(s, 7500000 + 220000, 1350000, R - 7500000 - 440000, 4300000, [
    ("가정", {"size": 15, "bold": True, "color": NAVY, "space": 6}),
    "순찰차 경광등 수요 연 1,000~1,200대 (경찰청 확인 필요)",
    "T2 단가 600만 원",
    "2028 시범구매 30대 (1.8억 원)",
    "2029 직납 300대 (18억 원)",
    "2030 직납 600대 (36억 원)",
    "레이더 모듈 공급은 특장업체·완성차 대상"],
    size=14, bullet=False, space=10)

# ================================================================================
# 15. R&D candidates
# ================================================================================
s = new_slide("1억 원 이상 정부 R&D 과제 후보", "구매연계형과 폴리스랩 3.0이 우선이고, 조달청 과제는 수요 목록 확인 후 정한다",
              "출처: 중기부 2026 기술개발 지원사업 통합공고, 과학치안진흥센터 2026 신규사업 공고, 조달청 2026 혁신제품 기술개발 공고(검색 요약 기준). "
              "공고 원문 사이트에 접속하지 못해 금액·일정·요건은 원문 재확인 필요. 2026년 창구는 대부분 마감, 다음 기회는 2027년 상반기로 판단.")
rows = [["과제", "주관", "과제당 지원", "2026 일정(참고)", "핵심 요건", "적합도"],
        ["민관공동기술사업화 R&D 구매연계형", "중기부", "2년 최대 6억", "3차 공고 5/25, 접수 6/15~6/29", "수요처 구매동의서 또는 구매계약서, 상반기 접수 시기 미확인", "★★★★★"],
        ["공공혁신수요기반 혁신제품 기술개발 시범구매연계형", "조달청", "2년 내외 10억 내외", "공고 5/13, 접수 5/18~6/10", "기업부설연구소 필수, 지정 수요 12개 중 1개 선택, 경광등 수요 미확인", "★★★"],
        ["치안현장 맞춤형 R&D 폴리스랩 3.0 신속시범형", "과기정통부·경찰청", "18개월 9억(선정 사례, 한도 미확인)", "선정계획 공고 4/21, 7월 착수", "시제품 보유, 18개월 내 TRL 8·현장 실증, 기업 주관 가능", "★★★★★"],
        ["치안신산업 핵심기술 사업화 지원", "과기정통부·경찰청", "2년 5억 내외", "~3/3 접수", "치안 R&D 성과 보유, 제품화·인증·시장진출 지원", "★★★★"],
        ["기술혁신개발사업 시장대응형", "중기부", "2년 5억", "상·하반기", "중소기업, 수요처 불요(예비)", "★★★"],
        ["경찰청 R&D 기술수요조사", "경찰청", "과제 아님", "3/23~4/21", "누구나 제출, 채택 시 지정공모 과제로 기획", "필수 활동"]]
add_table(s, L, 1200000, [2900000, 1450000, 1600000, 1800000, 2610480, 1100000], rows, size=11.5, bold_first_col=True,
          min_row=640000, aligns=[None, None, None, None, None, PP_ALIGN.CENTER])

# ================================================================================
# 16. combos + calendar
# ================================================================================
s = new_slide("추천 신청 조합과 2027년 캘린더", "수요처 협의가 가장 오래 걸리므로 2026년 4분기에 시작한다",
              "사업계획서 5.2, 5.4장. 접수 시기는 2026년 공고 패턴을 기준으로 한 추정이며 2027 공고 확인 필요. 창업성장(디딤돌)은 창업 7년 이내 대상이라 해당하지 않음.")
combos = [("기본안", "구매연계형(6억) + 폴리스랩 신속시범(9억). 수요처가 다르면 중복이 아니며 한 건만 선정돼도 개발비를 충당한다."),
          ("대안", "조달청 시범구매연계형(10억) 단독. 지정 수요 12개 중 경광등 관련 수요가 있을 때만 가능하며 금액은 가장 크다."),
          ("후속(2028~2029)", "치안신산업 사업화 지원(5억) + 혁신제품 지정. 폴리스랩 성과를 제품화·인증·판로로 잇는다.")]
y = 1200000
for h, b in combos:
    card(s, L, y, 5400000, 1600000)
    tbox(s, L + 200000, y + 120000, 5000000, 1400000, [(h, {"size": 16, "bold": True, "color": NAVY, "space": 3}), (b, {"size": 13})])
    y += 1700000
rows = [["시기", "할 일"],
        ["2026.10~12", "수요처 구매동의서 협의, 특허 FTO, 기획서, ODM 확약, KPEX 신청"],
        ["2027.1~2", "구매연계형 상반기 접수, 벤처·이노비즈 등 가점 인증 확인"],
        ["2027.2~3", "치안신산업 사업화 지원 공고 확인(공동 참여 검토)"],
        ["2027.3~4", "경찰청 R&D 기술수요조사 수요 제출, 폴리스랩 3.0 접수"],
        ["2027.5~6", "조달청 시범구매연계형 접수(수요 목록 확인 후), 구매연계형 하반기"],
        ["2027.7~", "선정 과제 착수, 시제품 제작, 시범 장착"],
        ["2028.1~3", "혁신제품 상반기 지정 신청"]]
add_table(s, 6000000, 1200000, [1500000, R - 6000000 - 1500000], rows, size=12.5, bold_first_col=True, min_row=600000)

# ================================================================================
# 17. project overview + budget chart
# ================================================================================
s = new_slide("제안 과제 개요: 24개월, 총 7.3억 원", "기본안은 중기부 구매연계형이며 공고별 서식에 맞춰 조정한다",
              "개발계획 과제제안서 1, 8장. 정부 지원 비율 약 75%. 지원 비율과 현금·현물 인정 범위는 공고별로 달라 서식에 옮기기 전 재산정 필요.")
rows = [["항목", "내용"],
        ["과제명", "주행·정차 중 전·후방 레이더 기반 2차사고 예방 및 과속 검지 기능을 갖춘 레이더 일체형 스마트 경찰 경광등 개발"],
        ["주관기관", "엠클라비스㈜ (2016년 설립, 서울 서초구)"],
        ["협력", "경광등 하우징·광학 협력사, 시험인증기관, 실증 경찰관서, 수요처"],
        ["기간 · 사업비", "24개월, 7.3억 원 (정부 5.5억 + 민간 1.8억: 현금 0.9, 현물 0.9)"],
        ["기술성숙도", "TRL 4 → 8 (순찰차 10대 3개월 실증)"],
        ["사업화", "혁신제품 지정 신청, 시범구매 30대, 3년차 직납 연 300대"]]
add_table(s, L, 1200000, [1400000, 5200000], rows, size=12.5, bold_first_col=True, min_row=600000)
bar_chart(s, 7300000, 1200000, R - 7300000, 4700000, "비목별 예산(억 원)",
          ["인건비", "연구재료비", "위탁연구", "인증·시험", "현장 실증", "지식재산"],
          [("예산", (2.5, 2.0, 1.4, 0.6, 0.5, 0.3))], fmt="0.0", maxv=3.0, size=10)

# ================================================================================
# 18. WP + gantt
# ================================================================================
s = new_slide("워크패키지와 24개월 일정", "1차년도에 TRL 6, 2차년도에 인증과 현장 실증으로 TRL 8을 달성한다",
              "개발계획 과제제안서 4.3, 5.3장.")
rows = [["WP", "내용", "담당", "기간(개월)"],
        ["WP1", "이동 플랫폼 레이더 신호처리, 후방 위험도 산출", "엠클라비스", "1~14"],
        ["WP2", "경광등 일체형 하우징·광학·전원·EMI 설계, 리프트 연동", "협력사 + 엠클라비스", "1~16"],
        ["WP3", "제어기, 운전석 표시기, 관제 S/W, 경광·전광판 로직", "엠클라비스", "3~18"],
        ["WP4", "인증·경찰 규격 시험, 현장 실증, 사업화 서류", "엠클라비스 + 시험기관 + 경찰", "10~24"]]
yb = add_table(s, L, 1150000, [800000, 6000000, 3400000, 1260480], rows, size=11, bold_first_col=True, min_row=380000,
               aligns=[PP_ALIGN.CENTER, None, None, PP_ALIGN.CENTER])
tasks = [("개념 시제품, 요구사항, 특허 FTO", [1]),
         ("WP1 신호처리 알고리즘", [1, 2, 3, 4]),
         ("WP2 하우징·EMI 설계, 시제품 3대", [1, 2, 3, 4]),
         ("WP3 제어기·관제 S/W", [2, 3, 4, 5]),
         ("1차년도 성능 검증(TRL 6), 특허 출원", [4]),
         ("시제품 10대, 인증·규격 시험", [5, 6]),
         ("현장 실증 10대, 3개월 이상", [6, 7]),
         ("개선·최종 평가, 혁신제품 서류", [7, 8])]
rows = [["구분", "1Q", "2Q", "3Q", "4Q", "5Q", "6Q", "7Q", "8Q"]]
fills = {}
for ri, (nm, act) in enumerate(tasks, start=1):
    rows.append([nm] + [""] * 8)
    for q in act:
        fills[(ri, q)] = BLUE
add_table(s, L, yb + 200000, [4260480] + [900000] * 8, rows, size=10, fills=fills, min_row=310000,
          aligns=[None] + [PP_ALIGN.CENTER] * 8, hdr_size=10)

# ================================================================================
# 19. KPIs
# ================================================================================
s = new_slide("성과지표 11개: 성능과 경찰관 선호도를 함께 본다", "주행 중 성능은 신규 목표라 개념 시제품 실측으로 먼저 검증한다",
              "개발계획 과제제안서 3.2장. 6번과 7번 수치는 제안 시점 추정이며 개념 시제품 측정값으로 대체한다.")
rows = [["번호", "평가항목", "목표", "측정 방법"],
        ["1", "속도 측정 오차(정지)", "±1km/h 이하", "공인시험기관 기준 차량 시험"],
        ["2", "속도 측정 오차(주행 60~120km/h)", "±3% 이내", "GPS 기준 차량과 비교 시험"],
        ["3", "후방 접근차량 검지거리", "80m", "실도로 시험"],
        ["4", "후방 접근 경보 검지율", "95% 이상", "실도로 100회 이상 접근 시험"],
        ["5", "경보 반응 시간(검지→경광 전환)", "0.5초 이하", "시험 장비 계측"],
        ["6", "레이더·제어기 소비전력", "60W 이하", "시험 성적서"],
        ["7", "일체형 장비 중량(경광 포함)", "25kg 이하", "시험 성적서"],
        ["8", "환경 조건", "IP67, -30~+65℃", "인증 시험"],
        ["9", "현장 실증", "10대, 3개월 이상, 만족도 4.0/5 이상", "실증 보고서, 설문"],
        ["10", "지식재산권", "출원 2건, 등록 1건", "출원·등록 증빙"],
        ["11", "경찰관 선호도", "재장착 희망 80% 이상, 유용성 4.0/5 이상", "장착 전·후 설문, 경보 끄기 로그"]]
add_table(s, L, 1200000, [800000, 4300000, 3500000, 2860480], rows, size=12, min_row=410000,
          aligns=[PP_ALIGN.CENTER, None, None, None])

# ================================================================================
# 20. preference validation
# ================================================================================
s = new_slide("선호도 검증 계획과 우려 대응", "현장에서 외면받지 않도록 오경보와 조작 부담을 설계 단계에서 푼다",
              "사업계획서 1.4장. 해결 못 하면 선호가 아닌 외면으로 이어질 수 있는 요인을 먼저 정리했다.")
steps = [("사전 인터뷰 (0단계)", "고속도로순찰대·교통순찰 경찰관 10~20명에게 사고 처리 중 위험 경험, 현재 경광등 불만, 후방 경보 기대를 묻는다."),
         ("실증 설문 (2차년도)", "장착 전·후 설문: 경보 유용성, 오경보 체감, 조작 부담, 안전하다고 느끼는 정도, 계속 장착 희망."),
         ("로그 지표", "경보 발생 횟수, 경찰관이 경보를 끈 횟수, 접근 차량 최대 속도 분포를 자동 기록한다.")]
y = 1200000
for h, b in steps:
    card(s, L, y, 5300000, 1600000)
    tbox(s, L + 200000, y + 120000, 4900000, 1400000, [(h, {"size": 16, "bold": True, "color": NAVY, "space": 3}), (b, {"size": 13})])
    y += 1700000
rows = [["우려", "대응"],
        ["오경보가 잦으면 끄고 쓰지 않는다", "오경보율을 성과지표로 두고 임계값을 경찰관이 조정"],
        ["조작이 번거롭다", "자동 전환 기본, 기존 리프트 경광등 조작 방식과 맞춤"],
        ["단속 기능이 추가 업무가 된다", "T2는 알림까지만, 증거·고지는 T3와 TCS에서 처리"],
        ["무겁고 전력을 많이 쓴다", "25kg·60W 이하 목표, 전기차 12V 대응"],
        ["고장 나면 경광등까지 멈춘다", "레이더 고장 시에도 경광·사이렌 독립 동작"],
        ["가격이 오른다", "경광등·레이더·단속장비 대체 총비용 비교 자료 준비"]]
add_table(s, 5950000, 1200000, [2500000, R - 5950000 - 2500000], rows, size=12, min_row=640000)

# ================================================================================
# 21. risks + 90 days
# ================================================================================
s = new_slide("리스크와 향후 90일 실행 항목", "수요처 확보와 특장 구조 우회가 가장 큰 위험이다",
              "사업계획서 6.4, 8장. 담당과 기한은 초안이며 대표이사 검토 후 확정.")
rows = [["리스크", "대응"],
        ["수요처 구매동의서를 못 받음", "특장업체·완성차로 대체, 수요 불요 과제(폴리스랩, 시장대응형) 병행"],
        ["특장 패키지가 단품 분리를 막음", "혁신제품 수의계약, 교통단속장비 예산으로 우회"],
        ["해외 특허 저촉", "착수 전 FTO, 번호판·얼굴 인식 미포함 유지"],
        ["주행 정확도·EMI 목표 미달", "개념 시제품 조기 검증, 대안 구조 준비"],
        ["과제 탈락", "2건 이상 병행, 자부담 범위 내 T2 최소 시제품 자체 진행"]]
add_table(s, L, 1200000, [2200000, 3500000], rows, size=12, bold_first_col=True, min_row=700000)
acts = [("2026.11.15", "경찰 현장 인터뷰 5건, 수요 우선순위 확정"),
        ("2026.11.30", "구매동의서 협의 개시(후보 3곳)"),
        ("2026.12.15", "해외 특허 FTO, 당사 특허 2건 출원 준비"),
        ("2026.12.15", "경광등 제조사 2곳·나눔컴퍼니 통합디바이스 연동 협의, 확약서 1건"),
        ("2026.12.31", "과제 기획서 완성, 개념 시제품 1대와 알고리즘 검증"),
        ("2026.12.31", "경찰청 경광등·단속장비 규격서 입수, KPEX 부스 신청")]
rows = [["기한", "실행 항목"]] + [[a, b] for a, b in acts]
add_table(s, 6400000, 1200000, [1500000, R - 6400000 - 1500000], rows, size=12, bold_first_col=True, min_row=640000)

# ================================================================================
# 22. evidence level
# ================================================================================
s = new_slide("근거 수준과 확인이 필요한 사항", "제출 전에 원문과 대조해야 하는 항목을 구분했다",
              "접속 차단된 사이트: 중기부·조달청·과학치안진흥센터 공고, 주요 언론 원문. 모든 외부 수치는 검색 결과 요약 기준.")
rows = [["항목", "현재 상태", "필요한 조치"],
        ["과제 금액·일정·요건", "공고 원문 미확인, 검색 요약 기준(구매연계형 3차 6/15~6/29, 조달청 5/18~6/10은 요약끼리 일치)", "공고 원문과 대조, 지정 서식으로 이전"],
        ["조달청 지정 수요", "12개 지정 수요 중 1개 선택, 경광등 관련 수요 미확인", "수요 목록 확인, 없으면 기본안에서 제외"],
        ["접수 중인 과제", "2026.10.6 기준 해당 과제 미확인, 다음 창구는 2027 상반기로 추정", "공고 모니터링, 수요처 구매동의서 선행 확보"],
        ["시장 규모·재무", "당사 가정(순찰차 경광등 연 1,000~1,200대, 단가 600만 원)", "경찰청 연간 물량·직납 단가 확인"],
        ["개발 사양", "기존 레이더 규격 기반 초안, 주행 중 성능 미검증", "개념 시제품 실측 후 지표 확정"],
        ["경찰관 선호도", "설문 자료 없음, 필요 근거만 확인", "사전 인터뷰와 실증 설문으로 검증"],
        ["보도 수치·사실 관계", "탑재형 단속 시기·대수, 경찰관 피해 수치, 경광등 납품사, 해외 특허 한국 출원", "원문 대조, 경찰청 확인, 변리사 검토"]]
add_table(s, L, 1200000, [2500000, 4800000, 4160480], rows, size=12, bold_first_col=True, min_row=600000)

# ================================================================================
# 23. sources
# ================================================================================
s = new_slide("출처", "외부 자료는 2026.10.6 웹 검색 기준이며 원문 대조가 필요하다",
              "링크는 검색 결과에 나온 주소를 그대로 적었다.")
left = ["경찰관 피해·치사율",
        "네이트뉴스 2026.1.10  m.news.nate.com/view/20260110n04374",
        "네이트뉴스 2026.1.4  news.nate.com/view/20260104n08943",
        "전북일보 2025.9.1  jjan.kr/articleAmp/20250901580341",
        "YTN 2026.7.9  ytn.co.kr/_ln/0115_202607091511331613",
        "파이낸셜뉴스 2026.6.24  fnnews.com/news/202606241046506951",
        "다음뉴스 2026.8.9  v.daum.net/v/20260809060311674",
        "리프트 경광등·탑재형 단속",
        "머니투데이 2015.2.12  news.mt.co.kr/mtview.php?no=2015021210368283643",
        "한국일보 2015.2.11  hankookilbo.com/news/article/201502111688050661",
        "충청투데이  cctoday.co.kr/news/articleView.html?idxno=854746",
        "경향신문 2022.3.3  khan.co.kr/article/202203031434001"]
right = ["해외·정책·내부 자료",
         "미국 NIJ 보고서  ojp.gov/pdffiles1/nij/252032.pdf",
         "NIOSH  cdc.gov/niosh/newsroom/feature/struck-by.html",
         "경찰청 K-치안산업 100 (2024.6)",
         "특허 도면: US9002313B2, US9791766B2, US10946793B1, US9928737B2 (엠클라비스 특허 조사 2026.4)",
         "제품 사진·사양: VITRONIC 발표자료(Walter Planer, ASECAP Days 2024.5), Hikvision 리플릿(2023), GET ADHAM 브로슈어, Ekin Patrol G2 매뉴얼(V1.0.241120)",
         "국내 규격: 나눔컴퍼니 순찰차 규격서 3종과 통합디바이스 규격서, 경기북부 자율방범대 경광등 입찰요청서",
         "경찰청 종합쇼핑몰 납품요구 물품 내역 (2024)",
         "엠클라비스 5사 경광등 비교표 (2025.10.31)",
         "엠클라비스 경광등 관련 전세계 동향 (2025.10.31)",
         "엠클라비스 경광등 관련 특허 조사 (2026.4)",
         "엠클라비스 MCRT-100N·100R 소개서, 2026 ITS 세계총회 출품 자료",
         "공고 정보: 중기부 2026 기술개발 지원사업 통합공고, 과학치안진흥센터 2026 신규사업 공고, 조달청 2026 혁신제품 기술개발 공고 (검색 요약 기준)"]
tbox(s, L, 1200000, 5800000, 5000000, [(t, {"size": 12, "bold": True, "color": NAVY, "space": 6}) if i in (0, 7) else (t, {"size": 11, "space": 6})
                                        for i, t in enumerate(left)], size=11)
tbox(s, 6300000, 1200000, R - 6300000, 5000000, [(t, {"size": 12, "bold": True, "color": NAVY, "space": 6}) if i == 0 else (t, {"size": 11, "space": 6})
                                                  for i, t in enumerate(right)], size=11)

prs.save(OUT)
print("saved", OUT, "slides", len(prs.slides))
for w in WARN:
    print("WARN", w)
