import os
import re
import json
import logging
from groq import Groq
from docx import Document
import PyPDF2  # 用于处理 PDF 文件

# 设置日志记录
logging.basicConfig(level=logging.DEBUG)

# API key
os.environ['GROQ_API_KEY'] = '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'  # 请确保您的 API 密钥是正确的

client = Groq()

def get_feedback(user_input=None, file_path=None, rubrics=None):
    # Step 1: 获取文件内容或用户输入的文本
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
                        file_text += page.extract_text()
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

    if not rubrics:
        return "No rubrics provided.", {}, ""

    # Step 2: 识别文档类型（General Writing 或 LEED Narrative）
    content_check_prompt = (
        f"Based on the content of the following text, determine if this is General Writing or a LEED Narrative. "
        f"Text:\n{prompt_text}"
    )

    content_type_response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are an experienced writing expert in the engineering field who can provide personalized feedback for students."},
            {"role": "user", "content": content_check_prompt}
        ]
    )
    content_type = content_type_response.choices[0].message.content.lower()

    # Step 3: 根据文档类型生成反馈提示（Prompt）
    if "leed narrative" in content_type:
        content_message = "This passage is identified as part of a LEED Narrative."
        # 如果是 LEED Narrative，使用 LEED Rubric 提供反馈
        feedback_prompt = (
            f"{content_message}\n\n"
            f"Please provide detailed feedback based on the following LEED Rubric. For each rubric, include up to three bullet points with your feedback under that category.\n\n"
            f"Rubrics:\n{rubrics}\n\nUser Text:\n{prompt_text}"
        )
    else:
        content_message = "This passage is identified as General Writing."
        # 对于普通写作，使用通用 Rubric 提供反馈
        feedback_prompt = (
            f"{content_message}\n\n"
            f"Please provide feedback based on the following writing rubrics. For each rubric, include up to three bullet points with your feedback under that category.\n\n"
            f"Rubrics:\n{rubrics}\n\nUser Text:\n{prompt_text}"
        )

    # Step 4: 使用 API 获取反馈
    feedback_response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You are an experienced writing expert who provides detailed feedback."},
            {"role": "user", "content": feedback_prompt}
        ]
    )

    feedback_text = feedback_response.choices[0].message.content

    # 打印反馈文本以进行调试
    logging.debug("Feedback Text:\n%s", feedback_text)

    # Step 5: 清理反馈文本
    def clean_feedback(feedback_text):
        clean_feedback_text = feedback_text.strip()
        return clean_feedback_text

    clean_feedback_text = clean_feedback(feedback_text)

    # 返回最终反馈
    final_feedback = f"{content_message}\n\n{clean_feedback_text}"

    return final_feedback, {}, feedback_text  # 不再返回分数