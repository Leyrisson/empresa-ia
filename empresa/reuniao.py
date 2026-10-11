"""Reuniões de projeto: agentes se reúnem na sala para discutir a empresa.

Ciclo de vida no orquestrador (um tick por ciclo):
  agendada  --(ciclos>=CICLOS_INICIO)-->  ocorrendo  --(ciclos>=DURACAO)-->  concluida

Quando concluída, uma **ata** é gravada em disco (no produto, quando houver)
e o resumo do resultado fica no banco. As pautas intercalam os produtos ativos
e os lançamentos. Tudo é determinístico (sem custo extra de LLM).
"""
from __future__ import annotations

import json
import os
import time

from . import config, db

CICLOS_INICIO = int(os.environ.get("EMPRESA_REUNIAO_INICIO", "1"))
DURACAO_CICLOS = int(os.environ.get("EMPRESA_REUNIAO_DURACAO", "2"))
ENTRE_REUNIOES = int(os.environ.get("EMPRESA_REUNIAO_ENTRE", "5"))

_TODOS = ["gerencia", "pesquisa", "produto", "dev_web", "dev_android", "qa", "financeiro", "marketing"]


def _pauta_padrao() -> tuple[str, str, list[str]]:
    """Escolhe o tema: lançamento recente senão o produto mais adiantado."""
    produtos = [p for p in db.listar_produtos("ativo") if p["estagio"] != "lancado"]
    lancados = [p for p in db.listar_produtos() if p["estagio"] == "lancado"]
    alvo = max(produtos, key=lambda p: p.get("progresso") or 0) if produtos else (lancados[0] if lancados else None)
    if not alvo:
        return ("Reunião de alinhamento", "Avaliar o portfólio e definir próximos produtos.", _TODOS,)
    if alvo["estagio"] == "lancado":
        titulo = f"Pós-lançamento de «{alvo['nome']}»"
        pauta = f"Colher métricas, projeto de venda e próximos passos de {alvo['nome']}."
    else:
        titulo = f"Alinhamento de «{alvo['nome']}»"
        pauta = f"Discutir o estágio {alvo['estagio']} de {alvo['nome']} e destravar o pipeline."
    # participantes: gerência + setores envolvidos
    setor = "dev_android" if str(alvo["tipo"]).lower().startswith("android") else "dev_web"
    part = ["gerencia", "pesquisa", "produto", setor, "qa", "marketing", "financeiro"]
    return titulo, pauta, part


def agendar(produto_id: int | None = None, titulo: str = "", pauta: str = "",
            participantes: list[str] | None = None) -> int:
    if not titulo or not pauta:
        t, p, part = _pauta_padrao()
        titulo = titulo or t
        pauta = pauta or p
        if participantes is None:
            participantes = part
    return db.criar_reuniao(titulo, pauta, participantes or _TODOS, produto_id)


def _contar(pilha) -> int:
    return db.cfg_get(pilha, 0)


def _somar(pilha, n: int = 1) -> None:
    db.cfg_set(pilha, db.cfg_get(pilha, 0) + n)


def tick() -> str:
    """Chamado 1x por ciclo. Devolve descrição do que aconteceu ('' se nada)."""
    ativa = db.reuniao_ativa()
    if not ativa:
        _somar("ciclos_desde_reuniao")
        ciclos = _contar("ciclos_desde_reuniao")
        if ciclos >= ENTRE_REUNIOES:
            rid = agendar()
            db.cfg_set("ciclos_desde_reuniao", 0)
            return f"reunião agendada (rid {rid})"
        return ""

    rid = ativa["id"]
    if ativa["status"] == "agendada":
        _somar("reuniao_ciclos")
        if _contar("reuniao_ciclos") >= CICLOS_INICIO:
            db.iniciar_reuniao(rid)
            _marcar_status(ativa, "reuniao")
            db.mensagem("gerencia", "todos",
                        f"Reunião na sala: {ativa['titulo']}. Atenção, vamos lá!",
                        tipo="anuncio", produto_id=ativa.get("produto_id"))
            db.cfg_set("reuniao_ciclos", 0)
            return f"reunião iniciada: {ativa['titulo']}"
        return ""

    # ocorrendo
    _somar("reuniao_ciclos")
    if _contar("reuniao_ciclos") >= DURACAO_CICLOS:
        ata = _gerar_ata(ativa)
        db.concluir_reuniao(rid, ata)
        _marcar_status(ativa, "ocioso")
        db.cfg_set("reuniao_ciclos", 0)
        db.mensagem("gerencia", "todos",
                    f"Ata da reunião «{ativa['titulo']}» registrada e arquivada.",
                    tipo="resposta", produto_id=ativa.get("produto_id"))
        _salvar_ata(ativa, ata)
        return f"reunião concluída: {ativa['titulo']}"
    return f"reunião em andamento: {ativa['titulo']}"


def _marcar_status(ativa: dict, status: str) -> None:
    for setor in json.loads(ativa.get("participantes") or "[]"):
        db.status_funcionario(setor, status, f"Reunião: {ativa['titulo']}" if status == "reuniao" else None)


def _ultimos_relatorios(limite: int = 6) -> list[dict]:
    with db.conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM mensagens WHERE para='gerencia' AND tipo='relatorio' "
            "ORDER BY id DESC LIMIT ?", (limite,))]


def _gerar_ata(ativa: dict) -> str:
    data = time.strftime("%Y-%m-%d %H:%M")
    part = json.loads(ativa.get("participantes") or "[]")
    ativos = [p for p in db.listar_produtos("ativo")]
    linhas = [
        f"# Ata — {ativa['titulo']}",
        "",
        f"**Data:** {data}",
        f"**Participantes:** {', '.join(part)}",
        f"**Pauta:** {ativa['pauta']}",
        "",
        "## Situação dos projetos",
    ]
    linhas += [f"- **{p['nome']}** ({p['tipo']}) — estágio `{p['estagio']}` · progresso {p.get('progresso',0)}% · MRR R$ {p.get('mrr_estimado') or 0:,.0f}" for p in ativos]
    linhas.append("")
    linhas.append("## Últimos relatórios dos setores")
    for m in _ultimos_relatorios():
        txt = (m.get("conteudo") or "").replace("\n", " ")[:150]
        linhas.append(f"- **{m['de']}** → {txt}")
    linhas += ["", "## Decisões",
               "- O pipeline segue com os estágios pendentes de cada produto.",
               "- A fila de ideias do dono tem prioridade na próxima contratação.",
               "- Empacotamento, verificação e docs são parte da definição de 'pronto'.",
               ""]
    return "\n".join(linhas)


def _salvar_ata(ativa: dict, ata: str) -> None:
    destino = str(config.PRODUTOS)
    pid = ativa.get("produto_id")
    if pid:
        p = db.produto(pid)
        if p and p.get("pasta"):
            destino = os.path.join(p["pasta"], "docs")
            os.makedirs(destino, exist_ok=True)
        elif p:
            destino = os.path.join(str(config.PRODUTOS), p["slug"], "docs")
            os.makedirs(destino, exist_ok=True)
    else:
        destino = os.path.join(str(config.VAR), "reunioes")
        os.makedirs(destino, exist_ok=True)
    nome = time.strftime("%Y-%m-%d") + "-reuniao-" + str(ativa["id"]).zfill(2) + ".md"
    caminho = os.path.join(destino, nome)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(ata)
    return None