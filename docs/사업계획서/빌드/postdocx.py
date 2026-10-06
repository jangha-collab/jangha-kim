import sys, zipfile, re, os
f=sys.argv[1]; tmp=f+".tmp"
zin=zipfile.ZipFile(f); zout=zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED)
B=('<w:tblBorders>'+''.join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>' for e in ("top","left","bottom","right","insideH","insideV"))+'</w:tblBorders>')
def fix_table(t):
    t=re.sub(r'(<w:tblLook [^>]*/>)(<w:jc [^>]*/>)', r'\2'+B+r'\1', t, count=1)
    def hdr(m):
        r=m.group(0)
        r=r.replace('<w:tcPr />','<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="E8EEF7"/></w:tcPr>')
        return r.replace('<w:r><w:t','<w:r><w:rPr><w:b/></w:rPr><w:t')
    return re.sub(r'<w:tr><w:trPr><w:tblHeader.*?</w:tr>', hdr, t, count=1, flags=re.S)
for it in zin.infolist():
    d=zin.read(it.filename)
    if it.filename=="word/document.xml":
        s=d.decode("utf-8")
        s=re.sub(r'<w:tbl>.*?</w:tbl>', lambda m: fix_table(m.group(0)), s, flags=re.S)
        d=s.encode("utf-8")
    zout.writestr(it,d)
zout.close(); os.replace(tmp,f)
