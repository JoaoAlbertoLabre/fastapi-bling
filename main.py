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

    palavras_nome = nome_normalizado.split()

    texto_completo = " ".join(palavras_nome)

    for palavra in palavras_busca:

        # Igual ao nome inteiro
        if palavra == texto_completo:
            score += 1000

        # Palavra isolada exata
        if palavra in palavras_nome:
            score += 300

        # Começa com palavra
        if texto_completo.startswith(palavra):
            score += 120

        # Palavra parcial
        if palavra in texto_completo:
            score += 40

        # Penaliza palavras compostas indesejadas
        termos_penalizados = [
            "porta",
            "suporte",
            "descanso",
            "base"
        ]

        for termo_ruim in termos_penalizados:

            if termo_ruim in palavras_nome and palavra == "copo":

                score -= 150

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
        key=lambda x: (
            x["relevancia"],
            x["estoque"]
        ),
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