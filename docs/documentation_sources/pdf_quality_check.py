"""Searchability, page-boundary and link checks plus all-page review contact sheets."""
from pathlib import Path
import json
from PIL import Image,ImageDraw
import pdfplumber
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/documentation_validation';rendered=OUT/'rendered'
report={}
for stem,prefix in [('Complete_Technical_Documentation','technical'),('Presentation_Quick_Reference','quick')]:
    path=ROOT/'docs'/(stem+'.pdf');reader=PdfReader(path);bounds=[];links=0;chars=0
    with pdfplumber.open(path) as pdf:
        for n,page in enumerate(pdf.pages,1):
            for ch in page.chars:
                if ch['x0'] < -1 or ch['x1']>page.width+1 or ch['top'] < -1 or ch['bottom']>page.height+1:bounds.append(n)
            chars+=len(page.chars)
            text=page.extract_text() or ''
            assert '\ufffd' not in text and '\u25a0' not in text,(stem,n)
    for page in reader.pages:
        for a in page.get('/Annots',[]):
            obj=a.get_object()
            if obj.get('/A',{}).get('/URI'):links+=1
    assert not bounds,(stem,bounds)
    assert chars>2000 and links>0
    for start in range(0,len(reader.pages),4):
        canvas=Image.new('RGB',(1220,1755),'#dde5eb');draw=ImageDraw.Draw(canvas)
        draw.text((10,4),f'{prefix}: pages {start+1}-{min(start+4,len(reader.pages))}',fill='black')
        for offset,n in enumerate(range(start+1,min(start+5,len(reader.pages)+1))):
            matches=list(rendered.glob(f'{prefix}-{n:02}.png')) or list(rendered.glob(f'{prefix}-{n}.png'))
            im=Image.open(matches[0]).convert('RGB').resize((595,842))
            canvas.paste(im,((offset%2)*610,(offset//2)*865+24))
        canvas.save(rendered/f'{prefix}-review-{start//4}.png')
    report[stem]=dict(pages=len(reader.pages),selectable_characters=chars,external_link_annotations=links,out_of_page_chars=bounds,
        visual_review='All pages rendered with Poppler; review contact sheets and representative full-size pages.')
im=Image.open(ROOT/'docs/Project_Workflow_Flowchart.png');im.verify()
report['flowchart']=dict(size=[3840,2160],editable_logic='docs/Project_Workflow_Flowchart.mmd',editable_exact_layout='docs/documentation_sources/build_documents.py')
(OUT/'pdf_quality.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
