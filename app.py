from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
from functools import lru_cache

# Import feedback function
from feedback import get_feedback

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
    json_path = 'cleaned_leed_rubric.json'  # Replace with the actual path of your LEED JSON file
    with open(json_path, 'r', encoding='utf-8') as f:
        leed_data = json.load(f)
    return leed_data

# Generate LEED table data for rendering in the frontend
@lru_cache(maxsize=1)
def generate_leed_table_data():
    leed_data = get_leed_data()
    table_data = []
    for section_name, items in leed_data.items():
        section = {
            'section': section_name,
            'items': items
        }
        table_data.append(section)
    return table_data

LEED_TABLE_DATA = generate_leed_table_data()

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

    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    return render_template('index.html', rubrics=rubrics, leed_table_data=LEED_TABLE_DATA)

# Save rubrics route
@app.route('/save_rubrics', methods=['POST'])
def save_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

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

# Get user rubrics route
@app.route('/get_user_rubrics', methods=['GET'])
def get_user_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    return jsonify({'success': True, 'rubrics': rubrics})

# Submit LEED scores route
@app.route('/submit_leed_scores', methods=['POST'])
def submit_leed_scores():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'})

    data = request.get_json()
    leed_scores = data.get('leed_scores')

    if not leed_scores:
        return jsonify({'success': False, 'error': 'No LEED scores provided.'})

    # Convert scores to strings before storing in session
    leed_scores_str = {k: str(v) for k, v in leed_scores.items()}
    session['leed_scores'] = leed_scores_str

    return jsonify({'success': True})

# Get LEED rubrics route
@app.route('/get_leed_rubrics', methods=['GET'])
def get_leed_rubrics():
    user_id = session.get('user_id')
    if not user_id:
        print('User not logged in.')
        return jsonify({'success': False, 'error': 'User not logged in.'})

    # Fetch LEED scores from session
    leed_scores = session.get('leed_scores')
    if not leed_scores:
        print('No LEED scores found in session.')
        return jsonify({'success': False, 'error': 'No LEED scores found. Please submit LEED scores first.'})

    # Generate rubrics based on LEED scores
    leed_data = get_leed_data()

    # Build a mapping from item titles to their data
    def normalize_title(title):
        return title.strip().lower()

    item_data_mapping = {}
    for category, items in leed_data.items():
        for item in items:
            item_title = item.get('name')
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
    total_points = 0
    if isinstance(points, dict):
        point_values = []
        for val in points.values():
            if isinstance(val, list):
                point_values.extend(val)
            elif isinstance(val, (int, float)):
                point_values.append(val)
        if point_values:
            total_points = max(point_values)
    elif isinstance(points, list):
        if points:
            total_points = max(points)
    elif isinstance(points, (int, float)):
        total_points = points
    else:
        total_points = 0
    return total_points

# Get feedback route
@app.route('/get_feedback', methods=['POST'])
def get_feedback_route():
    user_id = session.get('user_id')
    if not user_id:
        print('User not logged in.')
        return jsonify({'success': False, 'error': 'User not logged in.'})

    prompt_time = datetime.utcnow()

    # Check if a file was uploaded
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
            return jsonify({'success': False, 'error': 'Invalid file type. Only PDF and DOCX files are allowed.'})
    else:
        # No file uploaded, get user input text
        user_input = request.form.get('message')
        file_path = None
        if not user_input:
            return jsonify({'success': False, 'error': 'No user input provided.'})
        prompt_content = user_input

    # Initialize leed_scores
    leed_scores = None

    # Check if LEED mode
    leed_scores_json = request.form.get('leed_scores')
    if leed_scores_json:
        leed_scores = json.loads(leed_scores_json)
        # Calculate total score
        try:
            total_score = sum(float(score) for score in leed_scores.values())
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid LEED scores provided.'})
        leed_scores['total_score'] = total_score

        # Get cached LEED data
        leed_data = get_leed_data()
        # Generate rubrics based on leed_scores and leed_data
        selected_rubrics = []
        for item_title, score in leed_scores.items():
            if item_title == 'total_score':
                continue  # Skip total_score in leed_scores
            if float(score) > 0:
                normalized_title = item_title.strip().lower()
                item_data = None
                for category_items in leed_data.values():
                    for item in category_items:
                        if item.get('name', '').strip().lower() == normalized_title:
                            item_data = item
                            break
                    if item_data:
                        break
                if item_data:
                    # Prepare the rubric text (you can adjust this as needed)
                    selected_rubrics.append(f"{item_title} (Score: {score}):\n{item_data}")
        rubrics_input = '\n\n'.join(selected_rubrics)
    else:
        # Get rubrics from request.form (Writing mode)
        rubrics_input = request.form.get('rubrics')
        if not rubrics_input:
            return jsonify({'success': False, 'error': 'No rubrics provided.'})

    if not rubrics_input:
        return jsonify({'success': False, 'error': 'No rubrics found.'})

    # Call get_feedback function
    feedback_text, scores, full_feedback = get_feedback(
        user_input=user_input,
        file_path=file_path,
        rubrics=rubrics_input,
        leed_scores=leed_scores  # Pass leed_scores here
    )

    response_time = datetime.utcnow()

    # Remove uploaded file after processing
    if file_path:
        os.remove(file_path)

    # Save chat history
    chat_history = ChatHistory(
        user_id=user_id,
        prompt_time=prompt_time,
        prompt_content=prompt_content,
        response_time=response_time,
        response_content=feedback_text
    )
    db.session.add(chat_history)
    db.session.commit()

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

# Run the Flask application
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Get the port from the environment variable, default to 5000
    app.run(host='0.0.0.0', port=port, debug=True)  # Host must be 0.0.0.0 to work on Heroku
