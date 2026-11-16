"""Build FR/EN print versions from Markdown: python scripts/build_one_pager.py --pdf.

HTML needs only Python. PDF needs ReportLab and DejaVu Sans (no AWS/network calls).
"""
from __future__ import annotations
import argparse
from html import escape
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CSS = '''@page{size:A4;margin:13mm}*{box-sizing:border-box}body{margin:0;color:#20202a;font:10.1pt/1.37 Arial,sans-serif;background:#fff}h1{font-size:29pt;letter-spacing:-1pt;margin:0;color:#29203d}h2{font-size:12.7pt;font-weight:500;margin:2mm 0 3mm;color:#6550a2}header{border-bottom:2px solid #7a5af5;padding-bottom:3mm;margin-bottom:4mm}header p{font-size:8.2pt;color:#55505f;margin:1.5mm 0}a{color:#57418f;text-decoration:none}main{columns:2;column-gap:7mm}section{break-inside:avoid;margin:0 0 3.3mm}h3{font-size:10.7pt;margin:0 0 1.3mm;color:#57418f}p{margin:0 0 2mm}strong{font-weight:700}section:first-child{background:#f4f0fc;padding:3mm;border-radius:2mm}section:last-child{background:#fff5e8;border-left:2pt solid #c88627;padding:2.5mm}footer{border-top:1px solid #ddd6eb;margin-top:3mm;padding-top:2mm;color:#625b6c;font-size:7.5pt;line-height:1.35}footer p{margin:0 0 1mm}'''


def inline(text, pdf=False):
    text = escape(text, quote=False)
    text = re.sub(r'\[([^]]+)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>' if pdf else r'<strong>\1</strong>', text)
    return re.sub(r'\*([^*]+)\*', r'<i>\1</i>' if pdf else r'<em>\1</em>', text)


def parse(source):
    title, tagline, meta, sections, footer = '', '', [], [], []
    for block in source.strip().split('\n\n'):
        if block.startswith('# '):
            title = block[2:]
        elif block.startswith('## '):
            tagline = block[3:]
        elif block.startswith('### '):
            lines = block.split('\n',1)
            sections.append((lines[0][4:], [lines[1]] if len(lines)>1 else []))
        elif block.startswith('*') and not block.startswith('**'):
            footer.append(block)
        elif not sections:
            meta.append(block)
        else:
            sections[-1][1].append(block)
    return title, tagline, meta, sections, footer


def render(source, lang):
    title, tagline, meta, sections, footer = parse(source)
    return ('<!doctype html><html lang="'+lang+'"><meta charset="utf-8"><title>AlphaForge AI</title><style>'+CSS+
            '</style><header><h1>'+inline(title)+'</h1><h2>'+inline(tagline)+'</h2>'+''.join('<p>'+inline(t)+'</p>' for t in meta)+
            '</header><main>'+''.join('<section><h3>'+inline(t)+'</h3>'+''.join('<p>'+inline(p)+'</p>' for p in paras)+'</section>' for t,paras in sections)+
            '</main><footer>'+''.join('<p>'+inline(p)+'</p>' for p in footer)+'</footer></html>')


def pdf(source, output):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, KeepTogether, PageTemplate, Paragraph, Spacer
    family = Path('/usr/share/fonts/truetype/dejavu')
    for name,file in [('AF','DejaVuSans.ttf'),('AF-Bold','DejaVuSans-Bold.ttf'),('AF-Italic','DejaVuSans-Oblique.ttf'),('AF-BoldItalic','DejaVuSans-BoldOblique.ttf')]:
        pdfmetrics.registerFont(TTFont(name,str(family/file)))
    pdfmetrics.registerFontFamily('AF',normal='AF',bold='AF-Bold',italic='AF-Italic',boldItalic='AF-BoldItalic')
    title, tagline, meta, sections, footer = parse(source)
    w,h=A4
    margin,gap,bottom,top=36,20,62,h-132
    width=(w-2*margin-gap)/2
    height=top-bottom
    ink,accent,muted=colors.HexColor('#23202b'),colors.HexColor('#6550a2'),colors.HexColor('#655f6c')
    def style(size,leading,**kw):
        options=dict(fontName='AF',fontSize=size,leading=leading,textColor=ink,alignment=TA_LEFT)
        options.update(kw)
        return ParagraphStyle('af',**options)
    heading=style(10.2,13.2,fontName='AF-Bold',textColor=accent,spaceAfter=3)
    groups=[]
    for font in (10.1,9.9,9.7,9.5):
        body=style(font,font*1.36,spaceAfter=5)
        groups=[]
        for label,paras in sections:
            groups.append([Paragraph(inline(label,True),heading),*[Paragraph(inline(p,True),body) for p in paras],Spacer(1,5)])
        sizes=[sum(f.wrap(width,10000)[1]+getattr(f,'spaceAfter',0) for f in group) for group in groups]
        split=min(range(1,len(groups)),key=lambda i:max(sum(sizes[:i]),sum(sizes[i:])))
        if max(sum(sizes[:split]),sum(sizes[split:])) <= height-10:
            break
    else:
        raise RuntimeError('Content does not fit one page at a readable type size.')
    def draw(canvas,doc):
        canvas.setTitle('AlphaForge AI — One-pager')
        canvas.setAuthor('William Caron-Bastarache · Joud Katbe')
        y=h-32
        for text,sty,space in [(title,style(27,31,fontName='AF-Bold'),4),(tagline,style(11.5,15,textColor=accent),6),*[(m,style(7.8,10.5,textColor=muted),2) for m in meta]]:
            para=Paragraph(inline(text,True),sty);_,ph=para.wrap(w-2*margin,200)
            y-=ph;para.drawOn(canvas,margin,y);y-=space
        canvas.setStrokeColor(accent);canvas.setLineWidth(1.5);canvas.line(margin,y-3,w-margin,y-3)
        canvas.setStrokeColor(colors.HexColor('#ded8e8'));canvas.setLineWidth(.5);canvas.line(margin,51,w-margin,51)
        y=43
        for text in footer:
            para=Paragraph(inline(text,True),style(6.7,9,textColor=muted));_,ph=para.wrap(w-2*margin,60)
            para.drawOn(canvas,margin,y-ph+6);y-=ph+2
    frames=[Frame(margin,bottom,width,height,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0),Frame(margin+width+gap,bottom,width,height,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]
    doc=BaseDocTemplate(str(output),pagesize=A4)
    doc.addPageTemplates(PageTemplate(id='two-columns',frames=frames,onPage=draw))
    story=[]
    for i,group in enumerate(groups):
        if i==split:story.append(FrameBreak())
        story.append(KeepTogether(group))
    doc.build(story)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',action='store_true')
    args=parser.parse_args()
    for lang,stem in [('fr','ONE_PAGER'),('en','ONE_PAGER.en')]:
        path=ROOT/'deliverables'/stem
        source=Path(str(path)+'.md').read_text()
        html=Path(str(path)+'.html');html.write_text(render(source,lang));print(html.relative_to(ROOT))
        if args.pdf:
            output=Path(str(path)+'.pdf');pdf(source,output);print(output.relative_to(ROOT))


if __name__=='__main__':
    main()
