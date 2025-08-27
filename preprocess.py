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

        # Ignore blank lines, page numbers, and update information
        if line == '' or re.match(r'^\d+$', line) or line.startswith('Updated to'):
            i += 1
            continue

        # Check item title
        if re.match(r'^(PREREQUISITE|CREDIT):', line):
            item = {}
            item['name'] = line
            item['type'] = 'Prerequisite' if 'PREREQUISITE' in line else 'Credit'
            item['required'] = 'Required' in lines[i+1] if (i+1) < len(lines) else False
            item['points'] = extract_points(lines[i+1]) if (i+1) < len(lines) else None

            # Initialize other fields
            item['applies_to'] = []
            item['intent'] = ''
            item['requirements'] = []

            i += 1  
            while i < len(lines):
                line = lines[i].strip()

                if re.match(r'^(PREREQUISITE|CREDIT):', line):
                    break

                if line.startswith('This prerequisite applies to') or line.startswith('This credit applies to'):
                    i += 1
                    applies_to = []
                    while i < len(lines) and (lines[i].strip().startswith('') or lines[i].strip().startswith('-')):
                        applies_to.append(lines[i].strip('- ').strip())
                        i += 1
                    item['applies_to'] = applies_to
                elif line == 'Intent':
                    i += 1
                    intent = ''
                    while i < len(lines) and lines[i].strip() not in ['Requirements', '']:
                        intent += lines[i].strip() + ' '
                        i += 1
                    item['intent'] = intent.strip()
                elif line == 'Requirements':
                    i += 1
                    requirements = []
                    current_requirement = None
                    stack = []  
                    while i < len(lines):
                        req_line = lines[i].strip()


                        if re.match(r'^(PREREQUISITE|CREDIT):', req_line):
                            break

                        if req_line == '' or re.match(r'^\d+$', req_line) or req_line.startswith('Updated to'):
                            i += 1
                            continue

                        if re.match(r'^(Option|AND|OR|Path|Case)\s*\d*[\.:]', req_line, re.IGNORECASE):
                            if current_requirement:
                                stack.append(current_requirement)
                            current_requirement = {'title': req_line, 'description': '', 'sub_requirements': []}
                            i += 1

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
                            if current_requirement:
                                current_requirement['description'] += req_line + ' '
                            i += 1

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
    match = re.search(r'(\d+)\s*[\–\-]\s*(\d+)\s*points?', line)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    else:

        match = re.search(r'(\d+)\s*points?', line)
        if match:
            return int(match.group(1))
        else:
            return None

def main():
    pdf_path = 'LEED v4 BD+C.pdf'  


    print('Extracting text from PDF, please wait...')
    text = extract_text_from_pdf(pdf_path)

    print('Parsing text...')
    items = parse_leed_text(text)

    with open('leed_rubric.json', 'w', encoding='utf-8') as f:
        json.dump({'items': items}, f, ensure_ascii=False, indent=2)

    print('The LEED Rubric has been successfully converted from PDF to JSON format and saved to leed_rubric.json')

if __name__ == '__main__':
    main()
