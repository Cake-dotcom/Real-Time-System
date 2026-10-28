"""Documentation-only deterministic PDF/diagram authoring; requires ReportLab/Pillow."""
from pathlib import Path
import re
from html import escape
from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.platypus import BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak,Table,TableStyle,Preformatted,Image
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[2]; DOCS=ROOT/'docs'; HERE=Path(__file__).parent
FONT=Path('C:/Windows/Fonts')
for name,file in [('Body','arial.ttf'),('Bold','arialbd.ttf'),('Mono','consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONT/file)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Body',boldItalic='Bold')
NAVY='#17324d'; BLUE='#235789'; TEAL='#247a63'


def diagram():
    # Editable source for exact PNG geometry is this function; .mmd preserves logic.
    im=PILImage.new('RGB',(3840,2160),'white'); d=ImageDraw.Draw(im); S=2
    def font(size,bold=False): return ImageFont.truetype(str(FONT/('arialbd.ttf' if bold else 'arial.ttf')),size*S)
    def text(x,y,s,size=25,bold=False,fill=NAVY,anchor='mm'):
        d.multiline_text((x*S,y*S),s,font=font(size,bold),fill=fill,anchor=anchor,align='center',spacing=6*S)
    def box(x,y,w,h,s,kind='process'):
        fills={'process':('#eaf2fb',BLUE),'reject':('#fbe9e7','#ae4943'),'output':('#e5f4ee',TEAL)}
        fill,edge=fills[kind]
        d.rounded_rectangle((x*S,y*S,(x+w)*S,(y+h)*S),radius=18*S,fill=fill,outline=edge,width=3*S)
        text(x+w/2,y+h/2,s,25,True)
    def diamond(x,y,w,h,s):
        d.polygon([(x*S,(y-h/2)*S),((x+w/2)*S,y*S),(x*S,(y+h/2)*S),((x-w/2)*S,y*S)],fill='#fff3d6',outline='#a26a16',width=3*S)
        text(x,y,s,24,True,fill='#573a10')
    def arrow(points,label=None,lxy=None,dashed=False):
        pts=[(int(x*S),int(y*S)) for x,y in points]
        d.line(pts,fill='#546777',width=3*S)
        x,y=points[-1]; px,py=points[-2]
        if x==px: tri=[(x,y),(x-7,y-12 if y>py else y+12),(x+7,y-12 if y>py else y+12)]
        else: tri=[(x,y),(x-12 if x>px else x+12,y-7),(x-12 if x>px else x+12,y+7)]
        d.polygon([(a*S,b*S) for a,b in tri],fill='#546777')
        if label: text(*lxy,label,21,True)
    text(960,65,'Security-Aware Real-Time Scheduling',45,True)
    text(960,120,'Security decisions change execution cost. Execution cost changes deadline feasibility.',27)
    box(55,210,290,150,'Configure workload\nRelease signed\nmessage')
    diamond(540,285,290,200,'Session, MAC\nand replay\nvalid?')
    box(765,210,420,150,'Validate reading / timing\nEvaluate health\nAssess sensor risk')
    diamond(1470,285,350,200,'Healthy +\nrequired checks\npass?')
    arrow([(345,285),(395,285)])
    arrow([(685,285),(765,285)],'Yes',(723,255))
    arrow([(1185,285),(1295,285)])
    box(715,430,510,100,'Reject / record gate failure\nNo trusted-history commit','reject')
    arrow([(540,385),(540,480),(715,480)],'No',(575,420))
    arrow([(1470,385),(1470,480),(1225,480)],'No',(1507,420))
    box(1480,650,350,150,'Risk-required mechanism\nFull remaining budget')
    arrow([(1645,285),(1870,285),(1870,725),(1830,725)],'Yes',(1740,255))
    diamond(1230,725,300,190,'Released demand\nfeasible?')
    arrow([(1480,725),(1380,725)])
    box(780,650,270,150,'EDF / fixed-point\nexecution\nAccount costs')
    arrow([(1080,725),(1050,725)],'Yes',(1063,615))
    diamond(535,725,300,190,'On time +\nprotection\nvalid?')
    arrow([(780,725),(685,725)])
    box(55,650,300,150,'Commit newer\ntrusted history\nReport results','output')
    arrow([(385,725),(355,725)],'Yes',(368,615))
    box(1000,875,490,110,'Critical-first subset / defer / reject\nSafe state if protected failure','reject')
    arrow([(1230,820),(1230,875)],'No',(1270,846))
    box(325,875,430,110,'Fail-stop / cleanup\nRecord actual outcome','reject')
    arrow([(535,820),(535,875)],'No',(575,846))
    text(1675,902,'Deferred work:\nrecheck at later events',22)
    text(960,1030,'All outcomes feed trace / metrics / dashboard. Only successful newer readings update trusted history.',23,True)
    text(960,1070,'Authenticated laboratory path. Synthetic scheduler benchmarks and legacy login are separate.',18)
    im.save(DOCS/'Project_Workflow_Flowchart.png',dpi=(300,300))


class Guide(BaseDocTemplate):
    def afterFlowable(self,flow):
        if isinstance(flow,Paragraph) and flow.style.name=='Chapter' and flow.getPlainText()!='Contents':
            label=flow.getPlainText(); key='chapter-'+str(self.seq.nextf('chapter'))
            self.canv.bookmarkPage(key); self.canv.addOutlineEntry(label,key,0)
            self.notify('TOCEntry',(0,label,self.page,key))


def inline(s):
    s=s.replace('→',' -> ').replace('−','-').replace('–','-').replace('—',' - ')
    s=escape(s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    s=re.sub(r'`([^`]+)`',r'<font name="Mono">\1</font>',s)
    s=re.sub(r'(https?://[^\s<>]+)',lambda m:'<link href="'+m[1].rstrip('.,')+'" color="#235789">'+m[1].rstrip('.,')+'</link>'+m[1][len(m[1].rstrip('.,')):],s)
    return s


def build(source,target,quick=False):
    width,height=A4; margin=43; usable=width-2*margin
    body=ParagraphStyle('Body',fontName='Body',fontSize=10.3 if not quick else 11.1,leading=14.2 if not quick else 15.3,spaceAfter=8,textColor=colors.HexColor(NAVY),splitLongWords=True)
    chapter=ParagraphStyle('Chapter',parent=body,fontName='Bold',fontSize=23,leading=28,spaceAfter=17)
    sub=ParagraphStyle('Sub',parent=body,fontName='Bold',fontSize=13,leading=17,spaceBefore=9,spaceAfter=7,keepWithNext=True)
    small=ParagraphStyle('Small',parent=body,fontSize=8.5,leading=11,spaceAfter=0)
    code=ParagraphStyle('Code',fontName='Mono',fontSize=8.1,leading=11,spaceBefore=6,spaceAfter=10,textColor=colors.HexColor(NAVY),backColor=colors.HexColor('#f1f5f9'),borderPadding=8)
    doc=Guide(str(target),pagesize=A4,leftMargin=margin,rightMargin=margin,topMargin=59,bottomMargin=45,
        title='Presentation Quick Reference' if quick else 'Complete Technical Documentation',author='Security-Aware Real-Time Sensor Scheduling System')
    def furniture(c,d):
        c.setFillColor(colors.HexColor(BLUE));c.rect(0,height-14,width,14,fill=1,stroke=0)
        c.setFont('Body',8);c.setFillColor(colors.HexColor('#546777'))
        c.drawString(margin,height-34,'SECURITY-AWARE REAL-TIME SENSOR SCHEDULING SYSTEM')
        c.setStrokeColor(colors.HexColor('#d6e1ea'));c.line(margin,34,width-margin,34)
        c.drawString(margin,22,'Presentation reference' if quick else 'Implementation guide | 2026-10-29')
        c.drawRightString(width-margin,22,str(d.page))
    doc.addPageTemplates(PageTemplate(id='main',frames=[Frame(margin,45,usable,height-104,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=furniture))
    story=[]
    if not quick:
        story += [Spacer(1,60),Paragraph('Complete Technical<br/>Documentation',ParagraphStyle('Title',parent=chapter,fontSize=34,leading=41)),Spacer(1,15),
            Paragraph('Security-Aware Real-Time<br/>Sensor Scheduling System',ParagraphStyle('Subtitle',parent=body,fontSize=21,leading=29)),Spacer(1,22),
            Paragraph('An implementation-grounded guide for setup, security, models, scheduling, experiments and development.',body),Spacer(1,22),
            Image(str(DOCS/'Project_Workflow_Flowchart.png'),width=usable,height=usable*9/16),Spacer(1,20),
            Paragraph('Edition: 29 October 2026<br/>Scope: documentation only; no runtime or research artifacts changed.<br/>Evidence: source inspection, preserved results and explicit validation records.',body),PageBreak(),
            Paragraph('Contents',chapter)]
        toc=TableOfContents();toc.levelStyles=[ParagraphStyle('TOC',fontName='Body',fontSize=10.5,leading=13,spaceBefore=0,textColor=colors.HexColor(NAVY))]
        story += [toc,PageBreak()]
    content=source.read_text(encoding='utf-8-sig')
    if not quick:
        content+='\n\n'+(HERE/'Command_Reference.md').read_text(encoding='utf-8-sig').replace('# Command reference and verification status','# Appendix. Command reference and verification status',1)
    lines=content.splitlines();i=0;first=True
    while i<len(lines):
        line=lines[i].strip()
        if not line: i+=1;continue
        if line.startswith('# '):
            if not first: story.append(PageBreak())
            first=False;story.append(Paragraph(inline(line[2:]),chapter));i+=1;continue
        if line.startswith('## '): story.append(Paragraph(inline(line[3:]),sub));i+=1;continue
        if line=='[WORKFLOW]':
            story.extend([Image(str(DOCS/'Project_Workflow_Flowchart.png'),width=usable,height=usable*9/16),Spacer(1,10)]);i+=1;continue
        if line.startswith('```'):
            rows=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                rows.append(lines[i]);i+=1
            story.append(Preformatted('\n'.join(rows),code,maxLineLength=92));i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[x.strip() for x in lines[i].strip().strip('|').split('|')];i+=1
                if all(re.fullmatch(r'[:\- ]+',x) for x in row):continue
                rows.append([Paragraph(inline(x),small) for x in row])
            count=len(rows[0]); widths=[usable/count]*count
            if count==2:widths=[usable*.37,usable*.63]
            t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce9f5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.8,colors.HexColor(BLUE)),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8fb')]),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#d6e1ea'))]))
            story.extend([t,Spacer(1,10)]);continue
        if line.startswith('- '):
            story.append(Paragraph(inline(line[2:]),ParagraphStyle('Bullet',parent=body,leftIndent=12,firstLineIndent=-8),bulletText='•'));i+=1;continue
        story.append(Paragraph(inline(line),body));i+=1
    doc.multiBuild(story)


if __name__=='__main__':
    diagram()
    build(HERE/'Quick_Reference.md',DOCS/'Presentation_Quick_Reference.pdf',True)
    build(HERE/'Technical_Documentation.md',DOCS/'Complete_Technical_Documentation.pdf')
    print('Built two searchable PDFs and 3840x2160 workflow PNG.')
