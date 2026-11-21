"""Troca de eixos e unidades para glTF 2.0 (Y para cima, mao direita, metros).

glTF 2.0: "+Y is up, +Z is forward (front of the asset faces +Z), units are meters".
Quake/Source/Blender usam Z para cima (mao direita); a conversao Z-up -> Y-up mantem a mao
direita com (x, y, z) -> (x, z, -y), sem inverter a ordem dos vertices das faces.
Converter de mao esquerda para mao direita espelha um eixo e EXIGE inverter a ordem das faces.
"""

from __future__ import annotations

from typing import Iterable, Literal

Sistema = Literal["y_up_rh", "z_up_rh", "y_up_lh", "z_up_lh"]

# Polegadas (unidades de mapa do Quake/Source sao ~1 polegada).
METROS_POR_POLEGADA = 0.0254


def converter_ponto(p: tuple[float, float, float], origem: Sistema, escala: float = 1.0) -> tuple[float, float, float]:
    x, y, z = p
    if origem == "y_up_rh":
        r = (x, y, z)
    elif origem == "z_up_rh":
        r = (x, z, -y)
    elif origem == "y_up_lh":
        r = (x, y, -z)
    elif origem == "z_up_lh":
        r = (x, z, y)
    else:  # pragma: no cover
        raise ValueError(origem)
    return (r[0] * escala, r[1] * escala, r[2] * escala)


def inverte_faces(origem: Sistema) -> bool:
    """True quando a conversao espelha a geometria (troca de mao) e a ordem das faces deve virar."""
    return origem.endswith("_lh")


def ordenar_triangulo(t: tuple[int, int, int], inverter: bool) -> tuple[int, int, int]:
    return (t[0], t[2], t[1]) if inverter else t


def limites(pontos: Iterable[tuple[float, float, float]]) -> tuple[list[float], list[float]]:
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    vazio = True
    for p in pontos:
        vazio = False
        for i in range(3):
            mn[i] = min(mn[i], p[i])
            mx[i] = max(mx[i], p[i])
    if vazio:
        return [0.0] * 3, [0.0] * 3
    return mn, mx
