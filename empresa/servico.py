"""Serviço systemd (de usuário) por produto web.

Cada produto web que fica pronto ganha um serviço systemd de usuário
(`empresa-produto-<slug>.service`) que:

  * roda `python3 app.py` na pasta do produto;
  * recebe a porta estável do produto por `PORT` e `<SLUG>_PORTA`;
  * **reinicia sozinho** se cair (`Restart=on-failure`);
  * sobe no login (e no boot, se `linger` estiver ligado).

Assim o link "▶ Abrir" do painel aponta para algo que **não morre** quando o
processo solto termina. Os serviços vivem em `~/.config/systemd/user/` (fora do
repositório) e os logs vão para o journal:
`journalctl --user -u empresa-produto-<slug> -f`.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config, db

_XDG = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
UNIDADES = _XDG / "systemd" / "user"
PYTHON = (os.environ.get("EMPRESA_PYTHON")
          or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else None)
          or shutil.which("python3") or "python3")

# estágios antes de o app existir de fato (não instalar serviço ainda)
_EM_BUILD = ("ideia", "pesquisa", "produto", "design", "arquitetura", "build")


def nome(slug: str) -> str:
    """Nome da unidade systemd do produto."""
    return f"empresa-produto-{slug}"


def _unidade(slug: str) -> Path:
    return UNIDADES / f"{nome(slug)}.service"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True, check=False)


def ativo(slug: str) -> bool:
    return _systemctl("is-active", "--quiet", nome(slug)).returncode == 0


def tem_unidade(slug: str) -> bool:
    return _unidade(slug).exists()


def _pasta(p: dict) -> Path:
    return config.RAIZ / (p.get("pasta") or f"produtos/{p['slug']}")


# --- portas ---------------------------------------------------------------

def _ocupada(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def _porta_livre(inicial: int) -> int:
    porta = max(1024, inicial)
    for _ in range(200):
        if not _ocupada(porta):
            return porta
        porta += 1
    return inicial


def _porta_do_url(p: dict) -> int | None:
    m = re.search(r":(\d{2,5})", p.get("url") or "")
    return int(m.group(1)) if m else None


def porta_de(p: dict) -> int:
    """Porta estável do produto.

    Reusa a porta já gravada na URL; se ela estiver ocupada por outro processo
    (e não pelo nosso próprio serviço), pega a próxima livre para não colidir.
    """
    slug = p["slug"]
    base = _porta_do_url(p)
    if base is None:
        return _porta_livre(8790 + (abs(hash(slug)) % 200))
    if _ocupada(base) and not ativo(slug):
        return _porta_livre(base + 1)
    return base


def _responde(porta: int, tentativas: int = 20, espera: float = 1.0) -> bool:
    for _ in range(tentativas):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=3)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(espera)
    return False


# --- unidade systemd ------------------------------------------------------

def _workdir(pasta: Path) -> str:
    try:
        return f"%h/{pasta.relative_to(Path.home())}"
    except ValueError:
        return str(pasta)


def _texto_unidade(p: dict, porta: int) -> str:
    pasta = _pasta(p)
    var_porta = p["slug"].upper().replace("-", "_")
    return (
        "[Unit]\n"
        f"Description=Empresa IA - produto {p['slug']} ({p.get('tipo', 'web')})\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={_workdir(pasta)}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        f"Environment=PORT={porta}\n"
        f"Environment={var_porta}_PORTA={porta}\n"
        f"ExecStart={PYTHON} app.py\n"
        "Restart=on-failure\n"
        "RestartSec=2\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _escrever(p: dict, porta: int) -> None:
    UNIDADES.mkdir(parents=True, exist_ok=True)
    _unidade(p["slug"]).write_text(_texto_unidade(p, porta), encoding="utf-8")


def _esperar(porta: int, url: str) -> str | None:
    return url if _responde(porta) else None


# --- API pública ----------------------------------------------------------

def instalar(p: dict) -> str | None:
    """Escreve/atualiza o serviço do produto, liga e devolve a URL (ou None).

    Idempotente: se o serviço já está no ar e responde, devolve a URL na hora.
    """
    if not p or not (p.get("slug")):
        return None
    pasta = _pasta(p)
    if not (pasta / "app.py").exists():
        return None

    slug = p["slug"]
    porta = porta_de(p)

    if ativo(p["slug"]) and _responde(porta, tentativas=1):
        url = f"http://127.0.0.1:{porta}"
        _gravar_url(p, url)
        return url

    _escrever(p, porta)
    _systemctl("daemon-reload")
    _systemctl("enable", nome(p["slug"]))
    _systemctl("restart", nome(p["slug"]))

    if not _responde(porta):
        return None
    url = f"http://127.0.0.1:{porta}"
    _gravar_url(p, url)
    return url


def remover(slug: str) -> None:
    _systemctl("disable", "--now", nome(slug))
    try:
        _unidade(slug).unlink()
    except FileNotFoundError:
        pass
    _systemctl("daemon-reload")


def _gravar_url(p: dict, url: str) -> None:
    if p.get("url") != url:
        try:
            db.atualizar_produto(p["id"], url=url)
            p["url"] = url
        except Exception:  # noqa: BLE001
            pass


# --- operações em lote / CLI ---------------------------------------------

def _web_com_app() -> list[dict]:
    produtos = db.listar_produtos()
    out = []
    for p in produtos:
        if str(p.get("tipo", "web")).lower() == "android":
            continue
        if (_pasta(p) / "app.py").exists():
            # só produtos já prontos (fora do build); os em construção
            # ganham serviço quando o build termina (via monitor).
            if p.get("url") or p.get("estagio") not in _EM_BUILD:
                out.append(p)
    return out


def ligar_linger() -> bool:
    """Liga `linger` para o usuário (serviços sobem no boot, sem login)."""
    try:
        r = subprocess.run(["loginctl", "enable-linger"],
                           capture_output=True, text=True, check=False)
        return r.returncode == 0
    except OSError:
        return False


def instalar_todos() -> list[tuple[str, str | None]]:
    db.init()
    ligar_linger()
    resultado = []
    for p in _web_com_app():
        try:
            resultado.append((p["slug"], instalar(p)))
        except Exception as e:  # noqa: BLE001
            resultado.append((p["slug"], None))
            print(f"[servico] erro em {p['slug']}: {e}", flush=True)
    return resultado


def executar(argumento: str | None = None) -> int:
    from . import agentes

    agentes.inicializar()
    if argumento in ("--todos", "todos", "-a", None):
        pares = instalar_todos()
        for slug, url in pares:
            marca = url or "não subiu"
            print(f"  {slug:<18} {marca}")
        return 0
    if argumento in ("--listar", "listar", "status", "-l"):
        for p in _web_com_app():
            estado = "ativo" if ativo(p["slug"]) else "parado"
            unidade = "tem unidade" if tem_unidade(p["slug"]) else "sem unidade"
            print(f"  {p['slug']:<18} {estado:<8} {unidade:<12} {p.get('url') or ''}")
        return 0
    if argumento in ("--remover", "remover"):
        return 0
    # argumento = slug do produto
    alvo = next((p for p in _web_com_app() if p["slug"] == argumento), None)
    if not alvo:
        print(f"produto web com app não encontrado: {argumento}")
        return 1
    url = instalar(alvo)
    print(f"  {alvo['slug']:<18} {url or 'não subiu'}")
    return 0 if url else 1
