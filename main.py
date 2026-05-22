from fastapi import FastAPI
from dotenv import load_dotenv
import requests
import os
import re
import unicodedata
import json
import time

# =========================================================
# CARREGA CONFIGURAÇÕES
# =========================================================

load_dotenv()

CLIENT_ID = os.getenv("BLING_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")

TOKEN_FILE = "bling_tokens.json"

# =========================================================
# CRIA ARQUIVO DE TOKENS SE NÃO EXISTIR
# =========================================================

if not os.path.exists(TOKEN_FILE):

    token_inicial = {
        "access_token": os.getenv("BLING_ACCESS_TOKEN", ""),
        "refresh_token": os.getenv("BLING_REFRESH_TOKEN", "")
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_inicial, f)

# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="Pratic Utilidades API",
    description="API Inteligente integrada ao Bling",
    version="2.0"
)

# =========================================================
# GERENCIAMENTO DE TOKENS
# =========================================================

def obter_tokens_salvos():

    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)

    except Exception as e:

        print("Erro ao ler tokens:", str(e))

        return {
            "access_token": "",
            "refresh_token": ""
        }


def atualizar_token_no_arquivo(access_token, refresh_token):

    dados = {
        "access_token": access_token,
        "refresh_token": refresh_token
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(dados, f)


def renovar_access_token():

    tokens = obter_tokens_salvos()

    refresh_token = tokens.get("refresh_token")

    if not refresh_token:

        print("❌ Refresh token ausente")

        return None

    url = "https://www.bling.com.br/Api/v3/oauth/token"

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    try:

        resposta = requests.post(
            url,
            data=payload,
            auth=(CLIENT_ID, CLIENT_SECRET),
            timeout=15
        )

        print("STATUS REFRESH:", resposta.status_code)
        print("RESPOSTA REFRESH:", resposta.text)

        if resposta.status_code != 200:
            return None

        dados = resposta.json()

        novo_access = dados.get("access_token")
        novo_refresh = dados.get("refresh_token")

        if not novo_access:
            return None

        # salva os novos tokens
        atualizar_token_no_arquivo(
            novo_access,
            novo_refresh or refresh_token
        )

        print("✅ Token renovado com sucesso")

        return novo_access

    except Exception as e:

        print("❌ Erro ao renovar token:", str(e))

        return None

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def normalizar_texto(texto):

    if not texto:
        return ""

    texto = texto.lower()

    # remove acentos
    texto = unicodedata.normalize(
        'NFKD',
        texto
    ).encode(
        'ASCII',
        'ignore'
    ).decode(
        'ASCII'
    )

    # remove caracteres especiais
    texto = re.sub(r"[^a-zA-Z0-9\s]", ' ', texto)

    # remove espaços duplicados
    texto = re.sub(r'\s+', ' ', texto)

    return texto.strip()


def calcular_relevancia(nome_produto, palavras_busca):

    score = 0

    nome_normalizado = normalizar_texto(nome_produto)

    palavras_nome = nome_normalizado.split()

    quantidade_palavras = len(palavras_nome)

    for palavra in palavras_busca:

        # CORREÇÃO DO BUG
        if palavra in palavras_nome:

            score += 300

            posicao = palavras_nome.index(palavra)

            if posicao == 0:
                score += 200

            elif posicao == 1:
                score += 100

        elif palavra in nome_normalizado:

            score += 50

    score -= quantidade_palavras * 3

    return max(score, 0)

# =========================================================
# ROTA INICIAL
# =========================================================

@app.get("/")
def inicio():

    return {
        "status": "API online",
        "empresa": "Pratic Utilidades",
        "sistema": "Busca Inteligente de Produtos"
    }

# =========================================================
# BUSCA DE PRODUTOS
# =========================================================

@app.get("/produto")
def buscar_produto(nome: str):

    tokens = obter_tokens_salvos()

    token_atual = tokens.get("access_token")

    termo_busca = normalizar_texto(nome)

    palavras_busca = termo_busca.split()

    filtrados = []

    pagina = 1

    tentativas_renovacao = 0

    while True:

        url = "https://api.bling.com.br/Api/v3/produtos"

        headers = {
            "Authorization": f"Bearer {token_atual}"
        }

        # melhora busca no próprio Bling
        params = {
            "pagina": pagina,
            "limite": 100,
            "pesquisa": nome
        }

        try:

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=15
            )

            # TOKEN EXPIRADO
            if response.status_code == 401 and tentativas_renovacao < 1:

                print("🔄 Token expirado. Tentando renovar...")

                token_atual = renovar_access_token()

                if token_atual:

                    tentativas_renovacao += 1

                    continue

                else:

                    return {
                        "erro": "Token expirado e falha ao renovar via Refresh Token."
                    }

            # ERRO GERAL
            if response.status_code != 200:

                return {
                    "erro": "Erro ao consultar Bling",
                    "status_code": response.status_code,
                    "resposta": response.text
                }

            dados = response.json()

            produtos = dados.get("data", [])

            if not produtos:
                break

            for produto in produtos:

                nome_produto = produto.get("nome", "")

                nome_normalizado = normalizar_texto(nome_produto)

                estoque = produto.get(
                    "estoque",
                    {}
                ).get(
                    "saldoVirtualTotal",
                    0
                )

                situacao = produto.get("situacao", "A")

                # ignora sem estoque
                if estoque <= 0:
                    continue

                # ignora inativos
                if situacao != "A":
                    continue

                # BUSCA FLEXÍVEL
                encontrou = any(
                    palavra in nome_normalizado
                    for palavra in palavras_busca
                )

                if encontrou:

                    score = calcular_relevancia(
                        nome_produto,
                        palavras_busca
                    )

                    # imagem
                    link_imagem = ""

                    midia = produto.get("midia", {})

                    if midia.get("imagens", {}).get("externas"):

                        link_imagem = midia[
                            "imagens"
                        ][
                            "externas"
                        ][0].get(
                            "link",
                            ""
                        )

                    elif midia.get("imagens", {}).get("internas"):

                        link_imagem = midia[
                            "imagens"
                        ][
                            "internas"
                        ][0].get(
                            "link",
                            ""
                        )

                    filtrados.append({

                        "relevancia": score,

                        "nome": nome_produto,

                        "codigo_barras": produto.get(
                            "codigo",
                            ""
                        ),

                        "preco_venda": produto.get(
                            "preco",
                            0.0
                        ),

                        "estoque": estoque,

                        "imagem": link_imagem,

                        "descricao_curta": produto.get(
                            "descricaoCurta",
                            ""
                        ),

                        "status": "Disponível"
                    })

            pagina += 1
            # ⏳ PAUSA DE SEGURANÇA (RATE LIMIT):
            # Como o limite do Bling é 3 por segundo, esperar 0.4s entre as páginas
            # garante no máximo 2.5 requisições por segundo. Totalmente seguro!
            time.sleep(0.4)

        except requests.RequestException as e:
            return {"erro": f"Exceção de comunicação de rede: {str(e)}"}

    # ordena por relevância
    filtrados = sorted(
        filtrados,
        key=lambda x: (
            x["relevancia"],
            x["estoque"]
        ),
        reverse=True
    )

    # remove relevância da resposta final
    for item in filtrados:
        item.pop("relevancia", None)

    filtrados = filtrados[:20]

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

    tokens = obter_tokens_salvos()

    token_atual = tokens.get("access_token")

    pagina = 1

    tentativas_renovacao = 0

    while True:

        url = "https://api.bling.com.br/Api/v3/produtos"

        headers = {
            "Authorization": f"Bearer {token_atual}"
        }

        params = {
            "pagina": pagina,
            "limite": 100,
            "codigo": codigo
        }

        try:

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=15
            )

            # TOKEN EXPIRADO
            if response.status_code == 401 and tentativas_renovacao < 1:

                token_atual = renovar_access_token()

                if token_atual:

                    tentativas_renovacao += 1

                    continue

                else:

                    return {
                        "encontrado": False,
                        "mensagem": "Falha ao renovar token"
                    }

            if response.status_code != 200:

                return {
                    "erro": "Erro ao consultar Bling",
                    "status_code": response.status_code,
                    "resposta": response.text
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

                    link_imagem = ""

                    midia = produto.get("midia", {})

                    if midia.get("imagens", {}).get("externas"):

                        link_imagem = midia[
                            "imagens"
                        ][
                            "externas"
                        ][0].get(
                            "link",
                            ""
                        )

                    elif midia.get("imagens", {}).get("internas"):

                        link_imagem = midia[
                            "imagens"
                        ][
                            "internas"
                        ][0].get(
                            "link",
                            ""
                        )

                    return {

                        "encontrado": True,

                        "produto": {

                            "nome": produto.get("nome"),

                            "codigo_barras": codigo_produto,

                            "preco_venda": produto.get("preco"),

                            "estoque": estoque,

                            "imagem": link_imagem,

                            "descricao_curta": produto.get(
                                "descricaoCurta",
                                ""
                            )
                        }
                    }

            pagina += 1

        except Exception as e:

            return {
                "erro": f"Erro de conexão: {str(e)}"
            }

    return {
        "encontrado": False,
        "mensagem": "Produto não encontrado ou sem estoque"
    }