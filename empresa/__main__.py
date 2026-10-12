"""CLI da Empresa IA.

Uso:
  python -m empresa servir        # só o dashboard (http://127.0.0.1:8770)
  python -m empresa trabalhar     # só o loop de trabalho (segundo plano)
  python -m empresa tudo          # dashboard + loop no mesmo processo
  python -m empresa um-ciclo      # executa uma rodada e sai (teste)
  python -m empresa status        # imprime o estado em texto
  python -m empresa doutor        # checa backend/ollama/opencode
  python -m empresa servico       # cria/sobe serviço systemd dos produtos web
  python -m empresa servico <slug>  # só de um produto
"""
from __future__ import annotations

import sys
import threading


def _monitorar() -> int:
    from . import monitor
    monitor.executar()
    return 0


def _status() -> int:
    from . import agentes, db
    agentes.inicializar()
    s = db.snapshot()
    c = s["config"]
    print(f"Empresa IA — backend={c['backend']} build={c['modo_build']} "
          f"modelo={c['modelo_planejador']} intensidade={c['intensidade']} "
          f"pausada={c['pausada']} builds_hoje={c['builds_hoje']} tick={c['tick']}")
    print(f"\nSetores e funcionários:")
    for setor in s["setores"]:
        f = s["funcionarios"].get(setor["id"], {})
        print(f"  {setor['emoji']} {setor['nome']:<24} {f.get('status','?'):<12} {f.get('tarefa_atual') or ''}")
    print("\nProdutos:")
    for p in s["produtos"]:
        print(f"  [{p['estagio']:>11}] {p['nome']} ({p['tipo']}) {p['progresso']}% "
              f"MRR~R${p['mrr_estimado']:.0f} status={p['status']}")
    print("\nÚltimas mensagens:")
    for m in s["mensagens"][:10]:
        print(f"  {m['de']:>12} -> {m['para']:<12} {m['tipo']:<9} {m['conteudo'][:70]}")
    return 0


def _doutor() -> int:
    import json
    from . import db, llm
    db.init()
    print(json.dumps(llm.disponivel(), indent=2, ensure_ascii=False))
    print("gerar():", llm.gerar("Diga apenas: pronto", num_predict=8))
    return 0


def main(argv: list[str] | None = None) -> int:
    from . import agentes, config, dashboard, orquestrador
    args = argv if argv is not None else sys.argv[1:]
    cmd = args[0] if args else "status"

    if cmd == "servir":
        dashboard.servir()
    elif cmd == "trabalhar":
        orquestrador.executar()
    elif cmd in ("um-ciclo", "1"):
        orquestrador.um_ciclo()
        print("um ciclo executado.")
    elif cmd in ("status", "st"):
        return _status()
    elif cmd in ("doutor", "doctor"):
        return _doutor()
    elif cmd in ("monitorar", "monitor"):
        return _monitorar()
    elif cmd in ("servico", "servicos", "serviço", "service"):
        from . import servico
        return servico.executar(args[1] if len(args) > 1 else None)
    elif cmd == "tudo":
        agentes.inicializar()
        t = threading.Thread(target=orquestrador.executar, daemon=True)
        t.start()
        dashboard.servir()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
