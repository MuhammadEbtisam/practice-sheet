import streamlit as st
from google import genai
from google.genai import types
import json
import re
import io
import base64
from youtube_transcript_api import YouTubeTranscriptApi
from pypdf import PdfReader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.mathtext as mathtext
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image as RLImage, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile
import os

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MCQ Extractor",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.main { background: #f8fafc; }

.hero-card {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 50%, #1a8c7a 100%);
    border-radius: 16px;
    padding: 2.5rem 3rem;
    color: white;
    margin-bottom: 2rem;
    box-shadow: 0 8px 32px rgba(30,58,95,0.18);
}
.hero-card h1 { font-size: 2.2rem; font-weight: 700; margin: 0 0 0.5rem 0; letter-spacing: -0.5px; }
.hero-card p  { font-size: 1.05rem; margin: 0; opacity: 0.88; }

.section-card {
    background: white;
    border-radius: 12px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    border: 1px solid #e8edf4;
}

.topic-badge {
    display: inline-block;
    background: linear-gradient(135deg, #1e3a5f, #2d6a9f);
    color: white;
    padding: 0.25rem 0.9rem;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 0.6rem;
    text-transform: uppercase;
}

.question-block {
    background: #f9fafb;
    border-left: 4px solid #2d6a9f;
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.2rem;
    margin: 0.8rem 0;
}
.question-text { font-weight: 600; color: #1e293b; margin-bottom: 0.6rem; font-size: 0.97rem; }
.option-row    { color: #374151; font-size: 0.92rem; padding: 0.18rem 0; }
.correct-opt   { color: #059669; font-weight: 600; }

.stats-row {
    display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;
}
.stat-box {
    flex: 1; min-width: 120px;
    background: white; border-radius: 10px; padding: 1rem 1.2rem;
    text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    border: 1px solid #e8edf4;
}
.stat-num  { font-size: 1.8rem; font-weight: 700; color: #1e3a5f; }
.stat-lbl  { font-size: 0.78rem; color: #64748b; margin-top: 0.2rem; }

.download-btn {
    display: inline-block;
    background: linear-gradient(135deg, #1e3a5f, #2d6a9f);
    color: white !important;
    padding: 0.65rem 1.6rem;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.95rem;
    margin-right: 0.8rem;
    box-shadow: 0 4px 12px rgba(30,58,95,0.25);
    transition: all 0.2s;
}
.download-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(30,58,95,0.3); }

.answer-btn {
    background: linear-gradient(135deg, #065f46, #059669) !important;
    box-shadow: 0 4px 12px rgba(5,150,105,0.25) !important;
}

.stButton > button {
    background: linear-gradient(135deg, #1e3a5f, #2d6a9f);
    color: white; border: none; border-radius: 8px;
    padding: 0.6rem 2rem; font-weight: 600; font-size: 0.97rem;
    box-shadow: 0 4px 12px rgba(30,58,95,0.2);
    transition: all 0.2s;
}
.stButton > button:hover { transform: translateY(-1px); }

.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    border-radius: 8px; border: 1.5px solid #d1d9e6;
    font-family: 'Inter', sans-serif;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #2d6a9f; box-shadow: 0 0 0 2px rgba(45,106,159,0.12);
}

div[data-testid="stTabs"] button {
    font-weight: 600; font-size: 0.95rem;
}

.api-key-section {
    background: linear-gradient(135deg, #fffbeb, #fef3c7);
    border: 1.5px solid #f59e0b;
    border-radius: 10px;
    padding: 1rem 1.4rem;
    margin-bottom: 1.2rem;
}
</style>
""", unsafe_allow_html=True)

# ── Helper: extract YouTube ID ────────────────────────────────────────────────
def extract_video_id(url: str) -> str | None:
    patterns = [
        r'(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ── Helper: fetch YouTube transcript ─────────────────────────────────────────
def get_youtube_transcript(url: str) -> str:
    vid = extract_video_id(url)
    if not vid:
        raise ValueError("Could not extract video ID from URL.")
    transcript = YouTubeTranscriptApi.get_transcript(vid)
    return " ".join(t['text'] for t in transcript)

# ── Helper: extract PDF text ──────────────────────────────────────────────────
def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

# ── Helper: render LaTeX expression as PNG image bytes ───────────────────────
def latex_to_image(latex_str: str, fontsize: int = 12, color: str = 'black') -> bytes | None:
    """Renders a LaTeX math string to a PNG image using matplotlib."""
    try:
        # Clean up the latex string
        latex_str = latex_str.strip()
        if not latex_str.startswith('$'):
            latex_str = f'${latex_str}$'
        
        fig, ax = plt.subplots(figsize=(0.1, 0.1))
        ax.axis('off')
        
        text_obj = ax.text(
            0.5, 0.5, latex_str,
            fontsize=fontsize,
            ha='center', va='center',
            color=color,
            transform=ax.transAxes,
            usetex=False  # use matplotlib mathtext, no LaTeX install needed
        )
        
        # Resize figure to fit text
        fig.canvas.draw()
        bbox = text_obj.get_window_extent(renderer=fig.canvas.get_renderer())
        dpi = 150
        width  = max(bbox.width  / dpi + 0.2, 0.5)
        height = max(bbox.height / dpi + 0.1, 0.3)
        fig.set_size_inches(width, height)
        fig.set_dpi(dpi)
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    pad_inches=0.03, transparent=True, dpi=dpi)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        plt.close('all')
        return None

# ── Helper: parse text with LaTeX into reportlab flowables ───────────────────
LATEX_PATTERN = re.compile(r'\$\$(.+?)\$\$|\$(.+?)\$', re.DOTALL)

def text_to_flowables(text: str, style, tmp_dir: str) -> list:
    """
    Splits text on LaTeX delimiters. Plain text → Paragraph; 
    math expressions → rendered PNG image inline.
    """
    flowables = []
    last = 0
    img_idx = [0]  # mutable counter

    def flush_text(t: str):
        t = t.strip()
        if t:
            # Escape XML special chars for reportlab
            t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            flowables.append(Paragraph(t, style))

    for m in LATEX_PATTERN.finditer(text):
        # text before match
        flush_text(text[last:m.start()])
        
        # the math part
        math_expr = m.group(1) or m.group(2)
        img_bytes = latex_to_image(math_expr, fontsize=11)
        if img_bytes:
            img_path = os.path.join(tmp_dir, f'math_{img_idx[0]}.png')
            img_idx[0] += 1
            with open(img_path, 'wb') as f:
                f.write(img_bytes)
            rl_img = RLImage(img_path, hAlign='LEFT')
            # scale to reasonable size
            rl_img.drawHeight = 0.45 * cm
            rl_img.drawWidth  = rl_img.drawWidth * (0.45 * cm / rl_img.drawHeight) \
                                 if rl_img.drawHeight > 0 else 3 * cm
            flowables.append(rl_img)
        else:
            # fallback: plain text without $ signs
            flush_text(math_expr)
        
        last = m.end()
    
    flush_text(text[last:])
    return flowables

# ── Gemini extraction ─────────────────────────────────────────────────────────
EXTRACTION_PROMPT = (
    "You are an expert MCQ extractor for Grade 12 STEM subjects "
    "(Physics, Math, Chemistry, English).\n\n"
    "Given the following content from a practice/question-solving session, "
    "extract ALL MCQ questions present.\n\n"
    "CRITICAL JSON RULES:\n"
    "1. Return ONLY a raw JSON array. No markdown fences, no explanation.\n"
    "2. ALL backslashes in math MUST be doubled inside JSON strings.\n"
    "   Example: write \\\\frac not \\frac, \\\\sqrt not \\sqrt, \\\\times not \\times.\n"
    "3. Wrap math in dollar signs: \"$\\\\frac{1}{2}$\", \"$\\\\sqrt{3}$\".\n"
    "4. A single backslash inside a JSON string is INVALID — always double it.\n\n"
    "Each question object:\n"
    "{\n"
    "  \"topic\": \"Topic name\",\n"
    "  \"question_number\": 1,\n"
    "  \"question_text\": \"text with math like $\\\\frac{d}{dx}$\",\n"
    "  \"options\": {\"A\": \"...\", \"B\": \"...\", \"C\": \"...\", \"D\": \"...\"},\n"
    "  \"correct_answer\": \"A\",\n"
    "  \"explanation\": \"explanation with math like $\\\\sqrt{2}$\"\n"
    "}\n\n"
    "Rules:\n"
    "- Extract EVERY MCQ — do not skip any.\n"
    "- Group similar questions under the same topic.\n"
    "- Infer topic from content if not mentioned.\n"
    "- Assign A/B/C/D labels if options are unlabeled.\n"
    "- correct_answer must be only a single letter: A, B, C, or D.\n\n"
    "Content to extract from:\n"
)

def clean_json_response(raw: str) -> str:
    """
    Robustly clean a model response so it can be parsed as JSON.
    Handles: code fences, single-escaped LaTeX backslashes, trailing commas.
    """
    # 1. Strip leading/trailing whitespace
    raw = raw.strip()
    
    # 2. Remove markdown code fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```\s*$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    # 3. Fix single-escaped LaTeX backslashes inside JSON strings.
    #    The model often emits \frac, \sqrt etc. which are invalid JSON escapes.
    #    We walk char-by-char tracking whether we're inside a string literal.
    fixed_chars = []
    in_string   = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if not in_string:
            if ch == '"':
                in_string = True
            fixed_chars.append(ch)
            i += 1
        else:
            if ch == '\\':
                nxt = raw[i + 1] if i + 1 < len(raw) else ''
                if nxt == '\\':
                    fixed_chars.append('\\\\')
                    i += 2
                elif nxt in ('"', 'n', 'r', 't', 'b', 'f', '/', 'u'):
                    fixed_chars.append(ch)
                    i += 1
                else:
                    # lone backslash — double it
                    fixed_chars.append('\\\\')
                    i += 1
            elif ch == '"':
                in_string = False
                fixed_chars.append(ch)
                i += 1
            else:
                fixed_chars.append(ch)
                i += 1

    raw = ''.join(fixed_chars)
    
    # 4. Remove trailing commas before } or ] (common model mistake)
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    
    return raw


def extract_mcqs(content: str, api_key: str) -> list[dict]:
    client = genai.Client(api_key=api_key)
    
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite',
        contents=EXTRACTION_PROMPT + content,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8192,
        )
    )
    
    raw = response.text
    cleaned = clean_json_response(raw)
    
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Surface the cleaned string for debugging
        raise json.JSONDecodeError(
            f"{e.msg} — check that content has valid MCQ questions.\n\nFirst 300 chars of cleaned response:\n{cleaned[:300]}",
            e.doc, e.pos
        )
    
    return data

# ── PDF Generation ────────────────────────────────────────────────────────────
def build_pdf(questions: list[dict], is_answer_key: bool, title_prefix: str) -> bytes:
    buf = io.BytesIO()
    tmp_dir = tempfile.mkdtemp()
    
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.2*cm, bottomMargin=2.2*cm,
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Normal'],
        fontSize=20, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1e3a5f'),
        spaceAfter=6, alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10, fontName='Helvetica',
        textColor=colors.HexColor('#64748b'),
        spaceAfter=4, alignment=TA_CENTER,
    )
    topic_style = ParagraphStyle(
        'Topic',
        parent=styles['Normal'],
        fontSize=12, fontName='Helvetica-Bold',
        textColor=colors.white,
        spaceBefore=14, spaceAfter=8,
    )
    q_num_style = ParagraphStyle(
        'QNum',
        parent=styles['Normal'],
        fontSize=10, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1e3a5f'),
        spaceBefore=8, spaceAfter=2,
    )
    q_text_style = ParagraphStyle(
        'QText',
        parent=styles['Normal'],
        fontSize=10, fontName='Helvetica',
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=4, leading=14,
    )
    option_style = ParagraphStyle(
        'Option',
        parent=styles['Normal'],
        fontSize=10, fontName='Helvetica',
        textColor=colors.HexColor('#374151'),
        leftIndent=12, spaceAfter=1, leading=13,
    )
    correct_style = ParagraphStyle(
        'Correct',
        parent=styles['Normal'],
        fontSize=10, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#059669'),
        leftIndent=12, spaceAfter=1, leading=13,
    )
    explain_style = ParagraphStyle(
        'Explain',
        parent=styles['Normal'],
        fontSize=9, fontName='Helvetica-Oblique',
        textColor=colors.HexColor('#4b5563'),
        leftIndent=12, spaceAfter=4, leading=12,
        backColor=colors.HexColor('#f0fdf4'),
    )
    
    story = []
    
    # ── Header ──
    story.append(Spacer(1, 0.3*cm))
    label = "ANSWER KEY & SOLUTIONS" if is_answer_key else "PRACTICE EXAMINATION"
    story.append(Paragraph(label, subtitle_style))
    story.append(Paragraph(title_prefix, title_style))
    story.append(Spacer(1, 0.3*cm))
    
    # Divider
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor('#1e3a5f'), spaceAfter=8))
    
    # Stats line
    total = len(questions)
    topics = list(dict.fromkeys(q['topic'] for q in questions))
    info_text = f"Total Questions: {total}  |  Topics: {len(topics)}  |  Marks: {total}"
    story.append(Paragraph(info_text, subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    
    # ── Questions grouped by topic ──
    grouped: dict[str, list] = {}
    for q in questions:
        grouped.setdefault(q['topic'], []).append(q)
    
    for t_idx, (topic, qs) in enumerate(grouped.items()):
        # Topic header as a colored table row
        topic_table = Table(
            [[Paragraph(f"  {topic.upper()}", topic_style)]],
            colWidths=[doc.width],
        )
        topic_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1e3a5f')),
            ('ROUNDEDCORNERS', [6]),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ]))
        story.append(topic_table)
        story.append(Spacer(1, 0.3*cm))
        
        for q in qs:
            q_items = []
            
            # Question number + text
            q_items.append(Paragraph(f"Q{q['question_number']}.", q_num_style))
            q_items += text_to_flowables(q['question_text'], q_text_style, tmp_dir)
            
            # Options
            for letter in ['A', 'B', 'C', 'D']:
                opt_text = q['options'].get(letter, '')
                if not opt_text:
                    continue
                
                if is_answer_key and letter == q.get('correct_answer'):
                    prefix = f"✓ {letter}. "
                    sty = correct_style
                else:
                    prefix = f"    {letter}. "
                    sty = option_style
                
                full_opt = prefix + opt_text
                q_items += text_to_flowables(full_opt, sty, tmp_dir)
            
            # Explanation (answer key only)
            if is_answer_key and q.get('explanation'):
                q_items.append(Spacer(1, 0.1*cm))
                exp_text = "Explanation: " + q['explanation']
                q_items += text_to_flowables(exp_text, explain_style, tmp_dir)
            
            # Answer line (practice sheet only)
            if not is_answer_key:
                q_items.append(Paragraph(
                    "Answer: ___________",
                    ParagraphStyle('Blank', parent=styles['Normal'],
                                   fontSize=9, textColor=colors.HexColor('#94a3b8'),
                                   leftIndent=12, spaceAfter=2)
                ))
            
            q_items.append(Spacer(1, 0.15*cm))
            
            # Light box around each question
            q_table = Table(
                [[q_items]],
                colWidths=[doc.width],
            )
            q_table.setStyle(TableStyle([
                ('BOX',           (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
                ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#f9fafb')),
                ('ROUNDEDCORNERS',[6]),
                ('TOPPADDING',    (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('LEFTPADDING',   (0,0), (-1,-1), 10),
                ('RIGHTPADDING',  (0,0), (-1,-1), 10),
            ]))
            story.append(KeepTogether(q_table))
            story.append(Spacer(1, 0.25*cm))
        
        # Page break between topics (not after last)
        if t_idx < len(grouped) - 1:
            story.append(PageBreak())
    
    # Footer note
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor('#e2e8f0'), spaceBefore=12))
    footer_text = "Answer Key" if not is_answer_key else "End of Solutions"
    story.append(Paragraph(footer_text, subtitle_style))
    
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawString(2*cm, 1.2*cm, f"{'Answer Key' if is_answer_key else 'Practice Sheet'}")
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, f"Page {doc.page}")
        canvas.restoreState()
    
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    return buf.read()

# ── UI rendering ──────────────────────────────────────────────────────────────
def render_question_preview(questions: list[dict], show_answers: bool = False):
    grouped: dict[str, list] = {}
    for q in questions:
        grouped.setdefault(q['topic'], []).append(q)
    
    for topic, qs in grouped.items():
        st.markdown(f'<div class="topic-badge">📌 {topic}</div>', unsafe_allow_html=True)
        for q in qs:
            with st.container():
                opts_html = ""
                for letter in ['A', 'B', 'C', 'D']:
                    opt = q['options'].get(letter, '')
                    if not opt:
                        continue
                    cls = 'correct-opt' if (show_answers and letter == q.get('correct_answer')) else 'option-row'
                    mark = "✓ " if (show_answers and letter == q.get('correct_answer')) else ""
                    opts_html += f'<div class="{cls}">{mark}{letter}. {opt}</div>'
                
                st.markdown(f"""
                <div class="question-block">
                    <div class="question-text">Q{q['question_number']}. {q['question_text']}</div>
                    {opts_html}
                </div>
                """, unsafe_allow_html=True)
                
                if show_answers and q.get('explanation'):
                    st.caption(f"💡 {q['explanation']}")

# ── Main App ──────────────────────────────────────────────────────────────────
def main():
    # Hero
    st.markdown("""
    <div class="hero-card">
        <h1>📝 MCQ Extractor & Exam Builder</h1>
        <p>Upload a YouTube video, transcript, or PDF practice sheet — get a clean exam paper & answer key instantly.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # ── Sidebar ──
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        st.markdown('<div class="api-key-section">', unsafe_allow_html=True)
        api_key = st.text_input(
            "🔑 Gemini API Key",
            type="password",
            placeholder="AIza...",
            help="Your Google Gemini API key. Get one at aistudio.google.com"
        )
        st.markdown("</div>", unsafe_allow_html=True)
        
        if api_key:
            st.success("✓ API key provided")
        else:
            st.warning("Enter your Gemini API key to begin")
            st.markdown("[Get a free API key →](https://aistudio.google.com/app/apikey)")
        
        st.markdown("---")
        st.markdown("### 📋 How it works")
        st.markdown("""
1. **Enter** your Gemini API key  
2. **Choose** your input type  
3. **Upload or paste** your content  
4. **Extract** MCQs automatically  
5. **Download** the exam PDFs
        """)
        st.markdown("---")
        st.markdown("### ℹ️ Supported content")
        st.markdown("""
- 🎥 YouTube practice videos  
- 📄 Pasted transcripts  
- 📑 PDF worksheets & past papers  
        """)
    
    if not api_key:
        st.info("👈 Please enter your Gemini API key in the sidebar to get started.")
        return
    
    # ── Input Section ──
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### 📥 Input Content")
    
    input_tab, yt_tab, pdf_tab = st.tabs([
        "📋 Paste Transcript", "🎥 YouTube URL", "📑 Upload PDF"
    ])
    
    content_text = ""
    source_name  = "Practice Sheet"
    
    with yt_tab:
        st.markdown("#### YouTube Video")
        yt_url = st.text_input("Video URL", placeholder="https://www.youtube.com/watch?v=...")
        col1, col2 = st.columns([1, 3])
        with col1:
            fetch_btn = st.button("Fetch Transcript", key="fetch_yt")
        
        if fetch_btn and yt_url:
            with st.spinner("Fetching transcript..."):
                try:
                    content_text = get_youtube_transcript(yt_url)
                    st.session_state['yt_transcript'] = content_text
                    st.session_state['yt_url'] = yt_url
                    st.success(f"✓ Transcript fetched — {len(content_text.split())} words")
                    with st.expander("Preview transcript"):
                        st.text(content_text[:1000] + "..." if len(content_text) > 1000 else content_text)
                except Exception as e:
                    st.error(f"Could not fetch transcript: {e}")
                    st.info("Try the 'Paste Transcript' tab to paste the transcript manually.")
        
        if 'yt_transcript' in st.session_state and not fetch_btn:
            content_text = st.session_state['yt_transcript']
            source_name  = f"YouTube — {st.session_state.get('yt_url','')[:40]}"
    
    with input_tab:
        st.markdown("#### Paste your transcript or question text")
        pasted = st.text_area(
            "Content",
            height=250,
            placeholder="Paste the full transcript or text of your practice session here...",
            label_visibility="collapsed"
        )
        if pasted.strip():
            content_text = pasted
            source_name  = "Pasted Transcript"
    
    with pdf_tab:
        st.markdown("#### Upload a PDF practice sheet")
        uploaded = st.file_uploader("PDF file", type=['pdf'], label_visibility="collapsed")
        if uploaded:
            with st.spinner("Extracting text from PDF..."):
                pdf_text = extract_pdf_text(uploaded.read())
                if pdf_text.strip():
                    content_text = pdf_text
                    source_name  = uploaded.name.replace('.pdf', '')
                    st.success(f"✓ PDF parsed — {len(pdf_text.split())} words extracted")
                    with st.expander("Preview extracted text"):
                        st.text(pdf_text[:1000] + "..." if len(pdf_text) > 1000 else pdf_text)
                else:
                    st.error("Could not extract text. The PDF may be scanned/image-based.")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ── Extract Button ──
    if content_text.strip():
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        col_a, col_b, col_c = st.columns([2, 1, 2])
        with col_b:
            extract_btn = st.button("🚀 Extract MCQs", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        if extract_btn:
            with st.spinner("Analyzing content and extracting questions... this may take a moment."):
                try:
                    questions = extract_mcqs(content_text, api_key)
                    st.session_state['questions']    = questions
                    st.session_state['source_name']  = source_name
                except json.JSONDecodeError as e:
                    st.error(f"Failed to parse model response as JSON: {e}")
                    st.stop()
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                    st.stop()
    
    # ── Results ──
    if 'questions' in st.session_state and st.session_state['questions']:
        questions   = st.session_state['questions']
        source_name = st.session_state.get('source_name', 'Practice Sheet')
        topics      = list(dict.fromkeys(q['topic'] for q in questions))
        
        st.markdown("---")
        
        # Stats
        st.markdown(f"""
        <div class="stats-row">
            <div class="stat-box"><div class="stat-num">{len(questions)}</div><div class="stat-lbl">Questions</div></div>
            <div class="stat-box"><div class="stat-num">{len(topics)}</div><div class="stat-lbl">Topics</div></div>
            <div class="stat-box"><div class="stat-num">{len(questions)}</div><div class="stat-lbl">Total Marks</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        # ── PDF Download ──
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### 📥 Download PDFs")
        
        with st.spinner("Generating PDFs..."):
            try:
                practice_pdf = build_pdf(questions, is_answer_key=False,  title_prefix=source_name)
                answers_pdf  = build_pdf(questions, is_answer_key=True,   title_prefix=source_name)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📄 Download Practice Sheet",
                        data=practice_pdf,
                        file_name=f"{source_name}_practice_sheet.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                with col2:
                    st.download_button(
                        label="✅ Download Answer Key",
                        data=answers_pdf,
                        file_name=f"{source_name}_answer_key.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
            except Exception as e:
                st.error(f"PDF generation error: {e}")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # ── Preview ──
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### 👁️ Preview")
        
        prev1, prev2 = st.tabs(["📋 Practice Sheet", "✅ Answer Key"])
        with prev1:
            render_question_preview(questions, show_answers=False)
        with prev2:
            render_question_preview(questions, show_answers=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
