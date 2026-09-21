"""Definição de incursões: schema, validação e carregamento dos JSON.

Uma incursão tem 3 linhas de 3 salas mais a sala de Objetivo, que é sempre Combate.
O grupo escolhe 1 sala por linha, três vezes, e então enfrenta o Objetivo.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .rules import chave_comparacao, normalizar_pericia

TIPOS_SALA = ("Combate", "Descanso", "Armadilha", "Evento", "Tesouro")
ORGANIZACOES = (
    "Vórtice Oculto",
    "Aliança das Sombras",
    "Guilda dos Mortos",
    "Sentinelas do Alvorecer",
)
DIFICULDADES = ("Fácil", "Média", "Difícil")

# Tipos que resolvem a sala por teste de perícia (margem vs CD).
TIPOS_COM_TESTE = ("Armadilha", "Evento", "Tesouro")

EXPR_DANO = re.compile(r"^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)

_INDICE_TIPOS = {chave_comparacao(t): t for t in TIPOS_SALA}
_INDICE_ORGS = {chave_comparacao(o): o for o in ORGANIZACOES}
_INDICE_DIFS = {chave_comparacao(d): d for d in DIFICULDADES}


class ErroDeValidacao(Exception):
    """Agrupa todos os problemas encontrados, em vez de estourar no primeiro."""

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        super().__init__(f"{len(problemas)} problema(s) encontrado(s)")

    def __str__(self) -> str:
        return "\n".join(f"  - {p}" for p in self.problemas)


@dataclass
class Monstro:
    nome: str
    ca: int
    ataque: int
    dano: str
    hp: int

    def para_dict(self) -> dict[str, Any]:
        return {"nome": self.nome, "ca": self.ca, "ataque": self.ataque, "dano": self.dano, "hp": self.hp}


@dataclass
class Sala:
    id: str
    nome: str
    tipo: str
    descricao: str
    dificuldade: Optional[str] = None
    cd: Optional[int] = None
    alvo_progresso: Optional[int] = None
    pericias: list[str] = field(default_factory=list)
    imagem: Optional[str] = None
    monstro: Optional[Monstro] = None
    recompensa: Optional[str] = None

    @property
    def tem_teste(self) -> bool:
        return self.tipo in TIPOS_COM_TESTE

    @property
    def e_combate(self) -> bool:
        return self.tipo == "Combate"

    def para_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "nome": self.nome,
            "tipo": self.tipo,
            "descricao": self.descricao,
            "dificuldade": self.dificuldade,
            "cd": self.cd,
            "alvo_progresso": self.alvo_progresso,
            "pericias": self.pericias,
            "imagem": self.imagem,
            "recompensa": self.recompensa,
        }
        d["monstro"] = self.monstro.para_dict() if self.monstro else None
        return d


@dataclass
class Incursao:
    id: str
    nome: str
    organizacao: str
    descricao: str
    linhas: list[list[Sala]]
    objetivo: Sala
    imagem_capa: Optional[str] = None
    recompensa_mes: int = 10

    def opcoes(self, linha: int) -> list[Sala]:
        """As 3 salas oferecidas na linha (1, 2 ou 3)."""
        return self.linhas[linha - 1]

    def sala(self, sala_id: str) -> Optional[Sala]:
        for s in [*[x for linha in self.linhas for x in linha], self.objetivo]:
            if s.id == sala_id:
                return s
        return None

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "organizacao": self.organizacao,
            "descricao": self.descricao,
            "imagem_capa": self.imagem_capa,
            "recompensa_mes": self.recompensa_mes,
            "linhas": [[s.para_dict() for s in linha] for linha in self.linhas],
            "objetivo": self.objetivo.para_dict(),
        }


def _inteiro(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def _sala_de_dict(dados: dict[str, Any], onde: str, problemas: list[str]) -> Optional[Sala]:
    sala_id = str(dados.get("id") or "").strip()
    if not sala_id:
        problemas.append(f"{onde}: sala sem 'id'.")
        return None

    onde = f"{onde} (sala {sala_id})"
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        problemas.append(f"{onde}: falta o nome.")

    tipo = _INDICE_TIPOS.get(chave_comparacao(str(dados.get("tipo") or "")))
    if not tipo:
        problemas.append(
            f"{onde}: tipo '{dados.get('tipo')}' inválido. Use um de: {', '.join(TIPOS_SALA)}."
        )
        return None

    descricao = str(dados.get("descricao") or "").strip()
    if not descricao:
        problemas.append(f"{onde}: falta a descrição mostrada aos jogadores.")

    dificuldade = None
    cd = _inteiro(dados.get("cd"))
    alvo = _inteiro(dados.get("alvo_progresso"))
    pericias: list[str] = []

    bruto_dif = str(dados.get("dificuldade") or "").strip()
    if bruto_dif:
        dificuldade = _INDICE_DIFS.get(chave_comparacao(bruto_dif))
        if not dificuldade:
            problemas.append(
                f"{onde}: dificuldade '{bruto_dif}' inválida. Use {', '.join(DIFICULDADES)}."
            )

    for nome_pericia in dados.get("pericias") or []:
        canonico = normalizar_pericia(str(nome_pericia))
        if canonico:
            if canonico not in pericias:
                pericias.append(canonico)
        else:
            problemas.append(f"{onde}: perícia '{nome_pericia}' não existe.")

    if tipo in TIPOS_COM_TESTE:
        if not dificuldade:
            problemas.append(f"{onde}: sala de {tipo} precisa de uma dificuldade.")
        if cd is None:
            problemas.append(f"{onde}: sala de {tipo} precisa de uma CD.")
        if alvo is None or alvo <= 0:
            problemas.append(f"{onde}: sala de {tipo} precisa de um alvo_progresso maior que zero.")
        if not pericias:
            problemas.append(f"{onde}: sala de {tipo} precisa de pelo menos uma perícia.")

    monstro = None
    bruto_monstro = dados.get("monstro")
    if tipo == "Combate":
        if not bruto_monstro:
            problemas.append(f"{onde}: sala de Combate precisa dos dados do monstro.")
        else:
            m_nome = str(bruto_monstro.get("nome") or "").strip()
            m_ca, m_atk, m_hp = (
                _inteiro(bruto_monstro.get("ca")),
                _inteiro(bruto_monstro.get("ataque")),
                _inteiro(bruto_monstro.get("hp")),
            )
            m_dano = str(bruto_monstro.get("dano") or "").strip()
            if not m_nome:
                problemas.append(f"{onde}: o monstro precisa de um nome.")
            for rotulo, valor in (("ca", m_ca), ("ataque", m_atk), ("hp", m_hp)):
                if valor is None:
                    problemas.append(f"{onde}: monstro sem '{rotulo}'.")
            if m_hp is not None and m_hp <= 0:
                problemas.append(f"{onde}: o HP do monstro precisa ser maior que zero.")
            if not EXPR_DANO.match(m_dano):
                problemas.append(
                    f"{onde}: dano '{m_dano}' fora do formato esperado (ex.: 2d6+3)."
                )
            if m_nome and None not in (m_ca, m_atk, m_hp):
                monstro = Monstro(m_nome, m_ca, m_atk, m_dano, m_hp)
    elif bruto_monstro:
        problemas.append(f"{onde}: só salas de Combate têm monstro.")

    return Sala(
        id=sala_id,
        nome=nome,
        tipo=tipo,
        descricao=descricao,
        dificuldade=dificuldade,
        cd=cd,
        alvo_progresso=alvo,
        pericias=pericias,
        imagem=(str(dados.get("imagem")).strip() or None) if dados.get("imagem") else None,
        monstro=monstro,
        recompensa=(str(dados.get("recompensa")).strip() or None) if dados.get("recompensa") else None,
    )


def de_dict(dados: dict[str, Any]) -> Incursao:
    """Valida e converte o dicionário cru numa Incursao. Levanta ErroDeValidacao."""
    problemas: list[str] = []

    incursao_id = str(dados.get("id") or "").strip()
    if not incursao_id:
        problemas.append("A incursão precisa de um 'id'.")
    elif not re.fullmatch(r"[a-z0-9_]+", incursao_id):
        problemas.append(
            f"id '{incursao_id}': use só letras minúsculas, números e '_' (vira nome de arquivo)."
        )

    nome = str(dados.get("nome") or "").strip()
    if not nome:
        problemas.append("A incursão precisa de um nome.")

    organizacao = _INDICE_ORGS.get(chave_comparacao(str(dados.get("organizacao") or "")))
    if not organizacao:
        problemas.append(
            f"organizacao '{dados.get('organizacao')}' inválida. Use uma de: {', '.join(ORGANIZACOES)}."
        )

    descricao = str(dados.get("descricao") or "").strip()
    if not descricao:
        problemas.append("A incursão precisa de uma descrição de abertura.")

    recompensa = _inteiro(dados.get("recompensa_mes"))
    if recompensa is None or recompensa < 0:
        problemas.append("recompensa_mes precisa ser um número de MEs (ex.: 10).")
        recompensa = 10

    linhas_brutas = dados.get("linhas") or []
    if len(linhas_brutas) != 3:
        problemas.append(f"A incursão precisa de exatamente 3 linhas (encontrei {len(linhas_brutas)}).")

    linhas: list[list[Sala]] = []
    for i, linha_bruta in enumerate(linhas_brutas, start=1):
        if len(linha_bruta) != 3:
            problemas.append(f"Linha {i}: precisa de exatamente 3 salas (encontrei {len(linha_bruta)}).")
        salas = [_sala_de_dict(s, f"linha {i}", problemas) for s in linha_bruta]
        linhas.append([s for s in salas if s])

    objetivo = None
    if not dados.get("objetivo"):
        problemas.append("Falta a sala de Objetivo.")
    else:
        objetivo = _sala_de_dict(dados["objetivo"], "objetivo", problemas)
        if objetivo and objetivo.tipo != "Combate":
            problemas.append(
                f"objetivo: o desafio final é sempre Combate (veio como '{objetivo.tipo}')."
            )

    vistos: dict[str, int] = {}
    for sala in [s for linha in linhas for s in linha] + ([objetivo] if objetivo else []):
        vistos[sala.id] = vistos.get(sala.id, 0) + 1
    for sala_id, quantas in vistos.items():
        if quantas > 1:
            problemas.append(f"sala_id '{sala_id}' aparece {quantas} vezes; cada sala precisa de um id único.")

    if problemas:
        raise ErroDeValidacao(problemas)

    return Incursao(
        id=incursao_id,
        nome=nome,
        organizacao=organizacao,
        descricao=descricao,
        linhas=linhas,
        objetivo=objetivo,
        imagem_capa=(str(dados.get("imagem_capa")).strip() or None) if dados.get("imagem_capa") else None,
        recompensa_mes=recompensa,
    )


def carregar(caminho: Path) -> Incursao:
    return de_dict(json.loads(Path(caminho).read_text(encoding="utf-8")))


def carregar_todas(pasta: Path) -> dict[str, Incursao]:
    """Carrega toda incursão válida da pasta. Uma inválida derruba o carregamento inteiro."""
    incursoes = {}
    for arquivo in sorted(Path(pasta).glob("*.json")):
        incursao = carregar(arquivo)
        incursoes[incursao.id] = incursao
    return incursoes
