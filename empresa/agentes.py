"""Os agentes: o Gerente (Aurélio) e os funcionários de cada setor.

Fluxo:
  Gerente cria um produto (pedindo ideia a Pesquisa) -> despacha o estagio atual
  para o setor responsavel -> o funcionario produz um artefato (arquivo em disco),
  manda relatorio ao gerente -> o gerente aprova, avanca o estagio e despacha o
  proximo. Ao passar por todos os estagios, o produto e marcado como 'lancado'.

A EMPRESA conduz o processo: o arquiteto-chefe (setor de produto/arquitetura)
quebra a construção em tarefas de programação, o opencode executa UMA tarefa por
vez (é só o "braço" que escreve o código), e a empresa VERIFICA cada entrega
(compila os .py) e manda corrigir quando reprova. Assim a fábrica decide o
processo — o opencode não é a fábrica, é uma ferramenta dela.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata

from . import config, db, conhecimento, empacotar, llm, monetizacao, reuniao
from .setores import ESTAGIOS, FUNCIONARIOS, ORDEM, setor_do_estagio, proximo_estagio, progresso

GERENTE = "gerencia"


def log(msg: str) -> None:
    linha = f"{db.agora()} {msg}"
    try:
        with open(config.LOG, "a", encoding="utf-8") as fh:
            fh.write(linha + "\n")
    except OSError:
        pass


def slugificar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto[:40] or "produto"


# ---------------------------------------------------------------- inicializacao
def inicializar(forcar: bool = False) -> None:
    from .setores import SETORES
    db.init()
    conhecimento.semear()
    travadas = db.recuperar_travadas()
    if travadas:
        log(f"recuperadas {travadas} tarefa(s) travada(s) por queda anterior")
    for s in SETORES:
        db.criar_setor(s)
    for setor, f in FUNCIONARIOS.items():
        db.criar_funcionario({"setor": setor, **f})
    if not db.cfg_get("fundada_em"):
        db.cfg_set("fundada_em", db.agora())
        db.mensagem(GERENTE, "todos",
                    "My AI Office fundado. Meta: software de infraestrutura de TI "
                    "vendido a empresas de tecnologia.", tipo="anuncio")
        log("my ai office fundado")


# ---------------------------------------------------------------- utilidades
def _pasta_produto(p: dict) -> str:
    pasta = p.get("pasta") or os.path.join(str(config.PRODUTOS), p["slug"])
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _ler_contexto(p: dict, limite: int = 2500) -> str:
    """Le os artefatos ja produzidos para dar contexto ao proximo setor."""
    pasta = _pasta_produto(p)
    partes = []
    for arq in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, arq)
        if os.path.isfile(caminho) and arq.endswith((".md", ".txt")):
            try:
                with open(caminho, encoding="utf-8") as fh:
                    partes.append(f"### {arq}\n{fh.read()[:1200]}")
            except OSError:
                continue
    return "\n\n".join(partes)[:limite]


def _salvar(p: dict, nome_arquivo: str, conteudo: str) -> str:
    pasta = _pasta_produto(p)
    caminho = os.path.join(pasta, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(conteudo)
    return caminho


def _status(setor: str, status: str, tarefa: str | None = None, humor: str | None = None):
    db.status_funcionario(setor, status, tarefa, humor)


def _instalar_scaffold(p: dict) -> int:
    """Copia a camada de adaptadores multi-fabricante para a pasta do produto.

    Nunca sobrescreve arquivos que o próprio produto já criou/ajustou — só
    garante que o esqueleto (dispositivos/, inventario.json, README) existe.
    """
    origem = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scaffold_infra")
    if not os.path.isdir(origem):
        return 0
    pasta = _pasta_produto(p)
    copiados = 0
    for raiz, _dirs, arquivos in os.walk(origem):
        for a in arquivos:
            if a.endswith(".pyc") or "__pycache__" in raiz:
                continue
            src = os.path.join(raiz, a)
            rel = os.path.relpath(src, origem)
            dst = os.path.join(pasta, rel)
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.copy2(src, dst)
                copiados += 1
            except OSError:
                continue
    return copiados


def _tem_adaptadores(p: dict) -> bool:
    """True se o produto mantém a camada de adaptadores (dispositivos/base.py)."""
    pasta = p.get("pasta") or os.path.join(str(config.PRODUTOS), p.get("slug", ""))
    return os.path.isfile(os.path.join(pasta, "dispositivos", "base.py"))


# ---------------------------------------------------------------- o GERENTE
def ciclo_gerente() -> None:
    """Uma rodada do gerente. Decide criar/dispachar/avancar produtos."""
    _status(GERENTE, "pensando", "Analisando a fábrica")
    ativos = [p for p in db.listar_produtos("ativo")]

    for p in ativos:
        _processar_produto(p)

    # capacidade livre? cria mais um produto. Ideia do dono fura o limite:
    # se ha ideia na fila, criamos o produto mesmo com a capacidade cheia.
    ativos = [p for p in db.listar_produtos("ativo")]
    if len(ativos) < config.MAX_PRODUTOS_ATIVOS or db.tem_ideia_na_fila():
        _contratar_novo_produto()
    ativos = [p for p in db.listar_produtos("ativo")]
    if not ativos and config.SO_IDEIAS_DO_DONO and not db.tem_ideia_na_fila():
        _status(GERENTE, "ocioso", "Aguardando ideia do dono", "neutro")
    else:
        _status(GERENTE, "ocioso", None, "satisfeito" if ativos else "neutro")


def _processar_produto(p: dict) -> None:
    pid = p["id"]
    estagio = p["estagio"]
    tarefas = [t for t in db.tarefas_do_produto(pid) if t["estagio"] == estagio]

    if tarefas:
        ultima = tarefas[-1]
        st = ultima["status"]
        if st in ("pendente", "em_andamento"):
            return  # setor trabalhando, gerente aguarda
        if st == "concluida":
            _avancar(p, ultima)
            return
        if st == "falhou":
            # uma segunda chance antes de seguir
            falhas = sum(1 for t in tarefas if t["status"] == "falhou")
            if falhas < 2:
                db.criar_tarefa({
                    "produto_id": pid, "setor": ultima["setor"], "estagio": estagio,
                    "titulo": ultima["titulo"] + " (2ª tentativa)",
                    "descricao": ultima.get("descricao") or "",
                })
                db.mensagem(GERENTE, ultima["setor"],
                            f"O trabalho de «{p['nome']}» em {estagio} falhou. Refaça com atenção.",
                            tipo="demanda", produto_id=pid)
                return
            db.mensagem(GERENTE, ultima["setor"],
                        f"Bloqueado em {estagio} de «{p['nome']}». Sigo com o dado parcial.",
                        tipo="info", produto_id=pid)
            _avancar(p, ultima, parcial=True)
            return
    else:
        _despachar(p, estagio)


def _despachar(p: dict, estagio: str) -> None:
    setor = setor_do_estagio(estagio, p["tipo"])
    if not setor:
        return
    desc = ESTAGIOS[ORDEM.index(estagio)]["titulo"]
    contexto = _ler_contexto(p)
    tarefa = {
        "produto_id": p["id"], "setor": setor, "estagio": estagio,
        "titulo": f"{desc}: {p['nome']}",
        "descricao": (
            f"Produto: {p['nome']} ({p['tipo']})\n"
            f"Pitch: {p['pitch']}\n"
            f"Estágio: {estagio} — {desc}\n\n"
            f"Contexto já produzido:\n{contexto}"
        ),
    }
    db.criar_tarefa(tarefa)
    db.mensagem(GERENTE, setor,
                f"Demanda: {desc} para «{p['nome']}» ({estagio}).",
                tipo="demanda", produto_id=p["id"])
    db.atualizar_produto(p["id"], progresso=progresso(estagio))
    log(f"gerente -> {setor}: {estagio} / {p['nome']}")


_EXT_CODIGO = (".py", ".js", ".ts", ".jsx", ".tsx", ".kt", ".java", ".swift",
               ".gradle", ".dart", ".go", ".rb", ".rs", ".c", ".cpp", ".cs",
               ".php", ".html", ".vue", ".svelte")


def _tem_codigo(p: dict) -> bool:
    """True se a pasta do produto tem código-fonte de verdade (não só .md)."""
    pasta = p.get("pasta") or os.path.join(str(config.PRODUTOS), p.get("slug", ""))
    if not os.path.isdir(pasta):
        return False
    for raiz, _dirs, arquivos in os.walk(pasta):
        for a in arquivos:
            if a.lower().endswith(_EXT_CODIGO):
                return True
    return False


def _entry_web(pasta: str) -> str | None:
    """Ponto de entrada ÚNICO do app web (na raiz da pasta), ou None."""
    for nome in ("app.py", "server.py", "main.py", "index.html"):
        if os.path.isfile(os.path.join(pasta, nome)):
            return nome
    return None


def _tem_app(p: dict) -> bool:
    """True se o produto tem app de verdade que ABRE (não só módulos soltos).

    Android/iOS/outros: basta ter código. Web: precisa de um ponto de entrada
    único na raiz (`app.py`/`server.py`/`main.py`/`index.html`).
    """
    if not _tem_codigo(p):
        return False
    if p.get("tipo") != "web":
        return True
    pasta = p.get("pasta") or os.path.join(str(config.PRODUTOS), p.get("slug", ""))
    return _entry_web(pasta) is not None


def _avancar(p: dict, tarefa: dict, parcial: bool = False) -> None:
    # Regra "só projetos reais": não passa do build sem código de verdade E
    # (para web) sem um ponto de entrada único que sobe o app inteiro.
    if config.EXIGIR_CODIGO and p["estagio"] == "build" and not _tem_app(p):
        pend = [t for t in db.tarefas_do_produto(p["id"])
                if t["estagio"] == "build" and t["status"] in ("pendente", "em_andamento")]
        if not pend and db.builds_hoje() < config.MAX_BUILDS_DIA:
            setor = setor_do_estagio("build", p["tipo"])
            db.criar_tarefa({
                "produto_id": p["id"], "setor": setor, "estagio": "build",
                "titulo": f"Construir o sistema: {p['nome']} (sem app que abre ainda)",
                "descricao": (f"Produto: {p['nome']} ({p['tipo']})\nPitch: {p['pitch']}\n"
                              "O build anterior não gerou um APP que abre. Para web, crie um "
                              "ponto de entrada ÚNICO `app.py` na raiz que sobe com "
                              "`python3 app.py`, ouve a porta PORT e serve a interface "
                              "completa; integre as funcionalidades em vez de módulos soltos."),
            })
            db.mensagem(GERENTE, setor,
                        f"«{p['nome']}» ainda sem app que abre — nova tentativa de build.",
                        tipo="demanda", produto_id=p["id"])
            log(f"build sem app; nova tentativa / {p['nome']}")
        else:
            db.mensagem(GERENTE, "todos",
                        f"«{p['nome']}» segura no build: sem app que abre ainda "
                        f"(builds hoje: {db.builds_hoje()}/{config.MAX_BUILDS_DIA}).",
                        tipo="info", produto_id=p["id"])
            log(f"build sem app; aguardando / {p['nome']}")
        return

    resultado = (tarefa.get("resultado") or "")[:400]
    prox = proximo_estagio(p["estagio"])
    db.mensagem(GERENTE, "todos",
                f"Relatório de {tarefa['setor']} aceito para «{p['nome']}» "
                f"({p['estagio']}). {'' if parcial else 'Avançando.'}",
                tipo="resposta", produto_id=p["id"])

    # Modelo determinístico de MRR (preço × clientes plausíveis): o LLM não
    # "chuta" mais o valor. Ver empresa/monetizacao.py.
    if tarefa["estagio"] in ("monetizacao", "lancamento"):
        mod = monetizacao.extrair(tarefa.get("resultado"), p.get("tipo"))
        db.atualizar_produto(p["id"], mrr_estimado=mod["mrr_estimado"],
                             mrr_preco=mod["preco_mensal"],
                             mrr_clientes=mod["clientes_estimados"])
        db.mensagem(GERENTE, "financeiro",
                    f"MRR de «{p['nome']}» pelo modelo realista: "
                    f"R$ {mod['preco_mensal']:,.2f}/cliente × "
                    f"{mod['clientes_estimados']} clientes = "
                    f"R$ {mod['mrr_estimado']:,.2f}/mês.",
                    tipo="info", produto_id=p["id"])

    if prox:
        db.atualizar_produto(p["id"], estagio=prox, progresso=progresso(prox))
        p2 = db.produto(p["id"]) or p
        _despachar(p2, prox)
    else:
        db.atualizar_produto(p["id"], estagio="lancado", progresso=100, status="lancado")
        db.mensagem(GERENTE, "marketing",
                    f"«{p['nome']}» concluído e lançado! Colher métricas.",
                    tipo="anuncio", produto_id=p["id"])
        try:
            reuniao.agendar(produto_id=p["id"],
                            titulo=f"Pós-lançamento de «{p['nome']}»",
                            pauta=f"Colher métricas, empacotar para clientes e vender {p['nome']}.")
        except Exception:  # noqa: BLE001
            pass
        log(f"produto lancado: {p['nome']}")


def _contratar_novo_produto() -> None:
    _status(GERENTE, "pensando", "Escolhendo o próximo produto")

    ideia = db.pegar_proxima_ideia()
    if ideia:
        # Ideia do dono tem prioridade: vira produto direto, sem IA inventar.
        dados = {
            "nome": ideia["titulo"],
            "tipo": "web",
            "pitch": ideia.get("pitch") or f"Ideia do dono: {ideia['titulo']}",
            "publico": "a definir",
            "como_lucra": "a definir",
            "valor_estimado": 0,
            "mrr_estimado": 0,
            "ideia_id": ideia["id"],
        }
    elif config.SO_IDEIAS_DO_DONO:
        # Trava ligada: só construímos o que o dono pediu. Sem ideia na fila,
        # a fábrica fica ociosa em vez de inventar produto.
        _status(GERENTE, "ocioso", "Sem ideias do dono na fila")
        log("gerente: fila de ideias vazia; aguardando o dono")
        return
    else:
        dados = _ideia_ia()

    if not dados or not dados.get("nome"):
        if config.SO_IDEIAS_DO_DONO:
            return
        tema = config.IDEIAS_DOMINIO[0]
        dados = {
            "nome": tema.title(), "tipo": "web",
            "pitch": f"Ferramenta de {tema} para empresas de tecnologia.",
            "publico": "times de TI/NOC/MSP", "valor_estimado": 0, "mrr_estimado": 0,
        }
    tipo = "web"
    nome = str(dados.get("nome"))[:60]
    slug = slugificar(nome)
    if db.slug_em_uso(slug):
        slug = f"{slug}-{db.agora().replace(':', '').replace('-', '')[-6:]}"
    pid = db.criar_produto({
        "slug": slug, "nome": nome, "tipo": tipo,
        "pitch": str(dados.get("pitch", ""))[:300],
        "estagio": "ideia", "progresso": 0,
        "valor_estimado": float(dados.get("valor_estimado") or 0),
        "mrr_estimado": float(dados.get("mrr_estimado") or 0),
        "pasta": os.path.join(str(config.PRODUTOS), slug), "status": "ativo",
    })
    if dados.get("ideia_id"):
        db.concluir_ideia(dados["ideia_id"], pid)
    db.criar_funcionario({"setor": GERENTE, **FUNCIONARIOS[GERENTE]})  # garante registro
    db.mensagem(GERENTE, "todos",
                f"Novo produto em pauta: «{nome}» ({tipo}) — {dados.get('pitch','')}",
                tipo="anuncio", produto_id=pid)
    _salvar(db.produto(pid), "00-pitch.md",
            f"# {nome}\n\n**Tipo:** {tipo}\n\n**Pitch:** {dados.get('pitch','')}\n\n"
            f"**Público:** {dados.get('publico','')}\n\n**Como lucra:** {dados.get('como_lucra','')}\n\n"
            f"**Valor estimado:** R$ {dados.get('valor_estimado',0)}\n\n"
            f"**MRR estimado:** R$ {dados.get('mrr_estimado',0)}\n")
    log(f"gerente criou produto: {nome} ({tipo})")


_ANCORAS = ("rede", "network", "infra", "servidor", "server", "firewall",
            "switch", "router", "mikrotik", "cisco", "fortigate", "palo alto",
            "snmp", "syslog", "devops", "aiops", "observabilidade", "monitor",
            "backup", "config", "gmud", "mudança", "change", "auditoria",
            "compliance", "inventário", "inventario", "topolog", "vpn", "vlan",
            "drift", "patch", "firmware", "certificado", "latência", "latencia",
            "interface", "container", "docker", "kubernetes", "telemetria",
            "alerta", "escalonamento", "comutação", "roteamento", "endereço",
            "dispositivo", "ativo")


def _no_dominio(nome: str, pitch: str) -> bool:
    """True se a ideia pertence ao domínio (infra de TI B2B).

    Rejeita temas de consumo (loja virtual, app pessoal, jogos...) e exige
    âncora de domínio. Âncoras curtas (<=4 letras) só casam como palavra
    inteira, para não casar por engano dentro de outra palavra.
    """
    texto = f"{nome} {pitch}".lower()
    if any(mau in texto for mau in config.FORA_DO_DOMINIO):
        return False
    palavras = set(re.findall(r"[a-z0-9]+", texto))
    for a in _ANCORAS:
        if len(a) <= 4:
            if a in palavras:
                return True
        elif a in texto:
            return True
    return any(tema.split(" ")[0] in texto for tema in config.IDEIAS_DOMINIO)


def _ideia_ia() -> dict | None:
    """O gerente pede uma ideia ao LLM — TRAVADA no domínio (infra de TI B2B).

    Rejeita ideias fora do domínio e repete; usa lista de temas permitidos e
    fallback determinístico. Nunca gera produto de consumo.
    """
    existentes = ", ".join(p["nome"] for p in db.listar_produtos()) or "nenhum"
    temas = "\n".join(f"- {t}" for t in config.IDEIAS_DOMINIO)
    sistema = (
        "Você é o gerente de uma fábrica de software de INFRAESTRUTURA DE TI. "
        "A empresa vende para EMPRESAS de tecnologia (NOCs, MSPs, provedores, "
        "times de infra e segurança) — nunca para consumidor final. "
        "Responda SEMPRE em JSON puro, em português."
    )
    prompt = (
        "Proponha UM produto de software de infraestrutura de TI, vendável a "
        "empresas, que uma equipe pequena com IA consegue construir. "
        f"Domínio: {config.DOMINIO}.\n"
        f"Escolha UM tema desta lista (ou algo muito próximo):\n{temas}\n\n"
        f"Não repita o que já temos: {existentes}\n\n"
        "PROIBIDO propor app de consumo, e-commerce, rede social, jogo, app "
        "pessoal, delivery ou qualquer coisa fora de infraestrutura de TI.\n"
        "Responda em JSON com as chaves: nome, tipo (\"web\"), pitch (1 frase "
        "técnica), publico (perfil do comprador corporativo), preco_mensal "
        "(R$ por cliente/mês), clientes_estimados (nº conservador), como_lucra."
    )
    for _tentativa in range(3):
        resp = llm.gerar(prompt, sistema=sistema, modelo=config.MODELO_IDEIA,
                         json_mode=True, num_predict=300, temperatura=0.8)
        dados = llm.extrair_json(resp)
        if not isinstance(dados, dict) or not dados.get("nome"):
            continue
        nome = str(dados.get("nome"))[:60]
        pitch = str(dados.get("pitch", ""))
        if not _no_dominio(nome, pitch):
            log(f"ideia descartada (fora do domínio): {nome}")
            continue
        dados["tipo"] = "web"
        mod = monetizacao.modelo(dados.get("preco_mensal"), dados.get("clientes_estimados"), "web")
        dados["mrr_estimado"] = mod["mrr_estimado"]
        return dados
    log("ideia: nenhuma proposta de domínio aprovada; usando tema padrão")
    return None


# ---------------------------------------------------------------- FUNCIONÁRIOS
_PROMPTS = {
    "ideia": (
        "Você é {nome}, do setor {setor}. Liste 5 funcionalidades concretas de "
        "operação de TI para «{produto}» — software vendido a empresas de "
        "tecnologia. Objetivo: {pitch}. Seja específico e curto (markdown)."
    ),
    "validacao": (
        "Você é {nome}, do setor {setor}. Valide a demanda de «{produto}» no "
        "mercado B2B de infraestrutura. Aponte ICP (quem assina a compra), "
        "concorrentes reais, risco técnico/regulatório e o canal de aquisição "
        "mais barato para os primeiros clientes. Curto, em markdown."
    ),
    "spec": (
        "Você é {nome}, do setor {setor}. Escreva a especificação de "
        "«{produto}»: problema operacional, usuários técnicos, 5-8 "
        "funcionalidades do MVP, telas do painel e critérios de aceite. "
        "Objetivo: {pitch}. Markdown, direto ao ponto."
    ),
    "design": (
        "Você é {nome}, do setor {setor}. Para «{produto}», descreva o fluxo "
        "das telas do painel em texto/ASCII: inventário, alertas, mudança, "
        "relatório. Cada tela: o que mostra, filtros e ação principal. "
        "Leve em conta: {pitch}. Markdown."
    ),
    "visual": (
        "Você é {nome}, do setor {setor}. Para «{produto}», defina a "
        "identidade de um painel de operação: paleta escura, tipografia "
        "monoespaçada para dados, cor semântica de severidade, 5 componentes "
        "(card de métrica, tabela, badge, timeline, modal). Markdown acionável."
    ),
    "arquitetura": (
        "Você é {nome}, do setor {setor}. Para «{produto}», modele a "
        "ARQUITETURA DE ADAPTADORES MULTI-FABRICANTE: contrato da classe base "
        "`Dispositivo` (conectar, coletar, aplicar, backup), um módulo por "
        "fabricante (Palo Alto XML API, FortiOS REST, RouterOS, IOS-XE "
        "RESTCONF) e o simulador local. Também modele o esquema SQLite "
        "(ativo, interface, config, change, alerta, telemetria) e a API "
        "mínima. Objetivo: {pitch}. Markdown + SQL."
    ),
    "deploy": (
        "Você é {nome}, do setor {setor}, Eng. de Plataforma. Para "
        "«{produto}», defina a operação: como roda numa máquina modesta "
        "(systemd unit, porta, variáveis de ambiente), backup/restore do "
        "SQLite, Dockerfile opcional, upgrade e o README de operação. "
        "Liste os comandos exatos. Markdown."
    ),
    "esquema": (
        "Você é {nome}, do setor {setor}, Banco de Dados. Para «{produto}», "
        "escreva o esquema SQLite completo (ativo, interface, config, change, "
        "alerta, telemetria, evidência de compliance), com chaves, índices "
        "para as consultas do painel, migração versionada e seed de "
        "demonstração. Entregue o SQL puro. Markdown + SQL."
    ),
    "pipeline": (
        "Você é {nome}, do setor {setor}, DevOps. Para «{produto}», defina o "
        "pipeline: verificação de sintaxe/lint, teste automatizado (no modo "
        "simulado), build da imagem/artefato, versionamento e release com "
        "rollback. Liste os comandos exatos e o que cada etapa reprova. "
        "Markdown."
    ),
    "teste": (
        "Você é {nome}, do setor {setor}, QA. Faça um plano de testes para "
        "«{produto}» cobrindo: modo SIMULADO (sem gear real), modo adaptador "
        "com rede indisponível, timeout, dado corrompido e rollback de "
        "mudança. Liste 8 casos com resultado esperado e 3 riscos. Markdown."
    ),
    "revisao": (
        "Você é {nome}, do setor {setor}, Auditoria. Audite «{produto}» como "
        "se fosse de fora: vazamento de credencial, segredo no repositório, "
        "sem TLS, permissão ampla, log com dado sensível, mudança sem backup "
        "de configuração e dependência de terceiros. Aponte 3-5 achados com "
        "severidade e a correção. Markdown curto."
    ),
    "hardening": (
        "Você é {nome}, do setor {setor}, SOC. Aplique hardening CIS a "
        "«{produto}»: credencial fora do código, TLS, cabeçalhos de "
        "segurança, validação de entrada, menor privilégio, audit trail de "
        "toda operação em dispositivo e backup da config ANTES de qualquer "
        "aplicação. Liste correções concretas (arquivo/linha). Markdown."
    ),
    "gmud": (
        "Você é {nome}, do setor {setor}, GMUD. Escreva o plano de mudança "
        "para «{produto}» entrar em produção: número, justificativa, escopo, "
        "risco, janela, passos, critério de sucesso, ROLLBACK testável e "
        "responsáveis. Inclua o workflow de estados e o checklist operacional. "
        "Markdown."
    ),
    "conformidade": (
        "Você é {nome}, do setor {setor}. Elabore o laudo de conformidade de "
        "«{produto}» contra ISO/IEC 27001:2022 (controles A.5–A.8) e CIS "
        "Controls v8 nível IG1: escopo, amostragem, matriz de lacunas com "
        "risco residual, plano de remediação priorizado e conclusão. Markdown."
    ),
    "observabilidade": (
        "Você é {nome}, do setor {setor}, AIOps. Defina a observabilidade "
        "embutida de «{produto}»: telemetria (métricas/logs/eventos), "
        "healthcheck, limiares, deduplicação e supressão de alerta, e o "
        "painel de estado. Entrega: esquema de telemetria, pipeline de "
        "alerta e métricas de operação (MTTR, alertas/semana). Markdown."
    ),
    "anomalia": (
        "Você é {nome}, do setor {setor}, ML. Para «{produto}», proponha a "
        "detecção de anomalia/analytics embutida: qual sinal, qual técnica "
        "leve (z-score, baseline sazonal, árvore simples ou LLM local), "
        "dataset de exemplo, métrica de avaliação e como explicar o "
        "resultado ao operador. Modo offline obrigatório. Markdown."
    ),
    "metricas": (
        "Você é {nome}, do setor {setor}, Dados & BI. Para «{produto}», "
        "defina o painel de métricas de operação: disponibilidade, MTTR, "
        "MTBF, changes/mês, alertas por severidade, custo por ativo. "
        "Entregue o dicionário de métricas e as consultas SQL que as geram. "
        "Markdown."
    ),
    "backend": (
        "Você é {nome}, do setor {setor}. O MVP de «{produto}» foi "
        "construído. Revise/ajuste o back-end: endpoints, timeouts, retry, "
        "tratamento de erros, autenticação/senhas e persistência. Liste "
        "correções concretas (arquivo/linha). Markdown."
    ),
    "frontend": (
        "Você é {nome}, do setor {setor}. O MVP de «{produto}» foi "
        "construído. Revise/ajuste a interface do painel: tabela densa, "
        "filtros, estados vazios, responsividade e atalhos. Liste correções "
        "concretas (arquivo/linha). Markdown."
    ),
    "automacao": (
        "Você é {nome}, do setor {setor}. Para «{produto}», liste 2-3 "
        "scripts de operação úteis (inventário, backup de configuração, "
        "relatório de mudança) com o comando de execução e agendamento. "
        "Markdown curto."
    ),
    "consultoria": (
        "Você é {nome}, do setor {setor}, Especialista sênior. Dê parecer "
        "técnico sobre «{produto}»: 3 melhorias concretas de arquitetura, "
        "segurança ou robustez, e verifique se a camada de adaptadores está "
        "realmente plugável (trocar o simulador por gear real sem reescrever). "
        "Objetivo: {pitch}. Markdown."
    ),
    "posicionamento": (
        "Você é {nome}, do setor {setor}, Marketing B2B. Para «{produto}», "
        "defina o posicionamento técnico: nome comercial, tagline, landing "
        "page (headline, prova técnica, CTA de trial self-service), 7 peças "
        "de conteúdo (artigo, comparativo, guia, template, demo) e o funil "
        "até o trial. Objetivo: {pitch}. Markdown."
    ),
    "monetizacao": (
        "Você é {nome}, do setor {setor}, Vendas B2B. Defina a estratégia de "
        "monetização de «{produto}»: modelo (assinatura por ativo monitorado, "
        "por tenant/MSP ou licença + suporte), prova de conceito de 30 dias, "
        "one-pager técnico, ROI e 3 canais de aquisição. NÃO invente "
        "faturamento: informe o preço mensal por cliente e quantos clientes "
        "pagantes são plausíveis. Termine com JSON assim: "
        "{{\"preco_mensal\": 99, \"clientes_estimados\": 20}}. Markdown."
    ),
    "lancamento": (
        "Você é {nome}, do setor {setor}, Financeiro. Para «{produto}», "
        "projete a receita B2B: cenário conservador e otimista, custos "
        "(servidor, suporte, GPU) e ponto de equilíbrio. NÃO invente o MRR: "
        "informe apenas o preço mensal por cliente e um número PLAUSÍVEL de "
        "clientes pagantes. Termine com JSON assim: "
        "{{\"preco_mensal\": 99, \"clientes_estimados\": 20}}. Markdown curto."
    ),
}


def ciclo_funcionario(setor: str) -> None:
    if setor == GERENTE:
        return
    tarefa = db.pegar_tarefa_pendente(setor)
    if not tarefa:
        _status(setor, "ocioso", None)
        return

    p = db.produto(tarefa["produto_id"])
    if not p:
        db.concluir_tarefa(tarefa["id"], "produto inexistente", ok=False)
        return

    _status(setor, "trabalhando", tarefa["titulo"], "focado")
    db.mensagem(setor, GERENTE, f"Assumi «{tarefa['titulo']}». Mãos à obra.",
                tipo="info", produto_id=p["id"])
    try:
        if tarefa["estagio"] == "build":
            resumo = _construir(p, tarefa)
        else:
            resumo = _gerar_documento(setor, p, tarefa)
        db.concluir_tarefa(tarefa["id"], resumo, ok=True)
        db.mensagem(setor, GERENTE,
                    f"Concluí «{tarefa['estagio']}» de «{p['nome']}». {resumo[:200]}",
                    tipo="relatorio", produto_id=p["id"])
        log(f"{setor} concluiu {tarefa['estagio']} / {p['nome']}")
    except Exception as e:  # noqa: BLE001
        db.concluir_tarefa(tarefa["id"], f"erro: {e}", ok=False)
        db.mensagem(setor, GERENTE, f"Falhei em «{tarefa['estagio']}»: {e}",
                    tipo="relatorio", produto_id=p["id"])
        log(f"ERRO {setor} {tarefa['estagio']}: {e}")
    finally:
        _status(setor, "ocioso", None)


def _gerar_documento(setor: str, p: dict, tarefa: dict) -> str:
    nome = FUNCIONARIOS[setor]["nome"]
    tmpl = _PROMPTS.get(tarefa["estagio"], "Você é {nome} do setor {setor}. Trabalhe a demanda para «{produto}».")
    prompt = tmpl.format(nome=nome, setor=setor, produto=p["nome"], tipo=p["tipo"], pitch=p["pitch"])
    resp = llm.gerar(prompt, modelo=FUNCIONARIOS[setor]["modelo"],
                     sistema=conhecimento.sistema_agente(setor),
                     num_predict=320, temperatura=0.6)
    if resp.startswith("__ERRO_LLM__") or not resp.strip():
        resp = f"# {tarefa['titulo']}\n\n(não foi possível consultar o LLM: {resp[:200]})"
    idx = ORDEM.index(tarefa["estagio"])
    arquivo = f"{idx:02d}-{tarefa['estagio']}.md"
    _salvar(p, arquivo, f"# {tarefa['titulo']}\n\n{resp}\n")
    return _resumo(resp)


def _plano_padrao(p: dict) -> list[dict]:
    """Plano mínimo quando o LLM não ajuda — a empresa ainda conduz a ordem."""
    return [
        {"titulo": "Estrutura, ponto de entrada e adaptadores",
         "objetivo": "Criar o esqueleto do painel: `app.py` que sobe e responde, "
                     "reusando a camada `dispositivos/` (adaptadores multi-fabricante "
                     "e modo simulado) já presente na pasta, com README de operação.",
         "arquivos": ["app.py", "dispositivos/base.py", "README.md"],
         "pronto": "o app inicia, lê o inventário e responde uma página"},
        {"titulo": "Funcionalidades do MVP",
         "objetivo": "Implementar as funcionalidades de operação descritas na spec "
                     "(inventário, backup de config, mudança com rollback).",
         "arquivos": ["app.py"],
         "pronto": "o fluxo principal funciona de ponta a ponta no modo simulado"},
        {"titulo": "Dados e persistência",
         "objetivo": "Guardar ativos, configs, mudanças e alertas (SQLite) de forma persistente.",
         "arquivos": ["app.py"],
         "pronto": "os dados continuam após reiniciar o app"},
        {"titulo": "Observabilidade e monetização",
         "objetivo": "Expor healthcheck e métricas de operação, e deixar visível a "
                     "proposta comercial (planos por ativo/tenant).",
         "arquivos": ["app.py", "templates/index.html"],
         "pronto": "a tela principal está pronta e as métricas aparecem"},
    ]


def _plano_build(p: dict, contexto: str) -> list[dict]:
    """A EMPRESA planeja: o arquiteto-chefe quebra a construção em tarefas."""
    sistema = ("Você é o arquiteto-chefe de uma software house. Planeja o trabalho "
               "para um engenheiro executar. Responda SEMPRE em JSON puro, em português.")
    prompt = (
        f"Produto: {p['nome']} ({p['tipo']})\nPitch: {p['pitch']}\n\n"
        f"Materiais já produzidos pela empresa:\n{contexto}\n\n"
        "REGRA DE OURO 1: é UM ÚNICO aplicativo. Para web, o ponto de entrada é "
        "SEMPRE `app.py` na raiz da pasta — ele sobe com `python3 app.py`, ouve a "
        "porta da variável de ambiente PORT e serve a interface completa. NÃO crie "
        "apps/módulos separados com seus próprios servidores; as tarefas abaixo são "
        "fatias incrementais do MESMO app (podem criar arquivos auxiliares importados "
        "por app.py, mas quem roda tudo é o app.py).\n\n"
        "REGRA DE OURO 2: TODO acesso a equipamento passa pela camada "
        "`dispositivos/` (adaptadores multi-fabricante + simulador) que já existe "
        "na pasta. NÃO chame a API de um fabricante direto no app; use "
        "`fabricar(ativo)` de `dispositivos`. Não reescreva a camada: estenda-a.\n\n"
        "Quebre a CONSTRUÇÃO do MVP em 3 a 5 tarefas de programação, em ordem de execução. "
        "A PRIMEIRA tarefa deve criar o `app.py` que já sobe e responde uma página. "
        "Cada tarefa deve ser executável por um engenheiro de forma independente. "
        "NÃO escreva o código; só o plano. Responda no formato JSON:\n"
        '{"tarefas":[{"titulo":"...","objetivo":"...","arquivos":["app.py"],'
        '"pronto":"critério de aceite"}]}'
    )
    resp = llm.gerar(prompt, sistema=sistema, modelo=config.MODELO_PLANEJADOR,
                     json_mode=True, num_predict=700, temperatura=0.5)
    dados = llm.extrair_json(resp) or {}
    plano = []
    for t in dados.get("tarefas") or []:
        if not isinstance(t, dict) or not str(t.get("titulo", "")).strip():
            continue
        plano.append({
            "titulo": str(t["titulo"])[:80],
            "objetivo": str(t.get("objetivo", ""))[:300],
            "arquivos": [str(a) for a in (t.get("arquivos") or []) if isinstance(a, str)][:6],
            "pronto": str(t.get("pronto", ""))[:160],
        })
    return plano or _plano_padrao(p)


def _instrucao_tarefa(p: dict, t: dict, contexto: str, i: int, n: int) -> str:
    arquivos = ", ".join(t.get("arquivos") or []) or "(conforme precisar)"
    regra_app = ""
    if p.get("tipo") == "web":
        regra_app = (
            "\nREGRA DE OURO 1 (web): o produto é UM ÚNICO aplicativo. O ponto de entrada "
            "é `app.py` na raiz e ele sobe com `python3 app.py`, ouvindo a porta da "
            "variável PORT e servindo a interface web. NUNCA crie um app/servidor "
            "separado com porta própria; se precisar de módulos, crie-os como arquivos "
            "que o `app.py` importa. Garanta que, ao terminar, `python3 app.py` sobe e "
            "responde uma página.\n"
        )
    regra_adaptadores = (
        "\nREGRA DE OURO 2 (infra): todo acesso a equipamento passa pela camada "
        "`dispositivos/` (adaptadores multi-fabricante + simulador) que JÁ EXISTE na "
        "pasta. Importe `from dispositivos import carregar_inventario, fabricar`. Nunca "
        "chame a API de um fabricante direto do app, e nunca apague `dispositivos/`. "
        "O desenvolvimento e o teste acontecem no modo SIMULADO (`inventario.json` "
        "aponta para `simulado`), sem gear real.\n"
    )
    return (
        f"Você é o ENGENHEIRO da empresa «{p['nome']}» ({p['tipo']}). "
        f"O arquiteto-chefe planejou {n} tarefa(s) e você executa SOMENTE a tarefa {i}.\n"
        f"Tarefa {i}/{n}: {t['titulo']}\n"
        f"Objetivo: {t.get('objetivo', '')}\n"
        f"Arquivos: {arquivos}\n"
        f"Pronto quando: {t.get('pronto', '')}\n"
        f"{regra_app}{regra_adaptadores}\n"
        f"Materiais já produzidos pela empresa:\n{contexto}\n\n"
        "Execute só esta tarefa, de forma incremental, sem reescrever o que já funciona. "
        "Ao final, diga em uma linha o que mudou e como rodar."
    )


def _verificar_codigo(pasta: str) -> str:
    """A EMPRESA verifica (não o opencode): há código e os .py compilam? '' se ok."""
    py, tem_codigo = [], False
    for raiz, _d, fs in os.walk(pasta):
        if "/." in raiz:
            continue
        for a in fs:
            if a.lower().endswith(_EXT_CODIGO):
                tem_codigo = True
            if a.endswith(".py"):
                py.append(os.path.join(raiz, a))
    if not tem_codigo:
        return "nenhum código-fonte encontrado (só texto/documentos)"
    if not py:
        return ""  # android/iOS/estático: sem .py para compilar, mas há código
    try:
        r = subprocess.run(["python3", "-m", "py_compile", *py],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:  # noqa: BLE001
        return f"falha ao compilar: {e}"
    if r.returncode == 0:
        return ""
    ult = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
    return ult[-1][:200] if ult else "erro de compilação"


def _construir(p: dict, tarefa: dict) -> str:
    pasta = _pasta_produto(p)
    contexto = _ler_contexto(p)

    # 0) Instala a camada de adaptadores multi-fabricante (esqueleto do produto).
    n_scaffold = _instalar_scaffold(p)
    if n_scaffold:
        log(f"scaffold_infra: {n_scaffold} arquivo(s) instalado(s) / {p['nome']}")

    if config.MODO_BUILD != "opencode":
        return _construir_por_llm(p, contexto)

    if db.builds_hoje() >= config.MAX_BUILDS_DIA:
        return (f"Limite de {config.MAX_BUILDS_DIA} builds/dia atingido; "
                "produto fica retido no build até haver verba de build (não avança sem código).")

    setor_dev = setor_do_estagio("build", p["tipo"])

    # 1) A EMPRESA planeja (arquiteto-chefe) — quem decide o processo é a fábrica.
    plano = _plano_build(p, contexto)[:config.MAX_TAREFAS_BUILD]
    _salvar(p, f"{ORDEM.index('build'):02d}-plano-build.md",
            f"# Plano de construção de {p['nome']}\n\n"
            "Definido pela empresa (arquiteto-chefe) → executado pelo engenheiro (opencode).\n\n"
            + "\n".join(f"- [ ] {i}. {t['titulo']} — {t.get('objetivo', '')}"
                        for i, t in enumerate(plano, 1)) + "\n")
    db.mensagem(GERENTE, setor_dev,
                f"Plano de build de «{p['nome']}» definido em {len(plano)} tarefas.",
                tipo="demanda", produto_id=p["id"])

    # 2) opencode EXECUTA uma tarefa por vez; a EMPRESA verifica e manda corrigir
    rel = []
    for i, t in enumerate(plano, 1):
        _status(setor_dev, "trabalhando", f"build {i}/{len(plano)}: {t['titulo']}")
        instr = _instrucao_tarefa(p, t, contexto, i, len(plano))
        llm.rodar_opencode(instr, pasta, timeout=config.TIMEOUT_TAREFA,
                           log_path=os.path.join(str(config.VAR), "builds.log"))
        defeito = _verificar_codigo(pasta)
        tentativa = 1
        while defeito and tentativa < 2:
            db.verificar(p["id"], f"build-{i}", False, defeito)
            corrigir = (f"{instr}\n\nA verificação da EMPRESA reprovou o resultado: "
                        f"{defeito}\nCorrija exatamente esse problema.")
            llm.rodar_opencode(corrigir, pasta, timeout=config.TIMEOUT_TAREFA,
                               log_path=os.path.join(str(config.VAR), "builds.log"))
            defeito = _verificar_codigo(pasta)
            tentativa += 1
        estado = "ok" if not defeito else f"pendência: {defeito}"
        db.verificar(p["id"], f"build-{i}", not defeito, estado)
        rel.append(f"- [{'x' if not defeito else ' '}] {i}. {t['titulo']} — {estado}")
        log(f"build {i}/{len(plano)} {t['titulo']}: {estado}")

    # 2b) A EMPRESA confere o ponto de entrada e manda CONSOLIDAR se faltar.
    #     Sem `app.py` único, o produto não abre (vira listagem estática) — a
    #     empresa exige o app integrado antes de dar o build por concluído.
    if p["tipo"] == "web" and not _entry_web(pasta):
        _status(setor_dev, "trabalhando", "consolidando o ponto de entrada (app.py)")
        db.verificar(p["id"], "entrada-web", False, "sem app.py — mandando consolidar")
        consolidar = (
            f"A EMPRESA reprovou: «{p['nome']}» ficou como módulos soltos, SEM o ponto de "
            "entrada único. Crie/ajuste `app.py` na RAIZ para ser a ÚNICA porta de entrada "
            "do app inteiro: sobe com `python3 app.py`, ouve a porta da variável PORT, "
            "serve a interface web (HTML/CSS/JS) e expõe as funcionalidades já "
            "implementadas nos arquivos desta pasta (importe-os — NÃO reescreva o que já "
            "funciona). Nada de apps/servidores separados. Ao final, `python3 app.py` "
            "precisa subir e responder uma página."
        )
        llm.rodar_opencode(consolidar, pasta, timeout=config.TIMEOUT_TAREFA,
                           log_path=os.path.join(str(config.VAR), "builds.log"))
        entrada = _entry_web(pasta)
        db.verificar(p["id"], "entrada-web", bool(entrada),
                     entrada or "ainda sem ponto de entrada")
        rel.append(f"- [{'x' if entrada else ' '}] consolidação: app.py único"
                   + (f" ({entrada})" if entrada else " — ausente"))
        log(f"build consolidação app.py: {'ok' if entrada else 'ausente'}")

    # 2c) A EMPRESA garante a camada de adaptadores multi-fabricante. Se o
    #     build apagou/reescreveu, reinstala o esqueleto (o app não pode falar
    #     com fabricante direto).
    if not _tem_adaptadores(p):
        _instalar_scaffold(p)
        db.verificar(p["id"], "adaptadores", _tem_adaptadores(p),
                     "camada dispositivos/ reinstalada" if _tem_adaptadores(p)
                     else "sem dispositivos/base.py")
        rel.append(f"- [{'x' if _tem_adaptadores(p) else ' '}] adaptadores "
                   "multi-fabricante (dispositivos/)")
        log(f"build adaptadores: {'ok' if _tem_adaptadores(p) else 'ausente'}")

    criados = _listar_arquivos(pasta)
    _salvar(p, f"{ORDEM.index('build'):02d}-build-relatorio.md",
            f"# Build de {p['nome']} ({p['tipo']}) — empresa conduz, opencode executa\n\n"
            "Tarefas planejadas pela empresa, executadas pelo opencode e verificadas "
            "pela empresa:\n\n" + "\n".join(rel) +
            f"\n\n## Arquivos ({len(criados)})\n" + "\n".join(f"- {a}" for a in criados) + "\n")
    if not _tem_codigo(p):
        raise RuntimeError("o build não produziu código real após o plano da empresa")
    if not _tem_adaptadores(p):
        raise RuntimeError("o build não manteve a camada de adaptadores "
                           "(dispositivos/base.py) — o produto não pode falar com "
                           "fabricante direto")
    if p["tipo"] == "web" and not _tem_app(p):
        raise RuntimeError("o build não produziu um app web com ponto de entrada único "
                           "(app.py) — fica retido no build até abrir de verdade")
    if config.EMPACOTAR:
        try:
            return (f"build conduzido em {len(plano)} tarefas; {len(criados)} arquivos. "
                    + empacotar.empacotar_e_documentar(p))
        except Exception as e:  # noqa: BLE001
            db.verificar(p["id"], "empacotar", False, str(e))
            return f"build em {len(plano)} tarefas (empacotamento falhou: {e})"
    return f"build conduzido em {len(plano)} tarefas; {len(criados)} arquivos"


def _construir_por_llm(p: dict, spec: str) -> str:
    # MODO_BUILD == "llm": a empresa pede os arquivos em JSON e escreve em disco
    sistema = ("Você é o time de desenvolvimento da empresa. Responda SOMENTE JSON com a "
               "chave 'arquivos': uma lista de objetos {path, conteudo}. Código funcional.")
    prompt = (f"Crie um MVP de app {p['tipo']} chamado «{p['nome']}». Objetivo: {p['pitch']}.\n"
              f"Materiais:\n{spec}\n\n"
              "Gere de 3 a 8 arquivos com um MVP que roda (README incluso, com instruções "
              "de execução e monetização). JSON puro.")
    resp = llm.gerar(prompt, sistema=sistema, modelo=config.MODELO_CODIGO,
                     json_mode=True, num_predict=1000, temperatura=0.4)
    dados = llm.extrair_json(resp) or {}
    pasta = _pasta_produto(p)
    n = 0
    for a in dados.get("arquivos") or []:
        caminho = str(a.get("path", "")).lstrip("/")
        if not caminho or ".." in caminho:
            continue
        destino = os.path.join(pasta, caminho)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(str(a.get("conteudo", "")))
        n += 1
    if n == 0:
        _salvar(p, "README.md", f"# {p['nome']}\n\nMVP ainda não gerado (LLM indisponível).\n")
    if config.EMPACOTAR:
        try:
            return f"App gerado com {n} arquivo(s) (modo llm). " + empacotar.empacotar_e_documentar(p)
        except Exception as e:  # noqa: BLE001
            db.verificar(p["id"], "empacotar", False, str(e))
            return f"App gerado com {n} arquivo(s) (modo llm; empacotamento falhou: {e})"
    return f"App gerado com {n} arquivo(s) (modo llm)."


def _listar_arquivos(pasta: str, limite: int = 40) -> list[str]:
    itens = []
    for raiz, _dirs, arquivos in os.walk(pasta):
        for a in arquivos:
            rel = os.path.relpath(os.path.join(raiz, a), pasta)
            if rel.startswith("."):
                continue
            itens.append(rel)
            if len(itens) >= limite:
                return itens
    return itens


def _resumo(texto: str, limite: int = 220) -> str:
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return " ".join(linhas)[:limite]
