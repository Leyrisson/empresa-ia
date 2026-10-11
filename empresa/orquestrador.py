"""Orquestrador: o loop em segundo plano que faz a empresa funcionar.

- Roda o gerente e depois cada setor, UM DE CADA VEZ (serializa as chamadas de
  LLM e o uso do opencode -> não disputa recursos com você).
- Baixa prioridade (os.nice) e intervalo entre ciclos (config.SLEEP).
- Pausa/retoma por flag no banco ou pelo arquivo var/PAUSA (dashboard).
"""
from __future__ import annotations

import os
import signal
import sys
import time
import traceback

from . import agentes, config, db, obsidian, relatorio
from .setores import SETORES

_PARAR = False


def _resumos_no_obsidian() -> None:
    """Notas-resumo de cada produto no vault (barato, idempotente)."""
    try:
        obsidian.escrever_indice()
        for p in db.listar_produtos():
            obsidian.escrever_resumo_produto(p)
    except Exception:  # noqa: BLE001
        agentes.log("ERRO escrevendo Obsidian: " + traceback.format_exc(limit=2))


def _verificar_relatorio_diario() -> None:
    """Dispara o relatório do dia quando a hora configurada chegar (1x/dia)."""
    hoje = time.strftime("%Y-%m-%d")
    if int(time.strftime("%H")) >= config.HORA_RELATORIO:
        if not db.relatorio_do_dia(hoje):
            try:
                r = relatorio.rodar()
                if r:
                    agentes.log(f"relatorio diario entregue ({r['canais']})")
            except Exception:  # noqa: BLE001
                agentes.log("ERRO relatorio: " + traceback.format_exc(limit=2))


def _sinais(_sig, _frame):
    global _PARAR
    _PARAR = True


def pausada() -> bool:
    return bool(db.cfg_get("pausada", False)) or config.PAUSA.exists()


def um_ciclo() -> None:
    """Uma volta completa: gerente + todos os setores."""
    agentes.inicializar()
    db.cfg_set("ultimo_tick", db.agora())
    agentes.ciclo_gerente()
    _resumos_no_obsidian()
    for s in SETORES:
        if _PARAR:
            return
        if s["id"] == "gerencia":
            continue
        if not pausada():
            try:
                agentes.ciclo_funcionario(s["id"])
            except Exception:  # noqa: BLE001
                agentes.log("ERRO ciclo " + s["id"] + ": " + traceback.format_exc(limit=2))


def executar(intervalo: float | None = None) -> None:
    """Loop principal (bloqueante). Use via systemd."""
    try:
        os.nice(config.NICE)
    except OSError:
        pass
    signal.signal(signal.SIGTERM, _sinais)
    signal.signal(signal.SIGINT, _sinais)

    agentes.inicializar()
    agentes.log(f"orquestrador iniciado (backend={config.BACKEND}, build={config.MODO_BUILD}, "
                f"intensidade={config.INTENSIDADE}, intervalo={intervalo or config.SLEEP}s)")

    while not _PARAR:
        try:
            if pausada():
                db.cfg_set("ultimo_tick", "pausada")
                time.sleep(3)
                continue
            um_ciclo()
            _verificar_relatorio_diario()
        except Exception:  # noqa: BLE001
            agentes.log("ERRO ciclo principal: " + traceback.format_exc(limit=3))
        for _ in range(int((intervalo or config.SLEEP) * 10)):
            if _PARAR:
                break
            time.sleep(0.1)
    agentes.log("orquestrador encerrado")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--uma-vez" in argv or "-1" in argv:
        um_ciclo()
        print("um ciclo executado.")
        return 0
    executar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
