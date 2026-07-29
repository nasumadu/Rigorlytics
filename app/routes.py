from flask import Blueprint, request, jsonify, render_template
from app.rag import generate_response
from app.live import get_mlb_games, get_nhl_games, get_espn_games

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



@main.route('/api/scores')
def api_scores():
    games = []
    try:
        for g in get_espn_games("football/nfl")[:6]:
            g["league"] = "NFL"
            games.append(g)
    except Exception:
        pass
    try:
        for g in get_espn_games("basketball/nba")[:6]:
            g["league"] = "NBA"
            games.append(g)
    except Exception:
        pass
    try:
        for g in get_mlb_games()[:8]:
            g["league"] = "MLB"
            games.append(g)
    except Exception:
        pass
    try:
        for g in get_espn_games("basketball/wnba")[:6]:
            g["league"] = "WNBA"
            games.append(g)
    except Exception:
        pass
    try:
        for g in get_nhl_games()[:6]:
            g["league"] = "NHL"
            games.append(g)
    except Exception:
        pass

    def rank(g):
        s = (str(g.get("detail", "")) + " " + str(g.get("status", ""))).lower()
        if "final" in s or "completed" in s or "off" in s:
            return 1
        live_words = ["quarter", "halftime", "period", "inning", "in progress",
                      "live", "ot", "end of", "top ", "bot ", "middle"]
        if any(w in s for w in live_words):
            return 0
        return 2

    games.sort(key=rank)
    return jsonify({"games": games[:20]}), 200

@main.route('/health')
def health():
    return jsonify({'status': 'Rigorlytics is running', 'version': '1.0'}), 200
