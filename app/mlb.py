import requests

BASE_URL = 'https://statsapi.mlb.com/api/v1'

def search_mlb_player(name):
    try:
        response = requests.get(
            f'{BASE_URL}/people/search',
            params={'names': name, 'sportId': 1},
            timeout=10
        )
        return response.json().get('people', [])
    except Exception as e:
        return []

def get_mlb_player_stats(player_id):
    try:
        response = requests.get(
            f'{BASE_URL}/people/{player_id}/stats',
            params={'stats': 'season', 'group': 'hitting', 'season': 2024},
            timeout=10
        )
        return response.json().get('stats', [])
    except Exception as e:
        return []

def search_mlb_data(question):
    context = ""
    mlb_players = [
        'Ohtani', 'Judge', 'Acuna', 'Betts', 'Trout',
        'Soto', 'Tatis', 'Freeman', 'Alvarez', 'Harper',
        'deGrom', 'Cole', 'Scherzer', 'Verlander', 'Kershaw'
    ]
    for name in mlb_players:
        if name.lower() in question.lower():
            players = search_mlb_player(name)
            if players:
                player = players[0]
                player_id = player.get('id')
                stats = get_mlb_player_stats(player_id)
                context += f"\nMLB Player: {player.get('fullName', name)}\n"
                context += f"Position: {player.get('primaryPosition', {}).get('name', 'N/A')}\n"
                context += f"Team: {player.get('currentTeam', {}).get('name', 'N/A')}\n"
                if stats:
                    splits = stats[0].get('splits', [])
                    if splits:
                        s = splits[0].get('stat', {})
                        context += f"2024 Stats:\n"
                        context += f"  AVG: {s.get('avg', 'N/A')}\n"
                        context += f"  HR: {s.get('homeRuns', 'N/A')}\n"
                        context += f"  RBI: {s.get('rbi', 'N/A')}\n"
                        context += f"  OPS: {s.get('ops', 'N/A')}\n"
                        context += f"  WAR: {s.get('war', 'N/A')}\n"
    return context
