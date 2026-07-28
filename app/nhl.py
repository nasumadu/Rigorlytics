import requests

NHL_API = 'https://api-web.nhle.com/v1'
NHL_SEARCH = 'https://search.d3.nhle.com/api/v1/search'

def search_nhl_player(name):
    try:
        response = requests.get(
            NHL_SEARCH,
            params={'q': name, 'type': 'player', 'limit': 5},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return []

def get_nhl_player_landing(player_id):
    try:
        response = requests.get(
            f'{NHL_API}/player/{player_id}/landing',
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
        'Kucherov', 'Pastrnak', 'Tkachuk', 'Pettersson',
        'Stamkos', 'Karlsson', 'Tavares', 'Girard',
        'Gretzky', 'Lemieux', 'Orr', 'Howe', 'Jagr'
    ]

    for name in nhl_players:
        if name.lower() in question.lower():
            players = search_nhl_player(name)
            if players:
                player = players[0]
                player_id = player.get('playerId')
                if player_id:
                    data = get_nhl_player_landing(player_id)
                    if data:
                        context += f"\nNHL Player: {data.get('firstName', {}).get('default', '')} {data.get('lastName', {}).get('default', '')}\n"
                        context += f"Position: {data.get('position', 'N/A')}\n"
                        context += f"Team: {data.get('fullTeamName', {}).get('default', 'N/A')}\n"
                        context += f"Jersey Number: #{data.get('sweaterNumber', 'N/A')}\n"
                        context += f"Nationality: {data.get('birthCountry', 'N/A')}\n"
                        context += f"Birth City: {data.get('birthCity', {}).get('default', 'N/A')}\n"

                        # Current season stats
                        season_totals = data.get('seasonTotals', [])
                        if season_totals:
                            latest = season_totals[-1]
                            context += f"\nLatest Season Stats:\n"
                            context += f"  Season: {latest.get('season', 'N/A')}\n"
                            context += f"  Team: {latest.get('teamName', {}).get('default', 'N/A')}\n"
                            context += f"  Games Played: {latest.get('gamesPlayed', 'N/A')}\n"
                            context += f"  Goals: {latest.get('goals', 'N/A')}\n"
                            context += f"  Assists: {latest.get('assists', 'N/A')}\n"
                            context += f"  Points: {latest.get('points', 'N/A')}\n"
                            context += f"  Plus/Minus: {latest.get('plusMinus', 'N/A')}\n"
                            context += f"  Penalty Minutes: {latest.get('pim', 'N/A')}\n"
                            context += f"  Shots: {latest.get('shots', 'N/A')}\n"
                            context += f"  Shooting %: {latest.get('shootingPctg', 'N/A')}\n"

                        # Career totals
                        career = data.get('careerTotals', {}).get('regularSeason', {})
                        if career:
                            context += f"\nCareer Totals:\n"
                            context += f"  Games Played: {career.get('gamesPlayed', 'N/A')}\n"
                            context += f"  Goals: {career.get('goals', 'N/A')}\n"
                            context += f"  Assists: {career.get('assists', 'N/A')}\n"
                            context += f"  Points: {career.get('points', 'N/A')}\n"

    return context
