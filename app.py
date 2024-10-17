from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json

# Import feedback function
from feedback import get_feedback

# Import LEED rubrics and table data
from leed_rubrics import LEED_RUBRICS, LEED_TABLE_DATA

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
            flash('Passwords do not match', 'danger')
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
            flash('Invalid username or password', 'danger')
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

    # Store leed_scores in session
    session['leed_scores'] = leed_scores

    # Generate rubrics based on leed_scores
    selected_rubrics = []
    for item_title, score in leed_scores.items():
        if score > 0:
            rubric = LEED_RUBRICS.get(item_title)
            if rubric:
                selected_rubrics.append(f"{item_title} (Score: {score}):\n{rubric}")

    return jsonify({'success': True, 'rubrics': selected_rubrics})

# Get feedback route
@app.route('/get_feedback', methods=['POST'])
def get_feedback_route():
    user_id = session.get('user_id')
    if not user_id:
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

    # Check if LEED mode
    leed_scores_json = request.form.get('leed_scores')
    if leed_scores_json:
        leed_scores = json.loads(leed_scores_json)
        # Get rubrics based on leed_scores
        selected_rubrics = []
        for item, score in leed_scores.items():
            if score > 0:
                rubric = LEED_RUBRICS.get(item)
                if rubric:
                    selected_rubrics.append(f"{item} (Score: {score}):\n{rubric}")
        rubrics_input = '\n\n'.join(selected_rubrics)
    else:
        # Get user's custom rubrics (Writing mode)
        user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
        rubrics_list = [rubric.text for rubric in user_rubrics]
        rubrics_input = '\n\n'.join(rubrics_list)

    if not rubrics_input:
        return jsonify({'success': False, 'error': 'No rubrics found.'})

    # Call get_feedback function
    feedback_text, scores, full_feedback = get_feedback(
        user_input=user_input,
        file_path=file_path,
        rubrics=rubrics_input
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
