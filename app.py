from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

from feedback import generate_feedback 
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, abort, g
from types import SimpleNamespace
import os
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from pprint import pformat
import tempfile
import re
from sqlalchemy import text
from functools import wraps

# --- App & Paths -------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def dump_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def is_required(points: Any) -> bool:
    return str(points).strip().lower() == "required"


def safe_points(points: Any) -> float:
    try:
        return float(points)
    except Exception:
        return 0.0
# --- Defaults (minimal but valid) -------------------------------------------

DEFAULT_LEED_TABLE: List[Dict[str, Any]] = [
    {
        "section": "Integrative Process",
        "items": [
            {"category": "IP", "name": "Integrative Process", "type": "credit", "points": 1},
            {"category": "IP", "name": "Project Boundary", "type": "prereq", "points": "Required"},
        ],
    },
    {
        "section": "Energy & Atmosphere",
        "items": [
            {"category": "EA", "name": "Fundamental Commissioning", "type": "prereq", "points": "Required"},
            {"category": "EA", "name": "Minimum Energy Performance", "type": "prereq", "points": "Required"},
            {"category": "EA", "name": "Optimize Energy Performance (low tier)", "type": "credit", "points": 6},
            {"category": "EA", "name": "Optimize Energy Performance (mid tier)", "type": "credit", "points": 12},
            {"category": "EA", "name": "Optimize Energy Performance (high tier)", "type": "credit", "points": 18},
        ],
    },
    {
        "section": "Water Efficiency",
        "items": [
            {"category": "WE", "name": "Indoor Water Use Reduction", "type": "prereq", "points": "Required"},
            {"category": "WE", "name": "Outdoor Water Use Reduction", "type": "credit", "points": 2},
            {"category": "WE", "name": "Indoor Water Use Reduction (credit)", "type": "credit", "points": 6},
        ],
    },
]

DEFAULT_WRITING_RUBRIC: List[Dict[str, Any]] = [
    {
        "name": "LEED Certification Achievement",
        "scoringCriteria": [
            {"points": 3, "description": "Project clearly achieves at least LEED Certified (40-49)."},
            {"points": 2, "description": "Effort shown but some prerequisites/points misaligned."},
            {"points": 1, "description": "Key prerequisites unmet or credits unrealistic."},
            {"points": 0, "description": "No credible certification path presented."},
        ],
    },
    {
        "name": "Reflection of Credit Requirements",
        "scoringCriteria": [
            {"points": 4, "description": "Accurate, specific requirements for each selected credit."},
            {"points": 3, "description": "Mostly correct; minor gaps."},
            {"points": 2, "description": "Several requirements missing/misunderstood."},
            {"points": 1, "description": "Vague or incorrect understanding."},
            {"points": 0, "description": "No requirements reflected."},
        ],
    },
    {
        "name": "Formatting: Credit Names and Points Claimed",
        "scoringCriteria": [
            {"points": 3, "description": "Clearly lists credit names & claimed points."},
            {"points": 2, "description": "Mostly clear; minor inconsistencies."},
            {"points": 1, "description": "Incomplete or confusing."},
            {"points": 0, "description": "Not listed / unreadable."},
        ],
    },
    {
        "name": "Realistic and Detailed Implementation of Credits",
        "scoringCriteria": [
            {"points": 3, "description": "Realistic, detailed strategies tied to LEED criteria."},
            {"points": 2, "description": "Generally realistic but lacks depth."},
            {"points": 1, "description": "Vague or impractical strategies."},
            {"points": 0, "description": "No credible strategies provided."},
        ],
    },
    {
        "name": "Grammar, Structure, and Clarity",
        "scoringCriteria": [
            {"points": 2, "description": "Clear, well-structured, minimal errors."},
            {"points": 1.5, "description": "Mostly clear; a few issues."},
            {"points": 1, "description": "Noticeable errors/structure issues."},
            {"points": 0, "description": "Hard to read; many errors."},
        ],
    },
]

COST_TIER_MAP: Dict[str, str] = {
    # —— HIGH cost ——
    "Optimize Energy Performance": "high",
    "Renewable Energy Production": "high",
    "Daylight": "high",
    "Access to Quality Transit": "high",
    "LEED for Neighborhood Development Location": "high",
    "Surrounding Density and Diverse Uses": "high",
    "Building Life-Cycle Impact Reduction": "high",
    "Rainwater Management": "high",


    # —— MEDIUM cost ——
    "Enhanced Commissioning": "medium",
    "Acoustic Performance": "medium",
    "Indoor Air Quality Assessment": "medium",
    "Quality Views": "medium",
    "High Priority Site": "medium",
    "Reduced Parking Footprint": "medium",
    "Sensitive Land Protection": "medium",
    "Heat Island Reduction": "medium",
    "Site Development Protect or Restore Habitat": "medium",
    "Cooling Tower Water Use": "medium",
    "Indoor Water Use Reduction": "medium",
    "Outdoor Water Use Reduction": "medium",

}

LEED_TABLE_PATH = ROOT / "leed_table_data.json"
if not LEED_TABLE_PATH.exists():
    LEED_TABLE_PATH = DATA_DIR / "leed_table_data.json"
LEED_TABLE_DATA = load_json(LEED_TABLE_PATH, DEFAULT_LEED_TABLE)

RUBRICS_PATH = DATA_DIR / "rubrics.json"
PLAN_PATH = DATA_DIR / "plan.json"
LAST_FEEDBACK_PATH = DATA_DIR / "last_feedback.json"
if not RUBRICS_PATH.exists():
    dump_json(RUBRICS_PATH, DEFAULT_WRITING_RUBRIC)


DB_PATH = ROOT / "instance" / "users.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config["JSON_AS_ASCII"] = False

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

app.logger.info(f"DB -> {app.config['SQLALCHEMY_DATABASE_URI']}")

class Account(db.Model):
    __tablename__ = "account"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), default="student")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw: str):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)


class Interaction(db.Model):
    __tablename__ = "interaction"
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)

    step1_json = db.Column(db.Text, default="[]")
    step2_json = db.Column(db.Text, default="[]")
    step1_total = db.Column(db.Float, default=0)
    step2_total = db.Column(db.Float, default=0)
    total_points = db.Column(db.Float, default=0)

    # interaction
    chat_history_id = db.Column(db.String(64))  
    prompt_text = db.Column(db.Text)            
    prompt_time = db.Column(db.DateTime)
    feedback_text = db.Column(db.Text)  
    feedback_summary = db.Column(db.Text)         
    feedback_time = db.Column(db.DateTime)

    rating = db.Column(db.Integer)              
    student_feedback_text = db.Column(db.Text) 

    status = db.Column(db.String(32), default="draft")  # draft/final
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


with app.app_context():
    db.create_all()  
    from sqlalchemy import text
    rows = db.session.execute(text("PRAGMA table_info('interaction')")).fetchall()
    cols = {r[1] for r in rows}
    if "feedback_summary" not in cols:
        db.session.execute(text("ALTER TABLE interaction ADD COLUMN feedback_summary TEXT"))
        db.session.commit()


@app.before_request
def _load_current_user():
    g.current_user = None
    uid = session.get('user_id')
    if uid:
        g.current_user = db.session.get(Account, uid)

@app.context_processor
def _inject_tpl_vars():
    cu = getattr(g, 'current_user', None)
    return {
        "current_user": cu,
        "user": cu,  
        "is_admin": bool(cu and getattr(cu, "role", "") == "admin"),
    }
# --- Routes: Pages -----------------------------------------------------------

@app.route("/")
def index():

    if not getattr(g, 'current_user', None):
        return redirect(url_for('login'))
    
    u = get_current_user()

    try:
        user_rubrics = Rubric.query.filter_by(user_id=u.id).all()
        rubrics = [r.text for r in user_rubrics]
    except Exception:
        rubrics = []

    return render_template(
        "index.html",
        rubrics=rubrics,
        leed_table_data=LEED_TABLE_DATA
    )

# --- Utilities ---------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if 'user_id' in session and Account.query.get(session['user_id']):
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        acc = Account.query.filter_by(username=username).first()
        if acc is None or not acc.check_password(password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

        session['user_id'] = acc.id
        flash('Welcome back!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')



@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        if Account.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.', 'danger')
            return redirect(url_for('register'))

        acc = Account(username=username)
        acc.set_password(password)
        db.session.add(acc)
        db.session.commit()

        session.clear()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

def get_or_create_demo_user():
    uid = session.get('user_id')
    if not uid:
        abort(401)
    acc = Account.query.get(uid)
    if not acc:
        session.pop('user_id', None)
        abort(401)
    return SimpleNamespace(id=acc.id, username=acc.username, role=getattr(acc, 'role', 'student'))

# --- Routes: Rubrics ---------------------------------------------------------

@app.get("/get_WRITING_RUBRICs")
def get_rubrics():
    rubrics = load_json(RUBRICS_PATH, DEFAULT_WRITING_RUBRIC)
    # Frontend accepts either pure array or {"rubrics": [...]}
    return jsonify(rubrics)


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        cu = getattr(g, 'current_user', None)
        if not cu or getattr(cu, "role", "") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

@app.post("/save_WRITING_RUBRICs")
@admin_required
def save_rubrics():
    try:
        data = request.get_json(force=True, silent=False)
        if not isinstance(data, list):
            return jsonify({"error": "Body must be a JSON array of rubrics"}), 400
        dump_json(RUBRICS_PATH, data)
        return jsonify({"message": "Rubrics saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# --- Routes: Feedback --------------------------------------------------------

@app.get("/get_last_feedback")
def get_last_feedback():
    payload = load_json(LAST_FEEDBACK_PATH, {"feedback": ""})
    return jsonify({"success": True, "feedback": payload.get("feedback", "")})


@app.post("/get_feedback")
def get_feedback():

    msg = request.form.get("message", "").strip()
    leed_scores_json = request.form.get("leed_scores")
    rubrics_text = request.form.get("rubrics", "")
    f = request.files.get("file")

    leed_scores = None
    if leed_scores_json:
        try:
            leed_scores = json.loads(leed_scores_json)
        except Exception:
            app.logger.warning("[FEEDBACK] invalid leed_scores_json")
            leed_scores = None

    user = get_current_user()
    draft = get_or_create_draft(user.id)
    try:
        priority_items = json.loads(draft.step1_json or "[]")
    except Exception:
        priority_items = []
    try:
        supplement_items = json.loads(draft.step2_json or "[]")
    except Exception:
        supplement_items = []

    app.logger.info(
        "[FEEDBACK] priority_items=%d, supplement_items=%d, leed_scores_keys=%d",
        len(priority_items), len(supplement_items),
        (len(leed_scores) if isinstance(leed_scores, dict) else 0)
    )

    uploaded_text = ""
    if f and f.filename:
        fname = f.filename.lower()
        try:
            if fname.endswith(".pdf"):
                try:
                    from pdfminer.high_level import extract_text as _pdf_extract
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        f.save(tmp.name)
                        uploaded_text = _pdf_extract(tmp.name) or ""
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                except Exception as e:
                    app.logger.warning(f"[FEEDBACK] PDF extract failed: {e}")
                    try:
                        uploaded_text = f.read().decode("utf-8", "ignore")
                    except Exception:
                        uploaded_text = ""
            elif fname.endswith(".docx"):
                try:
                    import docx as _docx
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                        f.save(tmp.name)
                        doc = _docx.Document(tmp.name)
                        uploaded_text = "\n".join(p.text for p in doc.paragraphs)
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                except Exception as e:
                    app.logger.warning(f"[FEEDBACK] DOCX extract failed: {e}")
                    try:
                        uploaded_text = f.read().decode("utf-8", "ignore")
                    except Exception:
                        uploaded_text = ""
            else:
                try:
                    uploaded_text = f.read().decode("utf-8", "ignore")
                except Exception:
                    uploaded_text = ""
        except Exception as e:
            app.logger.warning(f"[FEEDBACK] upload handling failed: {e}")

    narrative_text = msg or uploaded_text

    app.logger.info(
        "[FEEDBACK] using priority=%d items, supplement=%d items; msg_len=%d; file=%s",
        len(priority_items), len(supplement_items), len(narrative_text), (f.filename if f else None)
    )

    feedback_text, scores, feedback_summary = generate_feedback(
        message=narrative_text,
        leed_scores=leed_scores,                
        rubrics_text=rubrics_text,
        uploaded_filename=(f.filename if f else None),
        priority_items=priority_items,          #  Step 1
        supplement_items=supplement_items,      #  Step 2
    )

    dump_json(LAST_FEEDBACK_PATH, {"feedback": feedback_text})

    chat_id = str(uuid.uuid4())
    rec = Interaction(
        user_id=user.id,
        step1_json=draft.step1_json,
        step2_json=draft.step2_json,
        step1_total=draft.step1_total or 0,
        step2_total=draft.step2_total or 0,
        total_points=(draft.total_points or 0),

        chat_history_id=chat_id,
        prompt_text=narrative_text or None,
        prompt_time=datetime.now(timezone.utc),
        feedback_text=feedback_text,
        feedback_summary=feedback_summary,
        feedback_time=datetime.now(timezone.utc),
        status="final",
    )
    db.session.add(rec)
    db.session.commit()

    return jsonify({
        "success": True,
        "feedback": feedback_text,
        "feedback_summary": feedback_summary,
        "scores": scores,                  
        "chat_history_id": chat_id,
    })



@app.post("/submit_feedback")
def submit_feedback():
    try:
        data = request.get_json(force=True) or {}
        chat_history_id = data.get("chat_history_id")
        rating = data.get("rating")
        feedback = data.get("feedback")

        user = get_current_user()
        rec = Interaction.query.filter_by(user_id=user.id, chat_history_id=chat_history_id).first()
        if not rec:
            return jsonify({"success": False, "error": "record not found"}), 404

        if rating is not None:
            try:
                rec.rating = int(rating)
            except:
                pass
        if feedback is not None:
            rec.student_feedback_text = feedback

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400

def _scores_to_credits(scores: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(scores, dict):
        return []
    credits: List[Dict[str, Any]] = []
    name_to_item: Dict[str, Dict[str, Any]] = {}
    for sec in LEED_TABLE_DATA:
        for it in sec.get("items", []):
            nm = it.get("name", "")
            if nm:
                name_to_item[nm] = it

    for name, raw in scores.items():
        it = name_to_item.get(name)
        if not it or is_required(it.get("points")):
            continue

        v = safe_points(raw)
        v = int(round(v))                 
        if v <= 0:
            continue                     

        maxp = it.get("points")
        if isinstance(maxp, (int, float)):
            v = min(v, int(round(float(maxp))))  

        credits.append({
            "category": it.get("category", ""),
            "name": name,
            "points": v,
        })
    return credits





def _merge_credits(*lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge multiple credits lists, and take the one with the larger credit value for items with the same name.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for lst in lists:
        for c in (lst or []):
            name = c.get("name", "")
            if not name:
                continue
            pts = safe_points(c.get("points"))
            if pts <= 0:
                continue
            pts = int(round(pts)) 
            prev = merged.get(name)
            if (prev is None) or (pts > safe_points(prev.get("points"))):
                merged[name] = {
                    "category": c.get("category", ""),
                    "name": name,
                    "points": pts,
                }
    return list(merged.values())


@app.post("/leed/submit_single")
def leed_submit_single():
    try:
        body = request.get_json(force=True) or {}
        scores = body.get("scores") or {}
        replace = bool(body.get("replace", False))

        # Key log: See how many keys are passed to the front end and what the first few items are
        app.logger.info("[LEED] submit_single got %d score items; sample=%s",
                        len(scores), list(scores.items())[:5])

        if not isinstance(scores, dict):
            return jsonify({"success": False, "error": "scores must be an object/dict"}), 400

        credits = _scores_to_credits(scores)
        subtotal = sum(safe_points(c.get("points")) for c in credits)

        user = get_current_user()
        draft = get_or_create_draft(user.id)

        if replace:
            draft.step1_json = "[]"
            draft.step1_total = 0
            draft.step2_json = json.dumps(credits, ensure_ascii=False)
            draft.step2_total = subtotal
            draft.total_points = subtotal
        else:
            try:
                old2 = json.loads(draft.step2_json or "[]")
            except Exception:
                old2 = []
            merged = _merge_credits(old2, credits)
            draft.step2_json = json.dumps(merged, ensure_ascii=False)
            draft.step2_total = sum(safe_points(x.get("points")) for x in merged)
            draft.total_points = (draft.step1_total or 0) + (draft.step2_total or 0)

        db.session.commit()

        # The actual plan after saving is directly returned to the front end to avoid empty data when "reading again"
        saved_plan = json.loads(draft.step2_json or "[]")
        cost_report = _cost_report_for_plan(saved_plan)
        return jsonify({
            "success": True,
            "total_points": round(draft.total_points or 0, 1),
            "plan": saved_plan,
            "cost_report": cost_report,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@app.get("/leed/plan_single")
def leed_plan_single():
    """
    Returns the "Merge Plan" in the single-step view:
    - Merge step1 + step2 in the database (for identical names, the largest value is taken).
    This way, the historical data for both steps can also be pre-populated in the single-step mode on the front-end.
    Response: { success, plan: [{category, name, points}], total_points }
    """
    user = get_current_user()
    draft = get_or_create_draft(user.id)

    try:
        step1 = json.loads(draft.step1_json or "[]")
    except Exception:
        step1 = []
    try:
        step2 = json.loads(draft.step2_json or "[]")
    except Exception:
        step2 = []

    merged = _merge_credits(step1, step2)
    total = sum(safe_points(x.get("points")) for x in merged)


    cost_report = _cost_report_for_plan(merged)
    # Do not force write back to DB (keep idempotent read); synchronize draft.total_points = total if necessary
    return jsonify({
        "success": True,
        "plan": merged,
        "total_points": round(total, 1),
        "cost_report": cost_report,  
    })


# --- Routes: LEED plan (priority & supplement) -------------------------------

def _load_plan() -> Dict[str, List[Dict[str, Any]]]:
    return load_json(PLAN_PATH, {"priority": [], "supplement": []})


@app.post("/leed/scores")
def leed_scores():
    try:
        body = request.get_json(force=True) or {}

        # === DEBUG ===
        app.logger.info("[LEED] /leed/scores raw body:\n%s", pformat(body))

        phase = body.get("phase", "priority")
        if phase not in {"priority", "supplement"}:
            return jsonify({"success": False, "error": "phase must be 'priority' or 'supplement'"}), 400

        scores = body.get("scores") or {}
        if not isinstance(scores, dict):
            return jsonify({"success": False, "error": "scores must be an object/dict"}), 400

        # === DEBUG ===
        app.logger.info("[LEED] phase=%s received %d score items; sample=%s",
                        phase, len(scores), pformat(list(scores.items())[:5]))

        credits = []
        for sec in LEED_TABLE_DATA:
            for it in sec.get("items", []):
                if is_required(it.get("points")):
                    continue
                name = it.get("name", "")
                val = int(round(safe_points(scores.get(name))))
                if val > 0:
                    credits.append({
                        "category": it.get("category", ""),
                        "name": name,
                        "points": val,
                    })

        user = get_current_user()
        draft = get_or_create_draft(user.id)

        arr_json = json.dumps(credits, ensure_ascii=False)
        pts = sum(safe_points(c.get("points")) for c in credits)

        # === DEBUG  ===
        app.logger.info("[LEED] phase=%s kept %d credits, subtotal=%.1f\n%s",
                        phase, len(credits), pts, pformat(credits[:8]))  # 只打印前8条，避免刷屏

        if phase == "priority":
            draft.step1_json = arr_json
            draft.step1_total = pts
        else:
            draft.step2_json = arr_json
            draft.step2_total = pts

        draft.total_points = (draft.step1_total or 0) + (draft.step2_total or 0)
        db.session.commit()

        # === DEBUG ===
        app.logger.info("[LEED] saved: step1=%.1f, step2=%.1f, total=%.1f",
                        draft.step1_total or 0, draft.step2_total or 0, draft.total_points or 0)

        return jsonify({"success": True, "total_points": round(draft.total_points or 0, 1)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400



@app.post("/leed/selection")
def leed_selection():
    """
    Body: { phase: "priority" | "supplement", credits: [{category,name,points}] }
    """
    try:
        body = request.get_json(force=True)
        phase = body.get("phase")
        credits = body.get("credits", [])
        if phase not in {"priority", "supplement"}:
            return jsonify({"success": False, "error": "phase must be 'priority' or 'supplement'"}), 400
        if not isinstance(credits, list):
            return jsonify({"success": False, "error": "credits must be a list"}), 400

        user = get_current_user()
        draft = get_or_create_draft(user.id)

        arr_json = json.dumps(credits, ensure_ascii=False)
        pts = sum(safe_points(c.get("points")) for c in credits if not is_required(c.get("points")))

        if phase == "priority":
            draft.step1_json = arr_json
            draft.step1_total = pts
        else:
            draft.step2_json = arr_json
            draft.step2_total = pts

        draft.total_points = (draft.step1_total or 0) + (draft.step2_total or 0)
        db.session.commit()

        return jsonify({"success": True, "total_points": round(draft.total_points or 0, 1)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 400


@app.get("/leed/plan")
def leed_plan():
    user = get_current_user()
    draft = get_or_create_draft(user.id)
    priority = json.loads(draft.step1_json or "[]")
    supplement = json.loads(draft.step2_json or "[]")

    # === DEBUG ===
    p_sum = sum(safe_points(x.get("points")) for x in priority)
    s_sum = sum(safe_points(x.get("points")) for x in supplement)
    app.logger.info("[LEED] /leed/plan -> step1: %d items, %.1f pts; step2: %d items, %.1f pts; total=%.1f",
                    len(priority), p_sum, len(supplement), s_sum, draft.total_points or 0)


    merged = _merge_credits(priority, supplement)
    cost_report = _cost_report_for_plan(merged)

    return jsonify({
        "success": True,
        "priority": priority,
        "supplement": supplement,
        "total_points": round(draft.total_points or 0, 1),
        "cost_report": cost_report,
    })



@app.post("/leed/suggestions")
def leed_suggestions():
    user = get_current_user()
    draft = get_or_create_draft(user.id)
    picked = {f"{x.get('category','')}|||{x.get('name','')}"
              for x in (json.loads(draft.step1_json or "[]") + json.loads(draft.step2_json or "[]"))}

    candidates = []
    for sec in LEED_TABLE_DATA:
        for it in sec.get("items", []):
            key = f"{it.get('category','')}|||{it.get('name','')}"
            if is_required(it.get("points")) or key in picked:
                continue
            candidates.append({
                "category": it.get("category", ""),
                "name": it.get("name", ""),
                "points": it.get("points", ""),
            })

    def _val(p):
        v = safe_points(p)
        return v if v > 0 else 999.0

    candidates.sort(key=lambda x: _val(x.get("points")))
    return jsonify({"success": True, "candidates": candidates[:50]})



def get_current_user():
    username = session.get("username") or "guest"
    acc = Account.query.filter_by(username=username).first()
    if not acc:
        acc = Account(username=username, role="student")
        acc.set_password("guest")  
        db.session.add(acc)
        db.session.commit()
    return acc

def get_or_create_draft(user_id: int) -> Interaction:
    draft = Interaction.query.filter_by(user_id=user_id, status="draft") \
                             .order_by(Interaction.updated_at.desc()).first()
    if not draft:
        draft = Interaction(user_id=user_id, status="draft")
        db.session.add(draft)
        db.session.commit()
    return draft
def _build_name_to_item() -> Dict[str, Dict[str, Any]]:
    m: Dict[str, Dict[str, Any]] = {}
    for sec in LEED_TABLE_DATA:
        for it in sec.get("items", []):
            nm = it.get("name", "")
            if nm:
                m[nm] = it
    return m

NAME_TO_ITEM = _build_name_to_item()

def _cost_tier(item: Dict[str, Any]) -> str:
    """Prefer item['cost'], else fallback to COST_TIER_MAP; default 'low'."""
    if not item:
        return "low"
    name = item.get("name", "") or ""
    v = item.get("cost") or COST_TIER_MAP.get(name)
    if not v:
        # try base name without trailing parenthesis, e.g. "Optimize Energy Performance (mid tier)" -> "Optimize Energy Performance"
        base = re.sub(r"\s*\(.+?\)\s*$", "", name)
        v = COST_TIER_MAP.get(base)
    if not v:
        return "low"
    v = str(v).lower()
    if v in ("high", "3"):
        return "high"
    if v in ("medium", "med", "2"):
        return "medium"
    return "low"


def _cost_report_for_plan(credits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对合并后的 plan 做成本分析，并在高成本占比过大时生成提示。"""
    by = {"low": {"count": 0, "points": 0.0},
          "medium": {"count": 0, "points": 0.0},
          "high": {"count": 0, "points": 0.0}}
    selected_names = set()

    for c in credits:
        nm = c.get("name", "")
        selected_names.add(nm)
        item = NAME_TO_ITEM.get(nm)
        tier = _cost_tier(item)
        by[tier]["count"] += 1
        by[tier]["points"] += safe_points(c.get("points"))

    high_pts = by["high"]["points"]
    # === 触发提示的阈值（可调）===
    has_warning = (high_pts >= 10) or (by["high"]["count"] >= 2)

    # 给出若干低/中成本的替代建议（从未选择的里挑）
    suggestions: List[Dict[str, Any]] = []
    if has_warning:
        for sec in LEED_TABLE_DATA:
            for it in sec.get("items", []):
                if is_required(it.get("points")):
                    continue
                nm = it.get("name", "")
                if nm in selected_names:
                    continue
                tier = _cost_tier(it)
                if tier == "high":
                    continue
                mp = safe_points(it.get("points"))
                if mp >= 2:
                    suggestions.append({"name": nm, "points": mp, "tier": tier})
        suggestions = sorted(suggestions, key=lambda x: (-x["points"], x["tier"]))[:3]

    high_names_preview = [
        c.get("name", "") for c in credits
        if _cost_tier(NAME_TO_ITEM.get(c.get("name", ""))) == "high"
    ][:3]

    msg = ""
    if has_warning:
        if suggestions:
            sug_text = ", ".join([f"{s['name']} (+{int(s['points'])})" for s in suggestions])
            msg = (
                f"Heads up: you're relying on {round(high_pts, 1)} points from high-cost credits "
                f"({', '.join(high_names_preview)}...). Consider balancing with lower-cost credits such as {sug_text}."
            )
        else:
            msg = (
                f"Heads up: you're relying on {round(high_pts, 1)} points from high-cost credits. "
                f"Consider adding some medium/low-cost credits to reduce budget risk."
            )

    return {
        "by_tier": by,
        "high_cost_points": round(high_pts, 1),
        "has_warning": bool(has_warning),
        "suggestions": suggestions,
        "message": msg,
    }


# --- Main --------------------------------------------------------------------

if __name__ == "__main__":
    # For local debugging only (Render/Gunicorn will import app:app)
    app.run(host="127.0.0.1", port=5000, debug=True)
