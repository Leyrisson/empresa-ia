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
CREATE TABLE IF NOT EXISTS ideias (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo       TEXT NOT NULL,
    tipo         TEXT DEFAULT 'web',
    pitch        TEXT,
    origem       TEXT DEFAULT 'dono',
    status       TEXT DEFAULT 'fila',
    criado_em    TEXT,
    escolhido_em TEXT,
    produto_id   INTEGER REFERENCES produtos(id)
);
CREATE TABLE IF NOT EXISTS relatorios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    data       TEXT UNIQUE,
    titulo     TEXT,
    conteudo   TEXT,
    canais     TEXT DEFAULT '',
    enviado_em TEXT
);
CREATE TABLE IF NOT EXISTS conhecimento (
    setor        TEXT PRIMARY KEY,
    conteudo     TEXT,
    versao       INTEGER DEFAULT 1,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS office (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT,
    tipo   TEXT,
    x      REAL DEFAULT 0,
    y      REAL DEFAULT 0,
    z      REAL DEFAULT 0,
    rot    REAL DEFAULT 0,
    cor    TEXT,
    setor  TEXT,
    estado TEXT DEFAULT 'livre'
);
CREATE TABLE IF NOT EXISTS verificacoes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER,
    etapa      TEXT,
    ok         INTEGER,
    detalhe    TEXT,
    criado_em  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ideias_status   ON ideias(status);
CREATE INDEX IF NOT EXISTS idx_rel_data        ON relatorios(data);
CREATE INDEX IF NOT EXISTS idx_office_setor    ON office(setor);
CREATE INDEX IF NOT EXISTS idx_ver_produto     ON verificacoes(produto_id);
CREATE INDEX IF NOT EXISTS idx_prod_slug       ON produtos(slug);
CREATE INDEX IF NOT EXISTS idx_prod_estagio    ON produtos(estagio, status);
CREATE TABLE IF NOT EXISTS reunioes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo        TEXT,
    pauta         TEXT,
    participantes TEXT,
    status        TEXT DEFAULT 'agendada',
    produto_id    INTEGER REFERENCES produtos(id),
    criado_em     TEXT,
    iniciado_em   TEXT,
    concluido_em  TEXT,
    resultado     TEXT
);
CREATE INDEX IF NOT EXISTS idx_reuniao_status ON reunioes(status);
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


def _cols(con, tabela: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def _add_col(con, tabela: str, coluna: str, ddl: str) -> None:
    if coluna not in _cols(con, tabela):
        con.execute(f"ALTER TABLE {tabela} ADD COLUMN {ddl}")


def _sembrar_office(con) -> None:
    """Planta baixa 3D do escritorio (salas, mesas, cadeiras, arquivos...)."""
    n = con.execute("SELECT COUNT(*) c FROM office").fetchone()["c"]
    if n:
        return
    objs = [
        # Gerente (mesa maior, centro quase ao fundo)
        ("Mesa do Gerente", "mesa", 7.6, 0, 0.0, 0.0, "c8a94b", "gerencia"),
        ("Cadeira do Gerente", "cadeira", 8.6, 0, 0.0, 0.0, "a0802f", "gerencia"),
        ("Mesa Grande (reunião)", "sala", 1.6, 0, 5.9, 0.0, "8e6f3f", None),
        ("Parede Sala Reunião", "parede", 1.6, 1.2, 7.3, 0.0, "d9c9a8", None),
        ("Parede Sala Reunião", "parede", 1.6, 1.2, 5.1, 0.0, "d9c9a8", None),
        # Setores — fileira A na frente
        ("Mesa Pesquisa", "mesa", 3.7, 0, -4.8, 0.0, "#5b9bd5", "pesquisa"),
        ("Mesa Produto", "mesa", 3.7, 0, -1.7, 0.0, "#70ad47", "produto"),
        ("Mesa Financeiro", "mesa", 3.7, 0, 1.7, 0.0, "#ffc000", "financeiro"),
        ("Mesa Marketing", "mesa", 3.7, 0, 4.8, 0.0, "#ed7d31", "marketing"),
        # fileira B (dev + qa)
        ("Mesa Dev Web", "mesa", 5.5, 0, -4.8, 0.0, "#4472c4", "dev_web"),
        ("Mesa Dev Android", "mesa", 5.5, 0, -1.7, 0.0, "#43b653", "dev_android"),
        ("Mesa QA", "mesa", 5.5, 0, 1.7, 0.0, "#7030a0", "qa"),
    ]
    # cadeiras ao lado de cada mesa de setor
    for (m, x, z) in [
        ("pesquisa", 3.7, -4.8), ("produto", 3.7, -1.7),
        ("financeiro", 3.7, 1.7), ("marketing", 3.7, 4.8),
        ("dev_web", 5.5, -4.8), ("dev_android", 5.5, -1.7), ("qa", 5.5, 1.7),
    ]:
        objs.append(("Cadeira " + m, "cadeira", x, 0, z + 1.05, 0.0, "#c7c7c7", m))
    # arquivo (estante de projetos) — canto esquerdo
    for i, zz in enumerate([-6.9, -5.8, -4.7, -3.6]):
        objs.append((f"Arquivo {i+1}", "arquivo", 2.2, 0, zz, 0.0, "#8a5a2b", None))
    for nome, tipo, x, y, z, rot, cor, setor in objs:
        con.execute(
            "INSERT INTO office(nome,tipo,x,y,z,rot,cor,setor,estado) VALUES(?,?,?,?,?,?,?,?, 'livre')",
            (nome, tipo, x, y, z, rot, cor, setor),
        )


def init() -> None:
    with conectar() as con:
        con.executescript(SCHEMA)
        _add_col(con, "produtos", "repo", "repo TEXT")
        _add_col(con, "setores", "sala", "sala TEXT")
        _add_col(con, "ideias", "pitch_extra", "pitch_extra TEXT")
        _sembrar_office(con)


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


# ---------------- ideias (sugestões do dono) ----------------
def criar_ideia(titulo: str, tipo: str = "web", pitch: str = "", origem: str = "dono") -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO ideias(titulo,tipo,pitch,origem,status,criado_em)"
            " VALUES(?,?,?,?, 'fila', ?)",
            (titulo, tipo, pitch, origem, agora()),
        )
        return cur.lastrowid


def listar_ideias(status: str | None = None) -> list[dict]:
    with conectar() as con:
        if status:
            q = "SELECT * FROM ideias WHERE status=? ORDER BY id"
            return [dict(r) for r in con.execute(q, (status,))]
        return [dict(r) for r in con.execute("SELECT * FROM ideias ORDER BY id")]


def pegar_proxima_ideia() -> dict | None:
    """Pega (atomicamente) a próxima ideia do dono na fila e marca como escolhida."""
    with conectar() as con:
        r = con.execute(
            "SELECT * FROM ideias WHERE status='fila' ORDER BY id LIMIT 1"
        ).fetchone()
        if not r:
            return None
        con.execute(
            "UPDATE ideias SET status='escolhida', escolhido_em=? WHERE id=?",
            (agora(), r["id"]),
        )
        return dict(r)


def concluir_ideia(iid: int, produto_id: int | None = None) -> None:
    with conectar() as con:
        con.execute(
            "UPDATE ideias SET status='concluida', produto_id=?, escolhido_em=COALESCE(escolhido_em, ?)"
            " WHERE id=?",
            (produto_id, agora(), iid),
        )


def descartar_ideia(iid: int) -> None:
    with conectar() as con:
        con.execute("UPDATE ideias SET status='descartada' WHERE id=?", (iid,))


# ---------------- relatórios diários ----------------
def registrar_relatorio(data: str, titulo: str, conteudo: str, canais: str) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO relatorios(data,titulo,conteudo,canais,enviado_em) VALUES(?,?,?,?,?) "
            "ON CONFLICT(data) DO UPDATE SET titulo=excluded.titulo, conteudo=excluded.conteudo,"
            " canais=excluded.canais, enviado_em=excluded.enviado_em",
            (data, titulo, conteudo, canais, agora()),
        )


def relatorio_do_dia(data: str) -> dict | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM relatorios WHERE data=?", (data,)).fetchone()
        return dict(r) if r else None


def listar_relatorios(limite: int = 8) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT data,titulo,canais,enviado_em FROM relatorios ORDER BY data DESC LIMIT ?",
            (limite,))]


# ---------------- conhecimento por setor ----------------
def conhecimento_setor(setor: str) -> dict | None:
    with conectar() as con:
        r = con.execute(
            "SELECT * FROM conhecimento WHERE setor=?", (setor,)).fetchone()
        return dict(r) if r else None


def salvar_conhecimento(setor: str, conteudo: str, versao: int) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO conhecimento(setor,conteudo,versao,atualizado_em) VALUES(?,?,?,?) "
            "ON CONFLICT(setor) DO UPDATE SET conteudo=excluded.conteudo,"
            " versao=excluded.versao, atualizado_em=excluded.atualizado_em",
            (setor, conteudo, versao, agora()),
        )


# ---------------- escritório 3D ----------------
def listar_office() -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM office ORDER BY id")]


def verificar(produto_id: int, etapa: str, ok: bool, detalhe: str) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO verificacoes(produto_id,etapa,ok,detalhe,criado_em) VALUES(?,?,?,?,?)",
            (produto_id, etapa, 1 if ok else 0, detalhe, agora()),
        )


def verificacoes_do_produto(pid: int) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM verificacoes WHERE produto_id=? ORDER BY id DESC LIMIT 12", (pid,))]


# ---------------- reuniões ----------------
def criar_reuniao(titulo: str, pauta: str, participantes: list[str],
                  produto_id: int | None = None) -> int:
    import json as _json
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO reunioes(titulo,pauta,participantes,status,produto_id,criado_em)"
            " VALUES(?,?,?, 'agendada',?,?)",
            (titulo, pauta, _json.dumps(participantes, ensure_ascii=False), produto_id, agora()),
        )
        return cur.lastrowid


def listar_reunioes(limite: int = 12) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM reunioes ORDER BY id DESC LIMIT ?", (limite,))]


def reuniao_ativa() -> dict | None:
    with conectar() as con:
        r = con.execute(
            "SELECT * FROM reunioes WHERE status IN ('agendada','ocorrendo') ORDER BY id LIMIT 1"
        ).fetchone()
        return dict(r) if r else None


def iniciar_reuniao(rid: int) -> None:
    with conectar() as con:
        con.execute("UPDATE reunioes SET status='ocorrendo', iniciado_em=? WHERE id=?",
                    (agora(), rid))


def concluir_reuniao(rid: int, resultado: str) -> None:
    with conectar() as con:
        con.execute(
            "UPDATE reunioes SET status='concluida', concluido_em=?, resultado=? WHERE id=?",
            (agora(), resultado, rid),
        )


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
        ideias = [dict(r) for r in con.execute("SELECT * FROM ideias ORDER BY id")]
        office = [dict(r) for r in con.execute("SELECT * FROM office ORDER BY id")]
        conhecimento = [dict(r) for r in con.execute(
            "SELECT setor, versao, atualizado_em FROM conhecimento")]
        relatorios = [dict(r) for r in con.execute(
            "SELECT data,titulo,canais FROM relatorios ORDER BY data DESC LIMIT 8")]
        reunioes = [dict(r) for r in con.execute(
            "SELECT * FROM reunioes ORDER BY id DESC LIMIT 8")]
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
            "hora_relatorio": config.HORA_RELATORIO,
        },
        "setores": setores,
        "funcionarios": funcs,
        "produtos": produtos,
        "mensagens": msgs,
        "eventos": evs,
        "tarefas": tars,
        "ideias": ideias,
        "office": office,
        "conhecimento": conhecimento,
        "relatorios": relatorios,
        "reunioes": reunioes,
    }
