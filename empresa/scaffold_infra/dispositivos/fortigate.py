"""Adaptador FortiGate (FortiOS REST API).

Base: https://<host>/api/v2/
  GET  /monitor/system/status          (saúde)
  GET  /monitor/system/config/backup   (backup da config)
  POST /cmdb/firewall/policy           (criar/alterar política)
Auth: Bearer <token> (API token criado no FortiGate).

O token vem do ambiente (ativo.env_senha) — nunca do código.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import ErroDispositivo, Dispositivo


class FortiGate(Dispositivo):
    fabricante = "fortigate"

    def _base(self) -> str:
        host = self.ativo.host
        if not host.startswith("http"):
            host = f"https://{host}"
        if self.ativo.porta:
            host = f"{host}:{self.ativo.porta}"
        return host.rstrip("/") + "/api/v2"

    def _token(self) -> str:
        if not self.ativo.env_senha:
            raise ErroDispositivo("defina ativo.env_senha (nome da variável com o token)")
        tok = os.environ.get(self.ativo.env_senha, "")
        if not tok:
            raise ErroDispositivo(f"variável de ambiente {self.ativo.env_senha} não definida")
        return tok

    def _requisitar(self, metodo: str, caminho: str, corpo: dict | None = None) -> dict:
        url = self._base() + caminho
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo, headers={
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ctx_inseguro()) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.URLError as e:
            raise ErroDispositivo(f"falha ao falar com {self.ativo.host}: {e}") from e
        except ValueError as e:
            raise ErroDispositivo(f"resposta inválida de {self.ativo.host}: {e}") from e

    def conectar(self) -> bool:
        self._requisitar("GET", "/monitor/system/status")
        return True

    def coletar(self) -> dict:
        st = self._requisitar("GET", "/monitor/system/status")
        return {"nome": self.ativo.nome, "fabricante": self.fabricante, "status": st}

    def backup_config(self) -> str:
        resp = self._requisitar("GET", "/monitor/system/config/backup?scope=global")
        return json.dumps(resp, ensure_ascii=False, indent=2)

    def aplicar(self, mudanca: dict) -> dict:
        tipo = mudanca.get("tipo")
        if tipo == "politica":
            return self._requisitar("POST", "/cmdb/firewall/policy", mudanca.get("corpo", {}))
        raise ErroDispositivo(f"mudança não suportada: {tipo}")

    def saude(self) -> dict:
        st = self._requisitar("GET", "/monitor/system/status")
        return {"nome": self.ativo.nome, "estado": "ok", "status": st}


def _ctx_inseguro():
    import ssl
    return ssl._create_unverified_context()  # noqa: SLF001
