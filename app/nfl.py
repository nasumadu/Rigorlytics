import requests

BASE_URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl'

def search_nfl_player(name):
    try:
        response = requests.get(
            f'{BASE_URL}/athletes',
            params={'limit': 5, 'search': name},
            timeout=10
        )
        return response.json().get('items', [])
    except Exception as e:
        return []

def get_nfl_team_stats(team):
    try:
        response = requests.get(
            f'{BASE_URL}/teams',
            timeout=10
        )
        teams = response.json().get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
        for t in teams:
            if team.lower() in t.get('team', {}).get('displayName', '').lower():
                return t.get('team', {})
        return {}
    except Exception as e:
        return {}

def search_nfl_data(question):
    context = ""
    nfl_players = [
        'Mahomes', 'Allen', 'Hurts', 'Burrow', 'Lawrence',
        'McCaffrey', 'Hill', 'Jefferson', 'Chase', 'Kelce',
        'Jackson', 'Herbert', 'Stroud', 'Young', 'Richardson'
    ]
    for name in nfl_players:
        if name.lower() in question.lower():
            players = search_nfl_player(name)
            if players:
                context += f"\nNFL Player found: {name}\n"
                context += f"Source: ESPN NFL API\n"
    return context
