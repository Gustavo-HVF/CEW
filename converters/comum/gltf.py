"""Construtor minimo de glTF 2.0 binario (.glb), deterministico.

Segue a especificacao Khronos glTF 2.0 (https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html):
- GLB: cabecalho 'glTF' versao 2, chunk JSON (preenchido com espacos) e chunk BIN (zeros),
  ambos alinhados a 4 bytes;
- accessors de POSITION levam min/max (obrigatorio pela especificacao);
- bufferViews alinhados a 4 bytes.
O resultado deve passar no glTF Validator oficial (npx gltf-validator), conferido em `cew check`.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Sequence

FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125
UNSIGNED_BYTE = 5121
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
_COMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class ConstrutorGltf:
    def __init__(self, gerador: str = "CEW"):
        self.doc: dict[str, Any] = {"asset": {"version": "2.0", "generator": gerador}, "scene": 0, "scenes": [{"nodes": []}]}
        self.bin = bytearray()

    def _lista(self, nome: str) -> list:
        return self.doc.setdefault(nome, [])

    def _anexar(self, dados: bytes, alvo: int | None = None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        vista: dict[str, Any] = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(dados)}
        if alvo is not None:
            vista["target"] = alvo
        self.bin += dados
        views = self._lista("bufferViews")
        views.append(vista)
        return len(views) - 1

    def accessor_float(self, valores: Sequence[Sequence[float]] | Sequence[float], tipo: str, alvo: int | None = ARRAY_BUFFER, min_max: bool = False) -> int:
        n = _COMP[tipo]
        planos: list[float] = []
        for v in valores:
            if n == 1:
                planos.append(float(v))  # type: ignore[arg-type]
            else:
                if len(v) != n:  # type: ignore[arg-type]
                    raise ValueError(f"esperado {tipo}")
                planos.extend(float(x) for x in v)  # type: ignore[union-attr]
        dados = struct.pack(f"<{len(planos)}f", *planos)
        # reler como float32 para min/max baterem bit a bit com o buffer
        planos32 = list(struct.unpack(f"<{len(planos)}f", dados))
        acc: dict[str, Any] = {"bufferView": self._anexar(dados, alvo), "componentType": FLOAT, "count": len(planos) // n, "type": tipo}
        if min_max and planos32:
            acc["min"] = [min(planos32[i::n]) for i in range(n)]
            acc["max"] = [max(planos32[i::n]) for i in range(n)]
        accs = self._lista("accessors")
        accs.append(acc)
        return len(accs) - 1

    def accessor_indices(self, indices: Sequence[int]) -> int:
        maior = max(indices) if indices else 0
        if maior < 65536:
            dados, comp = struct.pack(f"<{len(indices)}H", *indices), UNSIGNED_SHORT
        else:
            dados, comp = struct.pack(f"<{len(indices)}I", *indices), UNSIGNED_INT
        acc = {"bufferView": self._anexar(dados, ELEMENT_ARRAY_BUFFER), "componentType": comp, "count": len(indices), "type": "SCALAR"}
        accs = self._lista("accessors")
        accs.append(acc)
        return len(accs) - 1

    def imagem_png(self, png: bytes, nome: str | None = None) -> int:
        img: dict[str, Any] = {"bufferView": self._anexar(png), "mimeType": "image/png"}
        if nome:
            img["name"] = nome
        imgs = self._lista("images")
        imgs.append(img)
        samplers = self._lista("samplers")
        if not samplers:
            samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
        texs = self._lista("textures")
        texs.append({"sampler": 0, "source": len(imgs) - 1})
        return len(texs) - 1

    def material(self, nome: str, cor_base: Sequence[float] = (1, 1, 1, 1), textura: int | None = None, metalico: float = 0.0, rugosidade: float = 1.0, extras: dict | None = None) -> int:
        pbr: dict[str, Any] = {"baseColorFactor": [float(c) for c in cor_base], "metallicFactor": metalico, "roughnessFactor": rugosidade}
        if textura is not None:
            pbr["baseColorTexture"] = {"index": textura}
        m: dict[str, Any] = {"name": nome, "pbrMetallicRoughness": pbr}
        if extras:
            m["extras"] = extras
        mats = self._lista("materials")
        mats.append(m)
        return len(mats) - 1

    def malha(self, nome: str, atributos: dict[str, int], indices: int | None, material: int | None = None, alvos_morph: list[dict[str, int]] | None = None, nomes_morph: list[str] | None = None) -> int:
        prim: dict[str, Any] = {"attributes": atributos, "mode": 4}
        if indices is not None:
            prim["indices"] = indices
        if material is not None:
            prim["material"] = material
        m: dict[str, Any] = {"name": nome, "primitives": [prim]}
        if alvos_morph:
            prim["targets"] = alvos_morph
            m["weights"] = [0.0] * len(alvos_morph)
            if nomes_morph:
                m["extras"] = {"targetNames": nomes_morph}
        malhas = self._lista("meshes")
        malhas.append(m)
        return len(malhas) - 1

    def no(self, nome: str, malha: int | None = None, na_cena: bool = True, extras: dict | None = None) -> int:
        n: dict[str, Any] = {"name": nome}
        if malha is not None:
            n["mesh"] = malha
        if extras:
            n["extras"] = extras
        nos = self._lista("nodes")
        nos.append(n)
        idx = len(nos) - 1
        if na_cena:
            self.doc["scenes"][0]["nodes"].append(idx)
        return idx

    def animacao_pesos(self, nome: str, no: int, tempos: Sequence[float], pesos_por_quadro: Sequence[Sequence[float]], interpolacao: str = "LINEAR", extras: dict | None = None) -> int:
        entrada = self.accessor_float(list(tempos), "SCALAR", alvo=None, min_max=True)
        planos = [w for quadro in pesos_por_quadro for w in quadro]
        saida = self.accessor_float(planos, "SCALAR", alvo=None)
        anim: dict[str, Any] = {
            "name": nome,
            "samplers": [{"input": entrada, "output": saida, "interpolation": interpolacao}],
            "channels": [{"sampler": 0, "target": {"node": no, "path": "weights"}}],
        }
        if extras:
            anim["extras"] = extras
        anims = self._lista("animations")
        anims.append(anim)
        return len(anims) - 1

    def glb(self) -> bytes:
        doc = dict(self.doc)
        while len(self.bin) % 4:
            self.bin.append(0)
        if self.bin:
            doc["buffers"] = [{"byteLength": len(self.bin)}]
        js = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        js += b" " * ((4 - len(js) % 4) % 4)
        partes = struct.pack("<I4s", len(js), b"JSON") + js
        if self.bin:
            partes += struct.pack("<I4s", len(self.bin), b"BIN\x00") + bytes(self.bin)
        return struct.pack("<4sII", b"glTF", 2, 12 + len(partes)) + partes


def ler_glb(dados: bytes) -> tuple[dict, bytes]:
    """Le um GLB (para verificacao): devolve (json, bin)."""
    if len(dados) < 20 or dados[:4] != b"glTF":
        raise ValueError("nao e GLB")
    versao, total = struct.unpack_from("<II", dados, 4)
    if versao != 2 or total > len(dados):
        raise ValueError("GLB invalido")
    tam_js, tipo = struct.unpack_from("<I4s", dados, 12)
    if tipo != b"JSON":
        raise ValueError("primeiro chunk GLB nao e JSON")
    doc = json.loads(dados[20 : 20 + tam_js].decode("utf-8"))
    pos = 20 + tam_js
    binario = b""
    if pos + 8 <= total:
        tam_bin, tipo = struct.unpack_from("<I4s", dados, pos)
        if tipo == b"BIN\x00":
            binario = dados[pos + 8 : pos + 8 + tam_bin]
    return doc, binario
