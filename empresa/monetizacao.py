"""Modelo determinístico de MRR: preço × nº de clientes plausível.

A fábrica não deixa mais o LLM 1.5B "chutar" o MRR (saía coisa de
R$ 15.000.000/mês). O setor financeiro só propõe duas coisas verificáveis:

    preco_mensal        quanto CADA cliente paga por mês (em R$)
    clientes_estimados  quantos clientes pagantes, de forma conservadora

e o MRR estimado é SEMPRE calculado aqui: `preco × clientes`, preso a faixas
plausíveis para um dev solo em pré-lançamento. Assim os relatórios, o dashboard
e o Obsidian param de exibir fantasia.

Tudo sobrescrevível por variável de ambiente EMPRESA_MRR_*.
"""
from __future__ import annotations

import os
import re

PRECO_MIN = float(os.environ.get("EMPRESA_MRR_PRECO_MIN", "5"))
PRECO_MAX = float(os.environ.get("EMPRESA_MRR_PRECO_MAX", "2000"))
CLIENTES_MAX = float(os.environ.get("EMPRESA_MRR_CLIENTES_MAX", "1000"))
# Teto duro do MRR "estimado": nenhum produto em pré-venda passa disso.
TETO = float(os.environ.get("EMPRESA_MRR_TETO", "50000"))

# Preço mensal de partida por tipo, usado quando o financeiro não traz número.
PRECO_PADRAO = {"web": 99.0, "android": 19.9, "ios": 19.9}


def preco_padrao(tipo: str | None) -> float:
    return PRECO_PADRAO.get((tipo or "web").strip().lower(), 49.0)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _para_float(valor) -> float | None:
    """Converte 'R$ 99,90' / '1.500,00' / 99.9 / '120' em float."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d.,]", "", str(valor)).strip().strip(".,")
    if not s:
        return None
    if "," in s and "." in s:          # 1.500,00 -> 1500.00
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                     # 99,90 -> 99.90
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def modelo(preco, clientes, tipo: str | None = "web") -> dict:
    """MRR = preço mensal × nº de clientes plausível, com tetos realistas.

    Sempre devolve as três parcelas, para os relatórios mostrarem a conta.
    """
    preco = _para_float(preco)
    if preco is None or preco <= 0:
        preco = preco_padrao(tipo)
    preco = round(_clamp(preco, PRECO_MIN, PRECO_MAX), 2)

    clientes = _para_float(clientes)
    if clientes is None or clientes < 0:
        clientes = 0.0
    clientes = int(_clamp(clientes, 0, CLIENTES_MAX))

    mrr = round(preco * clientes, 2)
    if mrr > TETO:
        mrr = TETO
    return {"preco_mensal": preco, "clientes_estimados": clientes, "mrr_estimado": mrr}


def extrair(texto: str | None, tipo: str | None = "web") -> dict:
    """Lê preço e nº de clientes do relatório do financeiro e calcula o MRR.

    Um `mrr_estimado` devolvido pelo LLM é IGNORADO de propósito: o valor é
    recalculado aqui. Faltando número, caem os defaults conservadores.
    """
    texto = texto or ""
    return modelo(
        _buscar(texto, "preco_mensal") or _buscar(texto, "preco"),
        _buscar(texto, "clientes_estimados") or _buscar(texto, "clientes"),
        tipo,
    )


def _buscar(texto: str, chave: str):
    m = re.search(
        r'"?\b' + chave + r'\b"?\s*[:=]\s*"?R?\$?\s*([0-9]+(?:[.,][0-9]+)*)',
        texto, re.IGNORECASE,
    )
    return m.group(1) if m else None


def normalizar(mrr_atual, tipo: str | None = "web") -> dict:
    """Recalcula um MRR já gravado (antigo, inflado) no modelo novo.

    Mantém a ordem de grandeza via nº de clientes, mas preso aos tetos — o que
    estava em milhões cai para o máximo plausível.
    """
    mrr = _para_float(mrr_atual) or 0.0
    preco = preco_padrao(tipo)
    return modelo(preco, round(mrr / preco) if preco else 0, tipo)
