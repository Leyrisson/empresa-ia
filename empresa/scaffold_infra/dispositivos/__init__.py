"""Pacote de adaptadores multi-fabricante.

Use sempre a fábrica, nunca importe um fabricante direto no app:

    from dispositivos import carregar_inventario, fabricar

    for ativo in carregar_inventario("inventario.json"):
        dev = fabricar(ativo)
        inventario = dev.coletar()
        config = dev.backup_config()
        resultado = dev.mudar({"tipo": "adicionar_rota", ...})  # com rollback
"""
from .base import Ativo, Dispositivo, ErroDispositivo, carregar_inventario, fabricar

__all__ = ["Ativo", "Dispositivo", "ErroDispositivo", "fabricar", "carregar_inventario"]
