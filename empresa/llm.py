"""Backend de LLM (sem dependencias externas) + braco opencode.

- `gerar()`       -> fala com ollama (ou localai) via HTTP puro.
- `extrair_json()`-> robustez para modelos que embrulham JSON em texto.
- `rodar_opencode()` -> deixa o setor de desenvolvimento ESCREVER codigo de verdade.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from . import config
from .db import agora

# garante que o opencode (instalado via mise) seja achavel num servico systemd
_CAMINHOS_EXTRA = [
    os.path.expanduser("~/.local/share/mise/shims"),
    os.path.expanduser("~/.local/bin"),
    "/usr/local/bin",
    "/usr/bin",
]


def _ambiente() -> dict:
    env = dict(os.environ)
    partes = env.get("PATH", "").split(":")
    for p in _CAMINHOS_EXTRA:
        if os.path.isdir(p) and p not in partes:
            partes.insert(0, p)
    env["PATH"] = ":".join(partes)
    return env


def acha_opencode() -> str | None:
    for p in _CAMINHOS_EXTRA:
        cand = os.path.join(p, "opencode")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("opencode", path=":".join(_CAMINHOS_EXTRA + [os.environ.get("PATH", "")]))


def _post_json(url: str, corpo: dict, timeout: int) -> dict:
    dados = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gerar(
    prompt: str,
    sistema: str | None = None,
    modelo: str | None = None,
    json_mode: bool = False,
    num_predict: int = 400,
    temperatura: float = 0.7,
) -> str:
    """Chama o LLM local e devolve o texto. Nunca levanta: em falha devolve ''."""
    if config.BACKEND == "offline":
        return ""
    mensagens = []
    if sistema:
        mensagens.append({"role": "system", "content": sistema})
    mensagens.append({"role": "user", "content": prompt})
    try:
        if config.BACKEND == "localai":
            corpo = {
                "model": modelo or config.MODELO_PLANEJADOR,
                "messages": mensagens,
                "temperature": temperatura,
                "max_tokens": num_predict,
            }
            resp = _post_json(config.LOCALAI_URL.rstrip("/") + "/v1/chat/completions", corpo, config.TIMEOUT_LLM)
            return resp["choices"][0]["message"]["content"]
        # ollama
        corpo = {
            "model": modelo or config.MODELO_PLANEJADOR,
            "messages": mensagens,
            "stream": False,
            "options": {"num_predict": num_predict, "temperature": temperatura},
        }
        if json_mode:
            corpo["format"] = "json"
        resp = _post_json(config.OLLAMA_URL.rstrip("/") + "/api/chat", corpo, config.TIMEOUT_LLM)
        return resp.get("message", {}).get("content", "")
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as e:
        return f"__ERRO_LLM__ {type(e).__name__}: {e}"


def extrair_json(texto: str) -> dict | None:
    if not texto:
        return None
    if texto.startswith("__ERRO_LLM__"):
        return None
    try:
        return json.loads(texto)
    except ValueError:
        pass
    m = re.search(r"\{[\s\S]*\}", texto)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def rodar_opencode(instrucao: str, pasta: str, timeout: int | None = None,
                   log_path: str | None = None) -> tuple[bool, str]:
    """Roda `opencode run --auto` numa pasta e devolve (ok, saida).

    - `os.nice` + `start_new_session`: roda em segundo plano, sem atrapalhar.
    - stdin fechado (licao do Telebot: com stdin de terminal o processo nao encerra).
    """
    exe = acha_opencode()
    if not exe:
        return False, "opencode nao encontrado no PATH"
    os.makedirs(pasta, exist_ok=True)
    env = _ambiente()

    def _preexec():
        try:
            os.nice(config.NICE)
        except OSError:
            pass

    try:
        proc = subprocess.Popen(
            [exe, "run", "--auto", instrucao],
            cwd=pasta,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            preexec_fn=_preexec,
        )
    except OSError as e:
        return False, f"falha ao iniciar opencode: {e}"

    try:
        saida, _ = proc.communicate(timeout=timeout or config.TIMEOUT_BUILD)
    except subprocess.TimeoutExpired:
        proc.kill()
        saida, _ = proc.communicate()
        saida = (saida or "") + f"\n[TIMEOUT apos {timeout or config.TIMEOUT_BUILD}s]"
        return False, saida
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"\n\n===== opencode {agora()} =====\n{saida}\n")
        except OSError:
            pass
    return proc.returncode == 0, saida or ""


def disponivel() -> dict:
    """Auto-diagnostico rapido do backend."""
    info = {"backend": config.BACKEND, "ollama": False, "modelos": [], "opencode": acha_opencode()}
    if config.BACKEND == "ollama":
        try:
            with urllib.request.urlopen(config.OLLAMA_URL.rstrip("/") + "/api/tags", timeout=5) as r:
                info["ollama"] = True
                info["modelos"] = [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception:  # noqa: BLE001
            pass
    return info


if __name__ == "__main__":
    print(json.dumps(disponivel(), indent=2, ensure_ascii=False))
    print("gerar:", gerar("Diga apenas: olá", num_predict=10))
    sys.exit(0)
