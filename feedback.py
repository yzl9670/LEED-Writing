# feedback.py
from __future__ import annotations
import os, json, re, logging, time
from typing import Dict, List, Tuple, Optional, Any

# Optional imports guarded (we only need openai)
try:
    import openai  # legacy SDK style still supported: openai.ChatCompletion.create
except Exception:
    openai = None

log = logging.getLogger("feedback")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ========================= Config (fast defaults) ============================
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "").strip()
CHAT_MODEL       = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
REQUEST_TIMEOUT  = float(os.getenv("FEEDBACK_LLM_TIMEOUT", "15"))  # seconds per request
MAX_TOKENS       = int(os.getenv("FEEDBACK_MAX_TOKENS", "700"))    # keep it compact
NARRATIVE_CLIP   = int(os.getenv("FEEDBACK_MAX_CHARS", "8000"))    # safety clip for long essays

_client = None
try:
    from openai import OpenAI  # 新 SDK
    if OPENAI_API_KEY:
        _client = OpenAI(api_key=OPENAI_API_KEY)
except Exception:
    _client = None

try:
    import openai as _openai_legacy
    if OPENAI_API_KEY and _client is None:
        _openai_legacy.api_key = OPENAI_API_KEY
except Exception:
    _openai_legacy = None

USE_LLM = bool(_client or (_openai_legacy and OPENAI_API_KEY))
if USE_LLM:
    log.info(f"Feedback LLM enabled: {CHAT_MODEL}")
else:
    log.warning("Feedback LLM disabled (no OPENAI_API_KEY or OpenAI SDK missing).")

# ============================= Public API ===================================
def generate_feedback(
    message: str = "",
    leed_scores: Optional[Dict[str, Any]] = None,   # optional flat dict fallback
    rubrics_text: str = "",                         # ignored here
    uploaded_filename: Optional[str] = None,        # not used
    priority_items: Optional[List[Dict[str, Any]]] = None,
    supplement_items: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any], str]:
    """
    Returns (feedback_text, scores_dict, shortcomings_summary).

    Behavior:
    - Feed the narrative + your PRIORITY and SUPPLEMENT selections directly to gpt-4o-mini.
    - Ask for strict credit-by-credit judgments:
        PRIORITY: does the narrative truly support the claimed points?
        SUPPLEMENT: are the top-ups reasonable to close the gap?
    - Produce a compact shortcomings summary for later progress checks.

    Notes:
    - If priority_items/supplement_items are missing, we try to derive a single
      combined list from `leed_scores` (flat dict) and treat them as PRIORITY.
    - We keep `scores_dict = {}` to avoid breaking your current frontend.
    """
    text = (message or "").strip()

    # Basic guard
    if not text:
        return (
            "No narrative text was provided. Please paste your LEED narrative (or upload a file and paste the key sections).",
            {},
            "No narrative provided; unable to judge credits."
        )

    # Clip very long essays for latency control
    narrative = _truncate(text, NARRATIVE_CLIP)

    # Normalize items
    priority = _normalize_items(priority_items)
    supplement = _normalize_items(supplement_items)

    # If neither list is provided, fall back to flat leed_scores (all as priority)
    if not priority and not supplement and isinstance(leed_scores, dict):
        priority = [
            {"name": k, "points": _safe_points(v)}
            for k, v in leed_scores.items()
            if isinstance(v, (int, float, str)) and _safe_points(v) > 0
        ]

    # If still empty, we can’t evaluate credits meaningfully
    if not priority and not supplement:
        return (
            "I received your narrative but no selected credits/points to evaluate. Save Step 1 and Step 2 first, then generate feedback.",
            {},
            "No credit selections present; cannot compute shortcomings."
        )

    # Build LLM request payload
    payload = {
        "narrative_excerpt": narrative,
        "priority": [{"name": i["name"], "claimed_points": i["points"]} for i in priority],
        "supplement": [{"name": i["name"], "claimed_points": i["points"]} for i in supplement],
        "rules": [
            "Judge only based on content in the narrative excerpt; do not assume facts that are not present.",
            "For PRIORITY, focus on whether evidence supports the claimed points (meet/partial/miss/unclear).",
            "For SUPPLEMENT, judge reasonableness: alignment with shortfall, cost-effectiveness, synergy with priorities.",
            "When 'partial', estimate a realistic max_supported_points number (<= claimed).",
            "Keep rationales <= 30 words; suggestions <= 20 words; be concrete.",
        ],
        "output_schema": {
            "priority": [
                {
                    "name": "string",
                    "claimed_points": "number",
                    "judgement": "one of: meet | partial | miss | unclear",
                    "max_supported_points": "number (0..claimed_points)",
                    "rationale": "string (<= 30 words)",
                    "missing": ["string", "... (specific evidence or requirements missing)"],
                    "suggestion": "string (<= 20 words)"
                }
            ],
            "supplement": [
                {
                    "name": "string",
                    "claimed_points": "number",
                    "judgement": "reasonable | questionable | unclear",
                    "rationale": "string (<= 30 words)",
                    "risk": "string (<= 20 words)",
                    "suggestion": "string (<= 20 words)"
                }
            ],
            "overall": {
                "priority_supported_points": "number",
                "supplement_supported_points": "number",
                "notes": "string (<= 30 words)"
            }
        }
    }

    # Call LLM (single, fast)
    model_json = _ask_llm_for_json(payload)

    if not model_json:
        # Fallback minimal message if LLM is unavailable or parsing failed
        return (
            _fallback_text(priority, supplement),
            {},
            _fallback_summary(priority, supplement)
        )

    # Compose feedback sections
    pri_rows = model_json.get("priority", []) or []
    sup_rows = model_json.get("supplement", []) or []
    overall = model_json.get("overall", {}) or {}

    # Compute totals from model output (guarded)
    pri_supported = _safe_points(overall.get("priority_supported_points"))
    sup_supported = _safe_points(overall.get("supplement_supported_points"))
    # If model didn’t compute, estimate from rows
    if pri_supported == 0 and pri_rows:
        pri_supported = sum(_safe_points(r.get("max_supported_points") if r.get("judgement") in ("meet", "partial")
                                         else 0) for r in pri_rows)
    if sup_supported == 0 and sup_rows:
        # For supplements we count claimed points for "reasonable", 0.5 for "questionable", 0 for "unclear"
        for r in sup_rows:
            jp = str(r.get("judgement", "")).lower()
            cp = _safe_points(r.get("claimed_points"))
            if jp == "reasonable":
                sup_supported += cp
            elif jp == "questionable":
                sup_supported += max(0.0, 0.5 * cp)

    # Compose human-readable feedback
    header = _render_header(pri_supported, sup_supported)
    pri_block = _render_priority_block(pri_rows) if pri_rows else "No priority credits to evaluate."
    sup_block = _render_supplement_block(sup_rows) if sup_rows else "No top-up credits to evaluate."
    actions = _render_next_actions(pri_rows, sup_rows)

    feedback_text = "\n".join([header, pri_block, sup_block, actions]).strip()
    shortcomings_summary = _shortcomings_summary(pri_rows, target_points=40.0,
                                                 supported_points=(pri_supported + sup_supported))

    return feedback_text, {}, shortcomings_summary


# =========================== LLM plumbing ===================================
def _ask_llm_for_json(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not USE_LLM:
        return None

    system = (
        "You are a LEED BD+C reviewer. Output ONLY valid minified JSON matching the provided schema. "
        "No prose, no markdown, no explanations outside JSON."
    )
    user = "Evaluate the LEED narrative vs selected credits. Respect the rules and schema.\n\n" + \
           json.dumps(payload, ensure_ascii=False)

    try:

        if _client is not None:
            resp = _client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.2,
                max_tokens=MAX_TOKENS,
            )
            text = resp.choices[0].message.content.strip()
            return _extract_json(text)


        if _openai_legacy is not None and hasattr(_openai_legacy, "ChatCompletion"):
            resp = _openai_legacy.ChatCompletion.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=0.2,
                max_tokens=MAX_TOKENS,
                timeout=REQUEST_TIMEOUT,
            )
            text = resp["choices"][0]["message"]["content"].strip()
            return _extract_json(text)

        return None

    except Exception as e:
        log.warning(f"LLM call failed: {e}")
        return None



def _extract_json(s: str) -> Optional[Dict[str, Any]]:
    # Try direct parse
    try:
        return json.loads(s)
    except Exception:
        pass
    # Greedy bracket capture
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        frag = s[start:end + 1]
        try:
            return json.loads(frag)
        except Exception:
            return None
    return None


# ========================== Renderers / Helpers ==============================
def _render_header(pri_supported: float, sup_supported: float) -> str:
    total = pri_supported + sup_supported
    status = "✅ On track for 40+" if total >= 40.0 else "⚠️ Below 40 — add credible points"
    return (
        f"**LEED Check Summary**\n"
        f"- Supported Priority: {pri_supported:.1f} pts\n"
        f"- Supported Top-ups: {sup_supported:.1f} pts\n"
        f"- **Total Supported:** {total:.1f} pts → {status}\n"
    )

def _render_priority_block(rows: List[Dict[str, Any]]) -> str:
    out = ["\n**Priority Credits — evidence vs. claimed**"]
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
            f"  - Why: {rationale}\n"
        )
        if missing:
            out.append(f"  - Missing: " + "; ".join(_trim(m, 80) for m in missing))
        if suggestion:
            out.append(f"  - Next: {suggestion}")
    return "\n".join(out)

def _render_supplement_block(rows: List[Dict[str, Any]]) -> str:
    out = ["\n**Top-up Credits — reasonableness check**"]
    for r in rows:
        name = r.get("name", "")
        claim = _safe_points(r.get("claimed_points"))
        judge = str(r.get("judgement", "")).lower()
        rationale = _trim(r.get("rationale", ""), 180)
        risk = _trim(r.get("risk", ""), 80)
        suggestion = _trim(r.get("suggestion", ""), 100)

        icon = {"reasonable": "✅", "questionable": "🟠", "unclear": "❓"}.get(judge, "•")
        out.append(
            f"- {icon} **{name}** — {claim:g} pts\n"
            f"  - Why: {rationale}\n"
        )
        if risk:
            out.append(f"  - Risk: {risk}")
        if suggestion:
            out.append(f"  - Next: {suggestion}")
    return "\n".join(out)

def _render_next_actions(pri_rows: List[Dict[str, Any]], sup_rows: List[Dict[str, Any]]) -> str:
    # Pull top 3 actionable next steps across both lists
    actions: List[str] = []
    for r in pri_rows:
        if len(actions) >= 3: break
        s = str(r.get("suggestion") or "").strip()
        if s: actions.append(s)
    for r in sup_rows:
        if len(actions) >= 3: break
        s = str(r.get("suggestion") or "").strip()
        if s: actions.append(s)
    if not actions:
        return "\n**Next Steps**\n- Tighten evidence for undersupported credits; ensure baselines, calculations, and required documents are clearly cited."
    return "\n**Next Steps**\n" + "\n".join(f"- {a}" for a in actions)

def _shortcomings_summary(pri_rows: List[Dict[str, Any]], target_points: float, supported_points: float) -> str:
    """Compact list of specific missing pieces for progress tracking."""
    misses: List[str] = []
    for r in pri_rows:
        judge = str(r.get("judgement", "")).lower()
        if judge in ("miss", "partial", "unclear"):
            name = r.get("name", "")
            missing = [m for m in (r.get("missing") or []) if isinstance(m, str)]
            if missing:
                misses.append(f"{name}: " + "; ".join(_trim(m, 50) for m in missing[:2]))
            else:
                misses.append(f"{name}: evidence not shown or unclear.")
        if len(misses) >= 6:  # keep short
            break
    gap = max(0.0, target_points - supported_points)
    gap_txt = f"Gap to 40: {gap:.1f} pts." if gap > 0 else "No gap to 40."
    return (("; ".join(misses) + " | " if misses else "") + gap_txt).strip()

# =============================== Utilities ==================================
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
    return s[:max_chars-1] + "…"

def _trim(s: str, max_len: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= max_len else (s[:max_len-1] + "…")

def _safe_points(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0

# ----------------------------- Fallbacks ------------------------------------
def _fallback_text(priority: List[Dict[str, Any]], supplement: List[Dict[str, Any]]) -> str:
    pri_total = sum(_safe_points(i.get("points")) for i in priority)
    sup_total = sum(_safe_points(i.get("points")) for i in supplement)
    total = pri_total + sup_total
    status = "on track for 40+" if total >= 40 else "below 40"
    return (
        "**LEED Check (degraded mode)**\n"
        "- Could not contact the model; returning a minimal summary.\n\n"
        f"Priority claimed: {pri_total:.1f} pts; Top-ups claimed: {sup_total:.1f} pts; Total: {total:.1f} ({status}).\n"
        "Please retry to get item-by-item judgments and targeted suggestions."
    )

def _fallback_summary(priority: List[Dict[str, Any]], supplement: List[Dict[str, Any]]) -> str:
    total = sum(_safe_points(i.get("points")) for i in (priority + supplement))
    gap = max(0.0, 40.0 - total)
    return f"No detailed shortcomings (model offline). Claimed total {total:.1f}. Gap to 40: {gap:.1f} pts."
