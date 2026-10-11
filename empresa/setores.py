"""Organograma da empresa: setores, funcionarios-agentese o pipeline de estagios.

A planta do escritorio usa coordenadas percentuais (0-100) para o dashboard.
"""
from __future__ import annotations

from . import config

# id, nome, funcao, emoji, cor, x, y, papel
SETORES = [
    {"id": "gerencia", "nome": "Gerência", "funcao": "Direção e despacho de demandas",
     "emoji": "🧑‍💼", "cor": "#f5c542", "mesa_x": 50, "mesa_y": 12, "papel": "gerente"},

    {"id": "pesquisa", "nome": "Pesquisa & Mercado", "funcao": "Nichos lucrativos e validação",
     "emoji": "🔎", "cor": "#4fc3f7", "mesa_x": 22, "mesa_y": 36, "papel": "funcionario"},
    {"id": "produto", "nome": "Produto & UX", "funcao": "Especificação, telas e escopo",
     "emoji": "📐", "cor": "#9575cd", "mesa_x": 50, "mesa_y": 36, "papel": "funcionario"},
    {"id": "financeiro", "nome": "Financeiro & BI", "funcao": "Receita, custos e métricas",
     "emoji": "📊", "cor": "#4db6ac", "mesa_x": 78, "mesa_y": 36, "papel": "funcionario"},

    {"id": "dev_web", "nome": "Desenvolvimento Web", "funcao": "Apps web que geram receita",
     "emoji": "🌐", "cor": "#81c784", "mesa_x": 20, "mesa_y": 66, "papel": "funcionario"},
    {"id": "dev_android", "nome": "Desenvolvimento Android", "funcao": "Apps Android lucrativos",
     "emoji": "📱", "cor": "#aed581", "mesa_x": 40, "mesa_y": 66, "papel": "funcionario"},
    {"id": "qa", "nome": "Qualidade", "funcao": "Testes, revisão e correção",
     "emoji": "🧪", "cor": "#ffb74d", "mesa_x": 60, "mesa_y": 66, "papel": "funcionario"},
    {"id": "marketing", "nome": "Monetização & Growth", "funcao": "Preço, canal e lançamento",
     "emoji": "📣", "cor": "#f06292", "mesa_x": 80, "mesa_y": 66, "papel": "funcionario"},
]

# nome humano + modelo de cada funcionario-agente
FUNCIONARIOS = {
    "gerencia":    {"nome": "Aurélio (Gerente)",   "emoji": "🧑‍💼", "modelo": config.MODELO_PLANEJADOR},
    "pesquisa":    {"nome": "Bruna (Mercado)",     "emoji": "🔎", "modelo": config.MODELO_PLANEJADOR},
    "produto":     {"nome": "Caio (Produto)",      "emoji": "📐", "modelo": config.MODELO_PLANEJADOR},
    "financeiro":  {"nome": "Dora (Financeiro)",   "emoji": "📊", "modelo": config.MODELO_PLANEJADOR},
    "dev_web":     {"nome": "Edu (Dev Web)",       "emoji": "🌐", "modelo": config.MODELO_CODIGO},
    "dev_android": {"nome": "Fábio (Dev Android)", "emoji": "📱", "modelo": config.MODELO_CODIGO},
    "qa":          {"nome": "Gabi (QA)",           "emoji": "🧪", "modelo": config.MODELO_CODIGO},
    "marketing":   {"nome": "Helena (Growth)",     "emoji": "📣", "modelo": config.MODELO_PLANEJADOR},
}

# Pipeline: cada estagio pertence a um setor (ou escolhe por tipo de produto).
ESTAGIOS: list[dict] = [
    {"id": "ideia",       "setor": "pesquisa",   "titulo": "Mapear ideias lucrativas"},
    {"id": "validacao",   "setor": "pesquisa",   "titulo": "Validar demanda e concorrência"},
    {"id": "spec",        "setor": "produto",    "titulo": "Escrever especificação do produto"},
    {"id": "design",      "setor": "produto",    "titulo": "Desenhar telas e fluxos"},
    {"id": "build",       "setor": None,         "titulo": "Construir o sistema"},  # web/android
    {"id": "teste",       "setor": "qa",         "titulo": "Testar e reportar falhas"},
    {"id": "monetizacao", "setor": "marketing",  "titulo": "Definir preço e canal"},
    {"id": "lancamento",  "setor": "financeiro", "titulo": "Projeção de receita e lançamento"},
]

ORDEM = [e["id"] for e in ESTAGIOS]


def setor_do_estagio(estagio: str, tipo: str | None = None) -> str | None:
    for e in ESTAGIOS:
        if e["id"] == estagio:
            if e["id"] == "build":
                return "dev_android" if (tipo or "").lower().startswith("android") else "dev_web"
            return e["setor"]
    return None


def proximo_estagio(atual: str) -> str | None:
    try:
        i = ORDEM.index(atual)
    except ValueError:
        return None
    return ORDEM[i + 1] if i + 1 < len(ORDEM) else None


def progresso(estagio: str) -> int:
    try:
        return int(round(100 * ORDEM.index(estagio) / (len(ORDEM) - 1)))
    except ValueError:
        return 0
