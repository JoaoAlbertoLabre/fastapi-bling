from fastapi import FastAPI
from dotenv import load_dotenv
import requests
import os
import re
import unicodedata
import json
import threading
import time

# =========================================================
# CONFIGURAÇÕES, LOCKS E CACHE
# =========================================================
load_dotenv()

CLIENT_ID = os.getenv("BLING_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")
TOKEN_FILE = "bling_tokens.json"

# LOCKS GLOBAIS DE CONCORRÊNCIA
json_lock = threading.Lock()  # Impede corrupção de arquivo
refresh_lock = threading.Lock()  # Impede múltiplas renovações simultâneas no Bling

# ESTRUTURA DE CACHE EM MEMÓRIA (TTL Cache)
CACHE_PRODUTOS = {}
CACHE_TTL_SEGUNDOS = 120  # Cache de 2 minutos (Ideal para varejo dinâmico)

if not os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": os.getenv("BLING_ACCESS_TOKEN", ""),
            "refresh_token": os.getenv("BLING_REFRESH_TOKEN", "")
        }, f)

# =========================================================
# FASTAPI
# =========================================================
app = FastAPI(
    title="Pratic Utilidades API Enterprise",
    description="API de Alta Performance com Cache, Lock de Concorrência e Resiliência",
    version="2.0"
)


# =========================================================
# GERENCIAMENTO DE TOKEN RESILIENTE (PRODUÇÃO SENIOR)
# =========================================================

def obter_tokens_salvos():
    with json_lock:
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"access_token": "", "refresh_token": ""}


def atualizar_token_no_arquivo(access_token, refresh_token):
    with json_lock:
        tokens = {"access_token": access_token, "refresh_token": refresh_token}
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)


def renovar_access_token(token_que_falhou):
    """
    Renova o token garantindo que requisições concorrentes não disparem
    múltiplos requests desnecessários ao Bling.
    """
    # LOCK DE REFRESH: Apenas UMA thread por vez entra aqui para renovar
    with refresh_lock:
        tokens_atuais = obter_tokens_salvos()

        # DOUBLE-CHECK: Se o token no arquivo já mudou em relação ao token
        # que falhou, significa que outra thread já renovou ele. Retorna o novo imediatamente.
        if tokens_atuais.get("access_token") != token_que_falhou:
            return tokens_atuais.get("access_token")

        refresh_token = tokens_atuais.get("refresh_token")
        if not refresh_token or not CLIENT_ID or not CLIENT_SECRET:
            return None

        url = "https://www.bling.com.br/Api/v3/oauth/token"
        dados = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        # POLÍTICA DE RETRY COM BACKOFF (Tenta até 3 vezes se a rede oscilar)
        for tentativa in range(3):
            try:
                resposta = requests.post(url, data=dados, auth=(CLIENT_ID, CLIENT_SECRET), timeout=10)
                if resposta.status_code == 200:
                    novos_dados = resposta.json()
                    novo_access = novos_dados["access_token"]
                    novo_refresh = novos_dados.get("refresh_token", refresh_token)

                    atualizar_token_no_arquivo(novo_access, novo_refresh)
                    return novo_access

                # Se não for erro de rede (Ex: Credencial inválida), não adianta tentar de novo
                if resposta.status_code in [400, 401, 403]:
                    break
            except requests.RequestException:
                time.sleep(0.5 * (tentativa + 1))  # Espera incremental: 0.5s, 1.0s...

        return None


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    texto = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def calcular_relevancia(nome_produto, palavras_busca):
    score = 0
    nome_normalizado = normalizar_texto(nome_produto)
    palavras_nome = nome_normalizado.split()
    quantidade_palavras = len(palavras_nome)

    for palavra in palavras_busca:
        if palavra in palavras_nome:  # Correção mantida (palavra)
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
# ROTA PRINCIPAL OTIMIZADA COM CACHE
# =========================================================

@app.get("/produto")
def buscar_produto(nome: str):
    termo_busca = normalizar_texto(nome)

    # ⚡ VERIFICAÇÃO DE CACHE (Retorno instantâneo)
    tempo_atual = time.time()
    if termo_busca in CACHE_PRODUTOS:
        dados_cache = CACHE_PRODUTOS[termo_busca]
        if tempo_atual - dados_cache["timestamp"] < CACHE_TTL_SEGUNDOS:
            return dados_cache["resultado"]

    # Se não está no cache, executa fluxo normal de busca
    tokens = obter_tokens_salvos()
    token_atual = tokens.get("access_token")
    palavras_busca = termo_busca.split()
    filtrados = []
    pagina = 1
    tentativas_renovacao = 0

    while True:
        url = "https://api.bling.com.br/Api/v3/produtos"
        headers = {"Authorization": f"Bearer {token_atual}"}
        params = {"pagina": pagina, "limite": 50, "pesquisa": nome, "criterio": 1}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)

            # Tratamento Resiliente com Lock de Refresh Duplo
            if response.status_code == 401 and tentativas_renovacao < 1:
                novo_token = renovar_access_token(token_atual)
                if not novo_token:
                    return {"erro": "Falha crítica de autenticação com o provedor de dados."}
                token_atual = novo_token
                tentativas_renovacao += 1
                continue

            if response.status_code != 200:
                return {"erro": "Erro na consulta remota", "status_code": response.status_code}

            dados = response.json()
            produtos = dados.get("data", [])

            if not produtos or pagina > 5:
                break

            for produto in produtos:
                nome_produto = produto.get("nome", "")
                nome_normalizado = normalizar_texto(nome_produto)

                estoque = produto.get("estoque", {}).get("saldoVirtualTotal", 0)
                situacao = produto.get("situacao", "A")

                if estoque <= 0 or situacao != "A":
                    continue

                # Flexibilidade comercial ANY (Traz mais vendas!)
                encontrou = any(palavra in nome_normalizado for palavra in palavras_busca)

                if encontrou:
                    score = calcular_relevancia(nome_produto, palavras_busca)

                    link_imagem = ""
                    midia = produto.get("midia", {})
                    if midia.get("imagens", {}).get("externas"):
                        link_imagem = midia["imagens"]["externas"][0].get("link", "")

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

        except requests.RequestException as e:
            return {"erro": f"Exceção de comunicação de rede: {str(e)}"}

    filtrados = sorted(filtrados, key=lambda x: (x["relevancia"], x["estoque"]), reverse=True)
    for item in filtrados:
        item.pop("relevancia", None)

    resultado_final = {
        "busca": nome,
        "quantidade": len(filtrados[:20]),
        "produtos": filtrados[:20]
    }

    # 💾 GRAVA O RESULTADO NO CACHE ANTES DE RETORNAR
    CACHE_PRODUTOS[termo_busca] = {
        "timestamp": tempo_atual,
        "resultado": resultado_final
    }

    return resultado_final