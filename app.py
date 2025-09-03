<<<<<<< HEAD
# feedback.py
# -*- coding: utf-8 -*-

"""
Overview
- No more chunking: index the student's whole narrative as a single document.
- Review order: PRIORITY items first (strict), then SUPPLEMENT items (feasibility/consistency).
- If neither `priority_items` nor `supplement_items` is provided, fall back to `leed_scores`
  (any key with a value > 0 is treated as an item to review).
- Returns: (feedback_text, scores_dict, err_msg). The scores_dict can be empty; it’s kept
  for front-end compatibility.

Environment
- Requires an OpenAI API key in `OPENAI_API_KEY`.
- Works with both the newer `OpenAI()` client and the legacy `openai.*.create` style SDK.
"""

from __future__ import annotations
import os
import io
import json
import uuid
import math
import logging
from typing import List, Dict, Any, Optional, Tuple

# ====== Logging ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ====== OpenAI client shim: support new and old SDKs ======
_OPENAI_MODE = None   # "new" | "old"
_client = None

def _init_openai():
    """Initialize OpenAI client for both new and legacy SDKs."""
    global _OPENAI_MODE, _client
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logging.warning("OPENAI_API_KEY is not set. Please configure it in your environment.")
    try:
        # New SDK
        from openai import OpenAI  # type: ignore
        _client = OpenAI(api_key=api_key) if api_key else OpenAI()
        _OPENAI_MODE = "new"
        logging.info("Using NEW OpenAI SDK client.")
    except Exception:
        # Legacy SDK
        import openai  # type: ignore
        openai.api_key = api_key or None
        _client = openai
        _OPENAI_MODE = "old"
        logging.info("Using OLD OpenAI SDK (openai.*.create).")

_init_openai()


# ====== File reading helpers: .docx/.pdf/.txt ======
def _read_docx(path: str) -> str:
    try:
        from docx import Document
    except Exception:
        logging.error("Missing dependency: python-docx")
        raise
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _read_pdf(path: str) -> str:
    try:
        import PyPDF2
    except Exception:
        logging.error("Missing dependency: PyPDF2")
        raise
    text = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                text.append(t)
    return "\n".join(text)


def read_text(user_input: Optional[str] = None, file_path: Optional[str] = None) -> str:
    """Return plain text from user input or an uploaded file."""
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".docx":
            return _read_docx(file_path)
        elif ext == ".pdf":
            return _read_pdf(file_path)
        else:
            with io.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    if user_input:
        return user_input.strip()
    return ""


# ====== OpenAI call wrappers ======
_EMBED_MODEL_CANDIDATES = ["text-embedding-3-small", "text-embedding-ada-002"]
_CHAT_MODEL_CANDIDATES = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

def get_embedding(text: str) -> Optional[List[float]]:
    """Get an embedding vector for a string using the first working model."""
    text = (text or "").strip()
    if not text:
        return None

    for model in _EMBED_MODEL_CANDIDATES:
        try:
            if _OPENAI_MODE == "new":
                emb = _client.embeddings.create(model=model, input=text)  # type: ignore
                return emb.data[0].embedding  # type: ignore
            else:
                emb = _client.Embedding.create(model=model, input=text)  # type: ignore
                return emb["data"][0]["embedding"]
        except Exception as e:
            logging.warning(f"Embedding model '{model}' failed: {e}")
            continue
    logging.error("All embedding model candidates failed.")
    return None


def chat_once(system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 300) -> str:
    """One-shot chat completion with fallback across model candidates."""
    last_err = None
    for model in _CHAT_MODEL_CANDIDATES:
        try:
            if _OPENAI_MODE == "new":
                resp = _client.chat.completions.create(  # type: ignore
                    model=model,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens
                )
                content = resp.choices[0].message.content or ""  # type: ignore
                return content.strip()
            else:
                resp = _client.ChatCompletion.create(  # type: ignore
                    model=model,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens
                )
                content = resp["choices"][0]["message"]["content"] or ""
                return content.strip()
        except Exception as e:
            last_err = e
            logging.warning(f"Chat model '{model}' failed: {e}")
            continue
    raise RuntimeError(f"All chat models failed. Last error: {last_err}")


# ====== Minimal local vector index (single full text) ======
class SimpleVectorIndex:
    """A tiny in-memory index for this request lifecycle."""
    def __init__(self):
        self._docs: List[str] = []
        self._embs: List[List[float]] = []
        self._metas: List[Dict[str, Any]] = []

    def add(self, document: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None):
        self._docs.append(document)
        self._embs.append(embedding)
        self._metas.append(metadata or {})

    @staticmethod
    def _cos_sim(a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        dot = 0.0
        na = 0.0
        nb = 0.0
        for x, y in zip(a, b):
            dot += x * y
            na += x * x
            nb += y * y
        if na <= 0 or nb <= 0:
            return 0.0
        return dot / (math.sqrt(na) * math.sqrt(nb))

    def query(self, query_embedding: List[float], n_results: int = 1) -> List[Dict[str, Any]]:
        if not self._docs:
            return []
        sims = [(i, self._cos_sim(query_embedding, emb)) for i, emb in enumerate(self._embs)]
        sims.sort(key=lambda x: x[1], reverse=True)
        out = []
        for i, score in sims[:max(1, n_results)]:
            out.append({
                "document": self._docs[i],
                "metadata": self._metas[i],
                "score": float(score)
            })
        return out


# Global index (re-initialized per request)
_INDEX = SimpleVectorIndex()


def index_full_text(text: str) -> Optional[str]:
    """Index the entire student narrative as a single document."""
    try:
        emb = get_embedding(text)
        if not emb:
            logging.warning("Failed to embed the full text.")
            return None
        doc_id = str(uuid.uuid4())
        _INDEX.add(document=text, embedding=emb, metadata={"id": doc_id, "full_text": True})
        logging.debug("Full text added to index.")
        return doc_id
    except Exception as e:
        logging.exception(f"Error indexing full text: {e}")
        return None


# ====== Item-by-item review ======
def process_leed_item(item_name: str, importance: str = "priority") -> str:
    """
    Review a single LEED item.
    importance: 'priority' | 'supplement'
    """
    item_name = (item_name or "").strip()
    if not item_name:
        return "Empty item name."

    logging.debug(f"Processing item: {item_name} ({importance})")

    # Trivial recall against the single full-text doc
    q = f"LEED item {importance}: {item_name}"
    q_emb = get_embedding(q)
    if not q_emb:
        return f"[{item_name}] Unable to create query embedding."

    results = _INDEX.query(query_embedding=q_emb, n_results=1)
    excerpt = results[0]["document"] if results else ""

    strict_note = (
        "This is a PRIORITY item. Be STRICT: prerequisites and critical thresholds must be explicitly satisfied. "
        "Identify any missing proofs, misinterpretations, or prerequisite gaps."
        if importance == "priority"
        else "This is a SUPPLEMENT item. Focus on plausibility, internal consistency, and whether the narrative proposes credible means of achievement."
    )

    prompt = f"""
You are an experienced LEED BD+C reviewer.
Focus on: "{item_name}".
{strict_note}

Student narrative (full-text excerpt; treat this as the student's entire narrative):
---
{excerpt}
---

Task:
1) State clearly whether the student's narrative sufficiently addresses "{item_name}".
2) If not fully sufficient, list the specific missing/unclear aspects.
3) Provide a concise, actionable recommendation (≤80 words).
Respond concisely, use bullet points if helpful, and avoid extra commentary.
"""

    try:
        resp = chat_once(
            system_prompt="You provide item-by-item LEED compliance feedback.",
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=220
        )
        return resp.strip()
    except Exception as e:
        logging.exception(f"Chat error on item '{item_name}': {e}")
        return f"[{item_name}] Review failed: {e}"


# ====== Main entry point ======
def get_feedback(
    user_input: Optional[str] = None,
    file_path: Optional[str] = None,
    rubrics: Optional[Any] = None,  # kept for compatibility; not used
    leed_scores: Optional[Dict[str, Any]] = None,
    priority_items: Optional[List[Any]] = None,
    supplement_items: Optional[List[Any]] = None
) -> Tuple[str, Dict[str, Any], str]:
    """
    Read text → verify it's a LEED Narrative → index full text → review PRIORITY items first,
    then SUPPLEMENT items.

    - priority_items / supplement_items can be like:
        ["Optimize Energy Performance", ...] or [{"name": "Optimize Energy Performance"}, ...]
    - If both are empty, fall back to `leed_scores` (any key with value > 0 becomes an item).

    Returns: (final_feedback_text, scores_dict (pass-through), err_msg)
    """
    # Reinitialize the ephemeral index per call (prevents cross-request bleed)
    global _INDEX
    _INDEX = SimpleVectorIndex()

    # 1) Read the narrative
    text = read_text(user_input=user_input, file_path=file_path)
    if not text or len(text.strip()) < 50:
        return "Your writing is too short to generate meaningful feedback.", {}, ""

    # 2) Quick classification: Is it a LEED Narrative?
    classify_prompt = f"""
Determine if the following text is specifically discussing a LEED Narrative for building certification.
If yes, respond with exactly "LEED Narrative".
If not, respond exactly "Not LEED Narrative".

Text:
{text[:6000]}  # truncated for safety
    """.strip()

    try:
        cls = chat_once(
            system_prompt="You classify whether the text is a LEED Narrative.",
            user_prompt=classify_prompt,
            temperature=0.0,
            max_tokens=5
        ).lower()
    except Exception as e:
        logging.exception(f"Classification error: {e}")
        return f"Error when checking narrative type: {e}", {}, ""

    if "leed narrative" not in cls:
        return "This passage is not a LEED Narrative.", {}, ""

    # 3) Index the full text
    index_full_text(text)

    # 4) Normalize priority/supplement arrays
    def _normalize_items(arr: Optional[List[Any]]) -> List[str]:
        if not arr:
            return []
        out = []
        for it in arr:
            if isinstance(it, dict) and "name" in it:
                out.append(str(it["name"]).strip())
            else:
                out.append(str(it).strip())
        return [x for x in out if x]

    priority_list = _normalize_items(priority_items)
    supplement_list = _normalize_items(supplement_items)

    # 5) Fallback: if both are empty, use leed_scores (keys with value > 0)
    fallback_list = []
    if not priority_list and not supplement_list and isinstance(leed_scores, dict):
        for k, v in leed_scores.items():
            if k == "total_score":
                continue
            try:
                val = float(v)
            except Exception:
                continue
            if val > 0:
                fallback_list.append(k)

    sections: List[str] = []

    # Priority items first (strict)
    if priority_list:
        pf = []
        for name in priority_list:
            pf.append(f"**{name}**\n{process_leed_item(name, importance='priority')}")
        sections.append("=== Priority Items Check ===\n" + "\n\n".join(pf))

    # Supplement items next (feasibility/consistency)
    if supplement_list:
        sf = []
        for name in supplement_list:
            sf.append(f"**{name}**\n{process_leed_item(name, importance='supplement')}")
        sections.append("=== Supplementary Items Check ===\n" + "\n\n".join(sf))

    # Fallback from numeric scores (treat as priority-level scrutiny)
    if not sections and fallback_list:
        items = []
        for name in fallback_list:
            items.append(f"**{name}**\n{process_leed_item(name, importance='priority')}")
        sections.append("=== Items From Scores (Fallback) ===\n" + "\n\n".join(items))

    final_feedback = "\n\n".join(sections) if sections else "No specific items were provided to review."
    # Currently we pass back `leed_scores` as-is for front-end compatibility.
    return final_feedback, (leed_scores or {}), ""


# ====== Local quick test ======
if __name__ == "__main__":
    demo_text = """
    Our project targets LEED v4 BD+C. We commit to meeting all prerequisites.
    We will optimize energy performance by improving the building envelope,
    adopting high-efficiency HVAC with VAV and heat recovery, and commissioning.
    Indoor water use reduction is addressed via WaterSense fixtures achieving >30% reduction baseline.
    We also consider enhanced refrigerant management by selecting low-GWP refrigerants.
    """
    fb, scores, err = get_feedback(
        user_input=demo_text,
        priority_items=["Optimize Energy Performance", "Indoor Water Use Reduction"],
        supplement_items=["Enhanced Refrigerant Management"]
    )
    print("=== FEEDBACK ===")
    print(fb)
    print("\n=== SCORES (passthrough) ===")
    print(json.dumps(scores, indent=2, ensure_ascii=False))
    if err:
        print("\nERR:", err)
=======
# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime  # Import timezone
import os
import json
from functools import lru_cache
import logging  # Ensure logging is imported
import PyPDF2
import docx
import sqlalchemy as sa

# Import feedback function
from feedback import get_feedback, process_leed_items, collection
#from leed_rubrics import LEED_TABLE_DATA

app = Flask(__name__)
# --- Secrets & DB config: set ONCE, before creating db ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')

db_url = os.getenv('DATABASE_URL', 'sqlite:///users.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024  # 80MB

# Single init for db & migrate
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Set logging level and format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# User model
class User(db.Model):
    __tablename__ = 'users' 
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.Text, nullable=False)
    
    rubrics = db.relationship('Rubric', backref='user', lazy=True)
    chat_histories = db.relationship('ChatHistory', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Rubric model
class Rubric(db.Model):
    __tablename__ = 'rubrics'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float, nullable=True)  
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# Chat history model
class ChatHistory(db.Model):
    __tablename__ = 'chat_history' 
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    prompt_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    prompt_content = db.Column(db.Text, nullable=False)
    response_time = db.Column(db.DateTime, nullable=False)
    response_content = db.Column(db.Text, nullable=False)
    user_rating = db.Column(db.Integer)  # User rating (optional)
    user_feedback = db.Column(db.Text)   # User feedback (optional)

# First run: create tables (avoids "no such table")
with app.app_context():
    db.create_all()

    logging.info("DB URL: %s", db.engine.url.render_as_string(hide_password=True))

    if db.engine.url.get_backend_name().startswith('postgresql'):
        try:
            maxlen = db.session.execute(sa.text("""
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name='users' AND column_name='password_hash'
            """)).scalar()

            logging.info(f"users.password_hash current maxlen: {maxlen}")

            if maxlen is not None:
                db.session.execute(sa.text(
                    "ALTER TABLE users ALTER COLUMN password_hash TYPE TEXT"
                ))
                db.session.commit()
                logging.info("users.password_hash has been changed to TEXT")
        except Exception as e:
            logging.warning(f"Failed to modify users.password_hash to TEXT or it is already TEXT: {e}")

# Cache LEED data
@lru_cache(maxsize=1)
def get_leed_data():
    json_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'leed_credits.json')
    logging.debug(f"Reading LEED data from {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        leed_data = json.load(f)
    logging.debug(f"LEED data loaded: {leed_data}")
    return leed_data

# Generate LEED table data for rendering in the frontend
@lru_cache(maxsize=1)
def generate_leed_table_data():
    leed_data = get_leed_data()
    table_data = []

    credits_collection = leed_data.get('LEED_Credits_Collection', {})
    logging.debug(f"credits_collection type: {type(credits_collection)}")
    logging.debug(f"credits_collection content: {credits_collection}")

    if not isinstance(credits_collection, dict):
        logging.error(f"Expected 'LEED_Credits_Collection' to be dict, got {type(credits_collection)}.")
        return table_data  # Return an empty table or process as needed

    for category_name, category_data in credits_collection.items():
        logging.debug(f"Processing category_name: {category_name}, type: {type(category_data)}")
        if not isinstance(category_data, dict):
            logging.error(f"Expected 'category_data' to be dict for category '{category_name}', got {type(category_data)}. Skipping.")
            continue  # Skip invalid structures

        section = {
            'section': f"{category_name} ({category_data.get('total_points', 0)} Points)",
            'items': []
        }
        credits = category_data.get('Credits', [])
        if not isinstance(credits, list):
            logging.error(f"Expected 'Credits' to be list for category '{category_name}', got {type(credits)}.")
            continue  # Skip invalid structures

        for credit in credits:
            if not isinstance(credit, dict):
                logging.error(f"Expected each 'credit' to be dict in category '{category_name}', got {type(credit)}. Skipping.")
                continue  # Skip invalid structures

            item = {
                'category': category_name,
                'type': credit.get('type', ''),
                'name': credit.get('name', ''),
                'points': credit.get('points', None)
            }
            section['items'].append(item)
        table_data.append(section)
    return table_data

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        # Create new user and save to database
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session.clear()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to main page
    if 'user_id' in session and User.query.get(session['user_id']):
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

        session['user_id'] = user.id

        flash('Welcome back!', 'success')

        return redirect(url_for('index'))

    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Main page route
@app.route('/')
def index():
    user_id = session.get('user_id')
    if not user_id or not User.query.get(user_id):
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    current_user = User.query.get(user_id)
    if not current_user:
        # Handle user not found
        return redirect(url_for('login'))

    # Get LEED table data
    leed_table_data = generate_leed_table_data()  # Use function to generate data
    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    return render_template('index.html', user=current_user, rubrics=rubrics, leed_table_data=leed_table_data)

@app.route('/get_user_rubrics', methods=['GET'])
def get_user_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    return jsonify({'success': True, 'rubrics': rubrics})

@app.route('/get_leed_rubrics', methods=['GET'])
def get_leed_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        print('User not logged in.')
        return jsonify({'success': False, 'error': 'User not logged in.'})

    # Get the current user object
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'User not found.'})
    
    # Fetch LEED scores from session
    leed_scores = session.get('leed_scores')
    if not leed_scores:
        print('No LEED scores found in session.')
        return jsonify({'success': False, 'error': 'No LEED scores found. Please submit LEED scores first.'})

    # Generate rubrics based on LEED scores
    leed_data = get_leed_data()
    print("DEBUG leed_data type:", type(leed_data))
    print("DEBUG leed_data content:", leed_data)

    # Build a mapping from item titles to their data
    def normalize_title(title):
        return title.strip().lower()

    item_data_mapping = {}
    credits_collection = leed_data.get('LEED_Credits_Collection', {})
    for rating_system, categories in credits_collection.items():
        for category_name, category_data in categories.items():
            credits = category_data.get("Credits", [])
            for item in credits:
                item_title = item.get('name', '')
                normalized_title = normalize_title(item_title)
                item_data_mapping[normalized_title] = item

    selected_rubrics = []
    for item_title, score in leed_scores.items():
        try:
            numeric_score = float(score)
        except (ValueError, TypeError):
            print(f'Invalid score for "{item_title}": {score}. Skipping.')
            continue  # Skip invalid scores

        if numeric_score > 0:
            normalized_title = normalize_title(item_title)
            item_data = item_data_mapping.get(normalized_title)
            if item_data:
                # Handle total points
                points = item_data.get('points', 0)
                total_points = calculate_total_points(points)

                # Extract descriptions from options if available
                descriptions = []
                requirements = item_data.get('requirements', {})
                if 'options' in requirements:
                    for option in requirements['options']:
                        option_desc = option.get('description', '')
                        if option_desc:
                            descriptions.append(option_desc)
                else:
                    # Use 'intent' as description if no options are available
                    intent = item_data.get('intent', 'No description available.')
                    descriptions.append(intent)

                # Get scoring criteria
                scoring_criteria = item_data.get('scoring_criteria', [])

                selected_rubrics.append({
                    'title': item_data.get('name'),
                    'user_score': numeric_score,
                    'descriptions': descriptions,
                    'scoring_criteria': scoring_criteria,
                    'total_points': total_points
                })
            else:
                print(f'Item data not found for: {item_title}')

    return jsonify({'success': True, 'rubrics': selected_rubrics})

# Helper function to calculate total points
def calculate_total_points(points):
    if isinstance(points, (int, float)):
        return points
    elif isinstance(points, str):
        if points.lower() == 'required':
            return 0  # Or set a default value as needed
        try:
            return float(points)
        except ValueError:
            return 0
    else:
        return 0

# Get feedback route

@app.route('/get_feedback', methods=['POST'])
def get_feedback_route():
    user_id = session.get('user_id')
    if not user_id:
        logging.warning('User not logged in.')
        return jsonify({'success': False, 'error': 'User not logged in.'}), 401

    prompt_time = datetime.utcnow()
    logging.debug(f"User ID: {user_id}, Prompt Time: {prompt_time}")

    # Check if there is a file uploaded
    file_path = None
    uploaded_file = request.files.get('file')
    if uploaded_file and uploaded_file.filename:
        filename = secure_filename(uploaded_file.filename)
        extension = filename.rsplit('.', 1)[1].lower()
        logging.debug(f"Uploaded file name: {filename}")
        # Verify that the file suffix is ​​allowed
        if '.' in filename and extension in ALLOWED_EXTENSIONS:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)
            logging.debug(f"Saved uploaded file to: {file_path}")
            user_input = None

            # Extract file contents
            file_text = ""
            if extension == 'pdf':
                try:
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                file_text += text + "\n"
                except Exception as e:
                    logging.error("Error extracting text from PDF", exc_info=True)
            elif extension == 'docx':
                try:
                    doc = docx.Document(file_path)
                    file_text = "\n".join([para.text for para in doc.paragraphs])
                except Exception as e:
                    logging.error("Error extracting text from DOCX", exc_info=True)

            # Use all extracted text directly
            if file_text:
                prompt_content = file_text
            else:
                prompt_content = f"Uploaded file: {filename}"
        else:
            logging.warning(f"Invalid file type: {filename}")
            return jsonify({
                'success': False, 
                'error': 'Invalid file type. Only PDF and DOCX files are allowed.'
            }), 400
    else:
        # 2. If no file is uploaded, read 'message'
        user_input = request.form.get('message', '').strip()
        logging.debug(f"User input message: {user_input}")
        if not user_input:
            logging.warning('No user input provided.')
            return jsonify({'success': False, 'error': 'No user input provided.'}), 400
        prompt_content = user_input

    # 3. Calculate LEED points
    leed_scores = None
    leed_scores_json = request.form.get('leed_scores')
    if leed_scores_json:
        try:
            leed_scores = json.loads(leed_scores_json)
            logging.debug(f"LEED scores: {leed_scores}")
            # Calculate the total score
            total_score = sum(
                float(score) for key, score in leed_scores.items()
                if key != 'total_score' and isinstance(score, (int, float, str)) and str(score).replace('.', '', 1).isdigit()
            )
            leed_scores['total_score'] = total_score
            logging.debug(f"Total LEED score: {total_score}")
        except (json.JSONDecodeError, ValueError) as e:
            logging.error("Invalid LEED scores provided.", exc_info=True)
            return jsonify({'success': False, 'error': 'Invalid LEED scores provided.'}), 400

    # Get all LEED project data
    leed_table_data = generate_leed_table_data()  
    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    # Build item list
    leed_items = []
    for category in leed_table_data:
        for item in category['items']:
            leed_items.append({
                'name': item['name'],
                'points': item.get('points', 0)
            })

    # Call process_leed_items to generate feedback (RAG + item-by-item scoring)
    try:
        feedback_text = process_leed_items(leed_items, collection)
        logging.debug(f"Feedback Text: {feedback_text}")
    except Exception as e:
        logging.exception("Error in get_feedback:")
        return jsonify({'success': False, 'error': str(e)}), 500

    response_time = datetime.utcnow()
    logging.debug(f"Response Time: {response_time}")

    # Clean up after uploading files (delete temporary files)
    if file_path:
        try:
            os.remove(file_path)
            logging.debug(f"Removed uploaded file: {file_path}")
        except Exception as e:
            logging.warning(f"Failed to remove uploaded file: {file_path}. Error: {e}")

    # Save the conversation records into the database
    try:
        chat_history = ChatHistory(
            user_id=user_id,
            prompt_time=prompt_time,
            prompt_content=prompt_content,
            response_time=response_time,
            response_content=feedback_text
        )
        db.session.add(chat_history)
        logging.debug(f"Added ChatHistory: {chat_history}")

        # Delete previous Rubric records
        Rubric.query.filter_by(user_id=user_id).delete()
        logging.debug(f"Deleted previous rubrics for user_id: {user_id}")

        # Storing New Rubrics
        if leed_scores:
            for k, v in leed_scores.items():
                if k == 'total_score':
                    continue
                try:
                    new_rubric = Rubric(
                        text=k,
                        score=float(v),
                        user_id=user_id
                    )
                    db.session.add(new_rubric)
                    logging.debug(f"Added Rubric: {new_rubric}")
                except ValueError as ve:
                    logging.error(f"Invalid score value for rubric '{k}': {v}", exc_info=True)
                    continue

        db.session.commit()
        logging.debug("Committed chat history and rubrics to the database.")
    except Exception as e:
        logging.exception("Error saving chat history or rubrics:")
        return jsonify({'success': False, 'error': f"Error saving data: {e}"}), 500

    # Return results to the front end
    return jsonify({
        'success': True,
        'feedback': feedback_text,
        'scores': leed_scores,
        'chat_history_id': chat_history.id
    })

# Submit user feedback route
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    data = request.get_json()
    chat_history_id = data.get('chat_history_id')
    rating = data.get('rating')
    feedback_text = data.get('feedback')

    chat_history = ChatHistory.query.filter_by(id=chat_history_id, user_id=user_id).first()
    if not chat_history:
        return jsonify({'success': False, 'error': 'Chat history not found.'})

    chat_history.user_rating = rating if rating else None
    chat_history.user_feedback = feedback_text if feedback_text else None

    db.session.commit()

    return jsonify({'success': True})

@app.route('/save_rubrics', methods=['POST'])
def save_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})
    
    # Get the current user object
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'User not found.'})
    
    # Permission check
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'You do not have permission to perform this action.'})
    
    data = request.get_json()
    rubrics_input = data.get('rubrics')

    if rubrics_input is not None:
        # Update rubrics in the database
        Rubric.query.filter_by(user_id=user_id).delete()
        for rubric_text in rubrics_input.strip().split('\n\n'):
            if rubric_text.strip():
                new_rubric = Rubric(text=rubric_text.strip(), user_id=user_id)
                db.session.add(new_rubric)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'No rubrics provided.'})
    
@app.route('/submit_leed_scores', methods=['POST'])
def submit_leed_scores():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'User not found.'})

    data = request.get_json()
    leed_scores = data.get('leed_scores')

    if not leed_scores:
        return jsonify({'success': False, 'error': 'No LEED scores provided.'})

    # Convert scores to strings before storing in session
    leed_scores_str = {k: str(v) for k, v in leed_scores.items()}
    session['leed_scores'] = leed_scores_str

    return jsonify({'success': True})

@app.route('/admin/get_leed_data', methods=['GET'])
def admin_get_leed_data():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    current_user = User.query.get(user_id)
    if not current_user or current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'You do not have permission to perform this action.'})

    leed_data = get_leed_data()
    return jsonify({'success': True, 'leed_data': leed_data})

@app.route('/admin/save_leed_data', methods=['POST'])
def admin_save_leed_data():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    current_user = User.query.get(user_id)
    if not current_user or current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'You do not have permission to perform this action.'})

    data = request.get_json()
    leed_data = data.get('leed_data')

    if not leed_data:
        return jsonify({'success': False, 'error': 'No LEED data provided.'})
    
    # Check if leed_data conforms to the expected structure
    if not isinstance(leed_data, dict):
        return jsonify({'success': False, 'error': 'LEED data must be a dictionary.'})

    if 'LEED_Credits_Collection' not in leed_data:
        return jsonify({'success': False, 'error': 'LEED data must contain "LEED_Credits_Collection".'})

    if not isinstance(leed_data['LEED_Credits_Collection'], dict):
        return jsonify({'success': False, 'error': '"LEED_Credits_Collection" must be a dictionary.'})

        # Save LEED data to 'leed_credits.json'
    json_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'leed_credits.json')  
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(leed_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.exception("Failed to save LEED data:")
        return jsonify({'success': False, 'error': f"Failed to save LEED data: {e}"}), 500

    # Clear the cache
    get_leed_data.cache_clear()

    return jsonify({'success': True})

def load_general_rubric():
    """
    Load the general writing Rubric.
    Ensure the 'cleaned_leed_rubric.json' file exists in the same directory or provide the correct path.
    """
    rubric_path = os.path.join(os.path.dirname(__file__), "cleaned_leed_rubric.json")
    if not os.path.exists(rubric_path):
        raise FileNotFoundError(f"Rubric file not found at path: {rubric_path}")
    
    with open(rubric_path, "r", encoding="utf-8") as f:
        try:
            rubric_data = json.load(f)
            if not isinstance(rubric_data, list):
                raise ValueError("Rubric data should be a list of dictionaries.")
            return rubric_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing rubric JSON: {e}")
        

# Temporarily storing Rubric data
rubric_storage = None

# Receive WRITING_RUBRIC data from the front end
@app.route('/save_WRITING_RUBRICs', methods=['POST'])
def save_writing_rubrics():
    global rubric_storage  # Using global variables to store
    try:
        # Get JSON data from the request
        rubric_data = request.get_json()
        if not rubric_data:
            return jsonify({"error": "No data provided"}), 400

        rubric_storage = rubric_data  # Save to global variable
        return jsonify({"message": "Rubric saved successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Get the currently stored Rubric data
@app.route('/get_WRITING_RUBRICs', methods=['GET'])
def get_writing_rubrics():
    LEED_RUBRIC = [
        {
            "name": "LEED Certification Achievement",
            "scoringCriteria": [
                {"points": 3, "description": "This is a test rubric."}
            ]
        }
    ]
    return jsonify(LEED_RUBRIC)

@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled exception occurred:")
    return jsonify({"error": "An unexpected error occurred.", "details": str(e)}), 500

@app.route('/get_last_feedback', methods=['GET'])
def get_last_feedback():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'}), 401

    # Query the last feedback record in descending order of response_time
    last_chat = ChatHistory.query.filter_by(user_id=user_id).order_by(ChatHistory.response_time.desc()).first()
    if not last_chat:
        return jsonify({'success': False, 'error': 'No previous feedback found.'})

    return jsonify({
        'success': True,
        'feedback': last_chat.response_content,
        'chat_history_id': last_chat.id  
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Get the port from the environment variable, default to 5000
    app.run(host='0.0.0.0', port=port, debug=True)  # Host must be 0.0.0.0 to work on Heroku
>>>>>>> dac79ff818159051f5076784da316ba3e020095f
