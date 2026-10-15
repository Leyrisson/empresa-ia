"""Adaptador Palo Alto (PAN-OS XML API) — REST/fragmentos.

Endpoints reais:
  https://<host>/api/?type=op&cmd=<show system info>       (chave de API)
  https://<host>/api/?type=config&action=show
  https://<host>/api/?type=config&action=set&xpath=...&element=...
Autenticação por API key (gerada no device) OU usuário/senha (type=keygen).

A senha/key vem do ambiente (ativo.env_senha) — nunca do código.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from .base import ErroDispositivo, Dispositivo


class PaloAlto(Dispositivo):
    fabricante = "paloalto"

    def _url(self, params: dict) -> str:
        esquema = "https"
        host = self.ativo.host
        if not host.startswith("http"):
            host = f"{esquema}://{host}"
        if self.ativo.porta:
            host = f"{host}:{self.ativo.porta}"
        return f"{host}/api/?" + urllib.parse.urlencode(params)

    def _segredo(self) -> str:
        return os.environ.get(self.ativo.env_senha, "") if self.ativo.env_senha else ""

    def _chamar(self, params: dict) -> str:
        if not self.ativo.env_senha:
            raise ErroDispositivo("defina ativo.env_senha (nome da variável com a API key)")
        chave = self._segredo()
        if not chave:
            raise ErroDispositivo(f"variável de ambiente {self.ativo.env_senha} não definida")
        params = dict(params, key=chave)
        req = urllib.request.Request(self._url(params), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ctx_inseguro()) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            raise ErroDispositivo(f"falha ao falar com {self.ativo.host}: {e}") from e

    def conectar(self) -> bool:
        self._chamar({"type": "op", "cmd": "<show><system><info></info></system></show>"})
        return True

    def coletar(self) -> dict:
        import xml.etree.ElementTree as ET
        texto = self._chamar({"type": "op", "cmd": "<show><system><info></info></system></show>"})
        dados = {}
        try:
            raiz = ET.fromstring(texto)
            for tag in ("hostname", "model", "sw-version", "uptime"):
                el = raiz.find(f".//{tag}")
                if el is not None:
                    dados[tag.replace("-", "_")] = (el.text or "").strip()
        except ET.ParseError:
            dados["bruto"] = texto[:400]
        return {"nome": self.ativo.nome, "fabricante": self.fabricante, **dados}

    def backup_config(self) -> str:
        return self._chamar({"type": "config", "action": "show"})

    def aplicar(self, mudanca: dict) -> dict:
        tipo = mudanca.get("tipo")
        if tipo == "set":
            params = {"type": "config", "action": "set",
                      "xpath": mudanca["xpath"], "element": mudanca["element"]}
            self._chamar(params)
            return {"ok": True, "aplicado": mudanca["xpath"]}
        if tipo == "commit":
            self._chamar({"type": "commit", "cmd": "<commit></commit>"})
            return {"ok": True, "aplicado": "commit"}
        raise ErroDispositivo(f"mudança não suportada: {tipo}")

    def saude(self) -> dict:
        info = self.coletar()
        return {"nome": self.ativo.nome, "uptime": info.get("uptime"), "estado": "ok"}


def _ctx_inseguro():
    import ssl
    # Muitos equipamentos usam certificado auto-assinado. Aceitar isso é uma
    # decisão explícita do operador — documentada no README do produto.
    return ssl._create_unverified_context()  # noqa: SLF001
