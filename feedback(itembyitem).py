import os
import logging
import openai
from docx import Document
import PyPDF2  # For handling PDF files
import json

from leed_utils import get_leed_data 

# Set up logging
logging.basicConfig(level=logging.DEBUG)

openai.api_key = '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'


# 你可能已经有的所有 LEED Sections，以及每个Section下的可选Items
# 这里做一个示例结构（或你自己已有类似数据）
LEED_SECTIONS = [
    "Location and Transportation",
    "Sustainable Sites",
    "Water Efficiency",
    "Energy and Atmosphere",
    "Materials and Resources",
    "Indoor Environmental Quality",
    "Innovation",
    "Regional Priority"
]


def get_feedback(user_input=None, file_path=None, rubrics=None, leed_scores=None):
    """
    Generates feedback for the user's input or uploaded file based on provided rubrics.
    Returns the feedback text, a dictionary of scores, and the raw feedback text from the AI.
    """

    # 1. 读取文本
    prompt_text = ""
    if file_path:
        try:
            if file_path.endswith('.docx'):
                doc = Document(file_path)
                file_text = '\n'.join([para.text for para in doc.paragraphs])
            elif file_path.endswith('.pdf'):
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    file_text = ''
                    for page in reader.pages:
                        extracted_text = page.extract_text()
                        if extracted_text:
                            file_text += extracted_text
            else:
                return "Unsupported file type.", {}, ""

            if not file_text.strip():
                return "The file is empty.", {}, ""
            prompt_text = file_text
        except Exception as e:
            logging.exception("Error reading file:")
            return f"Error reading file: {e}", {}, ""
    elif user_input:
        prompt_text = user_input
    else:
        return "No input provided.", {}, ""

    if len(prompt_text.strip()) < 100:
        return "Your writing is too short to get meaningful feedback. Could you please provide more details?", {}, ""

    # 2. 判断是否为 LEED Narrative
    content_check_prompt = (
        f"Based on the content of the following text, determine whether it is a LEED Narrative. "
        f"If it is a LEED Narrative, respond 'LEED Narrative'. "
        f"If it is not related to LEED Narrative, respond 'This is not related to LEED Narrative.'.\n\n"
        f"Text:\n{prompt_text}"
    )

    try:
        content_type_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # 或 "gpt-4o-mini"
            messages=[
                {"role": "system", "content": "You are an assistant that classifies text into 'General Writing' or 'LEED Narrative'."},
                {"role": "user", "content": content_check_prompt}
            ],
            temperature=0.0,
        )
        content_type = content_type_response['choices'][0]['message']['content'].strip().lower()
    except Exception as e:
        logging.exception("Error during content type determination:")
        return f"Error during content type determination: {e}", {}, ""

    if "leed narrative" not in content_type:
        return "This passage is not related to LEED Narrative."

    # 3. 如果是 LEED narrative，继续
    content_message = "This passage is identified as part of a LEED Narrative."
    leed_rubric_data = get_leed_data()

    # 4. 计算总分是否通过
    total_score = leed_scores.get('total_score', 0) if leed_scores else 0
    if total_score < 40:
        pass_message = f"Total score is {total_score}. The total score is less than 40 and does not meet the requirement."
    else:
        pass_message = f"Total score is {total_score}. Pass!"

    # 5. 整理 student 的 scored items，并把它们按 Section 归组
    # 假设你对每个 item_name 有个映射，能知道它属于哪个 section。这里演示：简单地用硬编码或一个函数
    # 如果你没有映射，就直接让 GPT 对所有 item 做一段overall反馈即可。

    # 先收集 scored items
    if leed_scores:
        scored_items = {}
        for item_title, val in leed_scores.items():
            if item_title == 'total_score':
                continue
            try:
                numeric_val = float(val)
            except ValueError:
                numeric_val = 0.0
            if numeric_val > 0:
                scored_items[item_title] = numeric_val
    else:
        scored_items = {}

    # 我们演示一个简单的映射: item_name 里带有关键字判断Section (仅示例)
    # 真实项目中，你可能在数据库或JSON里维护 "item -> section" 映射
    def guess_section_by_item_name(item_name):
        # 仅作为demo: 根据几个关键字来“猜”它属于哪个section
        name_lower = item_name.lower()
        if "location" in name_lower or "transport" in name_lower:
            return "Location and Transportation"
        elif "site" in name_lower:
            return "Sustainable Sites"
        elif "water" in name_lower:
            return "Water Efficiency"
        elif "energy" in name_lower or "commissioning" in name_lower or "refrigerant" in name_lower:
            return "Energy and Atmosphere"
        elif "material" in name_lower or "recycle" in name_lower or "demolition" in name_lower:
            return "Materials and Resources"
        elif "air" in name_lower or "iaq" in name_lower or "daylight" in name_lower or "thermal" in name_lower:
            return "Indoor Environmental Quality"
        elif "innovation" in name_lower or "leed ap" in name_lower:
            return "Innovation"
        elif "regional" in name_lower:
            return "Regional Priority"
        else:
            return "Unknown Section"

    # 把 scored items 归类到一个 { section_name: [(item_name, val), ...], ... } 的结构
    sectioned_scored_items = {}
    for section_name in LEED_SECTIONS:
        sectioned_scored_items[section_name] = []

    for item_name, val in scored_items.items():
        s = guess_section_by_item_name(item_name)
        # 如果猜出的section不在8大类里，就统一丢到 'Unknown Section' 或者随意
        if s not in sectioned_scored_items:
            sectioned_scored_items.setdefault("Unknown Section", [])
            sectioned_scored_items["Unknown Section"].append((item_name, val))
        else:
            sectioned_scored_items[s].append((item_name, val))

    # 6. 生成对每个 section 的简短反馈 Prompt
    # 这里我们不会去逐条多行解释，而是告诉 GPT：对本 section 的全部 items 做一个**精简总结**和建议
    # 最后再汇总所有 section 的反馈

    section_feedback_texts = []
    for section_name in LEED_SECTIONS:
        items_in_section = sectioned_scored_items.get(section_name, [])
        if not items_in_section:
            # 学生没在此section claim分数，可选择略过或写个空
            continue

        # 构造一小段描述
        items_text = "\n".join([f"- {item_name}: {val} credits" for item_name, val in items_in_section])

        # 在这里你可以设置一个 Prompt（或把 8 大 section 全部合并到同一个 Prompt 里，让 GPT 按顺序输出 8 段）
        # 为了示例，这里演示：对每个 Section 单独调用 GPT，并且让它**简短**输出
        # 如果你担心一次 API 调用过多，也可以 8 个 Section 全部合并到一个 Prompt 中

        # 要简短：限制最多2-3句话 或 2-3 bullet points
        prompt_for_this_section = f"""
The following is a LEED Narrative excerpt: 
{prompt_text}

The student has claimed the following credits in Section "{section_name}":
{items_text}

Please provide a concise feedback (no more than 3 bullet points) on:
1) Whether the claimed credits in this section seem justified by the text,
2) Brief suggestions for improvement or clarifications needed.

Be very concise. Do not exceed about 100 words total for this section.
"""

        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an experienced LEED reviewer. Provide concise section-level feedback."},
                    {"role": "user", "content": prompt_for_this_section}
                ],
                temperature=0.7
            )
            section_feedback = resp['choices'][0]['message']['content'].strip()
            section_feedback_texts.append(f"=== {section_name} ===\n{section_feedback}")
        except Exception as e:
            logging.exception("Error generating section feedback:")
            section_feedback_texts.append(f"=== {section_name} ===\nError: {e}")

    # 最后把所有 Section 的反馈合并
    combined_section_feedback = "\n\n".join(section_feedback_texts)

    # 7. 生成最后Rubric-Based反馈（可选择保留或删掉）
    # 你原来的做法是：把 item-level feedback 拼到 final_prompt 里，这里简化为只拼 section-level feedback
    final_prompt = f"""
{content_message}

{pass_message}

Below is the section-level feedback obtained for each LEED Section where the student claimed credits:

{combined_section_feedback}

Now, after considering the above feedback, please provide a final summary of the student's LEED Narrative performance based on these LEED Rubrics. 
For each rubric, please follow this format exactly, including all line breaks and spacing for readability:

[Rubric Title]

**Score:** X/Y

- Bullet point feedback.
- Bullet point feedback.
- Bullet point feedback.

Please be succinct but address any major strengths or weaknesses. 
Here are the LEED Rubrics:

{format_leed_rubrics(leed_rubric_data)}

Here is the user's text for evaluation:

{prompt_text}
"""

    try:
        final_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a very strict and experienced writing expert who provides concise feedback."},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.7,
        )
        final_feedback_text = final_response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logging.exception("Error during final feedback generation:")
        return f"Error during final feedback generation: {e}", {}, ""

    logging.debug("Final Feedback Text:\n%s", final_feedback_text)

    # 8. 提取 Rubric Scores
    scores = extract_scores(final_feedback_text, leed_rubric_data)

    # 合并输出
    combined_feedback = (
        f"{content_message}\n\n"
        f"{pass_message}\n\n"
        f"=== Section-by-Section Feedback ===\n\n"
        f"{combined_section_feedback}\n\n"
        f"=== Final Rubric-Based Feedback ===\n\n"
        f"{final_feedback_text}"
    )

    return combined_feedback, scores, final_feedback_text


def format_leed_rubrics(leed_rubric_data):
    rubrics_text = ""
    for rubric in leed_rubric_data:
        rubric_name = rubric.get('name')
        scoring_criteria = rubric.get('scoringCriteria', [])
        total_points = max([crit.get('points', 0) for crit in scoring_criteria])

        rubrics_text += f"{rubric_name} (Total Points: {total_points})\n"
        rubrics_text += "Scoring Criteria:\n"
        for criterion in scoring_criteria:
            points = criterion.get('points')
            description = criterion.get('description')
            rubrics_text += f"  - {points} Points: {description}\n"
        rubrics_text += "\n"
    return rubrics_text


def extract_scores(feedback_text, rubric_data):
    # (保持原逻辑) 用 GPT 再来解析得到 JSON
    if isinstance(rubric_data, list):
        rubrics_list = [rubric.get('name') for rubric in rubric_data]
    else:
        rubrics_list = [rubric.get('title') for rubric in rubric_data]

    rubrics_text = "\n".join(rubrics_list)

    prompt = f"""
The following is feedback text that includes scores for various rubrics:

{feedback_text}

Please extract the scores for each rubric listed below and return them in **valid JSON format**.

Rubrics:
{rubrics_text}

The JSON format should be exactly:
{{
    "LEED Certification Achievement": {{"score": X, "total": Y}},
    "Reflection of Credit Requirements": {{"score": X, "total": Y}},
    "Formatting: Credit Names and Points Claimed": {{"score": X, "total": Y}},
    "Realistic and Detailed Implementation of Credits": {{"score": X, "total": Y}},
    "Grammar, Structure, and Clarity": {{"score": X, "total": Y}}
}}

- Do not alter or reformat the rubric titles.
- Return them EXACTLY as listed above.
- Return ONLY the JSON object and NOTHING else.
- The JSON must start with "{" and end with "}".
- If you cannot provide a valid JSON exactly as above, return an empty JSON object: {{}}.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        json_text = response['choices'][0]['message']['content'].strip()
        if not (json_text.startswith("{") and json_text.endswith("}")):
            logging.error("AI did not return a valid JSON object, or returned extra text.")
            return {}
        scores = json.loads(json_text)
    except Exception as e:
        logging.exception("Error during score extraction:")
        scores = {}

    return scores
