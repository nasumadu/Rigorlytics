import requests

BASE_URL = 'https://api-web.nhle.com/v1'

def search_nhl_player(name):
    try:
        response = requests.get(
            f'https://search.d3.nhle.com/api/v1/search',
            params={'q': name, 'type': 'player', 'limit': 5},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return []

def get_nhl_player_stats(player_id):
    try:
        response = requests.get(
            f'{BASE_URL}/player/{player_id}/landing',
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {}

def search_nhl_data(question):
    context = ""
    nhl_players = [
        'McDavid', 'Draisaitl', 'MacKinnon', 'Ovechkin',
        'Matthews', 'Crosby', 'Hedman', 'Makar', 'Hughes',
        'Kucherov', 'Pastrnak', 'Tkachuk', 'Pettersson'
    ]
    for name in nhl_players:
        if name.lower() in question.lower():
            players = search_nhl_player(name)
            if players:
                context += f"\nNHL Player found: {name}\n"
                context += f"Source: NHL official API\n"
    return context
