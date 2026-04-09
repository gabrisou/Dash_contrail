"""
Contrail Chat - Servidor Flask + Claude API + API TI Contrail
Deploy no Railway
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests
import json
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# Configuracoes
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONTRAIL_API_BASE = os.getenv("CONTRAIL_API_BASE", "https://api-read.contrail.com.br")
CONTRAIL_API_KEY  = os.getenv("CONTRAIL_API_KEY",  "3Ydk7CP3JRJMOH9zU1qKSk3VT5k0bRMmh77FaeZsVPdOCXff")
HEADERS_TI        = {"X-API-Key": CONTRAIL_API_KEY}
LIMIT_MAX         = 500

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Funcoes de consulta
def consultar_endpoint(endpoint, params):
    try:
        if "limit" in params:
            params["limit"] = min(int(params["limit"]), LIMIT_MAX)
        r = requests.get(
            f"{CONTRAIL_API_BASE}/api/v1/{endpoint}",
            headers=HEADERS_TI,
            params=params,
            timeout=30
        )
        return r.json()
    except Exception as e:
        return {"erro": str(e)}

def meta_endpoint(endpoint):
    try:
        r = requests.get(
            f"{CONTRAIL_API_BASE}/api/v1/meta/{endpoint}",
            headers=HEADERS_TI,
            timeout=15
        )
        return r.json()
    except Exception as e:
        return {"erro": str(e)}

def chamar_ferramenta(nome, inputs):
    mapa = {
        "consultar_financeiro":  "financeiro",
        "consultar_tracking":    "tracking",
        "consultar_documentos":  "documentos",
        "consultar_movimentos":  "movimentos-cheio",
    }
    mapa_meta = {
        "meta_financeiro":  "financeiro",
        "meta_tracking":    "tracking",
        "meta_documentos":  "documentos",
        "meta_movimentos":  "movimentos-cheio",
    }
    if nome in mapa:
        return json.dumps(consultar_endpoint(mapa[nome], inputs), ensure_ascii=False, default=str)
    if nome in mapa_meta:
        return json.dumps(meta_endpoint(mapa_meta[nome]), ensure_ascii=False, default=str)
    return "Ferramenta nao encontrada"

# Ferramentas para o Claude
TOOLS = [
    {
        "name": "consultar_financeiro",
        "description": (
            "Consulta dados financeiros e de viagens da Contrail (bi_financeiro). "
            "Use para perguntas sobre viagens, fretes, carretas, clientes, faturamento, operacoes. "
            "Filtros: eq_<coluna>=valor (exato), like_<coluna>=valor (parcial), "
            "date_column=<coluna>, date_start=YYYY-MM-DD, date_end=YYYY-MM-DD, "
            "order_by=<coluna>, order_dir=asc|desc, limit, offset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":       {"type": "integer", "description": "Numero de registros max 500"},
                "offset":      {"type": "integer", "description": "Paginacao"},
                "order_by":    {"type": "string",  "description": "Coluna para ordenar"},
                "order_dir":   {"type": "string",  "description": "asc ou desc"},
                "date_column": {"type": "string",  "description": "Coluna de data"},
                "date_start":  {"type": "string",  "description": "Data inicio YYYY-MM-DD"},
                "date_end":    {"type": "string",  "description": "Data fim YYYY-MM-DD"}
            }
        }
    },
    {
        "name": "consultar_tracking",
        "description": "Consulta dados de tracking/rastreamento. Mesmos filtros do financeiro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"}, "offset": {"type": "integer"},
                "order_by": {"type": "string"}, "order_dir": {"type": "string"},
                "date_column": {"type": "string"}, "date_start": {"type": "string"}, "date_end": {"type": "string"}
            }
        }
    },
    {
        "name": "consultar_documentos",
        "description": "Consulta documentos da Contrail (CTe, NFe). Mesmos filtros do financeiro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"}, "offset": {"type": "integer"},
                "order_by": {"type": "string"}, "order_dir": {"type": "string"},
                "date_column": {"type": "string"}, "date_start": {"type": "string"}, "date_end": {"type": "string"}
            }
        }
    },
    {
        "name": "consultar_movimentos",
        "description": "Consulta movimentos de cheio (sistiju). Mesmos filtros do financeiro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"}, "offset": {"type": "integer"},
                "order_by": {"type": "string"}, "order_dir": {"type": "string"},
                "date_column": {"type": "string"}, "date_start": {"type": "string"}, "date_end": {"type": "string"}
            }
        }
    },
    {
        "name": "meta_financeiro",
        "description": "Retorna colunas disponiveis e tipos do financeiro. Use quando nao souber o nome exato de uma coluna.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "meta_tracking",
        "description": "Retorna colunas disponiveis do tracking.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "meta_documentos",
        "description": "Retorna colunas disponiveis dos documentos.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "meta_movimentos",
        "description": "Retorna colunas disponiveis dos movimentos.",
        "input_schema": {"type": "object", "properties": {}}
    }
]

SYSTEM = (
    "Voce e o assistente de dados da Contrail Logistica S.A., Jundiai-SP.\n\n"
    "Voce acessa a API oficial da Contrail com 4 fontes:\n"
    "- financeiro: viagens, fretes, carretas, clientes, faturamento\n"
    "- tracking: rastreamento de veiculos\n"
    "- documentos: CTe, NFe e outros documentos\n"
    "- movimentos-cheio: movimentos de containers cheios\n\n"
    "Como usar os filtros:\n"
    "- Filtro exato: eq_cliente=UNIMETAL\n"
    "- Filtro parcial: like_cliente=UNIMETAL\n"
    "- Filtro de data: date_column=hora_planejamento, date_start=2026-04-04, date_end=2026-04-04\n"
    "- Ordenacao: order_by=hora_planejamento, order_dir=desc\n\n"
    "REGRAS:\n"
    "- Use meta_financeiro se nao souber os nomes das colunas\n"
    "- Nao adicione filtros que o usuario nao pediu\n"
    "- Responda em portugues brasileiro\n"
    "- Formate valores monetarios como R$ X.XXX\n"
    "- Se precisar de mais dados use offset para paginar"
)

# Endpoint do chat
@app.route("/chat", methods=["POST"])
def chat():
    data     = request.json
    pergunta = data.get("mensagem", "")
    historico = data.get("historico", [])

    if not pergunta:
        return jsonify({"erro": "Mensagem vazia"}), 400

    messages = historico + [{"role": "user", "content": pergunta}]

    def serializar(content):
        result = []
        for block in content:
            if hasattr(block, 'type'):
                if block.type == 'text':
                    result.append({"type": "text", "text": block.text})
                elif block.type == 'tool_use':
                    result.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
            elif isinstance(block, dict):
                result.append(block)
        return result

    try:
        while True:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages
            )

            content_s = serializar(response.content)
            messages.append({"role": "assistant", "content": content_s})

            if response.stop_reason == "end_turn":
                texto = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        texto += block.text
                return jsonify({"resposta": texto, "historico": messages})

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if hasattr(block, 'type') and block.type == "tool_use":
                        resultado = chamar_ferramenta(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": resultado
                        })
                messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "Contrail Chat", "api": CONTRAIL_API_BASE})

@app.route("/ping-api", methods=["GET"])
def ping_api():
    try:
        r = requests.get(f"{CONTRAIL_API_BASE}/health", headers=HEADERS_TI, timeout=10)
        return jsonify({"status": "ok", "contrail_api": r.json()})
    except Exception as e:
        return jsonify({"status": "erro", "detalhe": str(e)})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
