from fastapi import FastAPI
from dotenv import load_dotenv
import requests
import os
import re
import unicodedata

# =========================================================
# CARREGA .ENV
# =========================================================

load_dotenv()

ACCESS_TOKEN = os.getenv("BLING_ACCESS_TOKEN")

# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="Pratic Utilidades API",
    description="API Inteligente de Produtos",
    version="1.0"
)

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def normalizar_texto(texto):

    if not texto:
        return ""

    texto = texto.lower()

    # Remove acentos
    texto = unicodedata.normalize(
        'NFKD',
        texto
    ).encode(
        'ASCII',
        'ignore'
    ).decode(
        'ASCII'
    )

    # Remove caracteres especiais
    texto = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto)

    # Remove espaços duplicados
    texto = re.sub(r'\s+', ' ', texto)

    return texto.strip()


def calcular_relevancia(nome_produto, palavras_busca):

    score = 0

    nome_normalizado = normalizar_texto(nome_produto)

    for palavra in palavras_busca:

        # Palavra exata
        if palavra == nome_normalizado:
            score += 100

        # Palavra contida
        elif palavra in nome_normalizado:
            score += 20

        # Palavra começa junto
        if nome_normalizado.startswith(palavra):
            score += 15

        # Palavra separada
        palavras_nome = nome_normalizado.split()

        if palavra in palavras_nome:
            score += 30

    return score

# =========================================================
# ROTA INICIAL
# =========================================================

@app.get("/")
def inicio():

    return {
        "status": "API online",
        "empresa": "Pratic Utilidades",
        "sistema": "Busca Inteligente Produtos"
    }

# =========================================================
# BUSCA INTELIGENTE DE PRODUTOS
# =========================================================

@app.get("/produto")
def buscar_produto(nome: str):

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    termo_busca = normalizar_texto(nome)

    palavras_busca = termo_busca.split()

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

        # Segurança API
        if response.status_code != 200:

            return {
                "erro": "Erro ao consultar Bling",
                "status_code": response.status_code,
                "resposta": response.text
            }

        dados = response.json()

        produtos = dados.get("data", [])

        # Sem mais produtos
        if not produtos:
            break

        for produto in produtos:

            nome_produto = produto.get("nome", "")

            nome_normalizado = normalizar_texto(
                nome_produto
            )

            estoque = produto.get(
                "estoque",
                {}
            ).get(
                "saldoVirtualTotal",
                0
            )

            situacao = produto.get(
                "situacao",
                ""
            )

            # Ignora sem estoque
            if estoque <= 0:
                continue

            # Ignora inativos
            if situacao != "A":
                continue

            # Verifica se TODAS as palavras existem
            encontrou = all(
                palavra in nome_normalizado
                for palavra in palavras_busca
            )

            if encontrou:

                score = calcular_relevancia(
                    nome_produto,
                    palavras_busca
                )

                filtrados.append({

                    "relevancia": score,

                    "nome": produto.get("nome"),

                    "codigo_barras": produto.get("codigo"),

                    "preco_venda": produto.get("preco"),

                    "estoque": estoque,

                    "imagem": produto.get(
                        "imagemURL",
                        ""
                    ),

                    "descricao_curta": produto.get(
                        "descricaoCurta",
                        ""
                    ),

                    "status": "Disponível"

                })

        pagina += 1

    # Ordena por relevância
    filtrados = sorted(
        filtrados,
        key=lambda x: x["relevancia"],
        reverse=True
    )

    # Remove score interno
    for item in filtrados:
        item.pop("relevancia", None)

    return {

        "busca": nome,

        "quantidade": len(filtrados),

        "produtos": filtrados

    }

# =========================================================
# BUSCA POR CÓDIGO DE BARRAS
# =========================================================

@app.get("/codigo/{codigo}")
def buscar_codigo_barras(codigo: str):

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

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

        if response.status_code != 200:

            return {
                "erro": "Erro ao consultar Bling"
            }

        dados = response.json()

        produtos = dados.get("data", [])

        if not produtos:
            break

        for produto in produtos:

            codigo_produto = str(
                produto.get("codigo", "")
            )

            estoque = produto.get(
                "estoque",
                {}
            ).get(
                "saldoVirtualTotal",
                0
            )

            if codigo == codigo_produto and estoque > 0:

                return {

                    "encontrado": True,

                    "produto": {

                        "nome": produto.get("nome"),

                        "codigo_barras": codigo_produto,

                        "preco_venda": produto.get("preco"),

                        "estoque": estoque,

                        "imagem": produto.get(
                            "imagemURL",
                            ""
                        ),

                        "descricao_curta": produto.get(
                            "descricaoCurta",
                            ""
                        )

                    }

                }

        pagina += 1

    return {

        "encontrado": False,

        "mensagem": "Produto não encontrado"

    }