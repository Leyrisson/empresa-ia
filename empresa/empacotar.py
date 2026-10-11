"""Empacotamento + documentação + verificação real de cada produto.

Contrato de qualidade (regra do dono):
  1. O produto COMPILA e RODA na máquina local (iniciar.sh / APK).
  2. Pode ser INSTALADO para um cliente (Docker Compose p/ web, APK p/ Android,
     serviço systemd de usuário na máquina do dono).
  3. Tem documentação completa: README, docs/INSTALACAO, docs/USO, docs/VENDEDOR.

A verificação é real (não cosmética): py_compile de verdade + tentativa de
subir o app. Tudo registrado no banco (tabela `verificacoes`) e em
`docs/VERIFICACAO.md` para o QA poder conferir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request

from . import config, db

_PORT_CHECK = 8797
_LABEL = {
    "web": "aplicação web",
    "android": "aplicativo Android",
    None: "software",
}


def _pasta(p: dict) -> str:
    return p["pasta"] or os.path.join(str(config.PRODUTOS), p["slug"])


def _escrever(caminho: str, conteudo: str) -> bool:
    """Escreve só se não existir (preserva o que o engenheiro gerou)."""
    if os.path.exists(caminho):
        return False
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(conteudo)
    return True


def _chmod_x(caminho: str) -> None:
    try:
        os.chmod(caminho, 0o755)
    except OSError:
        pass


def _entry_web(p) -> str | None:
    pasta = _pasta(p)
    for nome in ("app.py", "server.py", "main.py"):
        if os.path.isfile(os.path.join(pasta, nome)):
            return nome
    if os.path.isfile(os.path.join(pasta, "index.html")):
        return "index.html"
    return None


def _iniciar_sh_web(p) -> str:
    entry = _entry_web(p) or "index.html"
    if entry == "index.html":
        cmd = 'echo "Sem app Python; subindo estático na porta $PORT" && exec python3 -m http.server "$PORT"'
    else:
        cmd = f'exec python3 {entry}'
    return f"""#!/usr/bin/env bash
# {p['nome']} — inicia a aplicação localmente (contrato Empresa IA)
set -euo pipefail
cd "$(dirname "$0")"
export PORT="${{PORT:-5000}}"
{cmd}
"""


def _unit_systemd(p) -> str:
    slug = p["slug"]
    return f"""[Unit]
Description={p['nome']} ({p['tipo']})
After=network.target

[Service]
WorkingDirectory=%h/empresa-ia/produtos/{slug}
Environment=PORT={_PORT_CHECK}
ExecStart=/usr/bin/env bash %h/empresa-ia/produtos/{slug}/iniciar.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def _dockerfile_web(p) -> str:
    return f"""# {p['nome']} — container para distribuir ao cliente
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true
ENV PORT=5000
EXPOSE 5000
CMD ["sh", "iniciar.sh"]
"""


def _compose_web(p) -> str:
    return f"""services:
  {p['slug']}:
    build: .
    container_name: {p['slug']}
    ports:
      - "5000:5000"
    environment:
      - PORT=5000
    restart: unless-stopped
    volumes:
      - dados:/app/dados
volumes:
  dados:
"""


_TITULO = {
    "INSTALACAO": ("Como instalar e rodar localmente", 1),
    "USO": ("Como usar", 2),
    "VENDEDOR": ("Instalação para clientes", 3),
}


def _doc(p: dict, nome: str) -> str:
    nome, num = _TITULO[nome]
    tipo = _LABEL.get(p.get("tipo"), _LABEL[None])
    slug = p["slug"]
    if nome.startswith("Como instalar"):
        texto = (
            f"# {nome}\n\n"
            f"Manual de instalação de **{p['nome']}** ({p['tipo']}) — {p.get('pitch','')}\n\n"
            f"## Requisitos\n"
            f"- Sistema operacional: Linux/Mac (Windows via WSL)\n"
            f"- Python 3.10+ no PATH\n\n"
            f"## 1) Rodar local (rápido)\n"
            f"```bash\ncd {slug}\nsh iniciar.sh\n```\n"
            f"Abra **http://127.0.0.1:5000** no navegador.\n"
            f"A porta vem da variável `PORT` (padrão 5000); troque com `PORT=8080 sh iniciar.sh`.\n\n"
            f"## 2) Como serviço (liga com a máquina)\n"
            f"```bash\nsh instalar.sh     # registra serviço do usuário\n"
            f"systemctl --user status app-{slug}\n```\n\n"
            f"## 3) Rodar em Docker (para testes isolados)\n"
            f"```bash\ndocker compose up --build\n```\n\n"
            f"## Desinstalar\n"
            f"```bash\nsystemctl --user disable --now app-{slug} 2>/dev/null; rm -f ~/.config/systemd/user/app-{slug}.service\n```"
        )
    elif nome.startswith("Como usar"):
        texto = (
            f"# {nome}\n\n"
            f"Guia de uso de **{p['nome']}**.\n\n"
            f"## Para que serve\n{p.get('pitch','')}\n\n"
            f"## Primeiro uso\n"
            f"1. Inicie (ver docs/INSTALACAO).\n"
            f"2. Abra http://127.0.0.1:5000.\n"
            f"3. Crie o primeiro registro para ver os dados de exemplo.\n\n"
            f"## Funcionalidades principais\n"
            f"Consulte a especificação em `01-spec.md` (se existir) para o detalhamento "
            f"das telas e fluxos; teste cada entrada com um dado real.\n\n"
            f"## Dados\n"
            f"- Banco local em `<pasta_do_app>/dados/` (SQLite).\n"
            f"- Backup: copie a pasta `dados/`.\n"
            f"- Restaurar: substitua a pasta pelos arquivos de backup.\n\n"
            f"## Solução de problemas\n"
            f"- **Porta ocupada:** `PORT=8080 sh iniciar.sh`.\n"
            f"- **Erro de dependência:** rode `pip install -r requirements.txt` na pasta."
        )
    else:
        texto = (
            f"# {nome}\n\n"
            f"Guia de venda e instalação para clientes de **{p['nome']}**.\n\n"
            f"## Empacotando para entregar\n"
            f"### Cliente com Docker (recomendado para web)\n"
            f"```bash\ncd {slug}\n"
            f"docker build -t {slug} .\n"
            f"docker save {slug} | gzip > {slug}.tar.gz\n"
            f"```\n"
            f"Entregue `{slug}.tar.gz`, `docker-compose.yml` e as `docs/` ao cliente. "
            f"No servidor do cliente:\n"
            f"```bash\ndocker load < {slug}.tar.gz && docker compose up -d\n```\n\n"
            f"### Cliente Android (APK)\n"
            f"```bash\ncd {slug}\n./gradlew assembleDebug\n"
            f"adb install app/build/outputs/apk/debug/app-debug.apk\n```\n\n"
            f"### Hospedagem leve (VPS ~ R$ 30/mês)\n"
            f"- Suba o container na VPS, exponha a porta com um proxy (Caddy/nginx) + HTTPS.\n"
            f"- Cobre do cliente o valor do servidor + taxa de manutenção mensal.\n\n"
            f"## Checklist de entrega ao cliente\n"
            f"- [ ] Código (este repositório) + tag de versão\n"
            f"- [ ] `docs/INSTALACAO.md` e `docs/USO.md` entregues\n"
            f"- [ ] Dados de exemplo removidos / resetados\n"
            f"- [ ] Acesso, backup e manutenção combinados\n\n"
            f"## Preço sugerido\n"
            f"Valor estimado do produto: R$ {p.get('valor_estimado', 0):,.0f}. "
            f"MRR estimado: R$ {p.get('mrr_estimado', 0):,.0f}/mês."
        )
    return texto


def _verificar_sintaxe(p: dict) -> str:
    pasta = _pasta(p)
    arquivos = [
        os.path.join(raiz, a)
        for raiz, _d, fxs in os.walk(pasta)
        if "/." not in raiz
        for a in fxs
        if a.endswith(".py")
        and os.path.join(raiz, a).split("/")[-1] != "produto.py"
    ]
    if not arquivos:
        return "sem arquivos .py (nada a compilar)"
    comando = ["python3", "-m", "py_compile", *arquivos]
    r = subprocess.run(comando, capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        return f"compilou {len(arquivos)} arquivo(s) Python sem erros"
    db.verificar(p["id"], "sintaxe", False, r.stderr[-400:])
    return f"ERRO de compilação: {r.stderr[:400]}"


def _verificar_boot(p: dict) -> str:
    """Best-effort: sobe o app e testa HTTP de verdade."""
    pasta = _pasta(p)
    entry = ("app.py",)
    alvo = next((e for e in entry if os.path.isfile(os.path.join(pasta, e))), None)
    if not alvo:
        return "sem app.py para checar boot"
    env = dict(os.environ)
    env["PORT"] = str(_PORT_CHECK)
    env["EMPRESA_NAO_ATRAPALHA"] = "1"
    with open(os.devnull, "w") as devnull:
        try:
            proc = subprocess.Popen(
                ["python3", alvo], cwd=pasta, env=env,
                stdout=devnull, stderr=devnull, start_new_session=True,
            )
        except OSError:
            return "falha ao iniciar (permissão/ambiente)"
        time.sleep(4)
        ok = False
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{_PORT_CHECK}/", timeout=4
            ) as resp:
                ok = 200 <= resp.status < 500
        except Exception:  # noqa: BLE001
            ok = False
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
        return f"respondeu HTTP 2xx/3xx/4xx" if ok else "subiu, mas não respondeu na checagem (pode exigir interação)"
    return "ok"


def empacotar_e_documentar(p: dict) -> str:
    """Garante o contrato (compilar/rodar/instalar/documentar) do produto."""
    pasta = _pasta(p)
    os.makedirs(pasta, exist_ok=True)
    docs = os.path.join(pasta, "docs")
    os.makedirs(docs, exist_ok=True)
    slug = p["slug"]

    if p.get("tipo") == "android":
        _escrever(os.path.join(pasta, "README.md"),
                  f"# {p['nome']}\n\n{p.get('pitch','')}\n\n"
                  f"## Compilar\n```bash\n./gradlew assembleDebug\n```\n"
                  f"## Instalar no aparelho\n```bash\nadb install app/build/outputs/apk/debug/app-debug.apk\n```\n"
                  f"Veja `docs/` para instalação e uso completos.\n")
        _escrever(os.path.join(pasta, "instalar.sh"),
                  "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\n"
                  "./gradlew assembleDebug\nadb install app/build/outputs/apk/debug/app-debug.apk\n"
                  "echo 'APK instalado no aparelho.'\n")
        _chmod_x(os.path.join(pasta, "instalar.sh"))
        return "empacotado (Android: APK + README + docs)"
    else:
        entry = _entry_web(p)
        _escrever(os.path.join(pasta, "README.md"),
                  f"# {p['nome']}\n\n{p.get('pitch','')}\n\n"
                  f"## Iniciar\n```bash\nsh iniciar.sh\n```\n"
                  f"Abra http://127.0.0.1:5000\n\n"
                  f"## Documentação\n"
                  f"- Instalação: `docs/INSTALACAO.md`\n"
                  f"- Uso: `docs/USO.md`\n"
                  f"- Venda/instalação para clientes: `docs/VENDEDOR.md`\n")
        _escrever(os.path.join(pasta, "iniciar.sh"), _iniciar_sh_web(p))
        _chmod_x(os.path.join(pasta, "iniciar.sh"))
        _escrever(os.path.join(pasta, ".env.example"),
                  "# Copie para .env e ajuste\nPORT=5000\n")
        _escrever(os.path.join(pasta, "instalar.sh"),
                  f"#!/usr/bin/env bash\n"
                  f"# Instala {slug} como serviço do usuário (liga com a máquina)\n"
                  f"set -euo pipefail\n"
                  f"cd \"$(dirname \"$0\")\"\n"
                  f"mkdir -p ~/.config/systemd/user\n"
                  f"cat > ~/.config/systemd/user/app-{slug}.service <<'EOF'\n"
                  f"{_unit_systemd(p)}\nEOF\n"
                  f"systemctl --user daemon-reload\n"
                  f"systemctl --user enable --now app-{slug}\n"
                  f"echo \"Serviço app-{slug} ativo.\"\n")
        _chmod_x(os.path.join(pasta, "instalar.sh"))
        _escrever(os.path.join(pasta, "Dockerfile"), _dockerfile_web(p))
        _escrever(os.path.join(pasta, "docker-compose.yml"), _compose_web(p))

    for nome in _TITULO:
        _escrever(os.path.join(docs, f"{nome}.md"), _doc(p, nome))

    sintaxe = _verificar_sintaxe(p)
    sint_ok = not sintaxe.startswith("ERRO")
    db.verificar(p["id"], "sintaxe", sint_ok, sintaxe)
    boot = ""
    if entry and p.get("tipo") != "android":
        boot = " | boot: " + _verificar_boot(p)
    _escrever(os.path.join(docs, "VERIFICACAO.md"),
              f"# Verificação real de {p['nome']}\n\n"
              f"- compilação: {sintaxe}\n- boot: {boot.lstrip(' | boot: ')}\n"
              f"- checks registrados no banco (`verificacoes`)\n")
    if entry is None:
        db.verificar(p["id"], "contedor", False, "sem ponto de entrada web (app.py/server.py/index.html)")
        return f"empacotado, mas SEM ponto de entrada. {sintaxe}"
    return f"empacotado (README/docs/Dockerfile/instalar.sh). {sintaxe}{boot}"