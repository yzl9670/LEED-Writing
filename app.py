# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timezone  # 导入 timezone
import os
import json
from functools import lru_cache
import logging  # 确保导入 logging

# Import feedback function
from feedback import get_feedback
from leed_rubrics import LEED_TABLE_DATA

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a secure secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'  # Adjust as needed
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure file uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure maximum upload size (optional)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 设置日志级别和格式
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)
    
    rubrics = db.relationship('Rubric', backref='user', lazy=True)
    chat_histories = db.relationship('ChatHistory', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Rubric model
class Rubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float, nullable=True)  
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Chat history model
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prompt_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    prompt_content = db.Column(db.Text, nullable=False)
    response_time = db.Column(db.DateTime, nullable=False)
    response_content = db.Column(db.Text, nullable=False)
    user_rating = db.Column(db.Integer)  # User rating (optional)
    user_feedback = db.Column(db.Text)   # User feedback (optional)

# Cache LEED data
@lru_cache(maxsize=1)
def get_leed_data():
    json_path = 'leed_data.json'  # Replace with the actual path of your LEED JSON file
    with open(json_path, 'r', encoding='utf-8') as f:
        leed_data = json.load(f)
    return leed_data

# Generate LEED table data for rendering in the frontend
@lru_cache(maxsize=1)
def generate_leed_table_data():
    leed_data = get_leed_data()
    table_data = []

    credits_collection = leed_data.get('LEED_Credits_Collection', {})
    for rating_system, categories in credits_collection.items():
        for category_name, category_data in categories.items():
            section = {
                'section': f"{category_name} ({category_data.get('total_points', 0)} Points)",
                'items': []
            }
            credits = category_data.get('Credits', [])
            for credit in credits:
                item = {
                    'category': category_name,
                    'type': credit.get('type', ''),  # 修正为 'type'
                    'name': credit.get('name', ''),  # 修正为 'name'
                    'points': credit.get('points', None)  # 修正为 'points'
                }
                section['items'].append(item)
            table_data.append(section)
    return table_data

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    # If user is already logged in, redirect to main page
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        # Create new user and save to database
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to main page
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

        session['user_id'] = user.id

        flash('Welcome back!', 'success')

        return redirect(url_for('index'))

    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Main page route
@app.route('/')
def index():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    current_user = User.query.get(user_id)
    if not current_user:
        # Handle user not found
        return redirect(url_for('login'))

    # Get LEED table data
    leed_table_data = generate_leed_table_data()  # 使用函数生成数据
    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    return render_template('index.html', user=current_user, rubrics=rubrics, leed_table_data=leed_table_data)

@app.route('/get_user_rubrics', methods=['GET'])
def get_user_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    return jsonify({'success': True, 'rubrics': rubrics})

@app.route('/get_leed_rubrics', methods=['GET'])
def get_leed_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        print('User not logged in.')
        return jsonify({'success': False, 'error': 'User not logged in.'})

    # Get the current user object
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'User not found.'})
    
    # Fetch LEED scores from session
    leed_scores = session.get('leed_scores')
    if not leed_scores:
        print('No LEED scores found in session.')
        return jsonify({'success': False, 'error': 'No LEED scores found. Please submit LEED scores first.'})

    # Generate rubrics based on LEED scores
    leed_data = get_leed_data()
    print("DEBUG leed_data type:", type(leed_data))
    print("DEBUG leed_data content:", leed_data)

    # Build a mapping from item titles to their data
    def normalize_title(title):
        return title.strip().lower()

    item_data_mapping = {}
    credits_collection = leed_data.get('LEED_Credits_Collection', {})
    for rating_system, categories in credits_collection.items():
        for category_name, category_data in categories.items():
            credits = category_data.get("Credits", [])
            for item in credits:
                item_title = item.get('name', '')
                normalized_title = normalize_title(item_title)
                item_data_mapping[normalized_title] = item

    selected_rubrics = []
    for item_title, score in leed_scores.items():
        try:
            numeric_score = float(score)
        except (ValueError, TypeError):
            print(f'Invalid score for "{item_title}": {score}. Skipping.')
            continue  # Skip invalid scores

        if numeric_score > 0:
            normalized_title = normalize_title(item_title)
            item_data = item_data_mapping.get(normalized_title)
            if item_data:
                # Handle total points
                points = item_data.get('points', 0)
                total_points = calculate_total_points(points)

                # Extract descriptions from options if available
                descriptions = []
                requirements = item_data.get('requirements', {})
                if 'options' in requirements:
                    for option in requirements['options']:
                        option_desc = option.get('description', '')
                        if option_desc:
                            descriptions.append(option_desc)
                else:
                    # Use 'intent' as description if no options are available
                    intent = item_data.get('intent', 'No description available.')
                    descriptions.append(intent)

                # Get scoring criteria
                scoring_criteria = item_data.get('scoring_criteria', [])

                selected_rubrics.append({
                    'title': item_data.get('name'),
                    'user_score': numeric_score,
                    'descriptions': descriptions,
                    'scoring_criteria': scoring_criteria,
                    'total_points': total_points
                })
            else:
                print(f'Item data not found for: {item_title}')

    return jsonify({'success': True, 'rubrics': selected_rubrics})

# Helper function to calculate total points
def calculate_total_points(points):
    if isinstance(points, (int, float)):
        return points
    elif isinstance(points, str):
        if points.lower() == 'required':
            return 0  # 或者根据需要设置默认值
        try:
            return float(points)
        except ValueError:
            return 0
    else:
        return 0

# Get feedback route
@app.route('/get_feedback', methods=['POST'])
def get_feedback_route():
    user_id = session.get('user_id')
    if not user_id:
        logging.warning('User not logged in.')
        return jsonify({'success': False, 'error': 'User not logged in.'}), 401

    prompt_time = datetime.now(timezone.utc)

    # 检查是否上传了文件
    if 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        filename = secure_filename(file.filename)
        if '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            user_input = None
            file_path = filepath
            prompt_content = f"Uploaded file: {filename}"
        else:
            return jsonify({'success': False, 'error': 'Invalid file type. Only PDF and DOCX files are allowed.'}), 400
    else:
        # 未上传文件，获取用户输入文本
        user_input = request.form.get('message')
        file_path = None
        if not user_input:
            return jsonify({'success': False, 'error': 'No user input provided.'}), 400
        prompt_content = user_input

    # 初始化 leed_scores
    leed_scores = None

    # 检查是否为 LEED 模式
    leed_scores_json = request.form.get('leed_scores')
    if leed_scores_json:
        try:
            leed_scores = json.loads(leed_scores_json)
            # 计算总分
            total_score = sum(
                float(score) for score in leed_scores.values()
                if isinstance(score, (int, float, str)) and str(score).replace('.', '', 1).isdigit()
            )
            leed_scores['total_score'] = total_score
        except (json.JSONDecodeError, ValueError) as e:
            logging.error("Invalid LEED scores provided.")
            return jsonify({'success': False, 'error': 'Invalid LEED scores provided.'}), 400

        # 获取缓存的 LEED 数据
        try:
            leed_data = get_leed_data()
        except Exception as e:
            logging.exception("Error loading LEED data:")
            return jsonify({'success': False, 'error': f'Error loading LEED data: {e}'}), 500

        # 访问 'LEED_Credits_Collection' 键
        leed_credits_collection = leed_data.get('LEED_Credits_Collection', {})
        if not leed_credits_collection:
            logging.error('LEED_Credits_Collection not found in LEED data.')
            return jsonify({'success': False, 'error': 'LEED_Credits_Collection not found in LEED data.'}), 500

        # 构建标题到数据的映射
        def normalize_title(title):
            return title.strip().lower()

        item_data_mapping = {}
        for rating_system, categories in leed_credits_collection.items():
            for category_name, category_data in categories.items():
                credits = category_data.get("Credits", [])
                for item in credits:
                    item_title = item.get('name', '')
                    normalized_title = normalize_title(item_title)
                    item_data_mapping[normalized_title] = item

        selected_rubrics = []
        for item_title, score in leed_scores.items():
            if item_title == 'total_score':
                continue  # 跳过 total_score
            try:
                numeric_score = float(score)
            except (ValueError, TypeError):
                logging.warning(f'Invalid score for "{item_title}": {score}. Skipping.')
                continue  # 跳过无效分数

            if numeric_score > 0:
                normalized_title = normalize_title(item_title)
                item_data = item_data_mapping.get(normalized_title)
                if item_data:
                    # 提取评分标准或其他相关数据
                    scoring_criteria = item_data.get('scoring_criteria', [])
                    selected_rubrics.append({
                        'name': item_data.get('name', ''),
                        'scoringCriteria': scoring_criteria
                    })
                else:
                    logging.warning(f'Item data not found for: {item_title}')
        # 不再构建 rubrics_input 字符串，而是直接传递 selected_rubrics 列表
    else:
        # 处理直接提供的 rubrics
        rubrics_input = request.form.get('rubrics')
        if not rubrics_input:
            return jsonify({'success': False, 'error': 'No rubrics provided.'}), 400

    # 加载通用写作 Rubric
    try:
        writing_rubric = load_general_rubric()
        logging.debug(f"Writing Rubric: {writing_rubric}")
        if not isinstance(writing_rubric, list):
            raise ValueError("General rubric should be a list of dictionaries.")
    except Exception as e:
        logging.exception("Error loading general rubric:")
        return jsonify({'success': False, 'error': f'Error loading general rubric: {e}'}), 500

    # 调用 get_feedback 函数
    try:
        feedback_text, scores, full_feedback = get_feedback(
            user_input=user_input,
            file_path=file_path,
            rubrics=writing_rubric,  # 传递列表而非字符串
            leed_scores=leed_scores
        )
    except Exception as e:
        logging.exception("Error in get_feedback_route:")
        return jsonify({'success': False, 'error': str(e)}), 500

    response_time = datetime.now(timezone.utc)

    # 处理上传的文件
    if file_path:
        try:
            os.remove(file_path)
        except Exception as e:
            logging.warning(f"Failed to remove uploaded file: {file_path}. Error: {e}")

    # 保存聊天记录
    try:
        chat_history = ChatHistory(
            user_id=user_id,
            prompt_time=prompt_time,
            prompt_content=prompt_content,
            response_time=response_time,
            response_content=feedback_text
        )
        db.session.add(chat_history)
        # 删除当前用户的旧 Rubric 记录
        Rubric.query.filter_by(user_id=user_id).delete()

        # 保存新的 rubric 和分数
        for rubric_title, score in scores.items():
            if rubric_title == 'total_score':
                continue  # 跳过 total_score
            new_rubric = Rubric(
                text=rubric_title,
                score=score,
                user_id=user_id
            )
            db.session.add(new_rubric)

        db.session.commit()
    except Exception as e:
        logging.exception("Error saving chat history or rubrics:")
        return jsonify({'success': False, 'error': f'Error saving data: {e}'}), 500

    logging.debug("Scores being returned (backend): %s", scores)
    return jsonify({'success': True, 'feedback': feedback_text, 'scores': scores, 'chat_history_id': chat_history.id})

# Submit user feedback route
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    data = request.get_json()
    chat_history_id = data.get('chat_history_id')
    rating = data.get('rating')
    feedback_text = data.get('feedback')

    chat_history = ChatHistory.query.filter_by(id=chat_history_id, user_id=user_id).first()
    if not chat_history:
        return jsonify({'success': False, 'error': 'Chat history not found.'})

    chat_history.user_rating = rating if rating else None
    chat_history.user_feedback = feedback_text if feedback_text else None

    db.session.commit()

    return jsonify({'success': True})

@app.route('/save_rubrics', methods=['POST'])
def save_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})
    
    # Get the current user object
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'User not found.'})
    
    # Permission check
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'You do not have permission to perform this action.'})
    
    data = request.get_json()
    rubrics_input = data.get('rubrics')

    if rubrics_input is not None:
        # Update rubrics in the database
        Rubric.query.filter_by(user_id=user_id).delete()
        for rubric_text in rubrics_input.strip().split('\n\n'):
            if rubric_text.strip():
                new_rubric = Rubric(text=rubric_text.strip(), user_id=user_id)
                db.session.add(new_rubric)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'No rubrics provided.'})
    
@app.route('/submit_leed_scores', methods=['POST'])
def submit_leed_scores():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'User not found.'})

    data = request.get_json()
    leed_scores = data.get('leed_scores')

    if not leed_scores:
        return jsonify({'success': False, 'error': 'No LEED scores provided.'})

    # Convert scores to strings before storing in session
    leed_scores_str = {k: str(v) for k, v in leed_scores.items()}
    session['leed_scores'] = leed_scores_str

    return jsonify({'success': True})

@app.route('/admin/get_leed_data', methods=['GET'])
def admin_get_leed_data():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    current_user = User.query.get(user_id)
    if not current_user or current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'You do not have permission to perform this action.'})

    leed_data = get_leed_data()
    return jsonify({'success': True, 'leed_data': leed_data})

@app.route('/admin/save_leed_data', methods=['POST'])
def admin_save_leed_data():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    current_user = User.query.get(user_id)
    if not current_user or current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'You do not have permission to perform this action.'})

    data = request.get_json()
    leed_data = data.get('leed_data')

    if not leed_data:
        return jsonify({'success': False, 'error': 'No LEED data provided.'})

    # Saving LEED data to a file
    json_path = 'leed_data.json'  # 确保与 get_leed_data() 的路径一致
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(leed_data, f, ensure_ascii=False, indent=4)

    # Clear the cache so that you can get the latest data next time
    get_leed_data.cache_clear()

    return jsonify({'success': True})

def load_general_rubric():
    """
    加载通用的写作 Rubric。
    确保 'cleaned_leed_rubric.json' 文件存在于同一目录或提供正确的路径。
    """
    rubric_path = os.path.join(os.path.dirname(__file__), "cleaned_leed_rubric.json")
    if not os.path.exists(rubric_path):
        raise FileNotFoundError(f"Rubric file not found at path: {rubric_path}")
    
    with open(rubric_path, "r", encoding="utf-8") as f:
        try:
            rubric_data = json.load(f)
            if not isinstance(rubric_data, list):
                raise ValueError("Rubric data should be a list of dictionaries.")
            return rubric_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing rubric JSON: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Get the port from the environment variable, default to 5000
    app.run(host='0.0.0.0', port=port, debug=True)  # Host must be 0.0.0.0 to work on Heroku
