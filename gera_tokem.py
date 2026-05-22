import requests
import os

from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"

load_dotenv(dotenv_path=env_path, override=True)

CLIENT_ID = os.getenv("BLING_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")

CODE = "86252c79af09148e79efde02448fb449ddbe939b"

REDIRECT_URI = "https://pratic-utilidades-api.onrender.com/"

url = "https://www.bling.com.br/Api/v3/oauth/token"

payload = {
    "grant_type": "authorization_code",
    "code": CODE,
    "redirect_uri": REDIRECT_URI
}

response = requests.post(
    url,
    data=payload,
    auth=(CLIENT_ID, CLIENT_SECRET),
    timeout=15
)

print(response.status_code)
print(response.text)