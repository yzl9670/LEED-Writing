# feedback.py

import os
import json
import logging
import openai
from docx import Document
import PyPDF2

logging.basicConfig(level=logging.DEBUG)

# Your OpenAI API Key
openai.api_key = "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"

def get_feedback(user_input=None, file_path=None, rubrics=None, leed_scores=None):
    """
    1) Read the text and determine if it is a LEED Narrative (using only GPT's built-in knowledge)
    2) If yes, perform a two-stage LEED review + LEED scoring provided by GPT
    3) Then use a general writing rubric to provide overall writing feedback
    4) Finally, merge the two parts and output
    """
    # ========== 0. Get Text ==========
    text = ""
    if file_path:
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.docx':
                doc = Document(file_path)
                text = '\n'.join(para.text for para in doc.paragraphs)
            elif ext == '.pdf':
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = ''
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text
            else:
                return "Unsupported file type.", {}, ""
            if not text.strip():
                return "The file is empty.", {}, ""
        except Exception as e:
            logging.exception("Error reading file:")
            return f"Error reading file: {e}", {}, ""
    elif user_input:
        text = user_input.strip()
    else:
        return "No input provided.", {}, ""

    if len(text) < 100:
        return "Your writing is too short to get meaningful feedback. Provide more details.", {}, ""

    # ========== 1. Determine if it is a LEED Narrative ==========
    check_prompt = f"""Determine if the following text is specifically discussing a LEED Narrative for building certification. 
If yes, respond with "LEED Narrative". 
If not, respond "Not LEED Narrative".

Text:
{text}
"""
    try:
        check_resp = openai.ChatCompletion.create(
            model="gpt-o1-mini",
            messages=[
                {"role": "system", "content": "You classify whether text is LEED-related or not."},
                {"role": "user", "content": check_prompt}
            ],
            temperature=0.0
        )
        check_result = check_resp["choices"][0]["message"]["content"].strip().lower()
    except Exception as e:
        logging.exception("Error checking narrative type:")
        return f"Error checking narrative type: {e}", {}, ""

    if "leed narrative" not in check_result:
        return "This passage is not related to LEED Narrative.", {}, ""

    # ========== 2. If it is a LEED Narrative, perform a two-stage LEED review + GPT scoring ==========
    # Phase A: Brief summary & flag suspicious items
    phase_a_prompt = f"""
You are an expert LEED BD+C reviewer. 
We have a LEED project narrative:

{text}

1) Provide a concise summary (2-3 sentences) of whether the claimed credits and prerequisites seem coherent and 
   consistent with LEED v4 BD+C requirements. 
2) List any items or credits that appear suspicious or unclear under "Flagged Items:" 
   (or "Flagged Items: None" if no concerns).
"""

    try:
        phase_a_resp = openai.ChatCompletion.create(
            model="gpt-o1-mini",
            messages=[
                {"role": "system", "content": "Act as an experienced LEED BD+C reviewer."},
                {"role": "user", "content": phase_a_prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )
        phase_1_text = phase_a_resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception("Error in LEED Phase A:")
        phase_1_text = f"Error in LEED Phase A: {e}"

    # Extract flagged items from phase_1_text
    flagged_items = []
    if "flagged items:" in phase_1_text.lower():
        flagged_part = phase_1_text.lower().split("flagged items:")[1].strip()
        lines = flagged_part.split("\n")
        for line in lines:
            line_clean = line.strip("-• ").strip()
            if line_clean and "none" not in line_clean:
                flagged_items.append(line_clean)

    # Phase B: In-depth analysis of flagged items
    phase_2_text = ""
    if flagged_items:
        # If there are many flagged items, process in batches
        chunk_size = 5
        phase_b_responses = []
        for i in range(0, len(flagged_items), chunk_size):
            chunk = flagged_items[i:i+chunk_size]
            chunk_str = "\n".join([f"- {c}" for c in chunk])
            prompt_b = f"""
You are an expert LEED reviewer. The following items were flagged as potentially unclear or suspicious:

{chunk_str}

For each item, explain briefly:
1) Why it might be unclear or not meeting LEED v4 BD+C requirements.
2) How to correct or clarify it to align with LEED.
"""
            try:
                chunk_resp = openai.ChatCompletion.create(
                    model="gpt-3.5-mini",
                    messages=[
                        {"role": "system", "content": "Act as an experienced LEED BD+C reviewer, providing item-level guidance."},
                        {"role": "user", "content": prompt_b}
                    ],
                    temperature=0.7,
                    max_tokens=800
                )
                phase_b_responses.append(chunk_resp["choices"][0]["message"]["content"].strip())
            except Exception as e:
                logging.exception("Error in LEED Phase B:")
                phase_b_responses.append(f"Error in LEED Phase B: {e}")
        phase_2_text = "\n\n".join(phase_b_responses)
    else:
        phase_2_text = "No flagged items, so no second-phase feedback was generated."

    # GPT-based LEED scoring
    leed_score_prompt = f"""
Based on the LEED narrative below, please provide a final LEED-based assessment:
- Estimate if the project would realistically meet LEED BD+C Certification (>=40 points),
- Identify any major prerequisites or credits that might not be properly addressed,

LEED Narrative (excerpt):
{text[:3000]}

If uncertain about some details, disclaim or state assumptions.
"""
    try:
        leed_score_resp = openai.ChatCompletion.create(
            model="gpt-o1-mini",
            messages=[
                {"role": "system", "content": "Provide a final LEED-based rating using your knowledge of LEED v4 BD+C."},
                {"role": "user", "content": leed_score_prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )
        leed_score_text = leed_score_resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception("Error in LEED final scoring:")
        leed_score_text = f"Error in LEED final scoring: {e}"

    # Summarize LEED feedback
    leed_feedback = (
        "=== LEED Phase 1 Summary ===\n"
        f"{phase_1_text}\n\n"
        "=== LEED Phase 2 Detailed Feedback ===\n"
        f"{phase_2_text}\n\n"
        "=== LEED Overall Scoring & Assessment ===\n"
        f"{leed_score_text}"
    )

    # ========== 3. Writing-Level Feedback ==========
    # Use rubrics and leed_scores parameters
    writing_feedback = ""
    scores = {}  # Initialize scores dict

    if rubrics:
        # 1) Convert Rubric into readable prompt
        rubric_text = format_general_rubric(rubrics)

        # 2) Let GPT provide scoring
        writing_prompt = f"""
The following is the student's LEED Narrative text:

{text[:2000]}

Now, please evaluate the writing quality (grammar, clarity, structure, etc.) using this general writing rubric:

{rubric_text}

Return your analysis with a short justification for each rubric dimension (score + explanation).
"""
        try:
            writing_resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a strict writing reviewer."},
                    {"role": "user", "content": writing_prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            writing_feedback = writing_resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logging.exception("Error in writing feedback:")
            writing_feedback = f"Error in writing feedback: {e}"
    else:
        writing_feedback = "(No general writing rubric provided)"

    # Final merge
    final_output = (
        f"--- PART A: LEED Feedback ---\n"
        f"{leed_feedback}\n\n"
        f"--- PART B: Writing Feedback ---\n"
        f"{writing_feedback}"
    )

    # Assuming you need to return 'scores' and 'full_feedback', you need to parse the relevant information here
    # For example, extract the total score from 'leed_score_text'
    # Here simplified to only return 'leed_scores' and 'writing_feedback'
    scores = leed_scores if leed_scores else {}

    return final_output, scores, writing_feedback


def format_general_rubric(rubric_list):
    """
    Convert general_rubric (list[dict]) into readable prompt text
    """
    text = ""
    for r in rubric_list:
        title = r.get("name", "Unknown Dimension")
        sc = r.get("scoringCriteria", [])
        text += f"{title}\n"
        for c in sc:
            pts = c.get("points", 0)
            desc = c.get("description", "")
            text += f"  - {pts} points: {desc}\n"
        text += "\n"
    return text


def map_credits_to_sections(leed_data, student_credits):
    """
    Map the student's claimed credits to the corresponding sections in leed_data.
    """
    item_map = {}
    missing_items = []

    for credit in student_credits:
        found = False
        for rating_system, categories in leed_data.items():
            for category_name, category_data in categories.items():
                for leed_credit in category_data.get("Credits", []):
                    if credit.lower() == leed_credit["name"].lower():
                        item_map.setdefault(section, []).append(leed_credit)
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if not found:
            missing_items.append(credit)

    return item_map, missing_items


def extract_student_credits(text):
    """
    Extract the claimed credits from the student's LEED Narrative.
    You need to implement the extraction logic based on the specific text format.
    The example simply returns a list and can be modified as needed.
    """
    # Example: Assuming credits are listed in a specific section, separated by commas
    # You need to implement extraction logic based on the actual situation
    # For example, use regular expressions to find patterns like "Credits: ..."
    credits = []
    import re
    pattern = r"Credits?:\s*(.*)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    for match in matches:
        # Split credits, assuming separated by commas or newlines
        parts = re.split(r",|\n", match)
        for part in parts:
            credit = part.strip()
            if credit:
                credits.append(credit)
    return credits
