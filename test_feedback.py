# test_feedback.py

from feedback import get_feedback

# 示例输入
user_input = "这是一个测试反馈请求。"
leed_scores = {
    "Surrounding Density and Diverse Uses": "5",
    "Access to Quality Transit": "5",
    "Indoor Water Use Reduction": "6",
    "Enhanced Commissioning": "6",
    "Optimize Energy Performance": "18",
    "total_score": "40"
}

feedback_text, scores, writing_feedback = get_feedback(
    user_input=user_input,
    file_path=None,
    rubrics=None,  # 或者传入实际的 rubrics 数据
    leed_scores=leed_scores
)

print("Feedback Text:")
print(feedback_text)
print("\nScores:")
print(scores)
print("\nWriting Feedback:")
print(writing_feedback)
