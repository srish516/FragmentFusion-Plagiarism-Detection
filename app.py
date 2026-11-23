"""FragmentFusion Studio - academic integrity workspace.
Run: python -m streamlit run app.py
"""
import html
import io
import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime

import requests
import streamlit as st

from engine import plagiarism_analysis, ai_signals, highlighted_html, words
import db

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title='FragmentFusion Studio | Academic Intelligence', page_icon='📚', layout='wide', initial_sidebar_state='expanded')
# Load high-contrast, widget-scoped styling without overriding Streamlit controls globally.
st.markdown('<style>' + (BASE / 'styles.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
db.init_db()
for key, initial in {'user':None, 'page':'Dashboard', 'last_plag':None,'last_ai':None,'references':{},'found_papers':[],'chat':[],'current_text':'','current_label':''}.items():
    if key not in st.session_state:
        st.session_state[key] = initial


def navigate(page):
    st.session_state.page = page
    st.rerun()


def esc(s):
    return html.escape(str(s or ''))


def heading(title, subtitle=''):
    st.markdown(f'<div class="eyebrow">FRAGMENTFUSION / {esc(title)}</div><h1 style="margin:6px 0 7px;font-size:32px">{esc(title)}</h1><div style="color:#6a7b91;margin-bottom:21px">{esc(subtitle)}</div>',unsafe_allow_html=True)


def metric_card(icon, name, value, color='#0d65d6'):
    st.markdown(f'<div class="stat-card"><div class="stat-icon">{icon}</div><div class="stat-label">{esc(name)}</div><div class="stat-value" style="color:{color}">{esc(value)}</div></div>',unsafe_allow_html=True)


def banner(text):
    st.markdown(f'<div class="caution">⚠️ {esc(text)}</div>',unsafe_allow_html=True)


def extract(upload):
    if not upload:
        return ''
    name = upload.name.lower()
    raw = upload.getvalue()
    if len(raw)>15*1024*1024:
        raise ValueError('Maximum upload size is 15 MB.')
    if name.endswith('.txt'):
        return raw.decode('utf-8-sig',errors='replace')
    if name.endswith('.docx'):
        from docx import Document
        d=Document(io.BytesIO(raw))
        return '\n'.join(p.text for p in d.paragraphs if p.text.strip())
    if name.endswith('.pdf'):
        try:
            import pymupdf
        except ImportError as e:
            raise RuntimeError('PDF extraction needs PyMuPDF. Install it separately with: python -m pip install pymupdf') from e
        with pymupdf.open(stream=raw,filetype='pdf') as doc:
            if len(doc)>120:
                raise ValueError('Please use a PDF with 120 pages or fewer.')
            return '\n'.join(page.get_text('text') for page in doc)
    raise ValueError('Allowed formats: PDF, DOCX, TXT.')


def input_widget(prefix, *, default_text='', key_upload=None, key_text=None):
    tab1, tab2 = st.tabs(['📄 Upload document', '✍️ Paste text'])
    with tab1:
        upload=st.file_uploader('Drop a document here', type=['docx','txt','pdf'],key=key_upload or prefix+'_upload',help='DOCX and TXT work immediately. PDF requires optional PyMuPDF.')
    with tab2:
        pasted=st.text_area('Paste your academic text here',value=default_text,height=200,key=key_text or prefix+'_paste',placeholder='Paste an assignment, abstract, paragraph, or research content...')
    mode=st.radio('Choose input to analyze', ['Uploaded file','Pasted text'],horizontal=True,key=prefix+'_mode')
    if mode=='Uploaded file':
        if upload:
            try:
                return extract(upload),upload.name
            except Exception as e:
                st.error(str(e))
        return '', 'Uploaded document'
    return pasted, 'Pasted text'


def plain_report(title, payload, kind):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen.canvas import Canvas
    except ImportError:
        return None
    out=io.BytesIO()
    c=Canvas(out,pagesize=A4)
    w,h=A4
    def lines(text):
        clean=str(text).encode('latin-1','replace').decode('latin-1')
        out=[]
        while len(clean)>102:
            pos=clean.rfind(' ',0,102)
            if pos<20:pos=102
            out.append(clean[:pos]);clean=clean[pos:].lstrip()
        return out+[clean]
    y=h-52
    c.setFont('Helvetica-Bold',18);c.drawString(43,y,'FragmentFusion Studio')
    y-=23;c.setFont('Helvetica',10);c.drawString(43,y,title[:90])
    y-=22;c.drawString(43,y,'Screening results are not proof of plagiarism or AI authorship.')
    y-=28;c.setFont('Helvetica-Bold',11);c.drawString(43,y, f"{kind}: {payload.get('similarity_percent',payload.get('signal_coverage_percent',0))}%")
    for s in payload['sentences']:
        if y<75:c.showPage();y=h-45
        y-=16;c.setFont('Helvetica-Bold',9)
        c.drawString(43,y,f"Sentence {s['index']} | {'Flagged for review' if s['flagged'] else 'No flag'}")
        c.setFont('Helvetica',9)
        for l in lines(s['text']):
            y-=12
            if y<55:c.showPage();y=h-45
            c.drawString(43,y,l)
        if s.get('source'):
            y-=13;c.drawString(43,y,'Candidate source: '+str(s['source'])[:85])
        for reason in s.get('reasons',[]):
            y-=13
            if y<55:c.showPage();y=h-45
            c.drawString(43,y,'Writing signal: '+reason[:90])
    c.save();out.seek(0)
    return out.getvalue()


def result_panel(payload,kind):
    is_plag=kind=='plagiarism'
    pct=payload['similarity_percent'] if is_plag else payload['signal_coverage_percent']
    cols=st.columns(4)
    labels=[('🔎','Matched-text coverage' if is_plag else 'Writing-signal coverage',f'{pct}%', '#d63a52' if is_plag else '#ab581d'),('📑','Sentences',payload['sentence_count'],'#1759bf'),('📝','Words',payload['word_count'],'#1759bf'),('⚑','Flagged sentences',payload['flagged_count'],'#d97717')]
    for col, (icon,label,value,color) in zip(cols,labels):
        with col:metric_card(icon,label,value,color)
    st.markdown('### Highlighted document')
    st.markdown('<div class="text-review">'+highlighted_html(payload['sentences'],'plagiarism' if is_plag else 'ai')+'</div>',unsafe_allow_html=True)
    if is_plag:
        banner('This is the proportion of words in matched sentences relative to the uploaded reference library. It is not a verified plagiarism percentage; no internet-wide plagiarism search is performed.')
        st.caption('🔴 Pink: candidate source match. 🟢 Green: no match above the configured threshold.')
    else:
        banner('AI-writing signals are heuristic stylistic indicators, NOT a measured percentage of AI-generated text. Unflagged text is not verified human-written. False positives and negatives are possible.')
        st.caption('🟠 Orange: flagged writing pattern. 🟢 Green: no detected signal with these rules; authorship unknown.')
    st.markdown('### Sentence-level evidence')
    if is_plag:
        data=[{'#':s['index'],'Text':s['text'],'Match score %':s['score'],'Source':s['source'] or '—','Status':'Review' if s['flagged'] else 'No match'} for s in payload['sentences']]
    else:
        data=[{'#':s['index'],'Text':s['text'],'Status':'Review' if s['flagged'] else 'No signal','Why':'; '.join(s['reasons']) or 'No configured signal triggered'} for s in payload['sentences']]
    st.dataframe(data,use_container_width=True,hide_index=True)
    if is_plag:
        matched=[s for s in payload['sentences'] if s['flagged']]
        with st.expander(f'🔍 Candidate source passages ({len(matched)})'):
            if not matched:st.info('No reference matches above the selected threshold.')
            for s in matched:
                st.markdown(f'**Sentence {s["index"]} · {esc(s["source"])} · {s["score"]}% match**')
                st.write(s['match'])
    else:
        with st.expander('How writing signals are calculated'):
            st.write('Simple explainable rules check formulaic wording, repetitive vocabulary, long structured sentences, dense abstract nouns, and predictable transition phrases. These signals occur in both human and machine writing and cannot identify the author.')
    report=plain_report('Analysis report',payload,'Text similarity' if is_plag else 'Writing-signal coverage')
    if report:
        st.download_button('⬇ Download PDF report',report,file_name='fragmentfusion_report.pdf',mime='application/pdf')


def auth():
    a,b,c=st.columns([1,2,1])
    with b:
        st.markdown('<div class="auth-wrap"><div class="eyebrow">WELCOME TO YOUR ACADEMIC WORKSPACE</div><h1>📚 FragmentFusion <span style="color:#0874df">Studio</span></h1><p>Academic Integrity & AI Writing Intelligence</p></div>',unsafe_allow_html=True)
        t1,t2=st.tabs(['🔐 Log in','✨ Create account'])
        with t1:
            with st.form('login_form'):
                email=st.text_input('Email address',placeholder='student@example.com')
                password=st.text_input('Password',type='password')
                submitted=st.form_submit_button('Log in →',use_container_width=True,type='primary')
            if submitted:
                user=db.login(email,password)
                if user:
                    st.session_state.user={k:user[k] for k in ('id','name','email','role')};navigate('Dashboard')
                else:st.error('Invalid email or password.')
        with t2:
            with st.form('register_form'):
                name=st.text_input('Full name')
                email=st.text_input('Academic email')
                role=st.selectbox('I am a', ['Student','Researcher','Faculty'])
                pw=st.text_input('Choose a password',type='password')
                confirm=st.text_input('Confirm password',type='password')
                registered=st.form_submit_button('Create account',use_container_width=True,type='primary')
            if registered:
                if len(name.strip())<2 or '@' not in email or '.' not in email.split('@')[-1]:st.error('Enter a valid name and email.')
                elif len(pw)<8:st.error('Use a password with at least 8 characters.')
                elif pw!=confirm:st.error('Passwords do not match.')
                else:
                    try:
                        db.register(name,email,pw,role)
                        st.success('Account created. Sign in using the Log in tab.')
                    except sqlite3.IntegrityError:st.error('That email is already registered.')
        st.caption('Your account and analysis history are stored locally in SQLite on this computer. Not configured for public internet hosting.')


def sidebar():
    with st.sidebar:
        st.markdown('<div class="ff-brand"><div class="logo">📖✨</div><div class="name">FragmentFusion<br><b>Studio</b></div><div class="tagline">Academic Integrity &<br>AI Writing Intelligence</div></div><hr>',unsafe_allow_html=True)
        nav=[('🏠','Dashboard'),('📑','Plagiarism Detector'),('🤖','AI Detection'),('📚','Research Paper Finder'),('💬','Academic Chatbot'),('📊','Reports & History'),('⚙️','Settings')]
        for icon,page in nav:
            if st.button(f'{icon}   {page}',key='nav_'+page,use_container_width=True,type='primary' if st.session_state.page==page else 'secondary'):
                navigate(page)
        st.markdown('<div style="height:32px"></div><hr>',unsafe_allow_html=True)
        st.caption('📍 LOCAL WORKSPACE')
        st.write('👤 '+st.session_state.user['name'])
        if st.button('↪ Log out',use_container_width=True):
            st.session_state.user=None
            st.session_state.chat=[]
            st.session_state.last_plag=None
            st.session_state.last_ai=None
            st.session_state.references={}
            st.rerun()


def dashboard():
    user=st.session_state.user
    now=datetime.now().hour
    greet='Good Morning' if now<12 else 'Good Afternoon' if now<17 else 'Good Evening'
    st.markdown(f'<div class="ff-header"><span class="location">📍 Academic Intelligence Workspace &nbsp; / &nbsp; Dashboard</span><span class="ff-profile">🔔 &nbsp; 👤 {esc(user["name"])} · {esc(user["role"])}</span></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="hero"><h1>{greet}, {esc(user["name"].split()[0])} 👋</h1><p>Welcome to <em style="color:#12ddff;font-weight:800;font-style:normal">FragmentFusion Studio</em><br>Analyze documents, review text similarity and AI writing signals, find research papers, and get academic guidance — all in one place.</p><span class="graphic">📚🔍</span></div>',unsafe_allow_html=True)
    hist=db.history(user['id'])
    p=[x for x in hist if x['kind']=='plagiarism']
    ai=[x for x in hist if x['kind']=='AI writing signals']
    cs=st.columns(4)
    for col, vals in zip(cs,[('📄','Documents analyzed',len(hist),'#075fd4'),('🚨','Plagiarism checks',len(p),'#c93856'),('🧠','AI signal checks',len(ai),'#6948b7'),('📈','Reports available',len(hist),'#188761')]):
        with col:metric_card(*vals)
    st.markdown('### Quick Actions')
    actions=st.columns(4)
    for col, icon, title, sub, page in zip(actions,['📄','✍️','📚','💬'],['Analyze Document','Paste Text for AI Check','Find Research Papers','Ask Academic Chatbot'],['PDF / DOCX / TXT','Review writing patterns','Search scholarly publications','Get academic help'],['Plagiarism Detector','AI Detection','Research Paper Finder','Academic Chatbot']):
        with col:
            st.markdown(f'<div style="background:white;border:1px solid #e1eaf7;border-radius:12px;padding:12px;font-size:13px;min-height:65px"><b>{icon} {title}</b><br><span style="color:#688098">{sub}</span></div>',unsafe_allow_html=True)
            if st.button('Open →',key='action_'+page,use_container_width=True):navigate(page)
    left,right=st.columns([1.15,1],gap='large')
    with left:
        st.markdown('### Recent Activity')
        if hist:
            rows=[{'Document':x['filename'],'Date':x['created_at'],'Type':x['kind'],'Coverage %':x['percentage'],'Status':'Completed'} for x in hist[:8]]
            st.dataframe(rows,use_container_width=True,hide_index=True)
        else:
            st.info('No analyses yet. Upload a file or paste text to create your first report.')
    with right:
        st.markdown('### Analysis Overview')
        if hist:
            st.markdown(f'<div class="ff-card"><h3>{len(hist)} analyses completed</h3><p>See your recent screening coverage below. Scores are not plagiarism or AI-authorship probabilities.</p></div>',unsafe_allow_html=True)
            series={'Text similarity':[x['percentage'] for x in reversed(p[:12])], 'Writing signals':[x['percentage'] for x in reversed(ai[:12])]}
            if any(series.values()):
                import pandas as pd
                n=max(len(v) for v in series.values())
                df=pd.DataFrame({k:([None]*(n-len(v))+v) for k,v in series.items()})
                st.line_chart(df)
        else:
            st.markdown('<div class="ff-card"><h3>📊 Your analysis insights</h3><p>Once you analyze your first document, coverage metrics and recent activity will appear here.</p></div>',unsafe_allow_html=True)
        st.caption('Dashboard values come from your saved local analyses, not sample or fabricated statistics.')


def references_widget():
    st.markdown('### Reference library')
    st.caption('Similarity detection compares your submission only with these available source texts. Upload original sources for meaningful screening.')
    refs=st.file_uploader('Upload comparison/reference documents',type=['txt','docx','pdf'],accept_multiple_files=True,key='ref_upload')
    if refs:
        for file in refs:
            try:
                text=extract(file)
                if text.strip():st.session_state.references[file.name]=text
            except Exception as ex:st.warning(f'{file.name}: {ex}')
    use_demo=st.checkbox('Include 2 clearly labeled demo reference documents',value=True,key='use_demo')
    combined=dict(st.session_state.references)
    if use_demo:
        for p in sorted((BASE/'data').glob('reference_*.txt')):
            combined['DEMO: '+p.name]=p.read_text(encoding='utf-8')
    st.caption(f'{len(combined)} reference document(s) selected. Demo documents are small teaching examples, not a plagiarism database.')
    return combined


def plagiarism_page():
    heading('Plagiarism Detector','Analyze academic text against uploaded sources. Inspect sentence-level evidence and potential overlaps.')
    left,right=st.columns([1.4,.8],gap='large')
    with left:
        st.markdown('<div class="ff-card"><h3>📄 Analyze your document</h3><p>Upload DOCX, TXT, optionally PDF, or paste an academic passage.</p></div>',unsafe_allow_html=True)
        content,label=input_widget('plag')
        threshold=st.slider('Sentence similarity threshold',30,95,58,1,help='Higher threshold means fewer candidate matches.') / 100
    with right:
        references=references_widget()
        st.markdown('<div class="ff-card"><h3>🔍 Transparent matching</h3><p>Each submitted sentence is compared to sentences from your selected reference documents using token-overlap cosine and sequence similarity.</p></div>',unsafe_allow_html=True)
    if st.button('🔎 Analyze for potential matches',type='primary',use_container_width=True,key='plag_run'):
        if not content.strip():st.warning('Upload a file or paste text and select the matching input mode.')
        elif not references:st.warning('Add at least one reference document.')
        else:
            with st.spinner('Comparing sentences with reference sources...'):
                result=plagiarism_analysis(content,references,threshold)
            st.session_state.last_plag=result
            st.session_state.current_text=content
            st.session_state.current_label=label
            db.add_analysis(st.session_state.user['id'],label,'plagiarism',result['similarity_percent'],result['word_count'],result['sentence_count'],result['flagged_count'],result['matched_sources'],json.dumps(result))
            st.success('Similarity screening completed. Review matches below.')
    if st.session_state.last_plag:result_panel(st.session_state.last_plag,'plagiarism')


def ai_page():
    heading('AI Detection','Review writing characteristics that sometimes occur in AI-assisted text; avoid definitive authorship claims.')
    st.markdown('<div class="ff-card"><h3>🧠 AI Writing Signals</h3><p>Paste text or upload a document to view sentence-level, explainable stylistic flags.</p></div>',unsafe_allow_html=True)
    content,label=input_widget('ai')
    if st.button('✨ Analyze writing signals',type='primary',use_container_width=True,key='ai_run'):
        if not content.strip():st.warning('Upload or paste some text and choose the correct input mode.')
        else:
            result=ai_signals(content)
            st.session_state.last_ai=result
            st.session_state.current_text=content
            st.session_state.current_label=label
            db.add_analysis(st.session_state.user['id'],label,'AI writing signals',result['signal_coverage_percent'],result['word_count'],result['sentence_count'],result['flagged_count'],0,json.dumps(result))
            st.success('Stylistic screening completed.')
    if st.session_state.last_ai:result_panel(st.session_state.last_ai,'ai')


def fetch_papers(query,year='',limit=12):
    params={'query.bibliographic':query,'rows':limit,'select':'DOI,title,author,published,container-title,is-referenced-by-count,URL,type,abstract','sort':'relevance'}
    if year:params['filter']=f'from-pub-date:{year}-01-01'
    resp=requests.get('https://api.crossref.org/works',params=params,headers={'User-Agent':'FragmentFusionStudio/1.0 (educational research-paper finder)'},timeout=15)
    resp.raise_for_status()
    data=resp.json().get('message',{}).get('items',[])
    papers=[]
    for item in data:
        title=(item.get('title') or ['Untitled'])[0]
        authors=', '.join(' '.join(filter(None,[a.get('given',''),a.get('family','')])) for a in item.get('author',[])[:4]) or 'Unknown authors'
        dp=item.get('published',{}).get('date-parts',[[None]])
        year_value=dp[0][0] if dp and dp[0] else 'Unknown'
        doi=item.get('DOI','')
        url='https://doi.org/'+doi if doi else item.get('URL','')
        abstract=re.sub(r'<[^>]+>',' ',item.get('abstract','') or '')
        papers.append({'title':title,'authors':authors,'year':year_value,'doi':doi,'url':url,'journal':(item.get('container-title') or [''])[0], 'citations':item.get('is-referenced-by-count',0),'abstract':re.sub(r'\s+',' ',abstract).strip()})
    return papers


def research_page():
    heading('Research Paper Finder','Discover real scholarly metadata from Crossref — no invented titles or DOI links.')
    st.markdown('<div class="ff-card"><h3>📚 Explore academic literature</h3><p>Enter a topic or keywords to retrieve matching scholarly publications and citation links.</p></div>',unsafe_allow_html=True)
    left,right=st.columns([4,1])
    with left:query=st.text_input('Research topic',placeholder='e.g., NLP-based plagiarism detection with transformer models')
    with right:year=st.selectbox('From year',['Any year']+[str(y) for y in range(datetime.now().year,1999,-1)])
    if st.button('🔍 Search research papers',type='primary'):
        if len(query.strip())<3:st.warning('Enter a research topic (at least 3 characters).')
        else:
            with st.spinner('Searching Crossref...'):
                try:
                    st.session_state.found_papers=fetch_papers(query,None if year=='Any year' else year)
                except requests.RequestException as exc:
                    st.session_state.found_papers=[]
                    st.error(f'Research search is temporarily unavailable. Check your internet connection. ({exc})')
    if st.session_state.found_papers:
        st.markdown(f'### Found {len(st.session_state.found_papers)} publications')
        for i,p in enumerate(st.session_state.found_papers):
            st.markdown(f'<div class="paper-card"><div class="paper-title">📄 {esc(p["title"])}</div><div class="paper-meta">👤 {esc(p["authors"])} &nbsp; · &nbsp; 📅 {esc(p["year"])} &nbsp; · &nbsp; {esc(p["journal"])}<br>DOI: {esc(p["doi"] or "Unavailable")} &nbsp; · &nbsp; Cited by: {esc(p["citations"])}</div></div>',unsafe_allow_html=True)
            if p['abstract']:
                with st.expander('Abstract preview'):st.write(p['abstract'][:2500])
            c1,c2=st.columns([1,4])
            with c1:
                if st.button('🔖 Save paper',key='save_'+str(i)):
                    db.save_paper(st.session_state.user['id'],p)
                    st.toast('Saved to your research library.')
            with c2:
                if p['url']:st.link_button('🔗 Open DOI / publisher page',p['url'])
    with st.expander('📁 My saved research papers'):
        saved=db.papers(st.session_state.user['id'])
        if saved:
            for p in saved:
                st.write(f"**{p['title']}** — {p['authors']} ({p['year']})")
                if p['url']:st.markdown(f"[Open publication]({p['url']})")
        else:st.info('No saved papers yet.')
    st.caption('Crossref returns publication metadata, not guaranteed full-text access. Search results require an internet connection.')


def assistant_answer(question):
    q=question.lower().strip()
    p=st.session_state.last_plag
    a=st.session_state.last_ai
    if any(v in q for v in ['my report','report explanation','explain report','my result','my percentage','both scores','analyze my score']):
        chunks=[]
        if p:
            chunks.append(f"**Text similarity screening:** {p['similarity_percent']}% of words were in sentences matching your selected reference sources. {p['flagged_count']} of {p['sentence_count']} sentences were flagged, across {p['matched_sources']} source(s). This is not a proof of plagiarism.")
        if a:
            chunks.append(f"**AI writing signal screening:** {a['signal_coverage_percent']}% of words were in sentences flagged by the project's explainable writing-style rules; {a['flagged_count']} of {a['sentence_count']} sentences were flagged. This does not establish AI authorship.")
        return '\n\n'.join(chunks) if chunks else 'There is no analysis in your current session. Run Plagiarism Detector or AI Detection, then ask me to explain the report.'
    if ('highlight' in q or 'flagged sentence' in q or 'why flagged' in q or 'matched sentence' in q):
        idx=re.search(r'(?:sentence|#)\s*(\d+)',q)
        number=int(idx.group(1)) if idx else None
        if ('ai' in q or 'writing' in q) and a:
            hits=[s for s in a['sentences'] if s['flagged']]
            if number:hits=[s for s in a['sentences'] if s['index']==number]
            if hits:
                s=hits[0]
                return f"**Sentence {s['index']}:** {s['text']}\n\n**Why flagged:** "+('; '.join(s['reasons']) if s['reasons'] else 'No AI-writing style rule was triggered.')+'\n\nThese are stylistic indicators only; they do not determine who wrote it.'
        if p:
            hits=[s for s in p['sentences'] if s['flagged']]
            if number:hits=[s for s in p['sentences'] if s['index']==number]
            if hits:
                s=hits[0]
                if s['flagged']:
                    return f"**Sentence {s['index']}:** {s['text']}\n\n**Candidate source:** {s['source']} ({s['score']}% matching score).\n\n**Reference passage:** {s['match']}\n\nPlease verify the source and consider a citation or accurate paraphrase."
                return f"Sentence {s['index']} was not flagged at the selected similarity threshold."
        return 'I cannot explain a highlighted sentence yet. First run an analysis, then ask “Why is sentence 1 flagged?” or “Explain AI sentence 2”.'
    if any(v in q for v in ['citation','cite','reference style','apa','ieee','bibliography']):
        return ('**APA 7:** In-text: (Surname, Year). Reference entry: Surname, A. A. (Year). Title of article. *Journal Title, volume*(issue), pages. https://doi.org/...\n\n'
                '**IEEE:** In-text: [1]. Reference entry: [1] A. A. Surname, “Article title,” *Journal Title*, vol. x, no. x, pp. xx–xx, Year, doi: ...\n\n'
                'Cite quotations and paraphrases, verify bibliographic details with the original paper, and follow your institution’s required style.')
    if any(v in q for v in ['what is plagiarism','types of plagiarism','plagiarism help','define plagiarism','direct plagiarism','paraphrasing plagiarism']):
        return ('**Plagiarism** is presenting someone else’s words or ideas as your own without appropriate acknowledgement. Common forms include:\n\n'
                '- **Direct:** copying text without attribution.\n- **Mosaic:** mixing copied phrases into original writing without adequate credit.\n- **Paraphrasing:** rewording a source but not citing it.\n- **Self-plagiarism:** reusing your own previously submitted work contrary to academic rules.\n- **Accidental:** incorrect quotation or missing citations.\n\nSimilarity tools flag candidate overlaps, not misconduct verdicts.')
    if any(v in q for v in ['ai detection','ai generated','ai writing','human written','ai signal','ai percentage','ai detector']):
        return ('**AI writing screening in this project** highlights sentences containing configured patterns: generic academic phrases, long formulaic sentences, repeated wording, dense abstract nouns, and predictable transitions.\n\n'
                'The displayed percentage is **word coverage inside flagged sentences**, not the probability that content was generated by AI. Human-written text can trigger the same rules. No text-only detector reliably verifies individual-sentence authorship. Review the text and writing process rather than penalizing a percentage.')
    m=re.search(r'(?:improve|rewrite|edit)\s+(?:this\s+)?sentence\s*:\s*(.+)',question,re.I|re.S)
    if m:
        sentence=m.group(1).strip()
        return f'**Original:** {sentence}\n\n**Editing suggestions:** Identify the main claim, replace broad adjectives with measurable specifics, and add a citation for any sourced idea. To propose an evidence-based rewrite, tell me the intended meaning and supporting evidence.'
    if any(v in q for v in ['improve','rewrite','writing','academic style','clarity','grammar','paraphrase']):
        return ('For better academic writing: (1) state one clear claim per sentence, (2) replace vague phrases such as “plays a crucial role” with precise evidence, (3) define technical terms, (4) vary sentence length naturally, (5) cite sources when restating their ideas, and (6) include your own analysis.\n\n'
                'Paste a specific sentence into the chat and ask “Improve this sentence: …” for targeted editorial guidance.')
    if any(v in q for v in ['project','modules','how it works','architecture','algorithm','feature','streamlit','fragmentfusion']):
        return ('**FragmentFusion Studio** has seven main modules: Login/Register (salted password hashes and local SQLite), Dashboard (real analysis history), Plagiarism Detector (sentence splitting, lexical cosine + sequence matching against uploaded references), AI Writing Signals (explainable heuristic flags), Research Paper Finder (live Crossref metadata), Academic Chatbot (project-specific explanations), and Reports/History (SQLite and PDF export).\n\n'
                'This version does not search the entire internet for plagiarism, use a learned AI-authorship classifier, or call a paid chatbot API. These are important scope limits to describe in your viva.')
    return ('I can help with **plagiarism and its types, AI writing signals, report percentages, highlighted sentences, academic writing, APA/IEEE citations, research papers, and how FragmentFusion works**.\n\n'
            'Try asking “Explain my report”, “Why is sentence 2 flagged?”, “How does plagiarism detection work?”, or “Show me IEEE citation format”.')


def chatbot_page():
    heading('Academic Chatbot','Context-aware academic assistance grounded in your current FragmentFusion screening results.')
    left,right=st.columns([1,2.55],gap='large')
    with left:
        st.markdown('<div class="ff-card"><h3>💬 Quick prompts</h3><p>Choose a topic and start a focused conversation.</p></div>',unsafe_allow_html=True)
        prompts=[('📖 Plagiarism Help','Explain plagiarism and its types'),('🧠 AI Detection Help','Explain AI detection and writing signals'),('📊 Report Explanation','Explain my report'),('🔎 Highlight Explanation','Why is sentence 1 flagged?'),('✍️ Academic Writing','How can I improve my academic writing?'),('🔖 Citation Assistant','Explain APA and IEEE citations'),('🛠️ Project Assistant','How does the FragmentFusion project work?')]
        for name,q in prompts:
            if st.button(name,key='prompt_'+name,use_container_width=True):
                st.session_state.chat.extend([{'role':'user','content':q},{'role':'assistant','content':assistant_answer(q)}])
                st.rerun()
        st.caption('Chatbot uses transparent project-specific rules and the last analysis in this session. It is not a connected large language model.')
    with right:
        st.markdown('<div class="chat-intro">🤖 <b>FragmentFusion Academic Assistant</b><br>Ask about source matches, AI-writing signals, citations, and your project.</div>',unsafe_allow_html=True)
        for entry in st.session_state.chat:
            with st.chat_message(entry['role']):st.markdown(entry['content'])
        if not st.session_state.chat:
            with st.chat_message('assistant'):
                st.markdown('Welcome! I can explain how your plagiarism analysis works and discuss specific flagged passages after you run a check. What would you like to learn?')
        if question:=st.chat_input('Ask anything about plagiarism, AI signals, reports, citations...'):
            st.session_state.chat.extend([{'role':'user','content':question},{'role':'assistant','content':assistant_answer(question)}])
            st.rerun()


def reports_page():
    heading('Reports & History','Review real saved checks on your local academic workspace.')
    hist=db.history(st.session_state.user['id'])
    if not hist:
        st.info('No saved analyses. Run a plagiarism or AI writing check to create one.')
        return
    st.dataframe([{'#':x['id'],'Document':x['filename'],'Type':x['kind'],'Screening coverage %':x['percentage'],'Words':x['word_count'],'Flagged':x['flagged_count'],'Date':x['created_at']} for x in hist],use_container_width=True,hide_index=True)
    opts={f"#{x['id']} · {x['filename']} · {x['kind']}":x for x in hist}
    selected=opts[st.selectbox('Open saved report',list(opts.keys()))]
    try:
        payload=json.loads(selected['details'])
        result_panel(payload,'plagiarism' if selected['kind']=='plagiarism' else 'ai')
    except (ValueError,KeyError):st.warning('The selected report cannot be displayed.')


def settings_page():
    heading('Settings','Manage the local academic workspace and review project limitations.')
    user=st.session_state.user
    st.markdown(f'<div class="ff-card"><h3>👤 Account details</h3><p>Name: {esc(user["name"])}<br>Email: {esc(user["email"])}<br>Role: {esc(user["role"])}</p></div>',unsafe_allow_html=True)
    st.markdown('<div class="ff-card"><h3>🔐 Local privacy</h3><p>Accounts and analysis history are stored in data/fragmentfusion.sqlite3 on this computer. Passwords are stored using salted PBKDF2 hashes. There is no password reset email service or enterprise access control. Do not publicly expose this development server.</p></div>',unsafe_allow_html=True)
    st.markdown('<div class="ff-card"><h3>⚙️ System boundaries</h3><p>Plagiarism screening only compares the provided reference library. AI-writing flags are heuristics, not a scientifically validated authorship detector. Crossref finds scholarly metadata and may not provide full-text downloads.</p></div>',unsafe_allow_html=True)


if not st.session_state.user:
    auth()
else:
    sidebar()
    {
        'Dashboard':dashboard,
        'Plagiarism Detector':plagiarism_page,
        'AI Detection':ai_page,
        'Research Paper Finder':research_page,
        'Academic Chatbot':chatbot_page,
        'Reports & History':reports_page,
        'Settings':settings_page
    }.get(st.session_state.page,dashboard)()
    st.markdown('<div style="height:22px"></div><hr><div class="note">© FragmentFusion Studio · NLP-Based Plagiarism Detection & Academic Intelligence · Educational screening, not an authorship verdict.</div>',unsafe_allow_html=True)
