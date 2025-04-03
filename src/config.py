import os

from dotenv import load_dotenv

load_dotenv()

LM_consumer_key = os.getenv("LM_consumer_key")
LM_consumer_secret = os.getenv("LM_consumer_secret")
