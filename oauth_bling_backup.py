from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
import requests
import os

# Carrega variáveis .env
load_dotenv()

# Inicializa FastAPI
app = FastAPI()

# Credenciais Bling
CLIENT_ID = os.getenv("BLING_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")

# URL callback
REDIRECT_URI = "http://localhost:8000/callback"

# URL base
BASE_URL = "https://www.bling.com.br/Api/v3"


# ROTA INICIAL
@app.get("/")
def inicio():

    state = "praticutilidades"

    auth_url = (
        f"https://www.bling.com.br/Api/v3/oauth/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )

    return RedirectResponse(auth_url)


# CALLBACK OAUTH
@app.get("/callback")
def callback(code: str = None, state: str = None):

    if not code:
        return {
            "erro": "Código OAuth não recebido"
        }

    token_url = "https://www.bling.com.br/Api/v3/oauth/token"

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(
        token_url,
        data=payload,
        auth=(CLIENT_ID, CLIENT_SECRET)
    )

    return response.json()