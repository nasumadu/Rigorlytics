import requests
import os

BALLDONTLIE_API_KEY = os.getenv('BALLDONTLIE_API_KEY', '')
BASE_URL = 'https://api.balldontlie.io/v1'
headers = {'Authorization': BALLDONTLIE_API_KEY}

def get_players(search_name):
    try:
        response = requests.get(
            f'{BASE_URL}/players',
            headers=headers,
            params={'search': search_name, 'per_page': 5},
            timeout=10
        )
        return response.json().get('data', [])
    except Exception as e:
        return []

def get_season_averages(player_id, season=2024):
    try:
        response = requests.get(
            f'{BASE_URL}/season_averages',
            headers=headers,
            params={'player_ids[]': player_id, 'season': season},
            timeout=10
        )
        return response.json().get('data', [])
    except Exception as e:
        return []

def get_career_context(player_name):
    try:
        url = "https://stats.nba.com/stats/commonplayerinfo"
        nba_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.nba.com/',
            'Accept': 'application/json',
            'x-nba-stats-origin': 'stats',
            'x-nba-stats-token': 'true'
        }
        return None
    except:
        return None

def search_player_data(question):
    context = ""
    nba_players = [
        'LeBron', 'James', 'Curry', 'Durant', 'Giannis',
        'Tatum', 'Luka', 'Doncic', 'Jokic', 'Embiid',
        'Harden', 'Mitchell', 'Morant', 'Booker', 'Davis',
        'Irving', 'Lillard', 'George', 'Butler', 'Beal',
        'Jordan', 'Kobe', 'Bryant', 'Shaq', 'Magic',
        'Bird', 'Pippen', 'Rodman', 'Wade', 'Allen',
        'Paul', 'Westbrook', 'Thompson', 'Green', 'Holiday'
    ]

    for name in nba_players:
        if name.lower() in question.lower():
            players = get_players(name)
            if players:
                player = players[0]
                player_id = player['id']
                team = player.get('team', {})

                context += f"\nNBA Player: {player['first_name']} {player['last_name']}\n"
                context += f"Position: {player.get('position', 'N/A')}\n"
                context += f"Height: {player.get('height', 'N/A')}\n"
                context += f"Weight: {player.get('weight', 'N/A')} lbs\n"
                context += f"Draft Year: {player.get('draft_year', 'N/A')}\n"
                context += f"Draft Round: {player.get('draft_round', 'N/A')}\n"
                context += f"Draft Pick: {player.get('draft_number', 'N/A')}\n"

                if team:
                    context += f"Current Team: {team.get('full_name', 'N/A')}\n"
                    context += f"Conference: {team.get('conference', 'N/A')}\n"
                    context += f"Division: {team.get('division', 'N/A')}\n"

                # Try multiple seasons
                for season in [2024, 2023, 2022]:
                    stats = get_season_averages(player_id, season)
                    if stats:
                        s = stats[0]
                        context += f"\n{season}-{str(season+1)[-2:]} Season Stats:\n"
                        context += f"  Games Played: {s.get('games_played', 'N/A')}\n"
                        context += f"  Minutes Per Game: {s.get('min', 'N/A')}\n"
                        context += f"  Points Per Game: {s.get('pts', 'N/A')}\n"
                        context += f"  Rebounds Per Game: {s.get('reb', 'N/A')}\n"
                        context += f"  Assists Per Game: {s.get('ast', 'N/A')}\n"
                        context += f"  Steals Per Game: {s.get('stl', 'N/A')}\n"
                        context += f"  Blocks Per Game: {s.get('blk', 'N/A')}\n"
                        context += f"  Turnovers Per Game: {s.get('turnover', 'N/A')}\n"
                        context += f"  Field Goal %: {s.get('fg_pct', 'N/A')}\n"
                        context += f"  3-Point %: {s.get('fg3_pct', 'N/A')}\n"
                        context += f"  Free Throw %: {s.get('ft_pct', 'N/A')}\n"
                        break

    return context if context else "No specific NBA player data found."
