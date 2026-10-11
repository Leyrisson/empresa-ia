"""Camada de banco (SQLite, stdlib) — e o 'escritorio' da empresa.

Tabelas:
  config      -> estado global (pausada, intensidade, meta_mrr, tick...)
  setores     -> os setores (salas) com posicao na planta do escritorio
  funcionarios-> agentes de IA (um por setor) e o que estao fazendo
  produtos    -> os sistemas que a empresa esta construindo (web/android)
  tarefas     -> demandas do gerente para cada setor
  mensagens   -> o 'mural' oficial: relatorios, demandas e respostas
  eventos     -> trilha curta para animar o fluxo no dashboard
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterable

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
CREATE TABLE IF NOT EXISTS setores (
    id      TEXT PRIMARY KEY,
    nome    TEXT NOT NULL,
    funcao  TEXT,
    emoji   TEXT,
    cor     TEXT,
    mesa_x  REAL DEFAULT 0,
    mesa_y  REAL DEFAULT 0,
    papel   TEXT DEFAULT 'funcionario'
);
CREATE TABLE IF NOT EXISTS funcionarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    setor        TEXT REFERENCES setores(id),
    nome         TEXT,
    emoji        TEXT,
    modelo       TEXT,
    status       TEXT DEFAULT 'ocioso',
    tarefa_atual TEXT,
    humor        TEXT DEFAULT 'neutro',
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS produtos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slug           TEXT UNIQUE,
    nome           TEXT,
    tipo           TEXT,
    pitch          TEXT,
    estagio        TEXT DEFAULT 'ideia',
    valor_estimado REAL DEFAULT 0,
    mrr_estimado   REAL DEFAULT 0,
    progresso      INTEGER DEFAULT 0,
    pasta          TEXT,
    status         TEXT DEFAULT 'ativo',
    criado_em      TEXT,
    atualizado_em  TEXT
);
CREATE TABLE IF NOT EXISTS tarefas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id    INTEGER REFERENCES produtos(id),
    setor         TEXT,
    estagio       TEXT,
    titulo        TEXT,
    descricao     TEXT,
    status        TEXT DEFAULT 'pendente',
    resultado     TEXT,
    criado_em     TEXT,
    concluido_em  TEXT
);
CREATE TABLE IF NOT EXISTS mensagens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    de         TEXT,
    para       TEXT,
    tipo       TEXT,
    produto_id INTEGER,
    conteudo   TEXT,
    criado_em  TEXT,
    lido       INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS eventos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    de        TEXT,
    para      TEXT,
    tipo      TEXT,
    rotulo    TEXT,
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_criado ON mensagens(criado_em);
CREATE INDEX IF NOT EXISTS idx_ev_criado  ON eventos(criado_em);
CREATE INDEX IF NOT EXISTS idx_tar_status ON tarefas(status, setor);
"""


def agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@contextmanager
def conectar():
    con = sqlite3.connect(str(config.BANCO), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    with conectar() as con:
        con.executescript(SCHEMA)


# ---------------- config (chave/valor) ----------------
def cfg_get(chave: str, padrao: Any = None) -> Any:
    with conectar() as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    if r is None:
        return padrao
    try:
        return json.loads(r["valor"])
    except (TypeError, ValueError):
        return r["valor"]


def cfg_set(chave: str, valor: Any) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO config(chave, valor) VALUES(?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, json.dumps(valor)),
        )


# ---------------- setores / funcionarios ----------------
def criar_setor(s: dict) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO setores(id,nome,funcao,emoji,cor,mesa_x,mesa_y,papel) "
            "VALUES(:id,:nome,:funcao,:emoji,:cor,:mesa_x,:mesa_y,:papel) "
            "ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, funcao=excluded.funcao,"
            " emoji=excluded.emoji, cor=excluded.cor, mesa_x=excluded.mesa_x,"
            " mesa_y=excluded.mesa_y, papel=excluded.papel",
            s,
        )


def criar_funcionario(f: dict) -> None:
    with conectar() as con:
        existe = con.execute(
            "SELECT id FROM funcionarios WHERE setor=?", (f["setor"],)
        ).fetchone()
        if existe:
            con.execute(
                "UPDATE funcionarios SET nome=?, emoji=?, modelo=? WHERE setor=?",
                (f["nome"], f["emoji"], f["modelo"], f["setor"]),
            )
        else:
            con.execute(
                "INSERT INTO funcionarios(setor,nome,emoji,modelo,status,atualizado_em)"
                " VALUES(?,?,?,?, 'ocioso', ?)",
                (f["setor"], f["nome"], f["emoji"], f["modelo"], agora()),
            )


def listar_setores() -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM setores ORDER BY papel DESC, id")]


def status_funcionario(setor: str, status: str, tarefa: str | None = None, humor: str | None = None):
    with conectar() as con:
        if humor is not None:
            con.execute(
                "UPDATE funcionarios SET status=?, tarefa_atual=?, humor=?, atualizado_em=? WHERE setor=?",
                (status, tarefa, humor, agora(), setor),
            )
        else:
            con.execute(
                "UPDATE funcionarios SET status=?, tarefa_atual=?, atualizado_em=? WHERE setor=?",
                (status, tarefa, agora(), setor),
            )


# ---------------- produtos ----------------
def criar_produto(p: dict) -> int:
    p = dict(p)
    p.setdefault("estagio", "ideia")
    p.setdefault("status", "ativo")
    p["criado_em"] = agora()
    p["atualizado_em"] = agora()
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO produtos(slug,nome,tipo,pitch,estagio,valor_estimado,"
            "mrr_estimado,progresso,pasta,status,criado_em,atualizado_em) "
            "VALUES(:slug,:nome,:tipo,:pitch,:estagio,:valor_estimado,"
            ":mrr_estimado,:progresso,:pasta,:status,:criado_em,:atualizado_em)",
            p,
        )
        return cur.lastrowid


def atualizar_produto(pid: int, **campos) -> None:
    if not campos:
        return
    campos["atualizado_em"] = agora()
    sets = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE produtos SET {sets} WHERE id=?", (*campos.values(), pid))


def listar_produtos(status: str | None = None) -> list[dict]:
    with conectar() as con:
        if status:
            q = "SELECT * FROM produtos WHERE status=? ORDER BY id"
            return [dict(r) for r in con.execute(q, (status,))]
        return [dict(r) for r in con.execute("SELECT * FROM produtos ORDER BY id")]


def produto(pid: int) -> dict | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM produtos WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def slug_em_uso(slug: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM produtos WHERE slug=?", (slug,)).fetchone() is not None


# ---------------- tarefas ----------------
def criar_tarefa(t: dict) -> int:
    t = dict(t)
    t["criado_em"] = agora()
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO tarefas(produto_id,setor,estagio,titulo,descricao,status,criado_em)"
            " VALUES(:produto_id,:setor,:estagio,:titulo,:descricao,'pendente',:criado_em)",
            t,
        )
        return cur.lastrowid


def pegar_tarefa_pendente(setor: str) -> dict | None:
    """Reserva atomicamente a proxima tarefa pendente do setor."""
    with conectar() as con:
        r = con.execute(
            "SELECT * FROM tarefas WHERE setor=? AND status='pendente' ORDER BY id LIMIT 1",
            (setor,),
        ).fetchone()
        if not r:
            return None
        con.execute("UPDATE tarefas SET status='em_andamento' WHERE id=?", (r["id"],))
        return dict(r)


def concluir_tarefa(tid: int, resultado: str, ok: bool = True) -> None:
    with conectar() as con:
        con.execute(
            "UPDATE tarefas SET status=?, resultado=?, concluido_em=? WHERE id=?",
            ("concluida" if ok else "falhou", resultado, agora(), tid),
        )


def tarefas_do_produto(pid: int) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM tarefas WHERE produto_id=? ORDER BY id", (pid,))]


def recuperar_travadas() -> int:
    """Tarefas que ficaram 'em_andamento' por queda do processo voltam a 'pendente'."""
    with conectar() as con:
        cur = con.execute(
            "UPDATE tarefas SET status='pendente' WHERE status='em_andamento'")
        return cur.rowcount


def builds_hoje() -> int:
    hoje = time.strftime("%Y-%m-%d")
    with conectar() as con:
        r = con.execute(
            "SELECT COUNT(*) c FROM tarefas WHERE estagio='build' AND status='concluida'"
            " AND concluido_em LIKE ?", (hoje + "%",)
        ).fetchone()
        return r["c"] if r else 0


# ---------------- mensagens / eventos ----------------
def mensagem(de: str, para: str, conteudo: str, tipo: str = "info", produto_id: int | None = None) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO mensagens(de,para,tipo,produto_id,conteudo,criado_em) VALUES(?,?,?,?,?,?)",
            (de, para, tipo, produto_id, conteudo, agora()),
        )
        mid = cur.lastrowid
        con.execute(
            "INSERT INTO eventos(de,para,tipo,rotulo,criado_em) VALUES(?,?,?,?,?)",
            (de, para, tipo, (conteudo or "")[:70], agora()),
        )
        return mid


def mensagens_recentes(limite: int = 60) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM mensagens ORDER BY id DESC LIMIT ?", (limite,))]


def eventos_recentes(segundos: int = 25) -> list[dict]:
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - segundos))
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM eventos WHERE criado_em >= ? ORDER BY id", (limite,))]


def marcar_lidas(ids: Iterable[int]) -> None:
    ids = list(ids)
    if not ids:
        return
    with conectar() as con:
        con.executemany("UPDATE mensagens SET lido=1 WHERE id=?", [(i,) for i in ids])


def snapshot() -> dict:
    """Estado completo para o dashboard."""
    with conectar() as con:
        setores = [dict(r) for r in con.execute("SELECT * FROM setores ORDER BY papel DESC, id")]
        funcs = {r["setor"]: dict(r) for r in con.execute("SELECT * FROM funcionarios")}
        produtos = [dict(r) for r in con.execute("SELECT * FROM produtos ORDER BY id DESC")]
        msgs = [dict(r) for r in con.execute("SELECT * FROM mensagens ORDER BY id DESC LIMIT 40")]
        evs = [dict(r) for r in con.execute(
            "SELECT * FROM eventos ORDER BY id DESC LIMIT 30")]
        tars = [dict(r) for r in con.execute(
            "SELECT * FROM tarefas ORDER BY id DESC LIMIT 60")]
    return {
        "config": {
            "pausada": cfg_get("pausada", False) or config.PAUSA.exists(),
            "intensidade": cfg_get("intensidade", config.INTENSIDADE),
            "meta_mrr": cfg_get("meta_mrr", config.META_MRR),
            "modelo_planejador": config.MODELO_PLANEJADOR,
            "modelo_codigo": config.MODELO_CODIGO,
            "backend": config.BACKEND,
            "modo_build": config.MODO_BUILD,
            "tick": cfg_get("ultimo_tick"),
            "builds_hoje": builds_hoje(),
        },
        "setores": setores,
        "funcionarios": funcs,
        "produtos": produtos,
        "mensagens": msgs,
        "eventos": evs,
        "tarefas": tars,
    }
