import requests

BASE_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba'

def search_wnba_player(name):
    try:
        response = requests.get(
            f'{BASE_URL}/athletes',
            params={'limit': 5, 'search': name},
            timeout=10
        )
        return response.json().get('items', [])
    except Exception as e:
        return []

def get_wnba_teams():
    try:
        response = requests.get(
            f'{BASE_URL}/teams',
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {}

def search_wnba_data(question):
    context = ""
    wnba_players = [
        'Clark', 'Stewart', 'Wilson', 'Ionescu', 'Charles',
        'Delle Donne', 'Bird', 'Taurasi', 'Parker', 'Diggins'
    ]
    for name in wnba_players:
        if name.lower() in question.lower():
            players = search_wnba_player(name)
            if players:
                context += f"\nWNBA Player found: {name}\n"
                context += f"Source: ESPN WNBA API\n"
    return context
