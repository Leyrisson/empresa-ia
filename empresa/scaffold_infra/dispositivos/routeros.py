"""Adaptador MikroTik (RouterOS).

Duas vias comuns:
  * REST API (RouterOS v7): http://<host>/rest/... com Basic Auth.
  * API binária (v6, porta 8728) — aqui usamos a via REST, mais simples.

Endpoints REST (v7):
  GET  /rest/system/resource
  GET  /rest/interface
  GET  /rest/ip/route
  PUT  /rest/ip/route            (adicionar rota)
Auth: usuário/senha (Basic). A senha vem do ambiente (ativo.env_senha).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from .base import ErroDispositivo, Dispositivo


class RouterOS(Dispositivo):
    fabricante = "mikrotik"

    def _base(self) -> str:
        host = self.ativo.host
        if not host.startswith("http"):
            esquema = "https" if self.ativo.extras.get("tls") else "http"
            host = f"{esquema}://{host}"
        if self.ativo.porta:
            host = f"{host}:{self.ativo.porta}"
        return host.rstrip("/") + "/rest"

    def _auth(self) -> str:
        senha = os.environ.get(self.ativo.env_senha, "") if self.ativo.env_senha else ""
        user = self.ativo.usuario or "admin"
        tok = base64.b64encode(f"{user}:{senha}".encode("utf-8")).decode("ascii")
        return f"Basic {tok}"

    def _requisitar(self, metodo: str, caminho: str, corpo: dict | None = None) -> list | dict:
        url = self._base() + caminho
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo, headers={
            "Authorization": self._auth(),
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ctx_inseguro()) as r:
                txt = r.read().decode("utf-8", "replace")
                return json.loads(txt) if txt.strip() else {}
        except urllib.error.HTTPError as e:
            raise ErroDispositivo(f"HTTP {e.code} em {self.ativo.host}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ErroDispositivo(f"falha ao falar com {self.ativo.host}: {e}") from e

    def conectar(self) -> bool:
        self._requisitar("GET", "/system/resource")
        return True

    def coletar(self) -> dict:
        recurso = self._requisitar("GET", "/system/resource")
        interfaces = self._requisitar("GET", "/interface")
        rotas = self._requisitar("GET", "/ip/route")
        return {
            "nome": self.ativo.nome, "fabricante": self.fabricante,
            "recurso": recurso, "interfaces": interfaces, "rotas": rotas,
        }

    def backup_config(self) -> str:
        interfaces = self._requisitar("GET", "/interface")
        rotas = self._requisitar("GET", "/ip/route")
        return json.dumps({"interfaces": interfaces, "rotas": rotas},
                          ensure_ascii=False, indent=2)

    def aplicar(self, mudanca: dict) -> dict:
        tipo = mudanca.get("tipo")
        if tipo == "adicionar_rota":
            return self._requisitar("PUT", "/ip/route", {
                "dst-address": mudanca["destino"],
                "gateway": mudanca.get("gateway", ""),
            })
        raise ErroDispositivo(f"mudança não suportada: {tipo}")

    def saude(self) -> dict:
        r = self._requisitar("GET", "/system/resource")
        return {"nome": self.ativo.nome, "estado": "ok", "recurso": r}


def _ctx_inseguro():
    import ssl
    return ssl._create_unverified_context()  # noqa: SLF001
