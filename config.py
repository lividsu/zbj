import os
from dotenv import load_dotenv, find_dotenv

# load env parameters form file named .env
load_dotenv(find_dotenv())

class Config:
    APP_ID = os.getenv("APP_ID")
    APP_SECRET = os.getenv("APP_SECRET")
    VERIFICATION_TOKEN = os.getenv("VERIFICATION_TOKEN")
    ENCRYPT_KEY = os.getenv("ENCRYPT_KEY")
    LARK_HOST = os.getenv("LARK_HOST")
    BOT_NAME = os.getenv("BOT_NAME", "八戒-Dev")
    BOT_OPEN_ID = os.getenv("BOT_OPEN_ID", "")
    MAX_IMAGES = int(os.getenv("MAX_IMAGES", "4"))
    
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "3002"))
    DEBUG = str(os.getenv("DEBUG", "true")).lower() in ("1", "true", "yes")

config = Config()
