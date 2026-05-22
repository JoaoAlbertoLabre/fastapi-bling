from fastapi import FastAPI
from dotenv import load_dotenv
import requests
import os
import re
import unicodedata
import json

# =========================================================
# CARREGA CONFIGURAÇÕES E ARQUIVO DE TOKENS
# =========================================================
load_dotenv()

CLIENT_ID = os.getenv("BLING_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")
TOKEN_FILE = "bling_tokens.json"

# Inicialização fallback caso não exista o arquivo JSON de tokens ainda
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
    description="API Inteligente de Produtos integrada ao Bling v3",
    version="1.1"
)


# =========================================================
# FUNÇÕES DE GERENCIAMENTO DE TOKEN (OAUTH 2.0)
# =========================================================

def obter_tokens_salvos():
    """Lê os tokens atuais do arquivo local."""
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"access_token": "", "refresh_token": ""}


def atualizar_token_no_arquivo(access_token, refresh_token):
    """Salva os novos tokens gerados."""
    tokens = {"access_token": access_token, "refresh_token": refresh_token}
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)


def renovar_access_token():
    """Usa o REFRESH_TOKEN para obter um novo ACCESS_TOKEN válido do Bling."""
    tokens = obter_tokens_salvos()
    refresh_token = tokens.get("refresh_token")

    if not refresh_token or not CLIENT_ID or not CLIENT_SECRET:
        print("Erro: Credenciais OAuth ausentes no .env ou arquivo de tokens.")
        return None

    url = "https://www.bling.com.br/Api/v3/oauth/token"
    dados = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    try:
        # O Bling v3 aceita autenticação básica com Client ID e Client Secret
        resposta = requests.post(url, data=dados, auth=(CLIENT_ID, CLIENT_SECRET), timeout=10)
        if resposta.status_code == 200:
            novos_dados = resposta.json()
            novo_access = novos_dados["access_token"]
            novo_refresh = novos_dados.get("refresh_token", refresh_token)  # Retorna o mesmo ou um novo

            atualizar_token_no_arquivo(novo_access, novo_refresh)
            print("🔄 Token do Bling renovado com sucesso automaticamente!")
            return novo_access
        else:
            print(f"Erro ao renovar token. Status: {resposta.status_code}, Resposta: {resposta.text}")
            return None
    except Exception as e:
        print(f"Exceção ao tentar renovar token: {e}")
        return None


# =========================================================
# FUNÇÕES AUXILIARES DE BUSCA
# =========================================================

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = texto.lower()
    # Remove acentos
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    # Remove caracteres especiais
    texto = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto)
    # Remove espaços duplicados
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def calcular_relevancia(nome_produto, palavras_busca):
    score = 0
    nome_normalizado = normalizar_texto(nome_produto)
    palavras_nome = nome_normalizado.split()
    quantidade_palavras = len(palavras_nome)

    for palavra in palavras_busca:
        if palabra in palavras_nome:
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
# ROTAS DA API
# =========================================================

@app.get("/")
def inicio():
    return {
        "status": "API online",
        "empresa": "Pratic Utilidades",
        "sistema": "Busca Inteligente de Estoque"
    }


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
        headers = {"Authorization": f"Bearer {token_atual}"}
        params = {"pagina": pagina, "limite": 100}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            # Tratamento inteligente de erro 401 (Token Expirado)
            if response.status_code == 401 and tentativas_renovacao < 1:
                token_atual = renovar_access_token()
                if token_atual:
                    tentativas_renovacao += 1
                    continue  # Refaz o mesmo loop da mesma página com o novo token
                else:
                    return {"erro": "Token expirado e falha ao renovar via Refresh Token."}

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

                # Mapeamento v3 correto da estrutura de estoque saldo físico/virtual
                estoque = produto.get("estoque", {}).get("saldoVirtualTotal", 0)
                situacao = produto.get("situacao", "A")

                if estoque <= 0 or situacao != "A":
                    continue

                # Verifica correspondência das palavras buscadas
                encontrou = all(palavra in nome_normalizado for palavra in palavras_busca)

                if encontrou:
                    score = calcular_relevancia(nome_produto, palavras_busca)

                    # Tratamento seguro da URL da imagem principal no Bling v3
                    link_imagem = ""
                    midia = produto.get("midia", {})
                    if midia.get("imagens", {}).get("externas"):
                        link_imagem = midia["imagens"]["externas"][0].get("link", "")
                    elif midia.get("imagens", {}).get("internas"):
                        link_imagem = midia["imagens"]["internas"][0].get("link", "")

                    filtrados.append({
                        "relevancia": score,
                        "nome": nome_produto,
                        "codigo_barras": produto.get("codigo", ""),
                        "preco_venda": produto.get("preco", 0.0),
                        "estoque": estoque,
                        "imagem": link_imagem,
                        "descricao_curta": produto.get("descricaoCurta", ""),
                        "status": "Disponível"
                    })

            pagina += 1

        except Exception as e:
            return {"erro": f"Erro interno de conexão com o Bling: {str(e)}"}

    # Ordenação por relevância e limite de resposta
    filtrados = sorted(filtrados, key=lambda x: (x["relevancia"], x["estoque"]), reverse=True)
    for item in filtrados:
        item.pop("relevancia", None)

    filtrados = filtrados[:20]
    return {"busca": nome, "quantidade": len(filtrados), "produtos": filtrados}


@app.get("/codigo/{codigo}")
def buscar_codigo_barras(codigo: str):
    tokens = obter_tokens_salvos()
    token_atual = tokens.get("access_token")

    tentativas_renovacao = 0
    pagina = 1

    while True:
        url = "https://api.bling.com.br/Api/v3/produtos"
        headers = {"Authorization": f"Bearer {token_atual}"}
        params = {"pagina": pagina, "limite": 100,
                  "codigo": codigo}  # Otimização: Passar o código direto por parâmetro diminui o laço do Bling

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 401 and tentativas_renovacao < 1:
                token_atual = renovar_access_token()
                if token_atual:
                    tentativas_renovacao += 1
                    continue
                else:
                    return {"encontrado": False, "mensagem": "Token expirado e falha na renovação"}

            if response.status_code != 200:
                return {"erro": "Erro ao consultar Bling", "status_code": response.status_code}

            dados = response.json()
            produtos = dados.get("data", [])

            if not produtos:
                break

            for produto in produtos:
                codigo_produto = str(produto.get("codigo", ""))
                estoque = produto.get("estoque", {}).get("saldoVirtualTotal", 0)

                if codigo == codigo_produto and estoque > 0:
                    link_imagem = ""
                    midia = produto.get("midia", {})
                    if midia.get("imagens", {}).get("externas"):
                        link_imagem = midia["imagens"]["externas"][0].get("link", "")
                    elif midia.get("imagens", {}).get("internas"):
                        link_imagem = midia["imagens"]["internas"][0].get("link", "")

                    return {
                        "encontrado": True,
                        "produto": {
                            "nome": produto.get("nome"),
                            "codigo_barras": codigo_produto,
                            "preco_venda": produto.get("preco"),
                            "estoque": estoque,
                            "imagem": link_imagem,
                            "descricao_curta": produto.get("descricaoCurta", "")
                        }
                    }
            pagina += 1
        except Exception as e:
            return {"erro": f"Erro de conexão: {str(e)}"}

    return {"encontrado": False, "mensagem": "Produto não encontrado ou sem estoque"}