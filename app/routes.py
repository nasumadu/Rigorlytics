from flask import Blueprint, request, jsonify, render_template
from app.rag import generate_response
from app.compare import build_comparison
from app.players import extract_names
from app.live import get_mlb_games, get_nhl_games, get_espn_games, is_today

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
    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    games = []

    def pull_espn(path, league, limit=6):
        out = []
        try:
            out = get_espn_games(path, today)
            if not out:
                out = get_espn_games(path, yesterday)
        except Exception:
            out = []
        for g in out[:limit]:
            g["league"] = league
            games.append(g)

    pull_espn("football/nfl", "NFL")
    pull_espn("basketball/nba", "NBA")
    pull_espn("basketball/wnba", "WNBA")

    try:
        mlb = get_mlb_games(today)
        if not mlb:
            mlb = get_mlb_games(yesterday)
        for g in mlb[:8]:
            g["league"] = "MLB"
            games.append(g)
    except Exception:
        pass

    try:
        nhl = get_nhl_games(today)
        if not nhl:
            nhl = get_nhl_games(yesterday)
        for g in nhl[:6]:
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




@main.route('/api/compare', methods=['POST'])
def api_compare():
    data = request.get_json() or {}
    question = data.get('question', '')
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    names = extract_names(question)
    if len(names) < 2:
        return jsonify({'type': 'none'}), 200

    payload = build_comparison(names[0], names[1])
    if not payload:
        return jsonify({'type': 'none'}), 200

    return jsonify(payload), 200


@main.route('/health')
def health():
    return jsonify({'status': 'Rigorlytics is running', 'version': '1.0'}), 200
