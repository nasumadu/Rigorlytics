import anthropic
import os
from dotenv import load_dotenv
from app.nba import search_player_data as search_nba
from app.nfl import search_nfl_data
from app.mlb import search_mlb_data
from app.nhl import search_nhl_data
from app.wnba import search_wnba_data

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

def gather_context(question):
    context = ""
    try:
        nba_data = search_nba(question)
        if nba_data and "No specific" not in nba_data:
            context += f"CURRENT ROSTER DATA:\n{nba_data}\n"
    except:
        pass
    try:
        nfl_data = search_nfl_data(question)
        if nfl_data:
            context += f"NFL DATA:\n{nfl_data}\n"
    except:
        pass
    try:
        mlb_data = search_mlb_data(question)
        if mlb_data:
            context += f"MLB DATA:\n{mlb_data}\n"
    except:
        pass
    try:
        nhl_data = search_nhl_data(question)
        if nhl_data:
            context += f"NHL DATA:\n{nhl_data}\n"
    except:
        pass
    try:
        wnba_data = search_wnba_data(question)
        if wnba_data:
            context += f"WNBA DATA:\n{wnba_data}\n"
    except:
        pass
    return context

def generate_response(question):
    try:
        context = gather_context(question)

        prompt = f"""You are Rigorlytics, an elite sports analytics AI with comprehensive knowledge of all sports statistics, history, and advanced metrics.

CRITICAL INSTRUCTIONS:
- You have deep knowledge of ALL sports statistics from your training data
- For historical players (Jordan, Kobe, Gretzky, Ruth, etc.) — USE YOUR KNOWLEDGE to provide specific stats
- For active players — use both the live data AND your knowledge of their career stats
- NEVER say you cannot provide stats — you know them from your training
- ALWAYS give specific numbers: PPG, APG, RPG, FG%, PER, WAR, Goals, TDs, ERA, etc.
- The live API data below supplements your knowledge — do not let it limit you
- If API data only shows roster info, IGNORE the limitation and use your full knowledge base

LIVE API DATA (use as supplement only):
{context if context else "No live data — use your comprehensive knowledge base fully."}

QUESTION: {question}

RESPONSE REQUIREMENTS:
1. Provide specific statistics and numbers
2. Compare players using actual career averages and totals
3. Use advanced metrics (PER, TS%, WAR, Corsi, EPA, etc.)
4. Give historical context and era adjustments
5. Be definitive and analytical — this is what Rigorlytics is built for
6. Minimum 3-4 specific statistical data points in every response"""

        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return message.content[0].text

    except Exception as e:
        return f"Rigorlytics encountered an error: {str(e)}"
