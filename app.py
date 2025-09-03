from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

from feedback import generate_feedback 
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from pprint import pformat

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

    # 选择（JSON存快照：[{category,name,points}, ...]）
    step1_json = db.Column(db.Text, default="[]")
    step2_json = db.Column(db.Text, default="[]")
    step1_total = db.Column(db.Float, default=0)
    step2_total = db.Column(db.Float, default=0)
    total_points = db.Column(db.Float, default=0)

    # 交互内容
    chat_history_id = db.Column(db.String(64))  # 前端传回来的 id
    prompt_text = db.Column(db.Text)            # 提示（学生输入）
    prompt_time = db.Column(db.DateTime)
    feedback_text = db.Column(db.Text)  
    feedback_summary = db.Column(db.Text)         
    feedback_time = db.Column(db.DateTime)

    rating = db.Column(db.Integer)              # 1-5
    student_feedback_text = db.Column(db.Text)  # 学生对回复的主观评价

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

# --- Routes: Pages -----------------------------------------------------------

@app.route("/")
def index():
    # Minimal "user" for Jinja: admin => can edit rubrics in UI
    user = {"username": "guest"}  # change to "admin" if you want admin UI
    return render_template("index.html", user=user, leed_table_data=LEED_TABLE_DATA)

# --- Utilities ---------------------------------------------------------------
@app.post("/login")
def login():
    data = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    acc = Account.query.filter_by(username=username).first()
    if not acc or not acc.check_password(password):
        return jsonify({"success": False, "error": "invalid credentials"}), 401
    session["username"] = username
    return jsonify({"success": True})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# --- Routes: Rubrics ---------------------------------------------------------

@app.get("/get_WRITING_RUBRICs")
def get_rubrics():
    rubrics = load_json(RUBRICS_PATH, DEFAULT_WRITING_RUBRIC)
    # Frontend accepts either pure array or {"rubrics": [...]}
    return jsonify(rubrics)


@app.post("/save_WRITING_RUBRICs")
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
    # 1) 基本入参
    msg = request.form.get("message", "").strip()
    leed_scores_json = request.form.get("leed_scores")
    rubrics_text = request.form.get("rubrics", "")
    f = request.files.get("file")

    # 2) 解析前端合并后的 flat 分数（兜底用）
    leed_scores = None
    if leed_scores_json:
        try:
            leed_scores = _json.loads(leed_scores_json)
        except Exception:
            leed_scores = None

    # 3) 取当前用户的草稿，拿到后端保存的 Step1/Step2（就是你要“传过去”的 items+分数）
    user = get_current_user()
    draft = get_or_create_draft(user.id)
    try:
        priority_items = _json.loads(draft.step1_json or "[]")
    except Exception:
        priority_items = []
    try:
        supplement_items = _json.loads(draft.step2_json or "[]")
    except Exception:
        supplement_items = []

    # 调试日志（方便你在终端看）
    app.logger.info(
        "[FEEDBACK] using priority=%d items, supplement=%d items; msg_len=%d; file=%s",
        len(priority_items), len(supplement_items), len(msg), (f.filename if f else None)
    )

    # 4) 若有上传文件，尽量抽文本（可选依赖：pdfminer.six / python-docx）
    uploaded_text = ""
    if f and f.filename:
        fname = f.filename.lower()
        try:
            if fname.endswith(".pdf"):
                try:
                    from pdfminer.high_level import extract_text as _pdf_extract
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
                    # 直接读文件对象在部分环境不行，先落到临时文件
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
                # 其它类型，尝试按文本读
                try:
                    uploaded_text = f.read().decode("utf-8", "ignore")
                except Exception:
                    uploaded_text = ""
        except Exception as e:
            app.logger.warning(f"[FEEDBACK] upload handling failed: {e}")

    # 5) 选用 message 或上传文件的文本（优先用用户输入）
    narrative_text = msg or uploaded_text

    # 6) 调用 feedback 生成（把 step1/step2 明确传进去！）
    feedback_text, scores, feedback_summary = generate_feedback(
        message=narrative_text,
        leed_scores=leed_scores,                  # 兜底：如果没存 step1/2，也能工作
        rubrics_text=rubrics_text,
        uploaded_filename=(f.filename if f else None),
        priority_items=priority_items,            # <<< 关键：传 Step 1
        supplement_items=supplement_items,        # <<< 关键：传 Step 2
    )

    # 7) 仍然保留 last_feedback 的文件写入（可选）
    dump_json(LAST_FEEDBACK_PATH, {"feedback": feedback_text})

    # 8) 入库（一样，保存一次快照）
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
        prompt_time=datetime.utcnow(),
        feedback_text=feedback_text,
        feedback_summary=feedback_summary,
        feedback_time=datetime.utcnow(),
        status="final",
    )
    db.session.add(rec)
    db.session.commit()

    return jsonify({
        "success": True,
        "feedback": feedback_text,
        "feedback_summary": feedback_summary,
        "scores": scores,                 # 维持原有字段，前端可继续用
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



# --- Routes: LEED plan (priority & supplement) -------------------------------

def _load_plan() -> Dict[str, List[Dict[str, Any]]]:
    return load_json(PLAN_PATH, {"priority": [], "supplement": []})


@app.post("/leed/scores")
def leed_scores():
    try:
        body = request.get_json(force=True) or {}

        # === DEBUG: 原始请求体 ===
        app.logger.info("[LEED] /leed/scores raw body:\n%s", pformat(body))

        phase = body.get("phase", "priority")
        if phase not in {"priority", "supplement"}:
            return jsonify({"success": False, "error": "phase must be 'priority' or 'supplement'"}), 400

        scores = body.get("scores") or {}
        if not isinstance(scores, dict):
            return jsonify({"success": False, "error": "scores must be an object/dict"}), 400

        # === DEBUG: 收到的字典键值对数量与前几项预览 ===
        app.logger.info("[LEED] phase=%s received %d score items; sample=%s",
                        phase, len(scores), pformat(list(scores.items())[:5]))

        # 把 scores(dict) 转成 credits 数组（只保留 >0 的分数；Prereq 跳过）
        credits = []
        for sec in LEED_TABLE_DATA:
            for it in sec.get("items", []):
                if is_required(it.get("points")):
                    continue
                name = it.get("name", "")
                val = safe_points(scores.get(name))
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

        # === DEBUG: 过滤后的 credits 与小计 ===
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

        # === DEBUG: 合计 ===
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

    # === DEBUG: 回读统计 ===
    p_sum = sum(safe_points(x.get("points")) for x in priority)
    s_sum = sum(safe_points(x.get("points")) for x in supplement)
    app.logger.info("[LEED] /leed/plan -> step1: %d items, %.1f pts; step2: %d items, %.1f pts; total=%.1f",
                    len(priority), p_sum, len(supplement), s_sum, draft.total_points or 0)

    return jsonify({
        "success": True,
        "priority": priority,
        "supplement": supplement,
        "total_points": round(draft.total_points or 0, 1)
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
    # 简单用 session["username"] 标识当前用户；没有则自动创建 guest
    username = session.get("username") or "guest"
    acc = Account.query.filter_by(username=username).first()
    if not acc:
        acc = Account(username=username, role="student")
        acc.set_password("guest")  # 演示用途
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

# --- Main --------------------------------------------------------------------

if __name__ == "__main__":
    # For local debugging only (Render/Gunicorn will import app:app)
    app.run(host="127.0.0.1", port=5000, debug=True)
