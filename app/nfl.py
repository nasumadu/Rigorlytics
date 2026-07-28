import requests

def get_nfl_player_stats(player_name):
    try:
        # ESPN NFL API
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes"
        response = requests.get(
            url,
            params={'limit': 1000},
            timeout=10
        )
        data = response.json()
        athletes = data.get('items', [])

        for athlete in athletes:
            full_name = athlete.get('displayName', '')
            if player_name.lower() in full_name.lower():
                athlete_id = athlete.get('id')
                return get_nfl_athlete_details(athlete_id, full_name)
        return ""
    except Exception as e:
        return ""

def get_nfl_athlete_details(athlete_id, name):
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes/{athlete_id}"
        response = requests.get(url, timeout=10)
        data = response.json()

        context = f"\nNFL Player: {name}\n"
        athlete = data.get('athlete', {})
        context += f"Position: {athlete.get('position', {}).get('displayName', 'N/A')}\n"
        context += f"Team: {athlete.get('team', {}).get('displayName', 'N/A')}\n"
        context += f"Age: {athlete.get('age', 'N/A')}\n"
        context += f"Experience: {athlete.get('experience', {}).get('years', 'N/A')} years\n"
        context += f"College: {athlete.get('college', {}).get('name', 'N/A')}\n"
        return context
    except Exception as e:
        return ""

def search_nfl_data(question):
    context = ""
    nfl_players = [
        'Mahomes', 'Allen', 'Hurts', 'Burrow', 'Lawrence',
        'McCaffrey', 'Hill', 'Jefferson', 'Chase', 'Kelce',
        'Jackson', 'Herbert', 'Stroud', 'Young', 'Richardson',
        'Brady', 'Manning', 'Rodgers', 'Favre', 'Montana',
        'Rice', 'Sanders', 'Brown', 'Moss', 'Owens',
        'Gronkowski', 'Fitzgerald', 'Tomlinson', 'Peterson',
        'Bosa', 'Donald', 'Watt', 'Mack', 'Miller'
    ]

    for name in nfl_players:
        if name.lower() in question.lower():
            stats = get_nfl_player_stats(name)
            if stats:
                context += stats

    return context
