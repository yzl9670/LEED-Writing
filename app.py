# app.py

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timezone  # Import timezone
import os
import json
from functools import lru_cache
import logging  # Ensure logging is imported

# Import feedback function
from feedback import get_feedback, process_leed_items, collection
#from leed_rubrics import LEED_TABLE_DATA

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a secure secret key
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure file uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure maximum upload size (optional)
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024  # 80 MB

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Set logging level and format
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
    json_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'leed_credits.json')
    logging.debug(f"Reading LEED data from {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        leed_data = json.load(f)
    logging.debug(f"LEED data loaded: {leed_data}")
    return leed_data

# Generate LEED table data for rendering in the frontend
@lru_cache(maxsize=1)
def generate_leed_table_data():
    leed_data = get_leed_data()
    table_data = []

    credits_collection = leed_data.get('LEED_Credits_Collection', {})
    logging.debug(f"credits_collection type: {type(credits_collection)}")
    logging.debug(f"credits_collection content: {credits_collection}")

    if not isinstance(credits_collection, dict):
        logging.error(f"Expected 'LEED_Credits_Collection' to be dict, got {type(credits_collection)}.")
        return table_data  # Return an empty table or process as needed

    for category_name, category_data in credits_collection.items():
        logging.debug(f"Processing category_name: {category_name}, type: {type(category_data)}")
        if not isinstance(category_data, dict):
            logging.error(f"Expected 'category_data' to be dict for category '{category_name}', got {type(category_data)}. Skipping.")
            continue  # Skip invalid structures

        section = {
            'section': f"{category_name} ({category_data.get('total_points', 0)} Points)",
            'items': []
        }
        credits = category_data.get('Credits', [])
        if not isinstance(credits, list):
            logging.error(f"Expected 'Credits' to be list for category '{category_name}', got {type(credits)}.")
            continue  # Skip invalid structures

        for credit in credits:
            if not isinstance(credit, dict):
                logging.error(f"Expected each 'credit' to be dict in category '{category_name}', got {type(credit)}. Skipping.")
                continue  # Skip invalid structures

            item = {
                'category': category_name,
                'type': credit.get('type', ''),
                'name': credit.get('name', ''),
                'points': credit.get('points', None)
            }
            section['items'].append(item)
        table_data.append(section)
    return table_data

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():

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

        session.clear()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to main page
    if 'user_id' in session and User.query.get(session['user_id']):
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
    if not user_id or not User.query.get(user_id):
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    current_user = User.query.get(user_id)
    if not current_user:
        # Handle user not found
        return redirect(url_for('login'))

    # Get LEED table data
    leed_table_data = generate_leed_table_data()  # Use function to generate data
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
            return 0  # Or set a default value as needed
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
    logging.debug(f"User ID: {user_id}, Prompt Time: {prompt_time}")

    # 1. Check if there is a file uploaded
    file_path = None
    uploaded_file = request.files.get('file')
    if uploaded_file and uploaded_file.filename:
        filename = secure_filename(uploaded_file.filename)
        logging.debug(f"Uploaded file name: {filename}")
        # Verify file suffix
        if '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)
            logging.debug(f"Saved uploaded file to: {file_path}")
            user_input = None
            prompt_content = f"Uploaded file: {filename}"
        else:
            logging.warning(f"Invalid file type: {filename}")
            return jsonify({
                'success': False, 
                'error': 'Invalid file type. Only PDF and DOCX files are allowed.'
            }), 400
    else:
        # 2. If there is no file, read 'message'
        user_input = request.form.get('message', '').strip()
        logging.debug(f"User input message: {user_input}")
        if not user_input:
            logging.warning('No user input provided.')
            return jsonify({'success': False, 'error': 'No user input provided.'}), 400
        prompt_content = user_input

    # 3. Earn LEED Points
    leed_scores = None
    leed_scores_json = request.form.get('leed_scores')
    if leed_scores_json:
        try:
            leed_scores = json.loads(leed_scores_json)
            logging.debug(f"LEED scores: {leed_scores}")
            # Calculate total score (optional)
            total_score = sum(
                float(score) for key, score in leed_scores.items()
                if key != 'total_score' and isinstance(score, (int, float, str)) and str(score).replace('.', '', 1).isdigit()
            )
            leed_scores['total_score'] = total_score
            logging.debug(f"Total LEED score: {total_score}")
        except (json.JSONDecodeError, ValueError) as e:
            logging.error("Invalid LEED scores provided.", exc_info=True)
            return jsonify({'success': False, 'error': 'Invalid LEED scores provided.'}), 400

    # 4. Get all LEED projects
    leed_table_data = generate_leed_table_data()  # Use function to generate data
    user_rubrics = Rubric.query.filter_by(user_id=user_id).all()
    rubrics = [rubric.text for rubric in user_rubrics]

    # Build project list
    leed_items = []
    for category in leed_table_data:
        for item in category['items']:
            leed_items.append({
                'name': item['name'],
                'points': item.get('points', 0)
            })

    # 5. Call get_feedback (RAG + item-by-item)
    try:
        feedback_text = process_leed_items(leed_items, collection)
        logging.debug(f"Feedback Text: {feedback_text}")
    except Exception as e:
        logging.exception("Error in get_feedback:")
        return jsonify({'success': False, 'error': str(e)}), 500

    response_time = datetime.now(timezone.utc)
    logging.debug(f"Response Time: {response_time}")

    # If you uploaded a file, clean it up after use
    if file_path:
        try:
            os.remove(file_path)
            logging.debug(f"Removed uploaded file: {file_path}")
        except Exception as e:
            logging.warning(f"Failed to remove uploaded file: {file_path}. Error: {e}")

    # 6. Save conversation records to the database
    try:
        chat_history = ChatHistory(
            user_id=user_id,
            prompt_time=prompt_time,
            prompt_content=prompt_content,
            response_time=response_time,
            response_content=feedback_text
        )
        db.session.add(chat_history)
        logging.debug(f"Added ChatHistory: {chat_history}")

        # Delete the previously recorded Rubric
        Rubric.query.filter_by(user_id=user_id).delete()
        logging.debug(f"Deleted previous rubrics for user_id: {user_id}")

        # Save New Rubric
        if leed_scores:
            for k, v in leed_scores.items():
                if k == 'total_score':
                    continue
                try:
                    new_rubric = Rubric(
                        text=k,
                        score=float(v),
                        user_id=user_id
                    )
                    db.session.add(new_rubric)
                    logging.debug(f"Added Rubric: {new_rubric}")
                except ValueError as ve:
                    logging.error(f"Invalid score value for rubric '{k}': {v}", exc_info=True)
                    continue

        db.session.commit()
        logging.debug("Committed chat history and rubrics to the database.")
    except Exception as e:
        logging.exception("Error saving chat history or rubrics:")
        return jsonify({'success': False, 'error': f"Error saving data: {e}"}), 500

    # 7. Return results to the front end
    return jsonify({
        'success': True,
        'feedback': feedback_text,
        'scores': leed_scores,
        'chat_history_id': chat_history.id
    })

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
    
    # Check if leed_data conforms to the expected structure
    if not isinstance(leed_data, dict):
        return jsonify({'success': False, 'error': 'LEED data must be a dictionary.'})

    if 'LEED_Credits_Collection' not in leed_data:
        return jsonify({'success': False, 'error': 'LEED data must contain "LEED_Credits_Collection".'})

    if not isinstance(leed_data['LEED_Credits_Collection'], dict):
        return jsonify({'success': False, 'error': '"LEED_Credits_Collection" must be a dictionary.'})

        # Save LEED data to 'leed_credits.json'
    json_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'leed_credits.json')  
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(leed_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.exception("Failed to save LEED data:")
        return jsonify({'success': False, 'error': f"Failed to save LEED data: {e}"}), 500

    # Clear the cache
    get_leed_data.cache_clear()

    return jsonify({'success': True})

def load_general_rubric():
    """
    Load the general writing Rubric.
    Ensure the 'cleaned_leed_rubric.json' file exists in the same directory or provide the correct path.
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
        

# Temporarily storing Rubric data
rubric_storage = None

# Receive WRITING_RUBRIC data from the front end
@app.route('/save_WRITING_RUBRICs', methods=['POST'])
def save_writing_rubrics():
    global rubric_storage  # Using global variables to store
    try:
        # Get JSON data from the request
        rubric_data = request.get_json()
        if not rubric_data:
            return jsonify({"error": "No data provided"}), 400

        rubric_storage = rubric_data  # Save to global variable
        return jsonify({"message": "Rubric saved successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Get the currently stored Rubric data
@app.route('/get_WRITING_RUBRICs', methods=['GET'])
def get_writing_rubrics():
    LEED_RUBRIC = [
        {
            "name": "LEED Certification Achievement",
            "scoringCriteria": [
                {"points": 3, "description": "This is a test rubric."}
            ]
        }
    ]
    return jsonify(LEED_RUBRIC)

@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Unhandled exception occurred:")
    return jsonify({"error": "An unexpected error occurred.", "details": str(e)}), 500

@app.route('/get_last_feedback', methods=['GET'])
def get_last_feedback():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'User not logged in.'}), 401

    # Query the last feedback record in descending order of response_time
    last_chat = ChatHistory.query.filter_by(user_id=user_id).order_by(ChatHistory.response_time.desc()).first()
    if not last_chat:
        return jsonify({'success': False, 'error': 'No previous feedback found.'})

    return jsonify({
        'success': True,
        'feedback': last_chat.response_content,
        'chat_history_id': last_chat.id  
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Get the port from the environment variable, default to 5000
    app.run(host='0.0.0.0', port=port, debug=True)  # Host must be 0.0.0.0 to work on Heroku
