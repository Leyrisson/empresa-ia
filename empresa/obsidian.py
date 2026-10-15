"""Ponte com o vault Obsidian do dono (~/Obsidian/EmpresaIA).

Cada produto ganha uma nota-resumo (`projetos/<slug>.md`) e cada dia ganha
um relatório (`relatorios/<AAAA-MM-DD>.md`). Tudo em português, com YAML,
links `[[...]]` e seção Relacionados — seguindo as regras do AGENTS.md.
"""
from __future__ import annotations

import time

from . import config, db


def _pasta() -> str:
    base = config.OBSIDIAN_EMPRESA
    (base / "projetos").mkdir(parents=True, exist_ok=True)
    (base / "relatorios").mkdir(parents=True, exist_ok=True)
    return str(base)


def _indice() -> str:
    pasta = _pasta()
    projetos = (config.OBSIDIAN_EMPRESA / "projetos").glob("*.md")
    relatorios = sorted(
        (config.OBSIDIAN_EMPRESA / "relatorios").glob("*.md"), reverse=True)
    linhas = ["---", "projeto: My AI Office", "tags: [my-ai-office, escrever-codigo]",
              "ultima_atualizacao: " + time.strftime("%Y-%m-%d") + "", "---", "",
              "# My AI Office — relatórios e projetos", "",
              "Escritório ao vivo em `http://127.0.0.1:8770`.", "",
              "## Relatórios", ""]
    linhas += ["- [[EmpresaIA/relatorios/" + r.stem + "|" + r.stem + "]]"
               for r in relatorios]
    linhas += ["", "## Notas de projeto", ""]
    linhas += ["- [[EmpresaIA/projetos/" + p.stem + "|" + p.stem + "]]"
               for p in projetos]
    linhas += ["", "## Atalhos", ""]
    linhas += ["- [[Empresa IA - Fábrica Autônoma de Software]]", ""]
    return "\n".join(linhas)


def escrever_indice() -> str:
    caminho = config.OBSIDIAN_EMPRESA / "_Índice.md"
    caminho.write_text(_indice(), encoding="utf-8")
    return str(caminho)


def _yaml(nome: str, tags: list[str], status: str) -> str:
    return (f"---\nprojeto: {nome}\ntags: [{', '.join(tags)}]\n"
            f"status: {status}\nultima_atualizacao: {time.strftime('%Y-%m-%d')}\n---\n")


def escrever_resumo_produto(p: dict) -> str:
    base = config.OBSIDIAN_EMPRESA / "projetos"
    base.mkdir(parents=True, exist_ok=True)
    slug = p["slug"]
    mrr_linha = f"MRR estimado R$ {p.get('mrr_estimado',0):,.0f}"
    if p.get("mrr_preco") and p.get("mrr_clientes"):
        mrr_linha += f" ({p['mrr_preco']:,.0f}/cliente × {p['mrr_clientes']} clientes)"
    conteudo = (
        _yaml(p["nome"], ["empresa-ia", "produto"], p["estagio"]) +
        f"# {p['nome']} ({p['tipo']})\n\n"
        f"**Pitch:** {p.get('pitch','')}\n\n"
        f"**Estágio:** `{p['estagio']}` · progresso {p.get('progresso',0)}% · "
        f"{mrr_linha}\n\n"
        f"{_bloco_tarefas(p)}\n"
        f"## Atualizado\nAtualização automática em {time.strftime('%Y-%m-%d')} pelo My AI Office.\n\n"
        f"## Relacionados\n"
        f"- [[Empresa IA - Fábrica Autônoma de Software]] — quem criou este produto.\n"
        f"- [[EmpresaIA/_Índice]] — demais relatórios e produtos.\n"
    )
    caminho = base / f"{slug}.md"
    caminho.write_text(conteudo, encoding="utf-8")
    return str(caminho)


def _bloco_tarefas(p: dict) -> str:
    linhas = ["## Tarefas do produto", ""]
    tars = db.tarefas_do_produto(p["id"])[-6:]
    if not tars:
        return ""
    for t in tars:
        st = "✅" if t["status"] == "concluida" else ("❌" if t["status"] == "falhou" else "🔄")
        linhas.append(f"- {st} **{t['titulo']}** ({t['setor']})")
    linhas.append("")
    return "\n".join(linhas)


def escrever_relatorio(data: str, titulo: str, conteudo: str) -> str:
    base = config.OBSIDIAN_EMPRESA / "relatorios"
    base.mkdir(parents=True, exist_ok=True)
    caminho = base / f"{data}.md"
    texto = _yaml("Relatório " + data, ["empresa-ia", "relatorio"], "entregue")
    texto += f"# {titulo}\n\n{conteudo}\n"
    caminho.write_text(texto, encoding="utf-8")
    return str(caminho)