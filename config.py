import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///classpulse.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Groq AI
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    
    # App Settings
    DEBUG = os.environ.get('DEBUG', 'False') == 'True'
    FAQ_SIMILARITY_THRESHOLD = 0.65

    # Rate Limiting
    RATE_LIMIT_MESSAGES = int(os.environ.get('RATE_LIMIT_MESSAGES', 10))
    RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('RATE_LIMIT_WINDOW_SECONDS', 60))
    RATE_LIMIT_BLOCK_DURATION = int(os.environ.get('RATE_LIMIT_BLOCK_DURATION', 300))
    RATE_LIMITING_ENABLED = os.environ.get('RATE_LIMITING_ENABLED', 'True') == 'True'

    # Token Budget
    DAILY_TOKEN_BUDGET = int(os.environ.get('DAILY_TOKEN_BUDGET', 100000))
    TOKEN_BUDGET_ENABLED = os.environ.get('TOKEN_BUDGET_ENABLED', 'False') == 'True'