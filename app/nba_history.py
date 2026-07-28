import requests

def get_player_career_stats(player_name):
    try:
        url = "https://stats.nba.com/stats/commonallplayers"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.nba.com/'
        }
        params = {
            'LeagueID': '00',
            'Season': '2024-25',
            'IsOnlyCurrentSeason': '0'
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        return None
