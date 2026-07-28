import requests
import os

BALLDONTLIE_API_KEY = os.getenv('BALLDONTLIE_API_KEY', '')
BASE_URL = 'https://api.balldontlie.io/v1'

headers = {
    'Authorization': BALLDONTLIE_API_KEY
}

def get_players(search_name):
    try:
        response = requests.get(
            f'{BASE_URL}/players',
            headers=headers,
            params={'search': search_name, 'per_page': 5}
        )
        return response.json().get('data', [])
    except Exception as e:
        return []

def get_player_stats(player_id):
    try:
        response = requests.get(
            f'{BASE_URL}/season_averages',
            headers=headers,
            params={'player_ids[]': player_id, 'season': 2024}
        )
        return response.json().get('data', [])
    except Exception as e:
        return []

def get_teams():
    try:
        response = requests.get(
            f'{BASE_URL}/teams',
            headers=headers
        )
        return response.json().get('data', [])
    except Exception as e:
        return []

def search_player_data(question):
    context = ""
    
    # Common player names to look for in the question
    common_players = [
        'LeBron', 'James', 'Curry', 'Durant', 'Giannis',
        'Tatum', 'Luka', 'Doncic', 'Jokic', 'Embiid',
        'Mahomes', 'Jackson', 'Allen', 'Kobe', 'Jordan',
        'Harden', 'Mitchell', 'Morant', 'Booker', 'Davis'
    ]
    
    for name in common_players:
        if name.lower() in question.lower():
            players = get_players(name)
            if players:
                player = players[0]
                player_id = player['id']
                stats = get_player_stats(player_id)
                
                context += f"\nPlayer: {player['first_name']} {player['last_name']}\n"
                context += f"Team: {player.get('team', {}).get('full_name', 'N/A')}\n"
                context += f"Position: {player.get('position', 'N/A')}\n"
                
                if stats:
                    s = stats[0]
                    context += f"2024 Season Stats:\n"
                    context += f"  Points per game: {s.get('pts', 'N/A')}\n"
                    context += f"  Rebounds per game: {s.get('reb', 'N/A')}\n"
                    context += f"  Assists per game: {s.get('ast', 'N/A')}\n"
                    context += f"  Field Goal %: {s.get('fg_pct', 'N/A')}\n"
                    context += f"  3-Point %: {s.get('fg3_pct', 'N/A')}\n"
                    context += f"  True Shooting %: {s.get('ts_pct', 'N/A')}\n"
                    context += f"  Games played: {s.get('games_played', 'N/A')}\n"
    
    return context if context else "No specific player data found for this query."
