"""Dashboard: servidor HTTP (stdlib) que mostra o escritório e a API de controle."""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agentes, config, db

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
        ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # silencia o log do http.server
        pass

    # ---------- helpers ----------
    def _json(self, obj, code=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, caminho: str):
        if not os.path.isfile(caminho):
            self.send_error(404)
            return
        ext = os.path.splitext(caminho)[1].lower()
        with open(caminho, "rb") as fh:
            corpo = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _ler_corpo(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, TypeError):
            return {}

    # ---------- rotas ----------
    def do_GET(self):
        rota = urlparse(self.path).path
        if rota in ("/", "/index.html"):
            return self._arquivo(str(config.TEMPLATES / "escritorio.html"))
        if rota == "/api/estado":
            return self._json(db.snapshot())
        if rota == "/api/ideias":
            return self._json(db.listar_ideias())
        if rota == "/api/relatorios":
            return self._json(db.listar_relatorios())
        if rota == "/api/conhecimento":
            with db.conectar() as con:
                return self._json([dict(r) for r in con.execute(
                    "SELECT setor, versao, atualizado_em FROM conhecimento ORDER BY setor")])
        if rota == "/api/conhecimento/texto":
            from urllib.parse import parse_qs
            setor = parse_qs(urlparse(self.path).query).get("setor", [""])[0]
            from . import conhecimento as kn
            return self._json({"setor": setor, "conteudo": kn.ler(setor)})
        if rota.startswith("/static/"):
            rel = rota[len("/static/"):].lstrip("/")
            if ".." in rel:
                return self.send_error(400)
            return self._arquivo(str(config.STATIC / rel))
        self.send_error(404)

    def do_POST(self):
        rota = urlparse(self.path).path
        corpo = self._ler_corpo()

        if rota == "/api/pausar":
            valor = bool(corpo.get("pausada", True))
            db.cfg_set("pausada", valor)
            if config.PAUSA.exists() and not valor:
                config.PAUSA.unlink(missing_ok=True)
            db.mensagem("gerencia", "todos",
                        "Empresa PAUSADA pelo dono." if valor else "Empresa RETOMADA pelo dono.",
                        tipo="anuncio")
            return self._json({"ok": True, "pausada": valor})

        if rota == "/api/intensidade":
            valor = str(corpo.get("valor", "baixa")).lower()
            if valor not in ("baixa", "media", "alta"):
                return self._json({"erro": "valor inválido"}, 400)
            db.cfg_set("intensidade", valor)
            config.INTENSIDADE = valor
            config.SLEEP = {"baixa": 20.0, "media": 8.0, "alta": 3.0}[valor]
            db.mensagem("gerencia", "todos", f"Intensidade ajustada para: {valor}.", tipo="anuncio")
            return self._json({"ok": True, "intensidade": valor})

        if rota == "/api/meta":
            try:
                valor = float(corpo.get("meta_mrr", 0))
            except (TypeError, ValueError):
                return self._json({"erro": "número inválido"}, 400)
            db.cfg_set("meta_mrr", valor)
            config.META_MRR = valor
            db.mensagem("gerencia", "financeiro", f"Nova meta de MRR: R$ {valor:.0f}.", tipo="demanda")
            return self._json({"ok": True, "meta_mrr": valor})

        if rota == "/api/novo-produto":
            nome = (corpo.get("nome") or "").strip()
            tipo = "android" if str(corpo.get("tipo", "web")).startswith("android") else "web"
            if nome:
                from .agentes import slugificar
                slug = slugificar(nome)
                if db.slug_em_uso(slug):
                    slug += "-" + db.agora()[-5:].replace(":", "")
                pid = db.criar_produto({
                    "slug": slug, "nome": nome[:60], "tipo": tipo,
                    "pitch": (corpo.get("pitch") or "Diretriz do dono.")[:300],
                    "valor_estimado": 0, "mrr_estimado": 0, "progresso": 0,
                    "pasta": os.path.join(str(config.PRODUTOS), slug), "status": "ativo",
                })
                db.mensagem("gerencia", "todos",
                            f"Diretriz do dono: iniciar «{nome}» ({tipo}).",
                            tipo="anuncio", produto_id=pid)
                return self._json({"ok": True, "produto_id": pid})
            db.cfg_set("pedido_extra", True)
            db.mensagem("gerencia", "pesquisa",
                        "O dono pediu um novo produto sem nome definido — proponha!", tipo="demanda")
            return self._json({"ok": True, "pedido_extra": True})

        if rota == "/api/tick":
            # força uma rodada imediata em thread separada
            threading.Thread(target=agentes.ciclo_gerente, daemon=True).start()
            for s in db.listar_setores():
                if s["id"] != "gerencia":
                    threading.Thread(target=agentes.ciclo_funcionario,
                                     args=(s["id"],), daemon=True).start()
            return self._json({"ok": True})

        if rota == "/api/ideias":
            titulo = (corpo.get("titulo") or "").strip()
            if not titulo:
                return self._json({"erro": "titulo obrigatório"}, 400)
            tipo = "android" if str(corpo.get("tipo", "web")).startswith("android") else "web"
            iid = db.criar_ideia(titulo[:80], tipo, (corpo.get("pitch") or "")[:400], "dono")
            return self._json({"ok": True, "ideia_id": iid})

        if rota == "/api/ideias/done":
            iid = int(corpo.get("id") or 0)
            db.concluir_ideia(iid)
            return self._json({"ok": True})

        if rota == "/api/ideias/descartar":
            iid = int(corpo.get("id") or 0)
            db.descartar_ideia(iid)
            return self._json({"ok": True})

        if rota == "/api/relatorio":
            # força o envio agora (botão no dashboard)
            from . import relatorio
            r = relatorio.rodar(force=True)
            if not r:
                return self._json({"erro": "não foi possível gerar"}, 500)
            return self._json({"ok": True, "canais": r["canais"]})

        self.send_error(404)


def servir(host: str | None = None, porta: int | None = None) -> None:
    host = host or config.HOST
    porta = porta or config.PORTA
    db.init()
    servidor = ThreadingHTTPServer((host, porta), Handler)
    agentes.log(f"dashboard em http://{host}:{porta}")
    print(f"Dashboard da Empresa IA -> http://{host}:{porta}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    servir()
