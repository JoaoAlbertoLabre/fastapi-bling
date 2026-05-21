from fastapi import FastAPI
from dotenv import load_dotenv
import requests
import os

load_dotenv()

app = FastAPI()

ACCESS_TOKEN = os.getenv("BLING_ACCESS_TOKEN")


@app.get("/")
def inicio():
    return {"status": "API online"}


@app.get("/produto")
def buscar_produto(nome: str):

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    termo = nome.lower().strip()

    filtrados = []

    pagina = 1

    while True:

        url = "https://api.bling.com.br/Api/v3/produtos"

        params = {
            "pagina": pagina,
            "limite": 100
        }

        response = requests.get(
            url,
            headers=headers,
            params=params
        )

        dados = response.json()

        produtos = dados.get("data", [])

        # Se não houver mais produtos
        if not produtos:
            break

        for produto in produtos:

            nome_produto = produto.get("nome", "").lower()

            estoque = produto.get("estoque", {}).get("saldoVirtualTotal", 0)

            if termo in nome_produto and estoque > 0:
                filtrados.append({
                    "nome": produto.get("nome"),
                    "codigo_barras": produto.get("codigo"),
                    "preco_venda": produto.get("preco"),
                    "estoque": estoque,
                })

        pagina += 1

    return {
        "busca": nome,
        "quantidade": len(filtrados),
        "produtos": filtrados
    }