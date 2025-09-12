
# feedback.py
from __future__ import annotations
import os, json, re, logging
from typing import Dict, List, Tuple, Optional, Any

USE_LLM = True
# ========================= Logging =========================
log = logging.getLogger("feedback")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ========================= Config ==========================
OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY", "").strip()
CHAT_MODEL            = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
REQUEST_TIMEOUT       = float(os.getenv("FEEDBACK_LLM_TIMEOUT", "60"))
MAX_TOKENS            = int(os.getenv("FEEDBACK_MAX_TOKENS", "900"))
NARRATIVE_CLIP        = int(os.getenv("FEEDBACK_MAX_CHARS", "8000"))

# Default rubric path: ./data/rubrics.json  (can be overridden by env)
_DEFAULT_DATA_DIR     = os.path.join(os.path.dirname(__file__), "data")
WRITING_RUBRICS_PATH  = os.getenv("WRITING_RUBRICS_PATH",
                                  os.path.join(_DEFAULT_DATA_DIR, "rubrics.json"))

# OpenAI clients (new SDK first, fallback to legacy)
_client_new = None
_client_legacy = None
try:
    from openai import OpenAI as _OpenAI
    if OPENAI_API_KEY:
        _client_new = _OpenAI(api_key=OPENAI_API_KEY)
except Exception:
    _client_new = None

try:
    import openai as _openai_legacy
    if OPENAI_API_KEY and _client_new is None:
        _openai_legacy.api_key = OPENAI_API_KEY
        _client_legacy = _openai_legacy
except Exception:
    _client_legacy = None

USE_LLM = bool((_client_new or _client_legacy) and OPENAI_API_KEY)
if USE_LLM:
    log.info(f"Feedback LLM enabled: {CHAT_MODEL}")
else:
    log.warning("Feedback LLM disabled (no OPENAI_API_KEY or OpenAI SDK missing).")

# ===========================================================
#                       PUBLIC API
# ===========================================================
def generate_feedback(
        
    message: str = "",
    leed_scores: Optional[Dict[str, Any]] = None,      
    rubrics_text: str = "",                             
    uploaded_filename: Optional[str] = None,            
    priority_items: Optional[List[Dict[str, Any]]] = None,   
    supplement_items: Optional[List[Dict[str, Any]]] = None, 
    prev_shortcomings: Optional[str] = None,                 
    writing_rubrics_path: Optional[str] = None               
) -> Tuple[str, Dict[str, Any], str]:

    # ---------- local helpers ----------
    def _render_header_claimed(claimed: float, degraded: bool = False) -> str:
        title = "**LEED Check Summary**" if not degraded else "**LEED Check (degraded mode)**"
        badge = "✅ On track for 40+" if claimed >= 40 else "⚠️ Below 40 — add credible points"
        return "\n".join([
            title,
            f"- **Total Claimed:** {claimed:.1f} pts → {badge}",
            ""
        ])

    def _sum_claimed(items: List[Dict[str, Any]]) -> float:
        total = 0.0
        for it in items or []:
            total += _safe_points(it.get("points") or it.get("claimed_points"))
        return round(total, 1)

    def _render_credit_block(rows: List[Dict[str, Any]]) -> str:
        out = ["\n**Credits — evidence vs. claimed**"]
        for r in rows:
            name = r.get("name", "")
            claim = _safe_points(r.get("claimed_points"))
            judge = str(r.get("judgement", "")).lower()
            maxpt = _safe_points(r.get("max_supported_points"))
            rationale = _trim(r.get("rationale", ""), 180)
            missing = [m for m in (r.get("missing") or []) if isinstance(m, str)][:3]
            suggestion = _trim(r.get("suggestion", ""), 100)

            icon = {"meet": "✅", "partial": "🟠", "miss": "❌", "unclear": "❓"}.get(judge, "•")
            out.append(
                f"- {icon} **{name}** — claimed {claim:g} pts; supported ≈ {maxpt:.1f} pts\n"
                f"  - Scoring Reason: {rationale}\n"
            )
            if missing:
                out.append(f"  - Missing: " + "; ".join(_trim(m, 80) for m in missing))
            if suggestion and suggestion.lower() != "none.":
                out.append(f"  - Next: {suggestion}")
        return "\n".join(out)

    def _render_credit_claims_only(credits: List[Dict[str, Any]]) -> str:
        out = ["\n**Credits — claims only (model offline)**"]
        for it in credits:
            name = it.get("name", "")
            pts = _safe_points(it.get("points"))
            out.append(f"- • **{name}** — claimed {pts:g} pts")
        return "\n".join(out)

    def _render_writing_block(writing_rows: List[Dict[str, Any]], rubrics: List[Dict[str, Any]]) -> str:
        if not writing_rows:
            max_total = sum(_safe_points(r.get("max_points") or r.get("total")) for r in (rubrics or []))
            return f"**Writing Feedback**\n- (No model scores returned.) Max total = {max_total:.0f}."
        out = ["**Writing Feedback**"]
        total_scored = 0.0
        total_max = 0.0
        for r in writing_rows:
            name = r.get("name", "")
            sc = _safe_points(r.get("score"))
            tot = _safe_points(r.get("total"))
            total_scored += sc
            total_max += tot
            rationale = _trim(r.get("rationale", ""), 180)
            suggestion = _trim(r.get("suggestion", ""), 100)
            out.append(f"- **{name}**: {sc:g}/{tot:g}")
            if suggestion and suggestion.lower() != "none.":
                out.append(f"  - Next: {suggestion}")
        out.insert(1, f"_Total: {total_scored:.1f}/{total_max:.0f}_")
        return "\n".join(out)

    def _build_writing_scores_dict(writing_rows: List[Dict[str, Any]], rubrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if writing_rows:
            for r in writing_rows:
                name = str(r.get("name") or "").strip()
                if not name:
                    continue
                d[name] = {
                    "score": _safe_points(r.get("score")),
                    "total": _safe_points(r.get("total"))
                }
        else:
            for r in rubrics or []:
                name = str(r.get("name") or "").strip()
                if not name:
                    continue
                mx = _safe_points(r.get("max_points") or r.get("total"))
                d[name] = {"score": 0.0, "total": mx}
        return d

    def _progress_note(prev_short: Optional[str], new_short: str) -> str:
        try:
            def _gap(txt: str) -> float:
                m = re.search(r"Gap to 40:\s*([0-9]+(?:\.[0-9])?)", txt or "", flags=re.I)
                return float(m.group(1)) if m else 0.0
            if not prev_short:
                return ""
            old_gap, new_gap = _gap(prev_short), _gap(new_short)
            if new_gap < old_gap:
                return f"Nice! Gap dropped from {old_gap:.1f} → {new_gap:.1f} pts."

            old_miss = len(re.findall(r":", prev_short))
            new_miss = len(re.findall(r":", new_short))
            if new_miss < old_miss:
                return "Good progress — fewer missing evidence items than last time."
            return ""
        except Exception:
            return ""

    def _load_writing_rubrics(path: Optional[str]) -> List[Dict[str, Any]]:
        p = path or os.path.join("data", "rubrics.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            return []
        arr = obj if isinstance(obj, list) else obj.get("rubrics") if isinstance(obj, dict) else []
        out: List[Dict[str, Any]] = []
        for x in arr or []:
            name = str(x.get("name") or "").strip()
            if not name:
                continue
            mx = _safe_points(x.get("max_points") or x.get("total"))
            if mx <= 0 and isinstance(x.get("scoringCriteria"), list):
                # {scoringCriteria:[{points, description}, ...]}
                mx = max([_safe_points(it.get("points")) for it in x["scoringCriteria"]] or [0])
            out.append({"name": name, "max_points": mx})
        return out

    # ----------  ----------
    text = (message or "").strip()
    if not text:
        return (
            "No narrative text was provided. Please paste your LEED narrative (or upload a file and paste the key sections).",
            {},
            "No narrative provided; unable to judge credits."
        )

    narrative = _truncate(text, NARRATIVE_CLIP)

    credits: List[Dict[str, Any]] = []
    credits += _normalize_items(priority_items)
    credits += _normalize_items(supplement_items)
    credits = _dedup_by_name_max(credits)

    if not credits and isinstance(leed_scores, dict):
        credits = [
            {"name": k, "points": _safe_points(v)}
            for k, v in leed_scores.items()
            if isinstance(v, (int, float, str)) and _safe_points(v) > 0
        ]

    if not credits:
        return (
            "I received your narrative but no selected credits/points to evaluate. Save the form first, then generate feedback.",
            {},
            "No credit selections present; cannot compute shortcomings."
        )

    writing_rubrics = _load_writing_rubrics(writing_rubrics_path)
 
    payload = {
        "narrative_excerpt": narrative,  # full text (truncated by NARRATIVE_CLIP)
        "credits": [{"name": it["name"], "claimed_points": it["points"]} for it in credits],
        "writing_rubrics": [{"name": r["name"], "max_points": r["max_points"]} for r in writing_rubrics],
        "rules": [
            # Holistic read & grounding
            "First, skim the entire narrative to form a coherent mental model of the project.",
            "Judge based on the narrative content only; never assume facts not present.",
            "Do NOT keyword-spot or grant points for mere mentions of terms/credit names.",
            # Credit scoring
            "For CREDITS, label judgement as meet | partial | miss | unclear.",
            "If 'meet' or 'partial', include 1–2 verbatim evidence quotes (<=18 words each) that support the score.",
            "If you cannot find an adequate quote, set judgement to 'unclear' or 'miss' and list what’s missing.",
            "When 'partial', estimate a realistic max_supported_points (<= claimed).",
            # Writing scoring (holistic)
            "For WRITING, score each rubric (0..max) based on global qualities (organization, coherence, specificity, consistency), not term counts.",
            "Penalize bullet lists or shopping-lists without methods, baselines, calculations, or credible implementation details.",
            # Brevity
            "Rationales <= 25 words; suggestions <= 16 words; be concrete.",
        ],
        "output_schema": {
            "credits": [
                {
                    "name": "string",
                    "claimed_points": "number",
                    "judgement": "one of: meet | partial | miss | unclear",
                    "max_supported_points": "number (0..claimed_points)",
                    "rationale": "string (<= 25 words)",
                    "missing": ["string"],
                    "suggestion": "string (<= 16 words)",
                    "evidence_quotes": ["string (1–2 quotes, each <= 18 words)"]
                }
            ],
            "writing": [
                {
                    "name": "string",
                    "score": "number (0..max for this rubric)",
                    "total": "number (the rubric max)",
                    "rationale": "string (<= 25 words)",
                    "suggestion": "string (<= 16 words)",
                    "evidence_quotes": ["string (0–2 quotes from narrative)"]
                }
            ],
            "overall": {
                "supported_points": "number",
                "notes": "string (<= 25 words)"
            }
        }
    }

    try:
        model_json = _ask_llm_for_json(payload)
    except Exception as e:
        return (f"**LEED Check (degraded mode)**\n- Error: {e}\n"
                "Falling back to claims-only.\n\n" + _render_credit_claims_only(credits),
                _build_writing_scores_dict([], writing_rubrics),
                "Model error; shortcomings unavailable.")


    if not model_json:
        claimed_total = _sum_claimed(credits)
        header = (
            f"**LEED Check (degraded mode)**\n"
            f"- Claimed Credits: {claimed_total:.1f} pts\n"
            f"- **Model offline** — item-by-item judging and writing rubric were not run.\n"
        )
        feedback_text = "\n".join([
            header,
            _render_credit_claims_only(credits),
            "**Next Steps**\n- Tighten evidence for each claimed credit; cite baselines, calcs, and required docs."
        ]).strip()
        gap = max(0.0, 40.0 - claimed_total)
        shortcomings = f"Model offline; no item-by-item judgments. Claimed total {claimed_total:.1f}. Gap to 40: {gap:.1f} pts."
        scores_dict = _build_writing_scores_dict([], writing_rubrics)  # 右栏 0/满分
        return feedback_text, scores_dict, shortcomings

    rows: List[Dict[str, Any]] = (
        model_json.get("credits", [])
        or model_json.get("priority", [])
        or model_json.get("items", [])
        or []
    )
    writing_rows: List[Dict[str, Any]] = model_json.get("writing", []) or []
    overall = model_json.get("overall", {}) or {}
    supported = _safe_points(
        overall.get("supported_points")
        or overall.get("priority_supported_points")  
        or 0
    )
    if supported <= 0 and rows:
        tot = 0.0
        for r in rows:
            j = str(r.get("judgement", "")).lower()
            cp = _safe_points(r.get("claimed_points"))
            if j == "meet":
                msp = _safe_points(r.get("max_supported_points")) or cp
                tot += max(0.0, min(msp, cp))
            elif j == "partial":
                msp = _safe_points(r.get("max_supported_points"))
                if msp <= 0 and cp > 0:
                    msp = max(0.0, min(cp, round(0.5 * cp, 1)))
                tot += max(0.0, min(msp, cp))
        supported = round(tot, 1)

    claimed_total = _sum_claimed(credits)
    header = _render_header_claimed(claimed_total, degraded=False)
    credit_block = _render_credit_block(rows) if rows else "No credits to evaluate."
    writing_block = _render_writing_block(writing_rows, writing_rubrics)

    # Next suggestion: Extract 3 suggestions from the credits list (filter "None." and remove duplicates)
    suggs: List[str] = []
    for r in rows:
        s = str(r.get("suggestion") or "").strip()
        if not s or s.lower() == "none.":
            continue
        if s not in suggs:
            suggs.append(s)
        if len(suggs) >= 3:
            break
    actions = "\n**Next Steps**\n" + "\n".join(f"- {s}" for s in suggs) if suggs else \
              "\n**Next Steps**\n- Tighten evidence for undersupported credits; ensure baselines, calculations, and required documents are clearly cited."

    # Summary of Shortcomings (including Gap to 40)
    shortcomings = _shortcomings_summary(rows, target_points=40.0, supported_points=supported)

    # Progress Tips
    progress_note = _progress_note(prev_shortcomings, shortcomings)
    progress_block = f"\n**Progress Note**\n- {progress_note}" if progress_note else ""

    TIP_MSG = "\n**Tip**\n- If your new writing changes which credits you are targeting, please re-submit the **LEED Certification form** so your selections stay in sync."

    feedback_text = "\n".join([p for p in [header, writing_block, credit_block, actions, progress_block] if p]).strip()
    feedback_text += TIP_MSG
    # Rubrics score structure on the right side of the front
    scores_dict = _build_writing_scores_dict(writing_rows, writing_rubrics)

    return feedback_text, scores_dict, shortcomings

# ===========================================================
#                     LLM plumbing
# ===========================================================
def _ask_llm_for_json(payload: dict) -> dict | None:
    import os, json, re
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY") or ""
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)

    sys_msg = (
        "You are a rigorous LEED reviewer.\n"
        "READ THE ENTIRE NARRATIVE ONCE BEFORE SCORING.\n"
        "Base all judgments on an integrated understanding of the narrative, not on keywords or term frequency.\n"
        "Award points ONLY when the narrative explicitly provides sufficient evidence; do not infer unstated details.\n"
        "For each scored item, include 1–2 short, verbatim evidence quotes from the narrative.\n"
        "If no adequate quote exists, mark the item as 'unclear' or 'miss'.\n"
        "Reply ONLY with a single JSON object that matches the caller's output_schema. No extra text."
    )
    user_msg = json.dumps(payload, ensure_ascii=False)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}\s*$", text, flags=re.S)
        text = m.group(0) if m else text
        return json.loads(text)
    except Exception as e:
        try:
            from flask import current_app as app
            app.logger.warning("Model failed: %s", e)
        except Exception:
            pass
        return None

def _strip_md_fences(s: str) -> str:
    s = (s or "").strip()
    # ```json\n ... \n```
    m = re.match(r"^```(?:json)?\s*\n(.*)\n```$", s, re.S)
    return m.group(1).strip() if m else s

def _extract_json(s: str) -> Optional[Dict[str, Any]]:
    s = _strip_md_fences(s)

    try:
        return json.loads(s)
    except Exception:
        pass

    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(s[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                frag = s[start:i+1]
                try:
                    return json.loads(frag)
                except Exception:
                    break
    return None


# ===========================================================
#                   Renderers / Builders
# ===========================================================
def _render_header_single(supported: float) -> str:
    status = "✅ On track for 40+" if supported >= 40.0 else "⚠️ Below 40 — add credible points"
    return (
        f"**LEED Check Summary**\n"
        f"- Supported Credits: {supported:.1f} pts\n"
        f"- **Total Supported:** {supported:.1f} pts → {status}\n"
    )

def _render_credit_block(rows: List[Dict[str, Any]]) -> str:
    out = ["\n**Credits — evidence vs. claimed**"]
    for r in rows:
        name = r.get("name", "")
        claim = _safe_points(r.get("claimed_points"))
        judge = str(r.get("judgement", "")).lower()
        maxpt = _safe_points(r.get("max_supported_points"))
        rationale = _trim(r.get("rationale", ""), 180)
        missing = [m for m in (r.get("missing") or []) if isinstance(m, str)][:3]
        suggestion = _trim(r.get("suggestion", ""), 100)

        icon = {"meet": "✅", "partial": "🟠", "miss": "❌", "unclear": "❓"}.get(judge, "•")
        out.append(
            f"- {icon} **{name}** — claimed {claim:g} pts; supported ≈ {maxpt:.1f} pts\n"
            f"  - Scoring Reason: {rationale}"
        )

        quotes = [q for q in (r.get("evidence_quotes") or []) if isinstance(q, str)][:2]
        if quotes:
            out.append("  - Evidence: " + " | ".join(f"“{_trim(q, 120)}”" for q in quotes))

        if missing:
            out.append("  - Missing: " + "; ".join(_trim(m, 80) for m in missing))
        if suggestion:
            out.append(f"  - Next: {suggestion}")
    return "\n".join(out)

def _render_credit_claims_only(credits: List[Dict[str, Any]]) -> str:
    out = ["\n**Credits (claims only)**"]
    for it in credits:
        out.append(f"- {it.get('name','')}: { _safe_points(it.get('points')):g} pts (claimed)")
    return "\n".join(out)

def _render_writing_block(writing_rows: List[Dict[str, Any]], rubrics: List[Dict[str, Any]]) -> str:
    if not writing_rows:
        total_max = sum(float(r.get("max_points", 0)) for r in rubrics)
        return f"**Writing Feedback**\n- (No model scores returned.) Max total = {total_max:g}."

    earned, max_total = 0.0, 0.0
    lines = ["**Writing Feedback**"]
    idx_by_name = {r["name"]: r for r in rubrics}
    for w in writing_rows:
        name = w.get("name", "")
        s = _safe_points(w.get("score"))
        t = _safe_points(w.get("total") or (idx_by_name.get(name, {}).get("max_points", 0)))
        earned += s
        max_total += t
        rationale = _trim(w.get("rationale", ""), 180)
        suggestion = _trim(w.get("suggestion", ""), 100)
        lines.append(f"- **{name}**: {s:.1f}/{t:.1f}")

        quotes = [q for q in (w.get("evidence_quotes") or []) if isinstance(q, str)][:2]
        if quotes:
            lines.append("  - Evidence: " + " | ".join(f"“{_trim(q, 120)}”" for q in quotes))

        if rationale:
            lines.append(f"  - Why: {rationale}")
        if suggestion:
            lines.append(f"  - Next: {suggestion}")

    if max_total <= 0:
        max_total = sum(float(r.get("max_points", 0)) for r in rubrics)
    lines.insert(1, f"- **Total Writing**: {earned:.1f}/{max_total:.1f}")
    return "\n".join(lines)

def _render_next_actions(pri_rows: List[Dict[str, Any]], sup_rows: List[Dict[str, Any]]) -> str:
    seen = set()
    actions: List[str] = []

    def push(s: str):
        s = (s or "").strip()
        if not s:
            return
        sl = s.lower().strip().strip(".")
        if sl in ("none", "n/a", "no action", "no changes", "-"):
            return
        if sl in seen:
            return
        seen.add(sl)
        actions.append(s.rstrip("."))  

    for r in pri_rows:
        if len(actions) >= 3: break
        push(str(r.get("suggestion") or ""))

    for r in sup_rows:
        if len(actions) >= 3: break
        push(str(r.get("suggestion") or ""))

    if not actions:
        return "\n**Next Steps**\n- Tighten evidence for undersupported credits; ensure baselines, calculations, and required documents are clearly cited."
    return "\n**Next Steps**\n" + "\n".join(f"- {a}." for a in actions)


def _build_writing_scores_dict(
    writing_rows: List[Dict[str, Any]],
    rubrics: List[Dict[str, Any]]
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    max_by_name = {r["name"]: float(r.get("max_points", 0)) for r in rubrics}
    for w in writing_rows:
        name = w.get("name", "")
        if not name:
            continue
        score = _safe_points(w.get("score"))
        total = _safe_points(w.get("total") or max_by_name.get(name, 0))
        out[name] = {"score": score, "total": total}
    return out

def _shortcomings_summary(rows: List[Dict[str, Any]], target_points: float, supported_points: float) -> str:
    items: List[str] = []
    for r in rows:
        judge = str(r.get("judgement", "")).lower()
        if judge in ("miss", "partial", "unclear"):
            name = r.get("name", "")
            missing = [m for m in (r.get("missing") or []) if isinstance(m, str)]
            if missing:
                items.append(f"{name}: " + "; ".join(_trim(m, 50) for m in missing[:2]))
            else:
                items.append(f"{name}: evidence not shown or unclear.")
        if len(items) >= 6:
            break
    gap = max(0.0, target_points - supported_points)
    gap_txt = f"Gap to 40: {gap:.1f} pts." if gap > 0 else "No gap to 40."
    return (("; ".join(items) + " | " if items else "") + gap_txt).strip()

# --------------------------- Progress note -----------------------------------
_gap_re = re.compile(r"Gap to 40:\s*([0-9]+(?:\.[0-9]+)?)\s*pts\.", re.IGNORECASE)

def _parse_gap_from_summary(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = _gap_re.search(s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def _progress_note(prev_shortcomings: Optional[str], new_shortcomings: Optional[str]) -> Optional[str]:
    g_prev = _parse_gap_from_summary(prev_shortcomings)
    g_new  = _parse_gap_from_summary(new_shortcomings)
    if g_new is None:
        return None
    if g_prev is None:
        return None

    delta = g_prev - g_new
    if delta >= 1.0:
        return f"Nice progress! Gap reduced {delta:.1f} pts (from {g_prev:.1f} to {g_new:.1f}). Keep going."
    elif delta > 0:
        return f"Small improvement: gap {g_prev:.1f} → {g_new:.1f}. A bit more evidence could close it."
    elif delta < 0:
        return f"Gap increased: {g_prev:.1f} → {g_new:.1f}. Re-check weakest credits and shore up documentation."
    return "Gap unchanged. Strengthen evidence on partial/miss credits for a meaningful boost."

# ===========================================================
#                       Utilities
# ===========================================================
def _load_writing_rubrics(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return _normalize_rubric_list(data)
        if isinstance(data, dict) and isinstance(data.get("rubrics"), list):
            return _normalize_rubric_list(data["rubrics"])
    except Exception as e:
        log.warning(f"Failed to load rubrics from {path}: {e}")

    fallback = [
        {"name": "LEED Certification Achievement", "max_points": 3},
        {"name": "Reflection of Credit Requirements", "max_points": 4},
        {"name": "Formatting: Credit Names and Points Claimed", "max_points": 3},
        {"name": "Realistic and Detailed Implementation of Credits", "max_points": 3},
        {"name": "Grammar, Structure, and Clarity", "max_points": 2},
    ]
    return _normalize_rubric_list(fallback)

def _normalize_rubric_list(arr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in arr or []:
        name = str(it.get("name", "")).strip()
        mp = it.get("max_points", it.get("total", it.get("max", 0)))
        try:
            mp = float(mp)
        except Exception:
            mp = 0.0
        if name and mp > 0:
            out.append({"name": name, "max_points": mp})
    return out

def _sum_claimed(credits: List[Dict[str, Any]]) -> float:
    s = 0.0
    for it in credits:
        s += _safe_points(it.get("points"))
    return s

def _normalize_items(items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not items:
        return out
    for it in items:
        name = (it.get("name") or "").strip()
        pts = _safe_points(it.get("points"))
        if name and pts > 0:
            out.append({"name": name, "points": pts})
    return out

def _truncate(s: str, max_chars: int) -> str:
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 1] + "…"

def _trim(s: Any, max_len: int) -> str:
    s = (str(s or "")).strip().replace("\n", " ")
    return s if len(s) <= max_len else (s[:max_len - 1] + "…")

def _safe_points(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0

def _dedup_by_name_max(items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    acc: Dict[str, Dict[str, Any]] = {}
    for it in items or []:
        name = (it.get("name") or "").strip()
        pts = _safe_points(it.get("points"))
        if not name or pts <= 0:
            continue
        keep = acc.get(name)
        if (keep is None) or (pts > _safe_points(keep.get("points"))):
            acc[name] = {"name": name, "points": pts}
    return list(acc.values())


# ===========================================================
#                       Fallbacks
# ===========================================================
def _fallback_text_single(credits: List[Dict[str, Any]]) -> str:
    total_claim = _sum_claimed(credits)
    status = "on track for 40+" if total_claim >= 40 else "below 40"
    return (
        "**LEED Check (degraded mode)**\n"
        "- Could not contact the model; returning a minimal summary.\n\n"
        f"Claimed total: {total_claim:.1f} pts ({status}).\n"
        "Please retry to get item-by-item judgments and targeted suggestions."
    )

def _fallback_summary_single(credits: List[Dict[str, Any]]) -> str:
    total_claim = _sum_claimed(credits)
    gap = max(0.0, 40.0 - total_claim)
    return f"No detailed shortcomings (model offline). Claimed total {total_claim:.1f}. Gap to 40: {gap:.1f} pts."
