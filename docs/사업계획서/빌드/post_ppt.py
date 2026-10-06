import sys, zipfile, re, os, datetime, zoneinfo
src, dst = sys.argv[1], sys.argv[2]
today = datetime.datetime.now(zoneinfo.ZoneInfo('Asia/Seoul')).date()
iso, short, kor = today.strftime('%Y-%m-%d'), today.strftime('%y/%m/%d'), f"{today.year}. {today.month}. {today.day}."
zin = zipfile.ZipFile(src); zout = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
for it in zin.infolist():
    d = zin.read(it.filename)
    if re.match(r'ppt/(slideMasters|slideLayouts|slides|notesMasters|notesSlides)/[^/]+\.xml$', it.filename):
        s = d.decode("utf-8")
        def _fld(m):
            cur = m.group(2)
            new = iso if re.fullmatch(r'\d{4}-\d\d-\d\d', cur) else (short if re.fullmatch(r'\d\d/\d\d/\d\d', cur) else kor)
            return m.group(1) + new + m.group(3)
        s = re.sub(r'(<a:fld [^>]*type="datetime[^"]*"[^>]*>.*?<a:t>)([^<]*)(</a:t>)', _fld, s, flags=re.S)
        s = s.replace('2025-01-19', iso).replace('21/09/09', short).replace('2026. 4. 13.', kor).replace('25/10/31', short)
        d = s.encode("utf-8")
    zout.writestr(it, d)
zout.close()
print(iso, short, kor)
