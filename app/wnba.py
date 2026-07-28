import requests

def get_wnba_player_stats(player_name):
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes"
        response = requests.get(
            url,
            params={'limit': 500},
            timeout=10
        )
        data = response.json()
        athletes = data.get('items', [])

        for athlete in athletes:
            full_name = athlete.get('displayName', '')
            if player_name.lower() in full_name.lower():
                athlete_id = athlete.get('id')
                return get_wnba_athlete_details(athlete_id, full_name)
        return ""
    except Exception as e:
        return ""

def get_wnba_athlete_details(athlete_id, name):
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/athletes/{athlete_id}"
        response = requests.get(url, timeout=10)
        data = response.json()

        context = f"\nWNBA Player: {name}\n"
        athlete = data.get('athlete', {})
        context += f"Position: {athlete.get('position', {}).get('displayName', 'N/A')}\n"
        context += f"Team: {athlete.get('team', {}).get('displayName', 'N/A')}\n"
        context += f"Age: {athlete.get('age', 'N/A')}\n"
        context += f"College: {athlete.get('college', {}).get('name', 'N/A')}\n"
        context += f"Experience: {athlete.get('experience', {}).get('years', 'N/A')} years\n"
        return context
    except Exception as e:
        return ""

def search_wnba_data(question):
    context = ""
    wnba_players = [
        'Clark', 'Stewart', 'Wilson', 'Ionescu', 'Charles',
        'Delle Donne', 'Bird', 'Taurasi', 'Parker', 'Diggins',
        'Griner', 'Ogwumike', 'Loyd', 'Howard', 'Plum',
        'Boston', 'Jones', 'Gray', 'Thomas', 'Collier'
    ]

    for name in wnba_players:
        if name.lower() in question.lower():
            stats = get_wnba_player_stats(name)
            if stats:
                context += stats

    return context
