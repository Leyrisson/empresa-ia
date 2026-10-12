"""Monitor de build real.

Vigia o produto ativo e avisa o dono quando o `build` de verdade termina:

  * notificacao no PC (`notify-send`, se existir);
  * mensagem no Telegram (reusa `relatorio.enviar_telegram`);
  * best-effort: sobe o app gerado e manda a URL para abrir no navegador.

Regra do projeto: nada e "lancado" sem codigo real. Este monitor so considera
"build concluido" quando o produto **tem codigo** e passou do estagio `build`.

Estado entre ciclos em `var/monitor_estado.json` (nunca dispara duas vezes).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config, db, relatorio

ESTADO = config.VAR / "monitor_estado.json"
LOG_DIR = config.VAR

# estagios que vem DEPOIS do build (na ordem do pipeline)
_APOS_BUILD = ("teste", "revisao", "backend", "frontend", "automacao",
               "consultoria", "monetizacao", "lancamento", "lancado")


def _carregar() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar(estado: dict) -> None:
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def _notificar(titulo: str, texto: str) -> None:
    relatorio.enviar_telegram(f"{titulo}\n\n{texto}")
    try:
        subprocess.Popen(["notify-send", "-a", "Empresa IA", titulo, texto],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _porta(pasta: Path, slug: str) -> int:
    """Porta pretendida pelo produto, ignorando linhas de exemplo/uso."""
    for nome in ("app.py", "iniciar.sh"):
        f = pasta / nome
        if not f.exists():
            continue
        for linha in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            baixa = linha.lower()
            if "port" not in baixa:
                continue
            if "python3" in baixa or "exemplo" in baixa or "--help" in baixa:
                continue
            m = re.search(r"(\d{4,5})", linha)
            if m:
                return int(m.group(1))
    return 8790 + (abs(hash(slug)) % 200)


def _porta_livre(inicial: int) -> int:
    porta = inicial
    for _ in range(200):
        if not _ocupada(porta):
            return porta
        porta += 1
    return inicial


def _ocupada(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def _responde(porta: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=3)
        return True
    except Exception:  # noqa: BLE001
        return False


def _subir(p: dict) -> str | None:
    """Best-effort: sobe o app do produto e devolve a URL, ou None."""
    pasta = config.RAIZ / (p.get("pasta") or f"produtos/{p['slug']}")
    if not pasta.exists():
        return None
    slug = p["slug"]

    # 1) URL já gravada? reusa se ainda responde.
    u = p.get("url") or ""
    m = re.search(r":(\d{2,5})", u)
    if m and _responde(int(m.group(1))):
        return u

    # 2) sobe numa porta LIVRE, forçando o app a usá-la via PORT/<SLUG>_PORTA.
    porta = _porta_livre(_porta(pasta, slug))
    var_slug = slug.upper().replace("-", "_")
    env = {**os.environ, "SEM_NAVEGADOR": "1", "EMPRESA_NAO_ATRAPALHA": "1",
           "PORT": str(porta), f"{var_slug}_PORTA": str(porta)}
    if (pasta / "app.py").is_file():
        entrar = ["python3", "app.py"]
    elif (pasta / "iniciar.sh").is_file():
        entrar = ["bash", "iniciar.sh"]
    else:
        return None
    log = LOG_DIR / f"monitor_{slug}.log"
    with open(log, "a") as fh:
        subprocess.Popen(entrar, cwd=str(pasta), stdout=fh, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    for _ in range(12):
        time.sleep(1)
        if _responde(porta):
            return f"http://127.0.0.1:{porta}"
    return None


def abrir(p: dict) -> str | None:
    """Sobe o app do produto (se preciso) e devolve a URL, guardando-a no banco."""
    if not p:
        return None
    url = _subir(p)
    if url and p.get("url") != url:
        try:
            db.atualizar_produto(p["id"], url=url)
        except Exception:  # noqa: BLE001
            pass
    return url


def um_ciclo(estado: dict) -> dict:
    from .agentes import _tem_app  # regra unica de "tem app que abre"

    ativos = [p for p in db.listar_produtos("ativo")] or db.listar_produtos()
    if not ativos:
        return estado
    p = ativos[-1]
    pid = p["id"]

    if not _tem_app(p):
        return estado

    if p["estagio"] in _APOS_BUILD and not estado.get(f"{pid}_build"):
        url = abrir(p)
        linhas = [f"Produto: {p['nome']} ({p['tipo']})",
                  f"Estágio agora: {p['estagio']}"]
        if url:
            linhas.append(f"Rodando em: {url}\n(É só abrir no navegador.)")
        else:
            linhas.append(f"App em produtos/{p['slug']} "
                          "(não consegui subir sozinho).")
        _notificar("🔨 Build real concluído", "\n".join(linhas))
        estado[f"{pid}_build"] = {"url": url, "em": time.strftime("%Y-%m-%d %H:%M")}

    if p["estagio"] in ("lancado", "lancamento") and not estado.get(f"{pid}_lancado"):
        url = estado.get(f"{pid}_build", {}).get("url")
        extra = f"\nAbra: {url}" if url else ""
        _notificar("🚀 Projeto real lançado", f"{p['nome']} ({p['tipo']}){extra}")
        estado[f"{pid}_lancado"] = True
    return estado


def executar(intervalo: float = 20.0) -> None:
    db.init()
    estado = _carregar()
    while True:
        try:
            estado = um_ciclo(estado)
            _salvar(estado)
        except Exception as e:  # noqa: BLE001
            print(f"[monitor] erro: {e}", flush=True)
        time.sleep(max(20.0, config.SLEEP))
