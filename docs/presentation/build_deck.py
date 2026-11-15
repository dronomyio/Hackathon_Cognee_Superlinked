from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parent
BG='#0B1424'; PANEL='#142238'; WHITE='#F3F7FF'; MUTED='#A7B7CC'; CYAN='#48DAC7'; BLUE='#80AAFF'; AMBER='#FFD282'
DPI=144
prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
previews=[]
def color(c): return RGBColor.from_string(c.lstrip('#'))
def font(size,bold=False):return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial'+(' Bold' if bold else '')+'.ttf',round(size*DPI/72))

def rect(x,y,w,h,fill,radius=False):
    sh=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    sh.fill.solid();sh.fill.fore_color.rgb=color(fill);sh.line.fill.background()
    if radius:sh.adjustments[0]=.08
    box=(round(x*DPI),round(y*DPI),round((x+w)*DPI),round((y+h)*DPI))
    draw.rounded_rectangle(box,radius=14,fill=fill) if radius else draw.rectangle(box,fill=fill)

def text(x,y,w,h,words,size=20,fill=WHITE,bold=False):
    # Explicitly wrap once so PowerPoint and preview use the same line breaks.
    f=font(size,bold);lines=[]
    for para in words.split('\n'):
        line=''
        for word in para.split():
            trial=(line+' '+word).strip()
            if draw.textlength(trial,font=f)>w*DPI and line:lines.append(line);line=word
            else:line=trial
        lines.append(line)
    line_height=size/72*1.18
    assert len(lines)*line_height <= h+.05, (words,len(lines),h)
    box=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=box.text_frame;tf.clear()
    tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0;tf.word_wrap=False
    for i,line in enumerate(lines):
        p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line;p.font.name='Arial';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=color(fill);p.line_spacing=1.18;p.space_before=Pt(0);p.space_after=Pt(0)
        draw.text((x*DPI,(y+i*line_height)*DPI),line,font=f,fill=fill,anchor='lt')

def begin(n,eyebrow,title,subtitle):
    global slide,img,draw
    slide=prs.slides.add_slide(prs.slide_layouts[6]);slide.background.fill.solid();slide.background.fill.fore_color.rgb=color(BG)
    img=Image.new('RGB',(round(13.333*DPI),round(7.5*DPI)),BG);draw=ImageDraw.Draw(img)
    rect(.48,.5,.07,.28,CYAN)
    text(.7,.47,11,.3,'COGNEE × SUPERLINKED  /  '+eyebrow,12,CYAN,True)
    text(.7,1.05,12,1.25,title,34,WHITE,True)
    text(.7,2.27,11.9,.65,subtitle,18,MUTED)
    rect(.7,6.96,11.9,.012,'#293A51')
    text(.7,7.10,10,.23,'HACKATHON  •  PERSONAL MARKET ASSISTANT  •  NOV 2026',9,MUTED)
    text(12,7.07,.6,.3,f'0{n} / 05',10,CYAN,True)

def finish(notes):
    slide.notes_slide.notes_text_frame.text=notes
    img.save(OUT/f'slide-{len(prs.slides)}.png');previews.append(img.copy())

begin(1,'THE PROBLEM','Market news is everywhere.\nPersonal context is missing.','A useful assistant must connect the latest news to what its owner actually holds.')
for x,num,title,body in [(.7,'01','Fragmented information','Articles, video summaries and market prices arrive across separate sources.'),(4.76,'02','Repeated manual work','The owner rechecks headlines and repeats portfolio context in every conversation.'),(8.82,'03','Weak evidence trail','A generic stock list or stale answer can hide what matters—and what is still unknown.')]:
    rect(x,3.25,3.8,2.7,PANEL,True);text(x+.22,3.48,3.3,.5,num,26,CYAN,True);text(x+.22,4.13,3.35,.5,title,19,WHITE,True);text(x+.22,4.8,3.35,1.0,body,16,MUTED)
text(.7,6.25,11.9,.45,'The challenge: turn a stream of headlines into a traceable, personal briefing.',19,WHITE,True)
finish('Problem: news overload is only part of the issue. The assistant also needs persistent ownership context, freshness and an evidence trail. Earlier generic stock research demonstrated why strict holdings-only scope matters. Sources have bounded coverage; the project does not read every news item or every video transcript.')

begin(2,'THE SOLUTION','An assistant that remembers\nwhat matters to you.','A continuous news-to-memory workflow, grounded in your confirmed portfolio.')
for x,title,body in [(.7,'Collect','Check configured crypto sources on a five-minute schedule. Keep dates and source links.'),(4.76,'Prioritize','Weight comma-separated keywords by their order. Investigate only confirmed holdings.'),(8.82,'Remember','Store dated assessments in Cognee. Answer through Band with supporting evidence.')]:
    rect(x,3.2,3.8,2.45,PANEL,True);text(x+.22,3.5,3.3,.5,title,23,CYAN,True);text(x+.22,4.18,3.35,1.15,body,18,WHITE)
rect(.7,5.95,11.9,.63,'#173B3E',True);text(.95,6.1,11.4,.4,'No new news? Log it. Missing evidence? Say “unavailable.”',22,CYAN,True)
finish('The solution combines ordered keyword relevance, source-linked news, portfolio-specific investigations and persistent Cognee memory. The local worker checks on a five-minute schedule, skipping elapsed ticks if a cycle takes longer. No-update checks are logged. This is a research assistant, not automated trading or a prediction of returns.')

begin(3,'HOW IT WORKS','From sources to a usable answer','Each layer has one job—and preserves the evidence needed by the next layer.')
steps=[('1','DISCOVER','Keenable','Dated news and\nYouTube metadata'),('2','PRIORITIZE','Superlinked SIE','Briefing model +\nGLiNER2.5-Decide'),('3','INVESTIGATE','Per-stock workers','Holdings, company news,\nprice and volume'),('4','REMEMBER','Cognee Cloud','forgeclaw-mesh\nDated assessment records'),('5','RESPOND','Band / assistant','Briefings, scores,\nsource links and charts')]
for i,(num,label,title,body) in enumerate(steps):
    x=.7+i*2.42;rect(x,3.3,2.18,2.5,PANEL,True);text(x+.16,3.52,1.9,.35,label,11,CYAN,True);text(x+.16,4.03,1.85,.85,title,20,WHITE,True);text(x+.16,5.02,1.85,.7,body,13,MUTED)
    if i<4:text(x+2.22,4.31,.22,.4,'›',23,CYAN,True)
text(.7,6.08,11.9,.6,'Parallel research collectors • serialized model calls • deduplication • durable upload queue',17,BLUE)
finish('Implementation: Python async workers, Keenable discovery, Superlinked SIE briefing and decision inference, Yahoo Finance adjusted-close and daily-volume data, Cognee REST ingestion/search, and Band SDK messaging. Source collectors have bounded concurrency. Model calls are serialized to respect the available inference concurrency. Cognee persistence uses a local outbox. Dot can coordinate connected-computer work, but its explicit Cognee write test remains unverified; it is not represented here as a completed integration.')

begin(4,'HOW WE BUILT & VALIDATED IT','Personal scope. Observable results.','A local macOS service runs the workflow; exported records make its output inspectable.')
for x,value,label in [(.7,'162','confirmed holdings'),(4.76,'159','price / volume charts'),(8.82,'5 min','configured news checks')]:
    rect(x,3.08,3.8,1.38,PANEL,True);text(x+.23,3.24,3.3,.7,value,36,CYAN,True);text(x+.23,3.96,3.3,.3,label,15,MUTED)
text(.7,4.82,5.65,1.35,'95 US + 67 Indian holdings\n49 automated tests passed\nCSV export + charts + source URLs',20,WHITE)
text(7,4.82,5.6,1.45,'Three market-data gaps remain.\nImpact scores were withheld when evidence was insufficient.\nPrice movement is not proof of causation.',17,MUTED)
finish('Validation snapshot from November 14, 2026: the user confirmed 95 US names as holdings; 67 Indian holdings were recovered from existing memory. 159 of 162 had complete two-week price observations; three were unavailable. Price and volume charts were created for supported holdings. Forty-nine tests passed. In the inspected scoring run, all 74 evaluated news items were classified insufficient and impact scores were withheld. These figures are a dated engineering snapshot, not a performance or investment-return claim.')

begin(5,'VALUE TO A PERSONAL ASSISTANT','Less repeated context.\nMore relevant daily decisions.','The assistant becomes a research companion with memory, priorities and a visible evidence trail.')
rect(.7,3.18,7.1,2.95,PANEL,True)
text(.95,3.45,6.6,.4,'WHAT THE OWNER CAN ASK',12,CYAN,True)
text(.95,4.06,6.5,1.65,'“What changed since my last briefing?”\n“Which of my holdings deserve investigation?”\n“Show 10 US and 10 Indian stocks with sources.”',22,WHITE)
text(8.2,3.4,4.25,1.7,'Remember my portfolio.\nRespect my keyword priorities.\nShow fresh evidence.\nMake uncertainty explicit.',21,WHITE,True)
rect(.7,6.28,11.9,.44,'#3B3024',True);text(.87,6.37,11.55,.25,'NEXT: reliable ingestion receipts and a verified Dot–Cognee write → index → recall test.',12,AMBER)
finish('Personal-assistant value: reduce repeated portfolio explanations, prioritize relevant news, preserve source provenance, compare with historical memory, and surface evidence gaps. The owner can request a 20-stock view selected only from their 162 holdings. Band access and local reports work. The explicit Dot–Cognee connection-test marker was absent from raw storage and search; one controlled write timed out while another document was processing. Reliable write receipts and verified retrieval remain the next milestone. No automatic trading is implemented.')

prs.core_properties.title='Cognee × Superlinked: Personal Market Assistant'
prs.core_properties.subject='Problem, solution, architecture, validation, and personal-assistant value'
prs.core_properties.author='Hackathon project'
prs.save(OUT/'Cognee_Superlinked_5_Slides.pptx')
previews[0].save(OUT/'Cognee_Superlinked_5_Slides.pdf',save_all=True,append_images=previews[1:],resolution=DPI)
thumbs=[]
for im in previews:
    im=im.copy();im.thumbnail((640,360));thumbs.append(im)
contact=Image.new('RGB',(1280,1080),'#202A3B')
for i,im in enumerate(thumbs):contact.paste(im,((i%2)*640,(i//2)*360))
contact.save(OUT/'preview.png')
print('Created PowerPoint, PDF and five-slide preview.')
