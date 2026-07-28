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
    
    nba_data = search_nba(question)
    if nba_data and "No specific" not in nba_data:
        context += f"NBA DATA:\n{nba_data}\n"
    
    nfl_data = search_nfl_data(question)
    if nfl_data:
        context += f"NFL DATA:\n{nfl_data}\n"
    
    mlb_data = search_mlb_data(question)
    if mlb_data:
        context += f"MLB DATA:\n{mlb_data}\n"
    
    nhl_data = search_nhl_data(question)
    if nhl_data:
        context += f"NHL DATA:\n{nhl_data}\n"
    
    wnba_data = search_wnba_data(question)
    if wnba_data:
        context += f"WNBA DATA:\n{wnba_data}\n"
    
    return context if context else "No specific player data found. Using general sports knowledge."

def generate_response(question):
    try:
        context = gather_context(question)
        
        prompt = f"""You are Rigorlytics, a rigorous sports analytics AI assistant.
You serve casual fans, fantasy players, athletes, agents, and team executives.
You provide data-driven, objective analysis across NBA, NFL, MLB, NHL, and WNBA.
Always base your responses on the statistical data provided.
Be conversational but analytical. Keep responses clear and insightful.
Never make up statistics. If data is limited, say so and provide analytical context.

Retrieved Sports Data:
{context}

User Question: {question}

Provide a data-driven analytical response. If comparing players, use the stats provided.
If historical data is unavailable, note the limitation and provide analytical context."""

        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
        
    except Exception as e:
        return f"Rigorlytics encountered an error: {str(e)}"
