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
    text(.7,7.10,10,.23,'HACKATHON  •  A UNIFIED BRAIN FOR PERSONAL ASSISTANTS  •  NOV 2026',9,MUTED)
    text(12,7.07,.6,.3,f'0{n} / 06',10,CYAN,True)

def finish(notes):
    slide.notes_slide.notes_text_frame.text=notes
    img.save(OUT/f'slide-{len(prs.slides)}.png');previews.append(img.copy())

begin(1,'THE PROBLEM','Personal assistants need\na unified brain.','Your personal context, assistant conversations and external research live in separate places.')
for x,num,title,body in [(.7,'01','Your context is split','Muse or Dot may know your preferences, goals and holdings—but that context is not automatically shared.'),(4.76,'02','Research is separate','Specialist agents find new information, but their findings need a durable path back to your assistant.'),(8.82,'03','You reconnect the dots','You repeat context, move answers between tools and work out whether an old finding is still relevant.')]:
    rect(x,3.25,3.8,2.7,PANEL,True);text(x+.22,3.48,3.3,.5,num,26,CYAN,True);text(x+.22,4.13,3.35,.5,title,19,WHITE,True);text(x+.22,4.75,3.35,1.15,body,16,MUTED)
text(.7,6.27,11.9,.45,'The missing layer: shared memory that connects “what you know about me” to “what is new.”',18,WHITE,True)
finish('Lead with the unified-brain problem, not cryptocurrency news. Personal assistants and specialist research tools each hold part of the context. The owner wants a shared, permissioned memory layer so relevant personal facts and external findings can be reused across assistants. This is not a claim that all private conversations are automatically synchronized.')

begin(2,'THE SOLUTION','Give your personal assistant\na bigger brain.','Cognee connects your personal context with fresh research from Superlinked agents.')
for x,title,body in [(.7,'Personal context','Muse or Dot contributes the context you choose: preferences, goals, holdings and prior decisions.'),(4.76,'Shared memory','Cognee is the common knowledge layer: linked facts, dated findings, source URLs and assessment history.'),(8.82,'External research','Superlinked-powered agents investigate new information and return useful evidence to that shared memory.')]:
    rect(x,3.2,3.8,2.55,PANEL,True);text(x+.22,3.48,3.35,.5,title,22,CYAN,True);text(x+.22,4.14,3.35,1.4,body,18,WHITE)
rect(.7,6.02,11.9,.63,'#173B3E',True);text(.95,6.17,11.4,.4,'Personal context + shared memory + specialist research = a better-informed assistant.',19,CYAN,True)
finish('The bigger brain is a metaphor for expanding accessible memory and evidence, not changing or training the underlying model. Target workflow: permitted context from Muse or Dot enters Cognee; research workers enrich the shared memory; connected assistants retrieve it. Explain that financial research is the first demonstration of this architecture, not its entire purpose.')

begin(3,'THE UNIFIED BRAIN','Different assistants.\nOne shared knowledge layer.','Target architecture: use the assistant you prefer, while authorized context stays connected.')
for y,title,body in [(3.25,'Muse','Personal context + questions'),(4.82,'OpenAI Dot','Personal context + questions')]:
    rect(.7,y,3.1,1.27,PANEL,True);text(.93,y+.18,2.65,.4,title,22,WHITE,True);text(.93,y+.72,2.65,.4,body,13,MUTED)
    text(3.98,y+.35,.55,.5,'↔',25,CYAN,True)
rect(4.65,3.25,3.75,2.84,'#173B3E',True);text(4.95,3.55,3.15,.55,'COGNEE',30,CYAN,True);text(4.95,4.23,3.15,.5,'THE UNIFIED BRAIN',14,CYAN,True);text(4.95,4.85,3.15,1.0,'Personal facts\nResearch + source evidence\nShared, dated memory',16,WHITE)
text(8.58,4.26,.55,.5,'↔',25,CYAN,True)
rect(9.25,3.25,3.37,2.84,PANEL,True);text(9.48,3.52,2.9,.8,'Superlinked\nresearch agents',23,WHITE,True);text(9.48,4.56,2.9,1.25,'Keenable discovery\nExternal news and video\nMarket data\nAnalysis and scoring',16,MUTED)
text(.7,6.37,11.9,.3,'Shared access is permissioned. End-to-end Dot write/index/recall verification remains pending.',13,AMBER)
finish('This diagram represents the intended cross-assistant architecture. A fact shared by Muse could be reused in Dot, and an approved finding from Dot could be reused in Muse, through the same Cognee dataset. The direct bidirectional Dot integration is not yet verified. Existing project memory and research records are in forgeclaw-mesh, and the Band interface works. Do not describe this as a completed automatic sync of all assistant conversations.')

begin(4,'HOW WE SOLVE IT','A continuous learning loop\naround your personal assistant.','The research workers do the extra work; the assistant stays focused on your question.')
steps=[('1','CONTEXT','Understand you','Use approved preferences,\ngoals and holdings.'),('2','RESEARCH','Investigate','Keenable discovers news;\nworkers check the evidence.'),('3','ASSESS','Find relevance','Ordered keywords +\nSuperlinked decision model.'),('4','REMEMBER','Build memory','Save dated findings and\nlinks in Cognee.'),('5','REUSE','Answer anywhere','Connected assistants\nretrieve shared knowledge.')]
for i,(num,label,title,body) in enumerate(steps):
    x=.7+i*2.42;rect(x,3.3,2.18,2.5,PANEL,True);text(x+.16,3.52,1.9,.35,label,11,CYAN,True);text(x+.16,4.03,1.85,.85,title,20,WHITE,True);text(x+.16,4.95,1.85,.8,body,12,MUTED)
    if i<4:text(x+2.22,4.31,.22,.4,'›',23,CYAN,True)
text(.7,6.14,11.9,.55,'Five-minute news checks • deduplicate findings • log no updates • preserve sources and uncertainty',16,BLUE)
finish('Built with Python async workers, Keenable discovery, Superlinked SIE briefing and GLiNER2.5-Decide inference, Cognee Cloud memory and Band messaging. The local service schedules news checks every five minutes and skips elapsed ticks when work runs longer. It retains a durable outbox for ingestion. Reuse across Muse and Dot is the target enabled by shared access; the Dot-specific connection test still needs to succeed. This loop enriches stored knowledge rather than retraining the assistant model.')

begin(5,'FIRST USE CASE','A personal market assistant\nthat researches your actual holdings.','Crypto news is the first demonstration of the unified brain—not the limit of the idea.')
for x,value,label in [(.7,'162','confirmed personal holdings'),(4.76,'159','price / volume charts'),(8.82,'5 min','configured news checks')]:
    rect(x,3.08,3.8,1.38,PANEL,True);text(x+.23,3.24,3.3,.7,value,36,CYAN,True);text(x+.23,3.96,3.3,.3,label,15,MUTED)
text(.7,4.83,5.65,1.5,'Cognee supplies the personal context.\nWorkers research 95 US + 67 Indian holdings.\nThe assistant returns a relevant briefing.',19,WHITE)
text(7,4.83,5.6,1.5,'Observed results: charts, CSV and source links.\n49 tests passed; three price-data gaps.\nImpact estimates withheld when evidence was insufficient.',17,MUTED)
finish('November 14, 2026 validation snapshot: 67 Indian holdings were retrieved from existing Cognee memory; the user confirmed the saved 95 US names as holdings. The workflow restricted research to those 162 names. 159 had complete two-week observations and supported charts. Forty-nine tests passed. All evaluated impact classifications in the inspected run were insufficient, so the slides do not claim actionable impact predictions. This use case demonstrates personal context informing external research and returning evidence to shared memory.')

begin(6,'WHY IT HELPS','Your assistant knows you.\nNow it can build on more knowledge.','The vision: work started in one assistant becomes useful context in another, with your permission.')
rect(.7,3.18,7.1,2.95,PANEL,True);text(.95,3.45,6.6,.4,'THE EXPERIENCE WE ARE BUILDING',12,CYAN,True)
text(.95,4.03,6.5,1.85,'Ask Muse: “What did Dot find about my goals?”\nAsk Dot: “Use the preferences I shared with Muse.”\nAsk either: “What changed—and why does it matter to me?”',21,WHITE)
text(8.2,3.43,4.25,2.25,'Less repeated context.\nMore specialist research.\nContinuity across assistants.\nAnswers grounded in your life.',21,WHITE,True)
rect(.7,6.32,11.9,.44,'#3B3024',True);text(.87,6.41,11.55,.25,'NEXT MILESTONE: verify Dot ↔ Cognee access, then demonstrate the same context in Muse and Dot.',12,AMBER)
finish('Close on the broader personal-assistant story: the user keeps the assistant they prefer, while Cognee provides a shared memory and research agents supply external evidence. Future applications could include travel, projects or learning, but these have not been implemented in this demo. Cross-assistant reuse requires actual authenticated access and explicit sharing scope. The Dot reference and connection test have not established a verified bidirectional memory integration yet. The next demo should store one approved fact through one assistant and retrieve it through the other.')

prs.core_properties.title='A Unified Brain for Personal Assistants — Muse, Dot, Cognee & Superlinked'
prs.core_properties.subject='Shared personal context, external research, and continuity across assistants'
prs.core_properties.author='Hackathon project'
prs.save(OUT/'Cognee_Superlinked_6_Slides.pptx')
previews[0].save(OUT/'Cognee_Superlinked_6_Slides.pdf',save_all=True,append_images=previews[1:],resolution=DPI)
contact=Image.new('RGB',(1280,1080),'#202A3B')
for i,im in enumerate(previews):
    im=im.copy();im.thumbnail((640,360));contact.paste(im,((i%2)*640,(i//2)*360))
contact.save(OUT/'preview.png')
print('Created six-slide PowerPoint, PDF, speaker notes and preview.')
