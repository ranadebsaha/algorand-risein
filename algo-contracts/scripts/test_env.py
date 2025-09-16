import os
from dotenv import load_dotenv

load_dotenv()

print("ALGOD_API_URL from env:", os.getenv("ALGOD_API_URL"))