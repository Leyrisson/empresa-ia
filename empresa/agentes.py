"""Os agentes: o Gerente (Aurélio) e os funcionários de cada setor.

Fluxo:
  Gerente cria um produto (pedindo ideia a Pesquisa) -> despacha o estagio atual
  para o setor responsavel -> o funcionario produz um artefato (arquivo em disco),
  manda relatorio ao gerente -> o gerente aprova, avanca o estagio e despacha o
  proximo. Ao passar por todos os estagios, o produto e marcado como 'lancado'.

O desenvolvimento (estagio 'build') usa o opencode para ESCREVER o app de verdade.
"""
from __future__ import annotations

import json
import os
import re
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

    # capacidade livre? cria mais um produto
    ativos = [p for p in db.listar_produtos("ativo")]
    if len(ativos) < config.MAX_PRODUTOS_ATIVOS:
        _contratar_novo_produto()
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


def _avancar(p: dict, tarefa: dict, parcial: bool = False) -> None:
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
    else:
        dados = _ideia_ia()

    if not dados or not dados.get("nome"):
        dados = {
            "nome": "Painel de Assinaturas", "tipo": "web",
            "pitch": "Painel simples para pequenos negócios venderem assinaturas recorrentes.",
            "publico": "pequenos negócios", "valor_estimado": 4900, "mrr_estimado": 990,
        }
    tipo = "android" if str(dados.get("tipo", "web")).lower().startswith("android") else "web"
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
    "teste": (
        "Você é {nome}, do setor {setor}, QA. Faça um plano de testes para «{produto}» ({tipo}). "
        "Liste 8 casos de teste com resultado esperado e 3 riscos. Markdown."
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


def _construir(p: dict, tarefa: dict) -> str:
    pasta = _pasta_produto(p)
    spec = _ler_contexto(p)
    if config.MODO_BUILD == "opencode":
        if db.builds_hoje() >= config.MAX_BUILDS_DIA:
            return (f"Limite de {config.MAX_BUILDS_DIA} builds/dia atingido; "
                    "segue para teste com o que existe.")
        instrucao = (
            f"Você é o engenheiro de software da empresa. Construa um aplicativo "
            f"{p['tipo']} funcional chamado «{p['nome']}».\n"
            f"Objetivo: {p['pitch']}\n\n"
            f"Especificação e materiais já produzidos:\n{spec}\n\n"
            f"Requisitos: gere código real e completo (arquivos, README com instruções "
            f"de execução), foque no MVP especificado e em formas de lucro. "
            f"Trabalhe somente dentro desta pasta. Ao terminar, liste no final os "
            f"arquivos criados."
        )
        ok, saida = llm.rodar_opencode(
            instrucao, pasta, timeout=config.TIMEOUT_BUILD,
            log_path=os.path.join(str(config.VAR), "builds.log"),
        )
        criados = _listar_arquivos(pasta)
        _salvar(p, f"{ORDEM.index('build'):02d}-build-relatorio.md",
                f"# Build de {p['nome']} ({p['tipo']})\n\n"
                f"- modo: opencode\n- sucesso: {ok}\n- arquivos: {len(criados)}\n\n"
                f"## Arquivos\n" + "\n".join(f"- {a}" for a in criados) +
                f"\n\n## Saída do engenheiro\n\n```\n{saida[-2500:]}\n```\n")
        if not ok and len(criados) <= 1:
            raise RuntimeError("opencode não produziu arquivos")
        pacote = ""
        if config.EMPACOTAR:
            try:
                pacote = " | " + empacotar.empacotar_e_documentar(p)
            except Exception as e:  # noqa: BLE001
                pacote = f" | empacotamento falhou: {e}"
                db.verificar(p["id"], "empacotar", False, str(e))
        return f"App {'gerado' if ok else 'parcialmente gerado'} com {len(criados)} arquivo(s).{pacote}"

    # MODO_BUILD == "llm": pede os arquivos em JSON e escreve em disco
    sistema = ("Você é um engenheiro. Responda SOMENTE JSON com a chave 'arquivos': "
               "uma lista de objetos {path, conteudo}. Código completo e funcional.")
    prompt = (f"Crie um MVP de app {p['tipo']} chamado «{p['nome']}». Objetivo: {p['pitch']}.\n"
              f"Materiais:\n{spec}\n\n"
              "Gere de 3 a 8 arquivos com um MVP que roda (README incluso, com instruções "
              "de execução e monetização). JSON puro.")
    resp = llm.gerar(prompt, sistema=sistema, modelo=config.MODELO_CODIGO,
                     json_mode=True, num_predict=1000, temperatura=0.4)
    dados = llm.extrair_json(resp) or {}
    arquivos = dados.get("arquivos") or []
    n = 0
    for a in arquivos:
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
            pacote = " | " + empacotar.empacotar_e_documentar(p)
            return f"App gerado com {n} arquivo(s) (modo llm).{pacote}"
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
