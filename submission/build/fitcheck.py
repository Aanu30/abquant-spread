"""Checks every text box of a .pptx: does the wrapped text fit its box? Uses the real Calibri/Cambria files."""
import sys, zipfile, re
from lxml import etree
from PIL import ImageFont

D = "/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts/"
FONTS = {("Calibri", False): D + "Calibri.ttf", ("Calibri", True): D + "Calibrib.ttf",
         ("Cambria", False): D + "Cambria.ttc", ("Cambria", True): D + "Cambriab.ttf"}
_cache = {}
def font(face, bold, size):
    face = "Cambria" if "Cambria" in face or face.startswith("+mj") else "Calibri"
    key = (face, bold, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(FONTS[(face, bold)], int(size * 20))  # 20 px per pt for precision
    return _cache[key]

ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main", "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
EMU = 914400
path = sys.argv[1]
z = zipfile.ZipFile(path)
slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)], key=lambda n: int(re.findall(r"\d+", n)[0]))
problems = 0
for sn in slides:
    root = etree.fromstring(z.read(sn))
    num = int(re.findall(r"\d+", sn)[0])
    for sp in root.iter("{%s}sp" % ns["p"]):
        tx = sp.find("p:txBody", ns)
        if tx is None:
            continue
        off, ext = sp.find(".//a:off", ns), sp.find(".//a:ext", ns)
        if off is None or ext is None:
            continue
        w, h = int(ext.get("cx")) / EMU, int(ext.get("cy")) / EMU
        body = tx.find("a:bodyPr", ns)
        l = int(body.get("lIns", 91440)) / EMU; r = int(body.get("rIns", 91440)) / EMU
        t = int(body.get("tIns", 45720)) / EMU; b = int(body.get("bIns", 45720)) / EMU
        avail_w = (w - l - r) * 72  # points
        total_h, name = 0.0, sp.find("p:nvSpPr/p:cNvPr", ns).get("name")
        text_all = ""
        for para in tx.findall("a:p", ns):
            ppr = para.find("a:pPr", ns)
            indent = 0
            if ppr is not None and ppr.find("a:buChar", ns) is not None:
                indent = 18
            words, maxsz = [], 0
            for run in para.findall("a:r", ns):
                rp = run.find("a:rPr", ns)
                sz = int(rp.get("sz", 1800)) / 100 if rp is not None else 18
                bold = rp is not None and rp.get("b") == "1"
                lat = rp.find("a:latin", ns) if rp is not None else None
                face = lat.get("typeface") if lat is not None else "Calibri"
                maxsz = max(maxsz, sz)
                for wd in re.findall(r"\S+\s*", run.find("a:t", ns).text or ""):
                    words.append((wd, face, bold, sz))
                text_all += run.find("a:t", ns).text or ""
            if not words:
                total_h += 14 * 1.2
                continue
            lines, cur = 1, 0.0
            for wd, face, bold, sz in words:
                wpx = font(face, bold, sz).getlength(wd.rstrip()) / 20
                spw = font(face, bold, sz).getlength(" ") / 20 if wd != wd.rstrip() else 0
                if cur + wpx > avail_w - indent and cur > 0:
                    lines += 1; cur = 0.0
                cur += wpx + spw
            sa = 0
            if ppr is not None and ppr.find("a:spcAft/a:spcPts", ns) is not None:
                sa = int(ppr.find("a:spcAft/a:spcPts", ns).get("val")) / 100
            total_h += lines * maxsz * 1.2 + sa
        need = total_h / 72 + t + b
        if need > h + 0.02:
            problems += 1
            print(f"slide {num}: '{name}' needs {need:.2f} in but box is {h:.2f} in  [{text_all[:50]}]")
print("overflow problems:", problems)
