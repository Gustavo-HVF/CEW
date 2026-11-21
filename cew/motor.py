"""Etapa 6: perfil do projeto -> nota de 0 a 10 por motor, com motivos (item 10).

O perfil sai do inventario/manifesto (2D/3D, peso e quantidade de assets) e do que a pessoa
informar (fisica, interface, multijogador, dispositivos, experiencia da equipe). A escolha final e
sempre da pessoa e fica registrada em recomendacao_motor.json.
"""

from __future__ import annotations

from collections import Counter

from . import GERADO_POR, SCHEMA_VERSION
from .logs import agora_iso
from .projeto import Projeto
from .registro import registro_do_projeto

MOTORES = {
    "phaser": {"nome": "Phaser (JS/TS)", "base": {"2d": 9.0, "3d": 1.0, "misto": 4.0}, "linguagens": {"javascript", "typescript", "phaser"}, "modelo": True},
    "pixijs": {"nome": "PixiJS (JS/TS)", "base": {"2d": 8.0, "3d": 0.5, "misto": 3.0}, "linguagens": {"javascript", "typescript", "pixijs"}, "modelo": True},
    "threejs": {"nome": "Three.js (TS, ou React Three Fiber)", "base": {"2d": 4.0, "3d": 9.0, "misto": 7.5}, "linguagens": {"javascript", "typescript", "threejs", "react"}, "modelo": True},
    "babylonjs": {"nome": "Babylon.js (JS/TS)", "base": {"2d": 3.5, "3d": 8.5, "misto": 7.5}, "linguagens": {"javascript", "typescript", "babylonjs"}, "modelo": True},
    "playcanvas": {"nome": "PlayCanvas (JS + editor na nuvem)", "base": {"2d": 4.0, "3d": 8.0, "misto": 6.5}, "linguagens": {"javascript", "playcanvas"}, "modelo": False},
    "godot": {"nome": "Godot (GDScript/C#, exportacao HTML5)", "base": {"2d": 7.5, "3d": 7.0, "misto": 7.0}, "linguagens": {"gdscript", "godot", "csharp"}, "modelo": False},
    "unity_webgl": {"nome": "Unity WebGL (C#)", "base": {"2d": 6.0, "3d": 7.0, "misto": 6.5}, "linguagens": {"csharp", "unity"}, "modelo": False},
    "construct3": {"nome": "Construct 3 (sem codigo)", "base": {"2d": 6.0, "3d": 1.0, "misto": 2.0}, "linguagens": {"construct"}, "modelo": False},
    "gdevelop": {"nome": "GDevelop (sem codigo)", "base": {"2d": 6.0, "3d": 2.0, "misto": 2.5}, "linguagens": {"gdevelop"}, "modelo": False},
}


def perfil_automatico(projeto: Projeto, preferencias: dict | None = None) -> dict:
    reg = registro_do_projeto(projeto.pasta)
    inv = projeto.ler("inventario")
    tipos = Counter((reg.get(i["formato"]["id"]) or {}).get("tipo") for i in inv["itens"])
    manifesto = projeto.ler("manifesto") if projeto.existe("manifesto") else {"assets": []}
    t_assets = Counter(a["tipo"] for a in manifesto["assets"])
    n3d = tipos.get("modelo", 0) + tipos.get("mapa", 0) + t_assets.get("modelo", 0) + t_assets.get("mapa", 0)
    n2d = tipos.get("textura", 0) + tipos.get("imagem", 0)
    if n3d == 0:
        dim = "2d"
    elif n3d * 10 < n2d:
        dim = "misto"
    else:
        dim = "3d"
    peso = sum(a["tamanho_bytes"] for a in manifesto["assets"]) / 1024**2
    evid = [f"{n3d} arquivos 3D (modelo/mapa) e {n2d} imagens no inventario", f"{len(manifesto['assets'])} assets convertidos ({peso:.1f} MB)"]
    perfil = {"dimensao": dim, "fisica": "simples" if dim != "2d" else "nenhuma", "peso_assets_mb": round(peso, 3), "quantidade_assets": len(manifesto["assets"]),
              "interface": "simples", "multijogador": False, "dispositivos": ["desktop", "celular"], "experiencia_equipe": [], "sem_codigo": False, "evidencia": evid}
    for k, v in (preferencias or {}).items():
        if k in perfil and v is not None:
            perfil[k] = v
    return perfil


def pontuar(perfil: dict) -> list[dict]:
    saida = []
    exp = {e.lower() for e in perfil.get("experiencia_equipe", [])}
    for mid, m in MOTORES.items():
        nota = m["base"][perfil["dimensao"]]
        motivos = [f"base {nota:g} para projeto {perfil['dimensao'].upper()}"]
        alertas = []
        fis = perfil["fisica"]
        if fis == "complexa":
            delta = {"babylonjs": 1.0, "godot": 0.8, "unity_webgl": 0.8, "playcanvas": 0.5, "threejs": -1.0, "pixijs": -2.0, "phaser": -0.5}.get(mid, -1.0)
            nota += delta
            motivos.append(f"fisica complexa: {delta:+g} (" + ("motor de fisica integrado" if delta > 0 else "precisa de biblioteca externa") + ")")
        elif fis == "simples" and mid == "pixijs":
            nota -= 0.5
            motivos.append("fisica simples: -0.5 (PixiJS so renderiza)")
        if "vr" in perfil["dispositivos"]:
            delta = {"babylonjs": 1.0, "threejs": 0.5, "playcanvas": 0.5}.get(mid, -3.0)
            nota += delta
            motivos.append(f"VR/WebXR: {delta:+g}")
        if "celular" in perfil["dispositivos"]:
            if mid == "unity_webgl":
                nota -= 1.5
                alertas.append("builds WebGL do Unity sao pesados no celular")
            if mid == "godot":
                nota -= 0.5
                alertas.append("exportacao HTML5 do Godot: conferir tamanho e threads/SharedArrayBuffer no host")
        if perfil["peso_assets_mb"] > 200:
            alertas.append(f"{perfil['peso_assets_mb']:.0f} MB de assets: use KTX2/meshopt e carregamento sob demanda")
        if perfil["interface"] == "rica":
            delta = {"pixijs": 0.5, "phaser": 0.3, "godot": 0.3}.get(mid, 0.0)
            if delta:
                nota += delta
                motivos.append(f"interface rica: {delta:+g}")
        if perfil["multijogador"]:
            if mid in ("construct3", "gdevelop"):
                nota -= 0.5
                motivos.append("multijogador: -0.5 (menos controle de rede)")
            alertas.append("multijogador exige servidor proprio (WebSocket/WebRTC)")
        if perfil.get("sem_codigo"):
            delta = 2.0 if mid in ("construct3", "gdevelop") else -1.0
            nota += delta
            motivos.append(f"equipe sem codigo: {delta:+g}")
        if exp & m["linguagens"]:
            nota += 1.0
            motivos.append("experiencia da equipe: +1")
        if mid == "godot" and "csharp" in exp:
            alertas.append("C# na exportacao web do Godot: verificar o suporte da versao usada")
        if mid == "playcanvas":
            alertas.append("editor na nuvem: os assets sobem para o servico do PlayCanvas")
        if not m["modelo"]:
            alertas.append("o CEW nao gera o projeto deste motor automaticamente; skills/05 traz o mapa de carregamento")
        saida.append({"id": mid, "nome": m["nome"], "nota": round(max(0.0, min(10.0, nota)), 1), "motivos": motivos, "alertas": alertas, "modelo_gerado_pelo_cew": m["modelo"]})
    saida.sort(key=lambda x: (-x["nota"], x["id"]))
    return saida


def recomendar(projeto: Projeto, preferencias: dict | None = None, dry_run: bool = False) -> dict:
    perfil = perfil_automatico(projeto, preferencias)
    motores = pontuar(perfil)
    antigo = projeto.ler("motor") if projeto.existe("motor") else None
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "gerado_em": agora_iso(), "projeto": projeto.nome, "perfil": perfil,
           "motores": motores, "recomendado": motores[0]["id"], "escolha_usuario": (antigo or {}).get("escolha_usuario")}
    if not dry_run:
        projeto.gravar("motor", doc)
    return doc


def escolher(projeto: Projeto, motor: str, motivo: str = "") -> dict:
    if motor not in MOTORES:
        raise ValueError(f"motor desconhecido: {motor} (opcoes: {', '.join(MOTORES)})")
    doc = projeto.ler("motor") if projeto.existe("motor") else recomendar(projeto)
    doc["escolha_usuario"] = {"motor": motor, "escolhido_em": agora_iso(), **({"motivo": motivo} if motivo else {})}
    projeto.gravar("motor", doc)
    projeto.definir_motor(motor)
    return doc
