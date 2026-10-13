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
import subprocess
import unicodedata

from . import config, db, conhecimento, empacotar, llm, reuniao
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
        db.mensagem(GERENTE, "todos", "Empresa fundada. Meta: criar sistemas web e Android lucrativos.",
                    tipo="anuncio")
        log("empresa fundada")


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

    # o financeiro pode devolver mrr_estimado no resultado
    m = re.search(r'"mrr_estimado"\s*:\s*([0-9]+(?:\.[0-9]+)?)', tarefa.get("resultado") or "")
    if m:
        try:
            db.atualizar_produto(p["id"], mrr_estimado=float(m.group(1)))
        except ValueError:
            pass

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
            "tipo": "android" if str(ideia["tipo"]).lower().startswith("android") else "web",
            "pitch": ideia.get("pitch") or f"Ideia do dono: {ideia['titulo']}",
            "publico": "a definir",
            "como_lucra": "a definir",
            "valor_estimado": 0,
            "mrr_estimado": 0,
            "ideia_id": ideia["id"],
        }
    elif config.SO_IDEIAS_DO_DONO:
        # So construimos o que o dono pediu em "Ideias". Sem ideia na fila,
        # a fabrica fica ociosa em vez de inventar produto (nada de "simulacao").
        _status(GERENTE, "ocioso", "Sem ideias do dono na fila")
        log("gerente: fila de ideias vazia; aguardando o dono")
        return
    else:
        dados = _ideia_ia()

    if not dados or not dados.get("nome"):
        if config.SO_IDEIAS_DO_DONO:
            return
        dados = {
            "nome": "Painel de Assinaturas", "tipo": "web",
            "pitch": "Painel simples para pequenos negócios venderem assinaturas recorrentes.",
            "publico": "pequenos negócios", "valor_estimado": 4900, "mrr_estimado": 990,
        }
    tipo, tipo_str = "web", str(dados.get("tipo", "web")).lower()
    if tipo_str.startswith("ios"):
        tipo = "ios"
    elif tipo_str.startswith("android"):
        tipo = "android"
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


def _ideia_ia() -> dict | None:
    """O gerente pede uma ideia ao LLM (usado quando a fila do dono está vazia)."""
    existentes = ", ".join(f"{p['nome']} ({p['tipo']})" for p in db.listar_produtos()) or "nenhum"
    sistema = (
        "Você é o gerente de uma empresa de software cujo objetivo é lançar apps "
        "web e Android LUCRATIVOS. Responda SEMPRE em JSON puro, em português."
    )
    prompt = (
        "Proponha UM produto de software lucrativo e realista para uma pessoa "
        "desenvolver sozinha com IA. Fuja do que já existe na empresa.\n"
        f"Já temos: {existentes}\n\n"
        "Responda em JSON com as chaves: nome, tipo (\"web\" ou \"android\"), "
        "pitch (1 frase), publico, valor_estimado (numero em reais, 0 se incerto), "
        "mrr_estimado (numero em reais), como_lucra."
    )
    resp = llm.gerar(prompt, sistema=sistema, json_mode=True, num_predict=260, temperatura=0.9)
    return llm.extrair_json(resp)


# ---------------------------------------------------------------- FUNCIONÁRIOS
_PROMPTS = {
    "ideia": (
        "Você é {nome}, do setor {setor}. Liste 5 ideias de funcionalidades/monetização "
        "concretas para «{produto}» ({tipo}). Objetivo do produto: {pitch}. "
        "Seja específico e curto (markdown com tópicos)."
    ),
    "validacao": (
        "Você é {nome}, do setor {setor}. Valide a demanda de «{produto}» ({tipo}). "
        "Aponte público, concorrentes, risco e o canal mais barato para os primeiros clientes. "
        "Curto, em markdown."
    ),
    "spec": (
        "Você é {nome}, do setor {setor}. Escreva a especificação de «{produto}» ({tipo}): "
        "problema, usuários, 5-8 funcionalidades do MVP, telas principais e critérios de aceite. "
        "Objetivo: {pitch}. Markdown, direto ao ponto."
    ),
    "design": (
        "Você é {nome}, do setor {setor}. Para «{produto}» ({tipo}), descreva o fluxo de telas "
        "em texto/ASCII: cada tela, o que mostra e as ações do usuário. Leve em conta: {pitch}. "
        "Markdown."
    ),
    "visual": (
        "Você é {nome}, do setor {setor}. Para «{produto}» ({tipo}), defina a identidade visual: "
        "paleta de cores (hex), tipografia, estilo de botões e 5 componentes de UI. "
        "Objetivo: {pitch}. Markdown curto e acionável para o dev implementar."
    ),
    "arquitetura": (
        "Você é {nome}, do setor {setor}. Para «{produto}» ({tipo}), modele os dados do MVP: "
        "tabelas/entidades, campos e a API mínima (endpoints e o que retornam). Objetivo: {pitch}. "
        "Escreva o schema em SQL puro (SQLite se possível). Markdown."
    ),
    "teste": (
        "Você é {nome}, do setor {setor}, QA. Faça um plano de testes para «{produto}» ({tipo}). "
        "Liste 8 casos de teste com resultado esperado e 3 riscos. Markdown."
    ),
    "revisao": (
        "Você é {nome}, do setor {setor}, Auditoria. Audite «{produto}» ({tipo}) como se fosse "
        "de fora: segurança, vazamento de dados, riscos e conformidade. Aponte 3-5 achados "
        "com severidade e a correção sugerida. Markdown curto."
    ),
    "backend": (
        "Você é {nome}, do setor {setor}. O MVP de «{produto}» ({tipo}) foi construído. "
        "Revise/ajuste o back-end: endpoints, tratamento de erros, autenticação/senhas e "
        "persistência. Liste correções concretas (arquivo/linha). Markdown."
    ),
    "frontend": (
        "Você é {nome}, do setor {setor}. O MVP de «{produto}» ({tipo}) foi construído. "
        "Revise/ajuste a interface: navegação, responsividade, mensagens e o fluxo principal "
        "de clique. Liste correções concretas (arquivo/linha). Markdown."
    ),
    "automacao": (
        "Você é {nome}, do setor {setor}, Python. Para «{produto}» ({tipo}), liste 2-3 scripts "
        "utilitários úteis (semear dados, backup, relatório de uso) com o comando de execução. "
        "Markdown curto."
    ),
    "consultoria": (
        "Você é {nome}, do setor {setor}, Especialista sênior. Dê parecer técnico sobre "
        "«{produto}» ({tipo}): 3 melhorias concretas de arquitetura/segurança/robustez e "
        "1 sugestão de simplificação. Objetivo: {pitch}. Markdown."
    ),
    "monetizacao": (
        "Você é {nome}, do setor {setor}. Defina a estratégia de monetização de «{produto}» ({tipo}): "
        "modelo (assinatura/anúncio/uso), preço sugerido em R$, plano gratis, e 3 canais de aquisição "
        "de baixo custo. Markdown."
    ),
    "lancamento": (
        "Você é {nome}, do setor {setor}, Financeiro. Para «{produto}» ({tipo}), projete a receita: "
        "cenário conservador e otimista de MRR, custos, ponto de equilíbrio. Responda também uma "
        "linha JSON no final assim: \"mrr_estimado\": NUMERO. Markdown curto."
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
        {"titulo": "Estrutura e ponto de entrada",
         "objetivo": "Criar o esqueleto do app: ponto de entrada que sobe e responde, "
                     "com README explicando como rodar.",
         "arquivos": ["app.py", "README.md"],
         "pronto": "o app inicia e responde uma página"},
        {"titulo": "Funcionalidades do MVP",
         "objetivo": "Implementar as funcionalidades principais descritas na spec/pitch.",
         "arquivos": ["app.py"],
         "pronto": "o fluxo principal funciona de ponta a ponta"},
        {"titulo": "Dados e persistência",
         "objetivo": "Guardar os dados do MVP (SQLite ou arquivos) de forma persistente.",
         "arquivos": ["app.py"],
         "pronto": "os dados continuam após reiniciar o app"},
        {"titulo": "Apresentação e monetização",
         "objetivo": "Deixar a interface apresentável e expor a forma de lucro da spec.",
         "arquivos": ["app.py", "templates/index.html"],
         "pronto": "a tela principal está pronta e a forma de lucro aparece"},
    ]


def _plano_build(p: dict, contexto: str) -> list[dict]:
    """A EMPRESA planeja: o arquiteto-chefe quebra a construção em tarefas."""
    sistema = ("Você é o arquiteto-chefe de uma software house. Planeja o trabalho "
               "para um engenheiro executar. Responda SEMPRE em JSON puro, em português.")
    prompt = (
        f"Produto: {p['nome']} ({p['tipo']})\nPitch: {p['pitch']}\n\n"
        f"Materiais já produzidos pela empresa:\n{contexto}\n\n"
        "REGRA DE OURO: é UM ÚNICO aplicativo. Para web, o ponto de entrada é "
        "SEMPRE `app.py` na raiz da pasta — ele sobe com `python3 app.py`, ouve a "
        "porta da variável de ambiente PORT e serve a interface completa. NÃO crie "
        "apps/módulos separados com seus próprios servidores; as tarefas abaixo são "
        "fatias incrementais do MESMO app (podem criar arquivos auxiliares importados "
        "por app.py, mas quem roda tudo é o app.py).\n\n"
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
            "\nREGRA DE OURO (web): o produto é UM ÚNICO aplicativo. O ponto de entrada "
            "é `app.py` na raiz e ele sobe com `python3 app.py`, ouvindo a porta da "
            "variável PORT e servindo a interface web. NUNCA crie um app/servidor "
            "separado com porta própria; se precisar de módulos, crie-os como arquivos "
            "que o `app.py` importa. Garanta que, ao terminar, `python3 app.py` sobe e "
            "responde uma página.\n"
        )
    return (
        f"Você é o ENGENHEIRO da empresa «{p['nome']}» ({p['tipo']}). "
        f"O arquiteto-chefe planejou {n} tarefa(s) e você executa SOMENTE a tarefa {i}.\n"
        f"Tarefa {i}/{n}: {t['titulo']}\n"
        f"Objetivo: {t.get('objetivo', '')}\n"
        f"Arquivos: {arquivos}\n"
        f"Pronto quando: {t.get('pronto', '')}\n"
        f"{regra_app}\n"
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

    criados = _listar_arquivos(pasta)
    _salvar(p, f"{ORDEM.index('build'):02d}-build-relatorio.md",
            f"# Build de {p['nome']} ({p['tipo']}) — empresa conduz, opencode executa\n\n"
            "Tarefas planejadas pela empresa, executadas pelo opencode e verificadas "
            "pela empresa:\n\n" + "\n".join(rel) +
            f"\n\n## Arquivos ({len(criados)})\n" + "\n".join(f"- {a}" for a in criados) + "\n")
    if not _tem_codigo(p):
        raise RuntimeError("o build não produziu código real após o plano da empresa")
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
