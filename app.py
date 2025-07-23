import streamlit as st
import sqlite3
import json
from datetime import datetime
from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
import streamlit.components.v1 as components

# --- Configuration ---
DB_FILE = "submissions.db"
COURSES = [
    "IMT 598 I: Foundations of Artificial Intelligence",
    "IMT 587 C: Principles of Information Project Management",
    "IMT 572 B: Data Science I – Theoretical Foundations"
]
RUBRIC_WEIGHTS = {
    "Understanding of Topic": 25,
    "Originality & Critical Thinking": 20,
    "Use of Evidence & Examples": 15,
    "Structure & Organization": 15,
    "Clarity & Writing Style": 10,
    "Citation & Academic Integrity": 15
}

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            course TEXT,
            assignment_text TEXT,
            rubric_text TEXT,
            ai_feedback TEXT,
            scorecard_json TEXT,
            computed_score REAL,
            computed_grade TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --- Helper Functions ---
def extract_text(file):
    if file.type == "application/pdf":
        reader = PdfReader(file)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    elif file.type.startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""

def generate_prompt(text):
    return (
        "Please review this student assignment for plagiarism and AI-generated content. "
        "Then provide a JSON scorecard with numeric scores (0-5) for each rubric category.\n\n"
        f"Rubric weights: {json.dumps(RUBRIC_WEIGHTS)}\n\n"
        "Assignment text:\n" + text
    )

def parse_scorecard(scorecard_str):
    try:
        return json.loads(scorecard_str)
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON scorecard: {e}")
        return {}

def compute_score(scorecard):
    total = 0.0
    max_scale = 5.0
    for criterion, weight in RUBRIC_WEIGHTS.items():
        value = scorecard.get(criterion, 0)
        try:
            total += (float(value) / max_scale) * weight
        except:
            pass
    return round(total, 2)

def grade_letter(score):
    if score >= 85:
        return "A"
    elif score >= 75:
        return "B+"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "F"

# --- Database Operations ---
def save_submission(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO submissions 
        (name, email, course, assignment_text, rubric_text, ai_feedback, scorecard_json, computed_score, computed_grade)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['name'], data['email'], data['course'], data['assignment_text'],
        data['rubric_text'], data.get('ai_feedback', ''), data.get('scorecard_str', ''),
        data.get('computed_score', 0), data.get('computed_grade', '')
    ))
    conn.commit()
    conn.close()

def fetch_submissions():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(
        "SELECT name, email, course, computed_score, computed_grade, submitted_at "
        "FROM submissions ORDER BY submitted_at DESC",
        conn
    )
    conn.close()
    return df

# --- Main Application ---
init_db()
st.set_page_config(page_title="Assignment Grader", layout="wide")
st.title("📄 Assignment Grader")

# --- Dynamic Form Reset Logic via uploader_id ---
if 'uploader_id' not in st.session_state:
    st.session_state['uploader_id'] = 0
form_id = st.session_state['uploader_id']

# Step 1: Process Assignment
with st.form(f"submit_form_{form_id}"):
    st.header("1️⃣ Submit Assignment")
    name = st.text_input("Student Name", key=f"name_{form_id}")
    email = st.text_input("Student Email", key=f"email_{form_id}")
    course = st.selectbox("Select Course", COURSES, key=f"course_{form_id}")
    uploaded_file = st.file_uploader(
        "Upload PDF or DOCX", type=["pdf", "docx"], key=f"file_{form_id}"
    )
    rubric_text = st.text_area(
        "Paste Grading Rubric (Full Text)", height=120, key=f"rubric_{form_id}"
    )
    submitted = st.form_submit_button("Process Assignment")

if submitted:
    if not all([name, email, course, uploaded_file, rubric_text]):
        st.warning("Please complete all fields and upload a valid file.")
    else:
        assignment_text = extract_text(uploaded_file)
        st.success("✅ Assignment processed.")
        st.subheader("Extracted Text Preview")
        st.text_area("", assignment_text, height=200)
        st.session_state["data"] = {
            "name": name,
            "email": email,
            "course": course,
            "assignment_text": assignment_text,
            "rubric_text": rubric_text
        }

# Step 2: ChatGPT Prompt & Scoring
if st.session_state.get("data"):
    d = st.session_state["data"]
    prompt = generate_prompt(d["assignment_text"])
    st.subheader("2️⃣ ChatGPT JSON Scorecard Prompt")
    st.markdown("Copy and paste the following into ChatGPT to obtain a JSON scorecard:")
    st.text_area("Prompt for ChatGPT", prompt, height=200, key=f"prompt_{form_id}")
    st.markdown("[Open ChatGPT](https://chat.openai.com/chat)", unsafe_allow_html=True)

    scorecard_str = st.text_area(
        "Paste ChatGPT JSON Scorecard", height=150, key=f"scorecard_{form_id}"
    )
    ai_feedback = st.text_area(
        "Paste ChatGPT Feedback / AI Analysis", height=150, key=f"feedback_{form_id}"
    )

    if scorecard_str:
        sc = parse_scorecard(scorecard_str)
        score = compute_score(sc)
        letter = grade_letter(score)
        st.info(f"Computed Score: {score}/100 → Grade: {letter}")
        d.update({
            "scorecard_str": scorecard_str,
            "ai_feedback": ai_feedback,
            "computed_score": score,
            "computed_grade": f"{letter}, {score}%"
        })
        st.session_state["data"] = d

    if st.button("💾 Save Submission and Grade"):
        save_submission(st.session_state["data"])
        st.success("✅ Submission and grade saved.")

# Submission Log
st.markdown("---")
st.header("📋 Submission Log")
sub_df = fetch_submissions()
if not sub_df.empty:
    display_df = sub_df.reset_index(drop=True)
    display_df.index = display_df.index + 1
    display_df.index.name = "No."
    st.dataframe(display_df)
    csv = display_df.to_csv(index=False).encode('utf-8')

    col1, col2 = st.columns([3,1])
    with col1:
        st.download_button(
            "⬇️ Download All Submissions as CSV",
            csv,
            "submissions.csv",
            "text/csv"
        )
    with col2:
        if st.button("➕ New Submission"):
            # increment form_id and clear data
            st.session_state['uploader_id'] += 1
            if 'data' in st.session_state:
                del st.session_state['data']
            # safely rerun or fallback to page reload
            try:
                st.experimental_rerun()
            except AttributeError:
                st.write("<script>location.reload()</script>", unsafe_allow_html=True)

else:
    st.info("No submissions recorded yet.")
