import json

def get_leed_data():
    json_path = 'cleaned_leed_rubric.json'  # 替换为您的实际路径
    with open(json_path, 'r', encoding='utf-8') as f:
        leed_data = json.load(f)
    return leed_data