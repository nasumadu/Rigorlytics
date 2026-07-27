import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'rigorlytics-dev-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'rigorlytics-jwt-key')
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
    BALLDONTLIE_API_KEY = os.getenv('BALLDONTLIE_API_KEY', '')
    DEBUG = os.getenv('DEBUG', 'True') == 'True'
