"""Dispositivo SIMULADO: implementa o contrato sem gear real.

É código de verdade (não um mock de teste): guarda config em memória, simula
interfaces, rotas e erro ocasional, e serve para desenvolver e testar o app
inteiro sem nenhum equipamento. Em produção, troque o inventário para um
fabricante real — o app não muda.
"""
from __future__ import annotations

import random
import time

from .base import Ativo, Dispositivo, ErroDispositivo

_INTERFACES = [
    {"nome": "ether1", "tipo": "physical", "ip": "10.0.0.1/24", "up": True, "velocidade": "1G"},
    {"nome": "ether2", "tipo": "physical", "ip": "10.0.1.1/24", "up": True, "velocidade": "1G"},
    {"nome": "sfp1", "tipo": "physical", "ip": "", "up": False, "velocidade": "10G"},
    {"nome": "vlan10", "tipo": "vlan", "ip": "10.10.0.1/24", "up": True, "velocidade": "-"},
]

_ROTAS = [
    {"destino": "0.0.0.0/0", "gateway": "10.0.0.254", "distancia": 1},
    {"destino": "10.10.0.0/24", "gateway": "0.0.0.0", "distancia": 0},
]


class Simulado(Dispositivo):
    fabricante = "simulado"
    simulado = True
    _config: str = ""

    def __init__(self, ativo: Ativo):
        super().__init__(ativo)
        self._conectado = False
        if not Simulado._config:
            Simulado._config = self._config_inicial()

    def _config_inicial(self) -> str:
        linhas = [f"# configuração de {self.ativo.nome} (simulado)"]
        for i in _INTERFACES:
            linhas.append(f"interface {i['nome']} ip {i['ip'] or '-'} up={i['up']}")
        for r in _ROTAS:
            linhas.append(f"rota {r['destino']} via {r['gateway']}")
        return "\n".join(linhas) + "\n"

    def conectar(self) -> bool:
        self._conectado = True
        return True

    def _exigir_sessao(self) -> None:
        if not self._conectado:
            self.conectar()

    def coletar(self) -> dict:
        self._exigir_sessao()
        return {
            "nome": self.ativo.nome,
            "fabricante": self.fabricante,
            "host": self.ativo.host,
            "modelo": "SIM-100",
            "versao": "1.0.0-sim",
            "interfaces": [dict(i) for i in _INTERFACES],
            "rotas": [dict(r) for r in _ROTAS],
            "uptime_s": 86400,
        }

    def backup_config(self) -> str:
        self._exigir_sessao()
        return Simulado._config

    def aplicar(self, mudanca: dict) -> dict:
        self._exigir_sessao()
        tipo = mudanca.get("tipo")
        if tipo == "restaurar_config":
            Simulado._config = mudanca.get("config", Simulado._config)
            return {"ok": True, "aplicado": "restaurar_config"}
        if tipo == "adicionar_rota":
            destino = mudanca.get("destino")
            gw = mudanca.get("gateway", "0.0.0.0")
            if not destino:
                raise ErroDispositivo("campo 'destino' obrigatório")
            _ROTAS.append({"destino": destino, "gateway": gw, "distancia": 1})
            Simulado._config += f"rota {destino} via {gw}\n"
            return {"ok": True, "aplicado": "adicionar_rota", "destino": destino}
        if tipo == "desligar_interface":
            nome = mudanca.get("interface")
            for i in _INTERFACES:
                if i["nome"] == nome:
                    i["up"] = False
                    return {"ok": True, "aplicado": "desligar_interface", "interface": nome}
            raise ErroDispositivo(f"interface {nome} não encontrada")
        # Simula instabilidade de rede ocasional (para o app tratar).
        if random.random() < 0.05:
            raise ErroDispositivo("timeout simulado ao aplicar mudança")
        return {"ok": True, "aplicado": tipo or "generico"}

    def saude(self) -> dict:
        self._exigir_sessao()
        return {
            "nome": self.ativo.nome,
            "latencia_ms": round(random.uniform(0.4, 3.0), 2),
            "cpu_pct": round(random.uniform(3, 25), 1),
            "memoria_pct": round(random.uniform(10, 45), 1),
            "uptime_s": 86400,
            "ts": time.time(),
        }
