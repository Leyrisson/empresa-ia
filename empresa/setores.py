"""Organograma do My AI Office: setores, funcionarios-agentes e pipeline.

A fábrica constrói SISTEMAS DE INFRAESTRUTURA DE TI, DevOps/AIOps e segurança
(multi-fabricante: Palo Alto, MikroTik, FortiGate, Cisco...), gestão de mudanças
(GMUD) e auditoria ISO 27001/CIS — vendidos a empresas de tecnologia.

A planta (`PLANTA`) é a fonte única da planta baixa: `db._sembrar_office` a
dessmina no banco e o dashboard (2D e 3D) a lê de lá. Coordenadas em grade
percentual/métrica (c1..c5 x r1..r5) para o dashboard.
"""
from __future__ import annotations

from . import config

# id, nome, funcao, emoji, cor, mesa_x, mesa_y, papel
SETORES = [
    {"id": "gerencia", "nome": "Gerência", "funcao": "Direção, estratégia e despacho",
     "emoji": "🧑‍💼", "cor": "#f5c542", "mesa_x": 12.1, "mesa_y": 5.5, "papel": "gerente"},

    # --- comercial ---
    {"id": "pesquisa", "nome": "Pesquisa & Mercado", "funcao": "Inteligência de mercado e validação B2B",
     "emoji": "🔎", "cor": "#4fc3f7", "mesa_x": 1.7, "mesa_y": -2.9, "papel": "funcionario"},
    {"id": "marketing", "nome": "Marketing & Growth", "funcao": "Posicionamento, conteúdo e aquisição",
     "emoji": "📣", "cor": "#f06292", "mesa_x": 1.7, "mesa_y": -0.1, "papel": "funcionario"},
    {"id": "vendas", "nome": "Vendas B2B", "funcao": "Pipeline, propostas e negociação com empresas",
     "emoji": "🤝", "cor": "#e57373", "mesa_x": 1.7, "mesa_y": 2.7, "papel": "funcionario"},
    {"id": "financeiro", "nome": "Financeiro", "funcao": "Receita, custos e precificação",
     "emoji": "💰", "cor": "#d4a017", "mesa_x": 1.7, "mesa_y": 5.5, "papel": "funcionario"},

    # --- produto / ui ---
    {"id": "produto", "nome": "Produto & UX", "funcao": "Especificação, escopo e fluxos",
     "emoji": "📐", "cor": "#9575cd", "mesa_x": 4.3, "mesa_y": -5.7, "papel": "funcionario"},
    {"id": "web_designer", "nome": "Web Designer", "funcao": "Identidade visual e interface",
     "emoji": "🎨", "cor": "#f48fb1", "mesa_x": 4.3, "mesa_y": -2.9, "papel": "funcionario"},
    {"id": "frontend", "nome": "Front-End", "funcao": "Interface e experiência do operador",
     "emoji": "💻", "cor": "#64b5f6", "mesa_x": 4.3, "mesa_y": -0.1, "papel": "funcionario"},
    {"id": "dev_web", "nome": "Desenvolvimento Web", "funcao": "Apps web de produto e painéis",
     "emoji": "🌐", "cor": "#81c784", "mesa_x": 4.3, "mesa_y": 2.7, "papel": "funcionario"},
    {"id": "backend", "nome": "Back-End", "funcao": "APIs, serviços e coleta de dados",
     "emoji": "⚙️", "cor": "#90a4ae", "mesa_x": 4.3, "mesa_y": 5.5, "papel": "funcionario"},

    # --- dados / qualidade ---
    {"id": "banco_dados", "nome": "Banco de Dados", "funcao": "Modelagem, SQL e persistência",
     "emoji": "🗃️", "cor": "#7986cb", "mesa_x": 6.9, "mesa_y": -5.7, "papel": "funcionario"},
    {"id": "dados_bi", "nome": "Dados & BI", "funcao": "Métricas, painéis e análise de operação",
     "emoji": "📊", "cor": "#4db6ac", "mesa_x": 6.9, "mesa_y": -2.9, "papel": "funcionario"},
    {"id": "ml", "nome": "ML & IA", "funcao": "Modelos, avaliação e inferência local",
     "emoji": "🧠", "cor": "#ba68c8", "mesa_x": 6.9, "mesa_y": -0.1, "papel": "funcionario"},
    {"id": "qa", "nome": "Qualidade", "funcao": "Testes, verificação e evidência",
     "emoji": "🧪", "cor": "#ffb74d", "mesa_x": 6.9, "mesa_y": 2.7, "papel": "funcionario"},
    {"id": "auditoria", "nome": "Auditoria", "funcao": "Revisão independente de segurança e risco",
     "emoji": "🕵️", "cor": "#ff8a65", "mesa_x": 6.9, "mesa_y": 5.5, "papel": "funcionario"},

    # --- infraestrutura ---
    {"id": "plataforma", "nome": "Eng. de Plataforma", "funcao": "Linux, containers, servidores e K8s",
     "emoji": "🏗️", "cor": "#5c6bc0", "mesa_x": 9.5, "mesa_y": -5.7, "papel": "funcionario"},
    {"id": "eng_redes", "nome": "Eng. de Redes", "funcao": "Multi-fabricante: Palo Alto, MikroTik, FortiGate, Cisco, Juniper",
     "emoji": "🔌", "cor": "#26c6da", "mesa_x": 9.5, "mesa_y": -2.9, "papel": "funcionario"},
    {"id": "devops", "nome": "DevOps & SRE", "funcao": "CI/CD, infra as code, deploy e confiabilidade",
     "emoji": "🔄", "cor": "#66bb6a", "mesa_x": 9.5, "mesa_y": -0.1, "papel": "funcionario"},
    {"id": "aiops", "nome": "AIOps & Observabilidade", "funcao": "Monitoramento, alertas e correlação de eventos",
     "emoji": "📡", "cor": "#29b6f6", "mesa_x": 9.5, "mesa_y": 2.7, "papel": "funcionario"},
    {"id": "seguranca", "nome": "Segurança & SOC", "funcao": "Firewall, hardening, detecção e resposta",
     "emoji": "🛡️", "cor": "#ef5350", "mesa_x": 9.5, "mesa_y": 5.5, "papel": "funcionario"},

    # --- operações / governança ---
    {"id": "gmud", "nome": "GMUD & Mudanças", "funcao": "Gestão de mudanças, janelas e rollback",
     "emoji": "🔀", "cor": "#ffa726", "mesa_x": 12.1, "mesa_y": -5.7, "papel": "funcionario"},
    {"id": "compliance", "nome": "Compliance ISO/CIS", "funcao": "Auditoria ISO 27001 e CIS Benchmarks",
     "emoji": "📋", "cor": "#8d6e63", "mesa_x": 12.1, "mesa_y": -2.9, "papel": "funcionario"},
    {"id": "automacao", "nome": "Automação & Integrações", "funcao": "Scripts, APIs e integrações de operação",
     "emoji": "🐍", "cor": "#ffd54f", "mesa_x": 12.1, "mesa_y": -0.1, "papel": "funcionario"},
    {"id": "especialista", "nome": "Especialistas", "funcao": "Consultoria técnica sênior",
     "emoji": "🛠️", "cor": "#b0bec5", "mesa_x": 12.1, "mesa_y": 2.7, "papel": "funcionario"},
]

# nome humano + modelo de cada funcionario-agente
FUNCIONARIOS = {
    "gerencia":     {"nome": "Aurélio (Gerente)",       "emoji": "🧑‍💼", "modelo": config.MODELO_PLANEJADOR},
    "pesquisa":     {"nome": "Bruna (Mercado)",         "emoji": "🔎", "modelo": config.MODELO_PLANEJADOR},
    "marketing":    {"nome": "Helena (Growth)",         "emoji": "📣", "modelo": config.MODELO_PLANEJADOR},
    "vendas":       {"nome": "Vera (Vendas B2B)",       "emoji": "🤝", "modelo": config.MODELO_PLANEJADOR},
    "financeiro":   {"nome": "Dora (Financeiro)",       "emoji": "💰", "modelo": config.MODELO_PLANEJADOR},
    "produto":      {"nome": "Caio (Produto)",          "emoji": "📐", "modelo": config.MODELO_PLANEJADOR},
    "web_designer": {"nome": "Nina (Web Designer)",     "emoji": "🎨", "modelo": config.MODELO_PLANEJADOR},
    "frontend":     {"nome": "Júlia (Front-End)",       "emoji": "💻", "modelo": config.MODELO_CODIGO},
    "dev_web":      {"nome": "Edu (Dev Web)",           "emoji": "🌐", "modelo": config.MODELO_CODIGO},
    "backend":      {"nome": "Igor (Back-End)",         "emoji": "⚙️", "modelo": config.MODELO_CODIGO},
    "banco_dados":  {"nome": "Mauro (Banco de Dados)",  "emoji": "🗃️", "modelo": config.MODELO_CODIGO},
    "dados_bi":     {"nome": "Bianca (Dados & BI)",     "emoji": "📊", "modelo": config.MODELO_CODIGO},
    "ml":           {"nome": "Márcio (ML & IA)",        "emoji": "🧠", "modelo": config.MODELO_CODIGO},
    "qa":           {"nome": "Gabi (QA)",               "emoji": "🧪", "modelo": config.MODELO_PLANEJADOR},
    "auditoria":    {"nome": "Larissa (Auditoria)",     "emoji": "🕵️", "modelo": config.MODELO_PLANEJADOR},
    "plataforma":   {"nome": "Paulo (Plataforma)",      "emoji": "🏗️", "modelo": config.MODELO_CODIGO},
    "eng_redes":    {"nome": "Ricardo (Eng. de Redes)", "emoji": "🔌", "modelo": config.MODELO_CODIGO},
    "devops":       {"nome": "Diego (DevOps)",          "emoji": "🔄", "modelo": config.MODELO_CODIGO},
    "aiops":        {"nome": "Aline (AIOps)",           "emoji": "📡", "modelo": config.MODELO_CODIGO},
    "seguranca":    {"nome": "Sérgio (Segurança)",      "emoji": "🛡️", "modelo": config.MODELO_CODIGO},
    "gmud":         {"nome": "Gustavo (GMUD)",          "emoji": "🔀", "modelo": config.MODELO_PLANEJADOR},
    "compliance":   {"nome": "Célia (Compliance)",      "emoji": "📋", "modelo": config.MODELO_PLANEJADOR},
    "automacao":    {"nome": "Paula (Automação)",       "emoji": "🐍", "modelo": config.MODELO_CODIGO},
    "especialista": {"nome": "Kléber (Especialista)",   "emoji": "🛠️", "modelo": config.MODELO_PLANEJADOR},
}

# ------------------------------------------------------------------ planta
# Grade 5 colunas x 5 fileiras. Salas sem setor (recepção, reunião, copa)
# existem só na planta — não têm agente.
COL = {"c1": 1.7, "c2": 4.3, "c3": 6.9, "c4": 9.5, "c5": 12.1}
ROW = {"r1": -5.7, "r2": -2.9, "r3": -0.1, "r4": 2.7, "r5": 5.5}

# nome, setor (ou None), tema, cor, coluna, fileira
PLANTA: list[dict] = [
    # comercial / admin
    {"nome": "Recepção", "setor": None, "tema": "recepcao", "cor": "#39405a", "col": "c1", "row": "r1"},
    {"nome": "Pesquisa & Mercado", "setor": "pesquisa", "tema": "comercial", "cor": "#26374a", "col": "c1", "row": "r2"},
    {"nome": "Marketing & Growth", "setor": "marketing", "tema": "comercial", "cor": "#463026", "col": "c1", "row": "r3"},
    {"nome": "Vendas B2B", "setor": "vendas", "tema": "comercial", "cor": "#4a2626", "col": "c1", "row": "r4"},
    {"nome": "Financeiro", "setor": "financeiro", "tema": "comercial", "cor": "#463c26", "col": "c1", "row": "r5"},

    # produto / ui
    {"nome": "Produto & UX", "setor": "produto", "tema": "produto", "cor": "#2e3a4a", "col": "c2", "row": "r1"},
    {"nome": "Web Designer", "setor": "web_designer", "tema": "ui", "cor": "#3a2636", "col": "c2", "row": "r2"},
    {"nome": "Front-End", "setor": "frontend", "tema": "ui", "cor": "#20354a", "col": "c2", "row": "r3"},
    {"nome": "Desenvolvimento Web", "setor": "dev_web", "tema": "dev", "cor": "#1f3a4a", "col": "c2", "row": "r4"},
    {"nome": "Back-End", "setor": "backend", "tema": "dev", "cor": "#33353d", "col": "c2", "row": "r5"},

    # dados / qualidade
    {"nome": "Banco de Dados", "setor": "banco_dados", "tema": "dados", "cor": "#2a3242", "col": "c3", "row": "r1"},
    {"nome": "Dados & BI", "setor": "dados_bi", "tema": "bi", "cor": "#26403a", "col": "c3", "row": "r2"},
    {"nome": "ML & IA", "setor": "ml", "tema": "ml", "cor": "#3a2a44", "col": "c3", "row": "r3"},
    {"nome": "Qualidade", "setor": "qa", "tema": "qa", "cor": "#2a2436", "col": "c3", "row": "r4"},
    {"nome": "Auditoria", "setor": "auditoria", "tema": "auditoria", "cor": "#3a2733", "col": "c3", "row": "r5"},

    # infraestrutura
    {"nome": "Eng. de Plataforma", "setor": "plataforma", "tema": "plataforma", "cor": "#262f4a", "col": "c4", "row": "r1"},
    {"nome": "Eng. de Redes", "setor": "eng_redes", "tema": "rede", "cor": "#1f3a44", "col": "c4", "row": "r2"},
    {"nome": "DevOps & SRE", "setor": "devops", "tema": "devops", "cor": "#1f3a2e", "col": "c4", "row": "r3"},
    {"nome": "AIOps & Observabilidade", "setor": "aiops", "tema": "noc", "cor": "#1d3346", "col": "c4", "row": "r4"},
    {"nome": "Segurança & SOC", "setor": "seguranca", "tema": "soc", "cor": "#3a2024", "col": "c4", "row": "r5"},

    # operações / governança
    {"nome": "GMUD & Mudanças", "setor": "gmud", "tema": "gmud", "cor": "#3a3220", "col": "c5", "row": "r1"},
    {"nome": "Compliance ISO/CIS", "setor": "compliance", "tema": "compliance", "cor": "#332a24", "col": "c5", "row": "r2"},
    {"nome": "Automação & Integrações", "setor": "automacao", "tema": "automacao", "cor": "#3a351f", "col": "c5", "row": "r3"},
    {"nome": "Especialistas", "setor": "especialista", "tema": "especialista", "cor": "#2e3340", "col": "c5", "row": "r4"},
    {"nome": "Gerência", "setor": "gerencia", "tema": "gerencia", "cor": "#3f3a55", "col": "c5", "row": "r5"},

    # salas ambientes (fora do grid, à direita)
    {"nome": "Sala de Reunião", "setor": None, "tema": "reuniao", "cor": "#2f2a40",
     "x": 14.7, "z": -2.9, "lx": 2.4, "lz": 3.4},
    {"nome": "Copa", "setor": None, "tema": "copa", "cor": "#3a3a2a",
     "x": 14.7, "z": 4.1, "lx": 1.9, "lz": 2.0},
]

LX_PADRAO, LZ_PADRAO = 1.9, 2.55


# Pipeline: cada estagio pertence a um setor (ou escolhe por tipo de produto).
ESTAGIOS: list[dict] = [
    {"id": "ideia",           "setor": "pesquisa",     "titulo": "Mapear o problema e o comprador"},
    {"id": "validacao",       "setor": "pesquisa",     "titulo": "Validar demanda, concorrência e regulação"},
    {"id": "spec",            "setor": "produto",      "titulo": "Escrever especificação e escopo MVP"},
    {"id": "design",          "setor": "produto",      "titulo": "Desenhar telas e fluxos do operador"},
    {"id": "visual",          "setor": "web_designer", "titulo": "Criar identidade visual e UI"},
    {"id": "arquitetura",     "setor": "eng_redes",    "titulo": "Modelar adaptadores multi-fabricante e API"},
    {"id": "esquema",         "setor": "banco_dados",  "titulo": "Modelar o esquema SQLite e a persistência"},
    {"id": "build",           "setor": None,           "titulo": "Construir o sistema"},
    {"id": "deploy",          "setor": "plataforma",   "titulo": "Empacotar, subir e documentar a operação"},
    {"id": "pipeline",        "setor": "devops",       "titulo": "Pipeline de build, teste e release"},
    {"id": "teste",           "setor": "qa",           "titulo": "Testar e reportar falhas"},
    {"id": "revisao",         "setor": "auditoria",    "titulo": "Auditoria independente de segurança e risco"},
    {"id": "hardening",       "setor": "seguranca",    "titulo": "Hardening: senhas, TLS, cabeçalhos, segredos"},
    {"id": "gmud",            "setor": "gmud",         "titulo": "Plano de mudança, janela e rollback"},
    {"id": "conformidade",    "setor": "compliance",   "titulo": "Laudo de conformidade ISO 27001 / CIS"},
    {"id": "observabilidade", "setor": "aiops",        "titulo": "Logs, métricas, healthcheck e alertas"},
    {"id": "anomalia",        "setor": "ml",           "titulo": "Detecção de anomalia e analytics embutida"},
    {"id": "metricas",        "setor": "dados_bi",     "titulo": "Painel de métricas e dicionário de dados"},
    {"id": "backend",         "setor": "backend",      "titulo": "Revisar/ajustar o back-end"},
    {"id": "frontend",        "setor": "frontend",     "titulo": "Revisar/ajustar a interface"},
    {"id": "automacao",       "setor": "automacao",    "titulo": "Scripts de operação e integrações"},
    {"id": "consultoria",     "setor": "especialista", "titulo": "Revisão técnica especializada"},
    {"id": "posicionamento",  "setor": "marketing",    "titulo": "Posicionamento, landing e conteúdo"},
    {"id": "monetizacao",     "setor": "vendas",       "titulo": "Preço, proposta e canal de venda B2B"},
    {"id": "lancamento",      "setor": "financeiro",   "titulo": "Projeção de receita e lançamento"},
]

ORDEM = [e["id"] for e in ESTAGIOS]


def setor_do_estagio(estagio: str, tipo: str | None = None) -> str | None:
    for e in ESTAGIOS:
        if e["id"] == estagio:
            if e["id"] == "build":
                # Produtos de infra são web (painel/CLI com interface web).
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


def ids_setores() -> list[str]:
    return [s["id"] for s in SETORES]
