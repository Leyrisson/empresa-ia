"""Relatório diário da empresa, entregue de três formas:

  1. no banco (tabela `relatorios`, para histórico e consulta futura);
  2. no Obsidian (`~/Obsidian/EmpresaIA/relatorios/<data>.md` + índice);
  3. manda no Telegram do dono (credenciais em `~/.config/omarchy-voice/...`).

O orquestrador dispara na `HORA_RELATORIO` configurada, uma vez por dia.
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.request

from . import config, db, obsidian

_LABEL_ESTAGIO = {
    "ideia": "💡 ideia", "validacao": "🔎 validação", "spec": "📄 spec",
    "design": "🎨 design", "build": "🔧 build", "teste": "🧪 teste",
    "monetizacao": "💰 monetização", "lancamento": "🚀 lançamento",
}


def _hoje() -> str:
    return time.strftime("%Y-%m-%d")


def _telegram_env() -> dict:
    creds = {}
    try:
        for linha in config.TELEGRAM_CREDS.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if "=" in linha and not linha.startswith("#"):
                k, v = linha.split("=", 1)
                creds[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return creds


def enviar_telegram(texto: str) -> bool:
    creds = _telegram_env()
    token = creds.get("TELEGRAM_BOT_TOKEN")
    chat = creds.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        for parte in _fatia(texto, 4000):
            corpo = urllib.parse.urlencode({
                "chat_id": chat, "text": parte, "parse_mode": "HTML" if False else "",
            }).encode()
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/sendMessage", data=corpo, timeout=25)
        return True
    except Exception:  # noqa: BLE001
        return False


def _fatia(texto: str, n: int):
    return [texto[i:i + n] for i in range(0, len(texto), n)]


def _resumo_produtos() -> str:
    linhas = []
    for p in db.listar_produtos():
        st = _LABEL_ESTAGIO.get(p["estagio"], p["estagio"])
        mrr = f" · R$ {p['mrr_estimado']:,.0f}/mês" if p.get("mrr_estimado") else ""
        linhas.append(f"- **{p['nome']}** ({p['tipo']}) — {st}{mrr}")
    return "\n".join(linhas) or "- (nenhum produto ainda)"


def _resumo_tarefas_hoje() -> str:
    hoje = _hoje()
    com = db.conectar()
    try:
        r = com.__enter__()
        linha = "SELECT status, COUNT(*) c FROM tarefas WHERE criado_em LIKE ? GROUP BY status"
        rows = [dict(x) for x in r.execute(linha, (hoje + "%",))]
    finally:
        com.__exit__(None, None, None)
    if not rows:
        return "- (nenhuma tarefa hoje)"
    return "\n".join(f"- {x['status']}: {x['c']}" for x in rows)


def montar() -> str:
    cfg = db.cfg_get
    produto_mais = max(
        (p for p in db.listar_produtos() if p["estagio"] != "lancado"),
        key=lambda p: db.progresso(p)
        if hasattr(db, "progresso") else 0, default=None)
    meta = cfg("meta_mrr", config.META_MRR)
    mrr_total = sum(p.get("mrr_estimado") or 0 for p in db.listar_produtos())
    ideias = [i for i in db.listar_ideias() if i["status"] == "fila"]
    texto = (
        f"🏢 **Empresa IA — relatório {_hoje()}**\n\n"
        f"**Produtos ({len(db.listar_produtos())})**\n{_resumo_produtos()}\n\n"
        f"**Tarefas de hoje**\n{_resumo_tarefas_hoje()}\n\n"
        f"**Métricas**\n"
        f"- builds hoje: {db.builds_hoje()}\n"
        f"- MRR total estimado: R$ {mrr_total:,.0f} (meta R$ {meta:,.0f})\n"
        f"- ideias do dono na fila: {len(ideias)}\n\n"
        f"Você vê tudo ao vivo em http://127.0.0.1:8770 — e adiciona ideias por lá."
    )
    return texto


def rodar(force: bool = False) -> dict | None:
    """Gera e entrega o relatório do dia (uma vez por dia, a menos que force)."""
    data = _hoje()
    existe = db.relatorio_do_dia(data)
    if existe and not force:
        return existe
    texto = montar()
    caminho_obs = obsidian.escrever_relatorio(data, f"Relatório {data}", texto)
    canais = ["banco"]
    if caminho_obs:
        canais.append("obsidian")
        obsidian.escrever_indice()
    if enviar_telegram(texto):
        canais.append("telegram")
    db.registrar_relatorio(data, f"Relatório {data}", texto, "+".join(canais))
    return db.relatorio_do_dia(data)