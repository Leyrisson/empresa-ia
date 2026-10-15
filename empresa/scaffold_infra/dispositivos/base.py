"""Camada de adaptadores multi-fabricante (Palo Alto, FortiGate, MikroTik...).

REGRA DE OURO desta camada:
  * O aplicativo NUNCA chama a API de um fabricante diretamente. Ele pede um
    dispositivo a `fabricar(ativo)` e usa o contrato (conectar/coletar/
    backup_config/aplicar/saude).
  * Trocar o modo SIMULADO por equipamento REAL é uma mudança de inventário,
    não de código do app.

Nada aqui depende de biblioteca externa: só a stdlib do Python.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Ativo:
    """Um equipamento no inventário."""
    nome: str
    fabricante: str
    host: str
    porta: int = 0
    usuario: str = ""
    # A senha NUNCA fica no inventário versionado. Guarde aqui o NOME da
    # variável de ambiente que contém a senha (ex.: "FW_EDGE_SENHA").
    env_senha: str = ""
    extras: dict = field(default_factory=dict)


class Dispositivo:
    """Contrato de um equipamento. Cada fabricante implementa os métodos."""

    fabricante = "base"
    simulado = False

    def __init__(self, ativo: Ativo):
        self.ativo = ativo

    # --- contrato -----------------------------------------------------
    def conectar(self) -> bool:
        """Estabelece sessão. Levanta ErroDispositivo se não alcançar."""
        raise NotImplementedError

    def coletar(self) -> dict:
        """Inventário/estado atual (interfaces, rotas, versão, licenças...)."""
        raise NotImplementedError

    def backup_config(self) -> str:
        """Configuração atual como texto. OBRIGATÓRIO antes de aplicar."""
        raise NotImplementedError

    def aplicar(self, mudanca: dict) -> dict:
        """Aplica uma mudança e devolve o resultado.

        Deve SEMPRE fazer backup_config() antes e guardar o suficiente para
        o rollback. Levanta ErroDispositivo em falha (sem deixar meio aplicado).
        """
        raise NotImplementedError

    def saude(self) -> dict:
        """Estado de saúde: latência, CPU, memória, uptime."""
        raise NotImplementedError

    # --- utilidades ---------------------------------------------------
    # --- utilidades ---------------------------------------------------
    def mudar(self, mudanca: dict) -> dict:
        """Aplica com backup + rollback automático em caso de falha."""
        antes = self.backup_config()
        try:
            resultado = self.aplicar(mudanca)
        except Exception as e:  # noqa: BLE001
            try:
                volta = self.reverter(antes)
            except Exception as e2:  # noqa: BLE001
                return {"ok": False, "erro": str(e),
                        "rollback": {"ok": False, "erro": str(e2)}}
            return {"ok": False, "erro": str(e), "rollback": rb(volta)}
        return {"ok": True, "resultado": resultado, "backup_antes": antes}

    def reverter(self, config: str) -> dict:
        """Reaplica uma configuração anterior (rollback)."""
        return self.aplicar({"tipo": "restaurar_config", "config": config})


class ErroDispositivo(RuntimeError):
    """Falha ao falar com o equipamento (rede, auth, API)."""


def fabricar(ativo: Ativo) -> Dispositivo:
    """Fábrica de adaptadores. Import tardio de propósito (evita dependência)."""
    fab = (ativo.fabricante or "").strip().lower()
    if fab in ("paloalto", "pan-os", "panos", "palo_alto"):
        from .paloalto import PaloAlto
        return PaloAlto(ativo)
    if fab in ("fortigate", "fortinet", "fortios"):
        from .fortigate import FortiGate
        return FortiGate(ativo)
    if fab in ("mikrotik", "routeros", "router_os"):
        from .routeros import RouterOS
        return RouterOS(ativo)
    from .simulado import Simulado
    return Simulado(ativo)


def carregar_inventario(caminho: str = "inventario.json") -> list[Ativo]:
    """Lê o inventário (JSON) e devolve a lista de ativos."""
    import json
    import os
    if not os.path.isfile(caminho):
        return []
    with open(caminho, encoding="utf-8") as fh:
        dados = json.load(fh)
    itens = dados.get("dispositivos", dados if isinstance(dados, list) else [])
    ativos = []
    for d in itens:
        ativos.append(Ativo(
            nome=d.get("nome", "dispositivo"),
            fabricante=d.get("fabricante", "simulado"),
            host=d.get("host", "127.0.0.1"),
            porta=int(d.get("porta", 0) or 0),
            usuario=d.get("usuario", ""),
            env_senha=d.get("env_senha", ""),
            extras=d.get("extras", {}),
        ))
    return ativos


__all__ = ["Ativo", "Dispositivo", "ErroDispositivo", "fabricar", "carregar_inventario"]
