import re
import json
import pdfplumber

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages:
            text += page.extract_text() + '\n'
    return text

def parse_leed_text(text):
    items = []
    lines = text.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 忽略空行、页码和更新信息
        if line == '' or re.match(r'^\d+$', line) or line.startswith('Updated to'):
            i += 1
            continue

        # 检测项目标题
        if re.match(r'^(PREREQUISITE|CREDIT):', line):
            item = {}
            item['name'] = line
            item['type'] = 'Prerequisite' if 'PREREQUISITE' in line else 'Credit'
            item['required'] = 'Required' in lines[i+1] if (i+1) < len(lines) else False
            item['points'] = extract_points(lines[i+1]) if (i+1) < len(lines) else None

            # 初始化其他字段
            item['applies_to'] = []
            item['intent'] = ''
            item['requirements'] = []

            i += 1  # 移动到下一行
            # 继续解析
            while i < len(lines):
                line = lines[i].strip()

                # 检查是否到达下一个项目
                if re.match(r'^(PREREQUISITE|CREDIT):', line):
                    break

                # 检查适用范围
                if line.startswith('This prerequisite applies to') or line.startswith('This credit applies to'):
                    i += 1
                    applies_to = []
                    while i < len(lines) and (lines[i].strip().startswith('') or lines[i].strip().startswith('-')):
                        applies_to.append(lines[i].strip('- ').strip())
                        i += 1
                    item['applies_to'] = applies_to
                # 检查 Intent
                elif line == 'Intent':
                    i += 1
                    intent = ''
                    while i < len(lines) and lines[i].strip() not in ['Requirements', '']:
                        intent += lines[i].strip() + ' '
                        i += 1
                    item['intent'] = intent.strip()
                # 检查 Requirements
                elif line == 'Requirements':
                    i += 1
                    requirements = []
                    current_requirement = None
                    stack = []  # 用于处理嵌套的子部分
                    while i < len(lines):
                        req_line = lines[i].strip()

                        # 检查是否到达下一个项目
                        if re.match(r'^(PREREQUISITE|CREDIT):', req_line):
                            break

                        # 忽略空行、页码和更新信息
                        if req_line == '' or re.match(r'^\d+$', req_line) or req_line.startswith('Updated to'):
                            i += 1
                            continue

                        # 处理选项或子标题
                        if re.match(r'^(Option|AND|OR|Path|Case)\s*\d*[\.:]', req_line, re.IGNORECASE):
                            # 新的子部分
                            if current_requirement:
                                stack.append(current_requirement)
                            current_requirement = {'title': req_line, 'description': '', 'sub_requirements': []}
                            i += 1
                        # 检测新的要求标题（全大写）
                        elif req_line.isupper() and not req_line.startswith('AND') and not req_line.startswith('OR'):
                            if current_requirement:
                                if stack:
                                    stack[-1]['sub_requirements'].append(current_requirement)
                                    current_requirement = stack.pop()
                                else:
                                    requirements.append(current_requirement)
                                    current_requirement = None
                            current_requirement = {'title': req_line, 'description': ''}
                            i += 1
                        else:
                            # 添加描述
                            if current_requirement:
                                current_requirement['description'] += req_line + ' '
                            i += 1
                    # 将最后的 requirement 添加到列表中
                    while current_requirement:
                        if stack:
                            stack[-1]['sub_requirements'].append(current_requirement)
                            current_requirement = stack.pop()
                        else:
                            requirements.append(current_requirement)
                            current_requirement = None
                    item['requirements'] = requirements
                else:
                    i += 1
            items.append(item)
        else:
            i += 1
    return items

def extract_points(line):
    # 处理积分范围，例如 "1–6 points"
    match = re.search(r'(\d+)\s*[\–\-]\s*(\d+)\s*points?', line)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    else:
        # 处理单个积分
        match = re.search(r'(\d+)\s*points?', line)
        if match:
            return int(match.group(1))
        else:
            return None

def main():
    pdf_path = 'LEED v4 BD+C.pdf'  # 请将此路径替换为您的实际 PDF 文件路径

    # 从 PDF 中提取文本
    print('正在从 PDF 中提取文本，请稍候...')
    text = extract_text_from_pdf(pdf_path)

    # 解析文本
    print('正在解析文本...')
    items = parse_leed_text(text)

    # 将结果写入 JSON 文件
    with open('leed_rubric.json', 'w', encoding='utf-8') as f:
        json.dump({'items': items}, f, ensure_ascii=False, indent=2)

    print('LEED Rubric 已成功从 PDF 转换为 JSON 格式并保存到 leed_rubric.json')

if __name__ == '__main__':
    main()
