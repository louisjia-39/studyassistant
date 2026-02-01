import streamlit as st
from pypdf import PdfReader
import os
import difflib
from openai import OpenAI
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
import hashlib
import re

# =========================
# OpenAI Client
# =========================
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("Missing OPENAI_API_KEY. Please set it as an environment variable or via your app secrets.")
    st.stop()

client = OpenAI(api_key=api_key)

# =========================
# Database Setup
# =========================
def get_db_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS study_history (
            id SERIAL PRIMARY KEY,
            subject TEXT,
            query TEXT,
            response TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS textbook_cache (
            subject TEXT PRIMARY KEY,
            content TEXT,
            filename TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()

init_db()

# =========================
# Page Config
# =========================
st.set_page_config(page_title="IB Multidisciplinary Study Assistant", layout="wide")
st.title("IB Multidisciplinary Study Assistant")

# =========================
# Access Control (Weekly + Manager)
# =========================
MANAGER_PASSWORD = os.environ.get("MANAGER_PASSWORD") or (
    st.secrets.get("MANAGER_PASSWORD") if hasattr(st, "secrets") else None
)

def _generate_weekly_password() -> str:
    year, week, _ = datetime.date.today().isocalendar()
    base = f"{year}-{week}"
    hashed = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return hashed[:8]

WEEKLY_PASSWORD = _generate_weekly_password()

if "has_access" not in st.session_state:
    st.session_state.has_access = False

with st.expander("🔐 Access Control", expanded=not st.session_state.has_access):
    access_code = st.text_input(
        "Enter access code", type="password", placeholder="Enter weekly or manager code"
    )
    if st.button("Submit Access Code"):
        if access_code == WEEKLY_PASSWORD:
            st.session_state.has_access = True
            st.success("Access granted for this week. Enjoy using the study assistant!")
        elif MANAGER_PASSWORD and access_code == MANAGER_PASSWORD:
            st.session_state.has_access = True
            st.info(f"Manager access granted. This week's user access code is: {WEEKLY_PASSWORD}")
        else:
            st.error("Invalid access code. Please try again.")

if not st.session_state.has_access:
    st.stop()

# =========================
# DB Helpers for History (NEW)
# =========================
def save_history(subj, q, r):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO study_history (subject, query, response) VALUES (%s, %s, %s)",
        (subj, q, r),
    )
    conn.commit()
    cur.close()
    conn.close()

def delete_history_record(record_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM study_history WHERE id = %s", (record_id,))
    conn.commit()
    cur.close()
    conn.close()

def clear_history_for_subject(subj: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM study_history WHERE subject = %s", (subj,))
    conn.commit()
    cur.close()
    conn.close()

# =========================
# Sidebar: Subject + Textbook Upload/Cache
# =========================
with st.sidebar:
    st.header("Subject & Textbook")
    subject = st.selectbox(
        "Select Subject",
        ["Economics", "Business Management", "Mathematics", "Chinese", "English",
         "Chemistry", "Physics", "Biology", "History", "Other"]
    )

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT content, filename FROM textbook_cache WHERE subject = %s", (subject,))
    cached = cur.fetchone()
    cur.close()
    conn.close()

    textbook_content = None

    if cached:
        st.success(f"Loaded cached textbook: {cached['filename']}")
        if st.button("Delete Cached Textbook"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM textbook_cache WHERE subject = %s", (subject,))
            conn.commit()
            cur.close()
            conn.close()
            st.rerun()
        textbook_content = cached["content"]
        uploaded_file = True  # your original flag for logic
    else:
        uploaded_file = st.file_uploader(
            f"Upload your {subject} textbook (PDF)",
            type=["pdf"]
        )
        if uploaded_file:
            if uploaded_file.size > 200 * 1024 * 1024:
                st.error("File too large. Please upload under 200MB.")
                st.stop()

            with st.spinner("Extracting and caching textbook..."):
                reader = PdfReader(uploaded_file)
                text = ""
                for page in reader.pages:
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    except Exception:
                        continue

                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO textbook_cache (subject, content, filename)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (subject)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        filename = EXCLUDED.filename,
                        timestamp = CURRENT_TIMESTAMP
                    """,
                    (subject, text, uploaded_file.name),
                )
                conn.commit()
                cur.close()
                conn.close()

                textbook_content = text
                st.success("PDF Cached!")
                st.rerun()

# Keep your original "must have textbook" gating logic
if not (cached or (locals().get("uploaded_file") and not isinstance(uploaded_file, bool))):
    st.info(f"👋 Please upload your {subject} textbook in the sidebar to get started.")
    st.stop()

# =========================
# Sidebar: History + Delete Controls (NEW)
# =========================
with st.sidebar:
    st.divider()
    st.header("🕒 Study History")

    # NEW: Clear history for this subject
    if st.button("🧹 Clear ALL history (this subject)", use_container_width=True):
        clear_history_for_subject(subject)
        if "current_history_id" in st.session_state:
            del st.session_state["current_history_id"]
        st.success("Cleared.")
        st.rerun()

    # Load recent history
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, query, timestamp FROM study_history WHERE subject = %s ORDER BY timestamp DESC LIMIT 10",
        (subject,),
    )
    history = cur.fetchall()
    cur.close()
    conn.close()

    # NEW: view + delete per item
    for h in history:
        c1, c2 = st.columns([0.78, 0.22])
        label = f"{h['timestamp'].strftime('%m-%d %H:%M')}: {h['query'][:20]}..."
        with c1:
            if st.button(label, key=f"hist_view_{h['id']}", use_container_width=True):
                st.session_state.current_history_id = h["id"]
        with c2:
            if st.button("🗑️", key=f"hist_del_{h['id']}", help="Delete this record", use_container_width=True):
                delete_history_record(int(h["id"]))
                # If user deleted the currently opened record, clear selection
                if st.session_state.get("current_history_id") == h["id"]:
                    del st.session_state["current_history_id"]
                st.rerun()

# =========================
# AI
# =========================
@st.cache_data
def get_ai_response(prompt, context, subject_name, allow_external=False):
    try:
        prev_match = None
        context_limit = 40000

        # --- Memory System: check similar previous queries ---
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT query, response FROM study_history WHERE subject = %s", (subject_name,))
            rows = cur.fetchall()
            cur.close()
            conn.close()

            best_score = 0.0
            best_query = None
            best_response = None

            for row in rows:
                try:
                    # RealDictCursor => row is dict-like
                    q = row["query"]
                    score = difflib.SequenceMatcher(None, prompt, q).ratio()
                    if score > best_score:
                        best_score = score
                        best_query = q
                        best_response = row["response"]
                except Exception:
                    continue

            if best_score > 0.4 and best_query is not None:
                prev_match = {"query": best_query, "response": best_response}
        except Exception:
            prev_match = None

        prev_context = ""
        if prev_match:
            prev_context = f"\nPREVIOUS RELATED ANSWER (for '{prev_match['query']}'):\n{prev_match['response']}\n"
            context_limit = 10000

        # --- Improved RAG snippet selection ---
        chapter_patterns = re.findall(r"\b\d+\.\d+\b", prompt)
        keywords = [w.strip(".,?!()") for w in prompt.split() if len(w) > 3]
        search_terms = list(set(chapter_patterns + keywords))

        relevant_snippets = []
        if search_terms:
            lines = context.split("\n")
            for i, line in enumerate(lines):
                if any(re.search(re.escape(term), line, re.IGNORECASE) for term in search_terms):
                    start = max(0, i - 30)
                    end = min(len(lines), i + 50)
                    relevant_snippets.append("\n".join(lines[start:end]))

        if not relevant_snippets:
            context_snippet = (context[:20000] + "\n... [SNIP] ...\n" + context[-10000:])[:context_limit]
        else:
            unique_snippets = list(set(relevant_snippets))
            joined_snippets = "\n--- SECTION START ---\n".join(unique_snippets)
            context_snippet = joined_snippets[:context_limit]

        external_instruction = ""
        if allow_external:
            external_instruction = (
                "If the textbook context is insufficient, you MAY use external knowledge "
                "but MUST explicitly state '【注：以下内容来源于外部资料，非教材原话】'."
            )

        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an expert IB {subject_name} tutor. {external_instruction} "
                        "Use the provided context and any previous related answers to refine your response. "
                        "If a previous answer is provided, improve upon it rather than repeating it."
                    ),
                },
                {
                    "role": "user",
                    "content": f"HIERARCHICAL CONTEXT FROM TEXTBOOK:\n{context_snippet}\n{prev_context}\n\nUSER REQUEST: {prompt}",
                },
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["💡 简化解释", "📑 完整理论", "🌍 案例/实验/应用", "📝 考试复习笔记", "💬 智能问答", "📜 历史详情"]
)

with tab1:
    st.header(f"💡 {subject} 简化解释")
    topic = st.text_input("知识点", key="topic_simple")
    if topic:
        with st.spinner("整理中..."):
            prompt = f"中英双语解释 '{topic}'。中文讲逻辑，英文留术语。禁止 LaTeX。"
            result = get_ai_response(prompt, textbook_content, subject)
            save_history(subject, f"简化解释: {topic}", result)
            st.markdown(result)

with tab2:
    st.header(f"📑 {subject} 完整理论")
    topic = st.text_input("理论概念", key="topic_theory")
    if topic:
        with st.spinner("生成中..."):
            prompt = f"提供 '{topic}' 的 IB 考试级理论。主体全英文，关键点中文注解。"
            result = get_ai_response(prompt, textbook_content, subject)
            save_history(subject, f"理论: {topic}", result)
            st.markdown(result)

with tab3:
    st.header(f"🌍 {subject} 案例/实验")
    topic = st.text_input("案例知识点", key="topic_example")
    if topic:
        with st.spinner("查找中..."):
            prompt = f"提供 2-3 个关于 '{topic}' 的英文案例/实验，配中文背景说明。"
            result = get_ai_response(prompt, textbook_content, subject)
            save_history(subject, f"案例: {topic}", result)
            st.markdown(result)

with tab4:
    st.header(f"📝 {subject} 详细复习笔记")
    st.write("请粘贴您的考试大纲、考题要求或想复习的具体内容，AI 将结合教材为您生成详细的复习笔记。")
    exam_content = st.text_area("考纲/题目要求", height=200)
    if st.button("生成详细笔记"):
        if exam_content:
            with st.spinner("深度扫描并生成极其详尽的笔记..."):
                prompt = (
                    "根据教材，为以下大纲生成极其详尽、无遗漏的复习笔记：\n"
                    f"{exam_content}\n\n要求：\n"
                    "1. 必须深入到教材的每一个层级（大标题、小标题、子要点）；\n"
                    "2. 包含教材中提到的所有定义、公式推导、图表逻辑和具体示例；\n"
                    "3. 结构严谨，体现知识的层级分支（不要简略概括）；\n"
                    "4. 采用中英双语，英文术语必须准确；\n"
                    "5. 教材不足处以外源资料补充并标注。"
                )
                result = get_ai_response(prompt, textbook_content, subject, allow_external=True)
                save_history(subject, f"复习笔记: {exam_content[:30]}...", result)
                st.markdown(result)
        else:
            st.warning("请先输入考试内容。")

with tab5:
    st.header(f"💬 {subject} 智能问答")
    user_query = st.text_input("问题", key="user_qa")
    if user_query:
        with st.spinner("思考中..."):
            result = get_ai_response(user_query, textbook_content, subject, allow_external=True)
            save_history(subject, user_query, result)
            st.write("---")
            st.markdown(result)

with tab6:
    st.header("📜 历史查看")

    # NEW: delete currently selected history record
    if "current_history_id" in st.session_state:
        record_id = st.session_state.current_history_id

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, query, response, timestamp FROM study_history WHERE id = %s",
            (record_id,),
        )
        record = cur.fetchone()
        cur.close()
        conn.close()

        if record:
            c1, c2 = st.columns([0.85, 0.15])
            with c1:
                st.subheader(f"问题: {record['query']}")
                st.caption(f"时间: {record['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            with c2:
                if st.button("🗑️ 删除本条", use_container_width=True):
                    delete_history_record(int(record["id"]))
                    del st.session_state["current_history_id"]
                    st.success("已删除")
                    st.rerun()

            st.markdown(record["response"])
        else:
            st.info("这条记录不存在或已被删除。")
            del st.session_state["current_history_id"]
            st.rerun()
    else:
        st.info("在左侧点击历史记录进行查看。")
