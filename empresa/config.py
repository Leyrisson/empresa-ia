"""Configuracao da Empresa IA.

Tudo sobrescrevivel por variavel de ambiente com prefixo EMPRESA_.
Ex.: EMPRESA_MODELO_PLANEJADOR=llama3.1:latest
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(os.environ.get("EMPRESA_RAIZ", Path(__file__).resolve().parent.parent))
VAR = RAIZ / "var"
PRODUTOS = RAIZ / "produtos"
TEMPLATES = RAIZ / "templates"
STATIC = RAIZ / "static"
CONHECIMENTO = RAIZ / "conhecimento"

VAR.mkdir(parents=True, exist_ok=True)
PRODUTOS.mkdir(parents=True, exist_ok=True)

BANCO = Path(os.environ.get("EMPRESA_BANCO", VAR / "empresa.db"))
LOG = Path(os.environ.get("EMPRESA_LOG", VAR / "empresa.log"))
PAUSA = VAR / "PAUSA"

# --- LLM ---
# Backend: "ollama" (padrao), "localai" ou "offline" (nao chama nada; so simula)
BACKEND = os.environ.get("EMPRESA_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("EMPRESA_OLLAMA_URL", "http://127.0.0.1:11434")
LOCALAI_URL = os.environ.get("EMPRESA_LOCALAI_URL", "http://127.0.0.1:8090")
# Modelos pequenos rodam em ~6 tok/s (cabe na GPU; não atrapalha).
# Modelos 7B aqui rodam 95% na CPU a ~1,5 tok/s — evite como padrão.
MODELO_PLANEJADOR = os.environ.get("EMPRESA_MODELO_PLANEJADOR", "qwen2.5:1.5b")
MODELO_CODIGO = os.environ.get("EMPRESA_MODELO_CODIGO", "qwen2.5-coder:1.5b")
TIMEOUT_LLM = int(os.environ.get("EMPRESA_TIMEOUT_LLM", "240"))

# --- opencode (braco que escreve codigo de verdade) ---
# "opencode" constroi os apps de verdade; "llm" so gera os arquivos por texto.
MODO_BUILD = os.environ.get("EMPRESA_MODO_BUILD", "opencode")
TIMEOUT_BUILD = int(os.environ.get("EMPRESA_TIMEOUT_BUILD", "1800"))
MAX_BUILDS_DIA = int(os.environ.get("EMPRESA_MAX_BUILDS_DIA", "6"))

# --- Ritmo / nao atrapalhar ---
# baixa: 20s entre ciclos | media: 8s | alta: 3s
INTENSIDADE = os.environ.get("EMPRESA_INTENSIDADE", "baixa")
SLEEP = {"baixa": 20.0, "media": 8.0, "alta": 3.0}.get(INTENSIDADE, 20.0)
MAX_PRODUTOS_ATIVOS = int(os.environ.get("EMPRESA_MAX_PRODUTOS_ATIVOS", "3"))
META_MRR = float(os.environ.get("EMPRESA_META_MRR", "10000"))
NICE = int(os.environ.get("EMPRESA_NICE", "15"))

# --- Dashboard ---
PORTA = int(os.environ.get("EMPRESA_PORTA", "8770"))
HOST = os.environ.get("EMPRESA_HOST", "127.0.0.1")

# --- Relatório diário + Obsidian + Telegram ---
# Horario (hora local) em que o relatorio do dia e gerado e enviado ao dono.
HORA_RELATORIO = int(os.environ.get("EMPRESA_HORA_RELATORIO", "18"))
# Pasta Obsidian do escritorio: relatorios + resumo de cada projeto.
OBSIDIAN_EMPRESA = Path(os.environ.get(
    "EMPRESA_OBSIDIAN", Path.home() / "Obsidian" / "EmpresaIA"))
# Onde o relatorio busca as credenciais do Telegram (token + chat id).
TELEGRAM_CREDS = Path(os.environ.get(
    "EMPRESA_TELEGRAM_CREDS",
    Path.home() / ".config" / "omarchy-voice" / "plugins" / "telebot" / "credenciais.env",
))
# Empacotar e documentar todo produto (instalar.sh, Dockerfile, docs/) apos o build.
EMPACOTAR = os.environ.get("EMPRESA_EMPACOTAR", "1") == "1"


def set_config(chave: str, valor: str) -> None:
    os.environ[f"EMPRESA_{chave.upper()}"] = str(valor)
