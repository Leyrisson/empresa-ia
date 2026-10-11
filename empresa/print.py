"""Gera uma foto (PNG) do escritorio com Pillow, sem navegador.

Usado pelo Telegram (/print e correlatos) e pelo dashboard. Nao precisa de
chromium nem de tela: desenha salas, mobilia, agentes e status numa imagem.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from . import db


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/liberation/LiberationSans-Regular.ttf", tamanho)
    except (OSError, IOError):  # pragma: no cover
        return ImageFont.load_default()


_MARGEM_X = 58
_MARGEM_Y = 58


def _mundo_para_tela(office: list[dict], largura: int, altura: int):
    """Projeta as coordenadas plano (x horizontal, z vertical) na imagem."""
    xs = [o["x"] for o in office]
    zs = [o["z"] for o in office] + [-7.1, 6.9]
    xmin, xmax = min(xs), max(xs)
    zmin, zmax = min(zs), max(zs)
    disp_x = largura - 2 * _MARGEM_X
    disp_y = altura - _MARGEM_Y - 30
    sx = disp_x / max(xmax - xmin, 1e-6)
    sy = disp_y / max(zmax - zmin, 1e-6)
    escala = min(sx, sy)

    def proj(x: float, z: float):
        px = _MARGEM_X + (x - xmin) * escala
        py = _MARGEM_Y + (zmax - z) * escala
        return px, py

    return proj, escala


def _cor(c: str | None, padrao: str = "#4d5bf9") -> str:
    c = c or padrao
    return c if c.startswith("#") else "#" + c


def _suavizar(cor: str) -> str:
    cor = _cor(cor)
    try:
        r, g, b = int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)
        return "#%02x%02x%02x" % (min(r + 26, 255), min(g + 26, 255), min(b + 38, 255))
    except (IndexError, ValueError):
        return "#4a5266"


def _cor_status(status: str) -> str:
    return {
        "cumprindo": "#7ee787", "reuniao": "#e3b341", "viajando": "#79c0ff",
        "apurado": "#ffa657", "ocioso": "#2a2e3a",
    }.get(status, "#2a2e3a")


def escritorio_png() -> bytes:
    """Desenha o estado atual do escritorio e devolve os bytes da imagem PNG."""
    est = db.snapshot()
    office = est.get("office") or []
    largura, altura = 980, 620
    img = Image.new("RGB", (largura, altura), "#13161f")
    d = ImageDraw.Draw(img)
    proj, escala = _mundo_para_tela(office, largura, altura)
    s_px = escala * 0.9   # mesa
    c_px = escala * 0.62

    def rect_centro(x, z, lx, lz, cor, borda=None):
        cx, cy = proj(x, z)
        return d.rounded_rectangle(
            (cx - lx / 2, cy - lz / 2, cx + lx / 2, cy + lz / 2),
            radius=8, fill=cor, outline=borda, width=2,
        )

    # cabecalho
    d.rectangle((0, 0, largura, _MARGEM_Y), fill="#10131b")
    d.text((18, 16), "Escritório Empresa IA — " + db.agora()[:16], fill="#cdd3e0",
           font=_fonte(20))

    # salas: chao + rotulo
    for o in [x for x in office if x["tipo"] == "sala"]:
        cx, cy = proj(o["x"], o["z"])
        lx = max((o.get("lx") or 0) * escala, 40)
        lz = max((o.get("lz") or 0) * escala, 52)
        rect_centro(o["x"], o["z"], lx, lz, _suavizar(o["cor"]))
        d.text((cx, cy + 3), (o["nome"] or "").title(), fill="#e8ecf5", font=_fonte(15),
               anchor="mm")

    # mobilia
    for o in office:
        if o["tipo"] == "mesa":
            rect_centro(o["x"], o["z"], s_px, c_px, _cor(o["cor"]), borda="#ffffff")
        elif o["tipo"] == "cadeira":
            cx, cy = proj(o["x"], o["z"])
            d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=_cor(o["cor"], "#9aa0b4"))
        elif o["tipo"] == "arquivo":
            cx, cy = proj(o["x"], o["z"])
            d.rounded_rectangle((cx - 6, cy - 12, cx + 6, cy + 12), radius=3,
                                fill=_cor(o["cor"], "#8a5a2b"), outline="#e8b765")

    # agentes posicionados na cadeira do seu setor
    setores = {s.get("id"): s for s in (est.get("setores") or [])}
    for o in office:
        if o["tipo"] != "cadeira" or not o.get("setor"):
            continue
        sid = o["setor"]
        s = setores.get(sid) or {}
        cx, cy = proj(o["x"], o["z"])
        cor = _cor(s.get("cor"), "#8f9bb3")
        d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=cor)
        d.ellipse((cx - 19, cy - 19, cx + 19, cy + 19), outline="#2a2e3a", width=4)
        d.text((cx, cy - 1), (s.get("nome") or sid)[0].upper(), fill="#0f1220",
               font=_fonte(15), anchor="mm")

    # sala de reuniao em andamento
    reuniao = next((r for r in (est.get("reunioes") or []) if r.get("status") == "ocorrendo"), None)
    if reuniao:
        mesa = next((o for o in office if o["tipo"] == "mesa" and "Reunião" in (o["nome"] or "")), None)
        if mesa:
            cx, cy = proj(mesa["x"], mesa["z"])
            rotulo = "REUNIÃO: " + (reuniao.get("titulo") or "Alinhamento")[:44]
            d.rounded_rectangle((cx - 130, cy + 16, cx + 130, cy + 40), radius=10,
                                fill="#2b2f3d", outline="#c8a94b")
            d.text((cx, cy + 28), rotulo, fill="#ffe08a", font=_fonte(13), anchor="mm")

    # rodape com numeros vivos
    rods = (f"Setores {len(est.get('setores') or [])} · "
            f"Produtos {len(est.get('produtos') or [])} · "
            f"Reunião {(reuniao and 'em andamento') or 'nenhuma'}")
    d.text((largura / 2, altura - 14), rods, fill="#8f97a8", font=_fonte(14), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def rel_user(r) -> str:
    return "em andamento" if r else "nenhuma"