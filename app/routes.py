from flask import Blueprint, request, jsonify, render_template
from app.rag import generate_response

main = Blueprint('main', __name__)

@main.route('/')
def home():
    return render_template('index.html')

@main.route('/ask')
def ask_page():
    return render_template('ask.html')

@main.route('/about')
def about():
    return render_template('about.html')

@main.route('/stats')
def stats():
    return render_template('stats.html')

@main.route('/fantasy')
def fantasy():
    return render_template('fantasy.html')

@main.route('/betting')
def betting():
    return render_template('betting.html')

@main.route('/pro')
def pro():
    return render_template('pro.html')

@main.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    question = data.get('question', '')
    if not question:
        return jsonify({'error': 'No question provided'}), 400
    answer = generate_response(question)
    return jsonify({'question': question, 'answer': answer, 'status': 'success'}), 200

@main.route('/health')
def health():
    return jsonify({'status': 'Rigorlytics is running', 'version': '1.0'}), 200
