"""Organograma da empresa: setores, funcionarios-agentese o pipeline de estagios.

A planta do escritorio usa coordenadas percentuais (0-100) para o dashboard.
"""
from __future__ import annotations

from . import config

# id, nome, funcao, emoji, cor, x, y, papel
SETORES = [
    {"id": "gerencia", "nome": "Gerência", "funcao": "Direção e despacho de demandas",
     "emoji": "🧑‍💼", "cor": "#f5c542", "mesa_x": 88, "mesa_y": 52, "papel": "gerente"},

    {"id": "pesquisa", "nome": "Pesquisa & Mercado", "funcao": "Nichos lucrativos e validação",
     "emoji": "🔎", "cor": "#4fc3f7", "mesa_x": 40, "mesa_y": 30, "papel": "funcionario"},
    {"id": "produto", "nome": "Produto & UX", "funcao": "Especificação, telas e escopo",
     "emoji": "📐", "cor": "#9575cd", "mesa_x": 40, "mesa_y": 48, "papel": "funcionario"},
    {"id": "web_designer", "nome": "Web Designer", "funcao": "Identidade visual, UI e páginas",
     "emoji": "🎨", "cor": "#f48fb1", "mesa_x": 63, "mesa_y": 86, "papel": "funcionario"},
    {"id": "especialista", "nome": "Especialistas", "funcao": "Consultoria técnica e boas práticas",
     "emoji": "🛠️", "cor": "#b0bec5", "mesa_x": 88, "mesa_y": 30, "papel": "funcionario"},
    {"id": "auditoria", "nome": "Auditoria", "funcao": "Auditoria independente (segurança e risco)",
     "emoji": "🕵️", "cor": "#ff8a65", "mesa_x": 17, "mesa_y": 86, "papel": "funcionario"},
    {"id": "financeiro", "nome": "Financeiro & BI", "funcao": "Receita, custos e métricas",
     "emoji": "📊", "cor": "#4db6ac", "mesa_x": 17, "mesa_y": 48, "papel": "funcionario"},
    {"id": "banco_dados", "nome": "Banco de Dados", "funcao": "Modelagem, SQL e persistência",
     "emoji": "🗃️", "cor": "#7986cb", "mesa_x": 40, "mesa_y": 63, "papel": "funcionario"},

    {"id": "dev_web", "nome": "Desenvolvimento Web", "funcao": "Apps web que geram receita",
     "emoji": "🌐", "cor": "#81c784", "mesa_x": 63, "mesa_y": 30, "papel": "funcionario"},
    {"id": "web_developer", "nome": "Web Developer", "funcao": "Integração e páginas web",
     "emoji": "🧩", "cor": "#aed581", "mesa_x": 88, "mesa_y": 30, "papel": "funcionario"},
    {"id": "frontend", "nome": "Front-End", "funcao": "Interface, componentes e experiência web",
     "emoji": "💻", "cor": "#64b5f6", "mesa_x": 63, "mesa_y": 48, "papel": "funcionario"},
    {"id": "backend", "nome": "Back-End", "funcao": "Serviços, APIs e lógica de servidor",
     "emoji": "⚙️", "cor": "#90a4ae", "mesa_x": 40, "mesa_y": 78, "papel": "funcionario"},
    {"id": "python", "nome": "Python", "funcao": "Automações e scripts",
     "emoji": "🐍", "cor": "#ffd54f", "mesa_x": 63, "mesa_y": 63, "papel": "funcionario"},
    {"id": "dev_android", "nome": "Desenvolvimento Android", "funcao": "Apps Android lucrativos",
     "emoji": "📱", "cor": "#aed581", "mesa_x": 63, "mesa_y": 63, "papel": "funcionario"},
    {"id": "ios", "nome": "iOS (Apple)", "funcao": "Apps iOS/Swift",
     "emoji": "🍎", "cor": "#ce93d8", "mesa_x": 88, "mesa_y": 48, "papel": "funcionario"},
    {"id": "qa", "nome": "Qualidade", "funcao": "Testes, revisão e correção",
     "emoji": "🧪", "cor": "#ffb74d", "mesa_x": 17, "mesa_y": 63, "papel": "funcionario"},
    {"id": "marketing", "nome": "Monetização & Growth", "funcao": "Preço, canal e lançamento",
     "emoji": "📣", "cor": "#f06292", "mesa_x": 17, "mesa_y": 30, "papel": "funcionario"},
]

# nome humano + modelo de cada funcionario-agente
FUNCIONARIOS = {
    "gerencia":    {"nome": "Aurélio (Gerente)",    "emoji": "🧑‍💼", "modelo": config.MODELO_PLANEJADOR},
    "pesquisa":    {"nome": "Bruna (Mercado)",      "emoji": "🔎", "modelo": config.MODELO_PLANEJADOR},
    "produto":     {"nome": "Caio (Produto)",       "emoji": "📐", "modelo": config.MODELO_PLANEJADOR},
    "web_designer": {"nome": "Nina (Web Designer)",  "emoji": "🎨", "modelo": config.MODELO_PLANEJADOR},
    "especialista": {"nome": "Kléber (Especialista)", "emoji": "🛠️", "modelo": config.MODELO_PLANEJADOR},
    "auditoria":   {"nome": "Larissa (Auditoria)",  "emoji": "🕵️", "modelo": config.MODELO_PLANEJADOR},
    "financeiro":  {"nome": "Dora (Financeiro)",    "emoji": "📊", "modelo": config.MODELO_PLANEJADOR},
    "banco_dados": {"nome": "Mauro (Banco de Dados)", "emoji": "🗃️", "modelo": config.MODELO_CODIGO},
    "dev_web":     {"nome": "Edu (Dev Web)",        "emoji": "🌐", "modelo": config.MODELO_CODIGO},
    "web_developer": {"nome": "Otávio (Web Dev)",   "emoji": "🧩", "modelo": config.MODELO_CODIGO},
    "frontend":    {"nome": "Júlia (Front-End)",    "emoji": "💻", "modelo": config.MODELO_CODIGO},
    "backend":     {"nome": "Igor (Back-End)",      "emoji": "⚙️", "modelo": config.MODELO_CODIGO},
    "python":      {"nome": "Paula (Python)",       "emoji": "🐍", "modelo": config.MODELO_CODIGO},
    "dev_android": {"nome": "Fábio (Dev Android)",  "emoji": "📱", "modelo": config.MODELO_CODIGO},
    "ios":         {"nome": "Queila (iOS)",         "emoji": "🍎", "modelo": config.MODELO_CODIGO},
    "qa":          {"nome": "Gabi (QA)",            "emoji": "🧪", "modelo": config.MODELO_CODIGO},
    "marketing":   {"nome": "Helena (Growth)",      "emoji": "📣", "modelo": config.MODELO_PLANEJADOR},
}

# Pipeline: cada estagio pertence a um setor (ou escolhe por tipo de produto).
ESTAGIOS: list[dict] = [
    {"id": "ideia",       "setor": "pesquisa",     "titulo": "Mapear ideias lucrativas"},
    {"id": "validacao",   "setor": "pesquisa",     "titulo": "Validar demanda e concorrência"},
    {"id": "spec",        "setor": "produto",      "titulo": "Escrever especificação do produto"},
    {"id": "design",      "setor": "produto",      "titulo": "Desenhar telas e fluxos"},
    {"id": "visual",      "setor": "web_designer", "titulo": "Criar identidade visual e UI"},
    {"id": "arquitetura", "setor": "banco_dados",  "titulo": "Modelar dados e API/backend"},
    {"id": "build",       "setor": None,           "titulo": "Construir o sistema"},  # web/android/ios
    {"id": "teste",       "setor": "qa",           "titulo": "Testar e reportar falhas"},
    {"id": "revisao",     "setor": "auditoria",    "titulo": "Auditoria de segurança e risco"},
    {"id": "backend",     "setor": "backend",      "titulo": "Revisar/ajustar o backend"},
    {"id": "frontend",    "setor": "frontend",     "titulo": "Revisar/ajustar a interface"},
    {"id": "automacao",   "setor": "python",       "titulo": "Scripts e automações auxiliares"},
    {"id": "consultoria", "setor": "especialista", "titulo": "Revisão técnica especializada"},
    {"id": "monetizacao", "setor": "marketing",    "titulo": "Definir preço e canal"},
    {"id": "lancamento",  "setor": "financeiro",   "titulo": "Projeção de receita e lançamento"},
]

ORDEM = [e["id"] for e in ESTAGIOS]


def setor_do_estagio(estagio: str, tipo: str | None = None) -> str | None:
    for e in ESTAGIOS:
        if e["id"] == estagio:
            if e["id"] == "build":
                t = (tipo or "").lower()
                if t.startswith("ios"):
                    return "ios"
                if t.startswith("android"):
                    return "dev_android"
                return "dev_web"
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
