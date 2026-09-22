"""Definição de incursões e do banco de salas de cada Organização.

Uma incursão guarda a lore de abertura, a lore de fecho (quando o grupo vence),
o tamanho (curta, média ou longa) e a sala final. As salas do meio não são
escritas na incursão: são sorteadas do banco da Organização quando a run começa,
então duas runs da mesma incursão percorrem caminhos diferentes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .rules import TIER_MAXIMO, chave_comparacao, nivel_maximo_do_tier, normalizar_pericia

TIPOS_SALA = ("Combate", "Descanso", "Armadilha", "Evento", "Tesouro")
ORGANIZACOES = (
    "Vórtice Oculto",
    "Aliança das Sombras",
    "Guilda dos Mortos",
    "Sentinelas do Alvorecer",
)
DIFICULDADES = ("Fácil", "Média", "Difícil")

# Quantas salas o grupo atravessa antes do objetivo, por tamanho.
TAMANHOS = {"Curta": 3, "Média": 5, "Longa": 7}

# Quantas opções o grupo recebe em cada passo.
OPCOES_POR_PASSO = 3

# Quantas criaturas uma sala de combate pode ter.
MAX_INIMIGOS = 6

# Tipos que resolvem a sala por teste de perícia (margem vs CD).
TIPOS_COM_TESTE = ("Armadilha", "Evento", "Tesouro")

EXPR_DANO = re.compile(r"^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)

_INDICE_TIPOS = {chave_comparacao(t): t for t in TIPOS_SALA}
_INDICE_ORGS = {chave_comparacao(o): o for o in ORGANIZACOES}
_INDICE_DIFS = {chave_comparacao(d): d for d in DIFICULDADES}
_INDICE_TAMANHOS = {chave_comparacao(t): t for t in TAMANHOS}


def arquivo_da_organizacao(organizacao: str) -> str:
    """Nome de arquivo do banco daquela Organização: 'Vórtice Oculto' -> vortice_oculto."""
    return chave_comparacao(organizacao).replace(" ", "_")


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
        return {
            "nome": self.nome,
            "ca": self.ca,
            "ataque": self.ataque,
            "dano": self.dano,
            "hp": self.hp,
        }


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
    monstros: list[Monstro] = field(default_factory=list)
    recompensa: Optional[str] = None
    pontos_organizacao: int = 0

    @property
    def monstro(self) -> Optional[Monstro]:
        """O primeiro inimigo da sala, para quando basta um nome."""
        return self.monstros[0] if self.monstros else None

    @property
    def tem_teste(self) -> bool:
        return self.tipo in TIPOS_COM_TESTE

    @property
    def e_combate(self) -> bool:
        return self.tipo == "Combate"

    def para_dict(self) -> dict[str, Any]:
        return {
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
            "pontos_organizacao": self.pontos_organizacao,
            "monstros": [m.para_dict() for m in self.monstros],
        }


@dataclass
class BancoDeSalas:
    """As salas que o sorteio de uma Organização pode oferecer."""

    organizacao: str
    salas: list[Sala]

    def sala(self, sala_id: str) -> Optional[Sala]:
        for s in self.salas:
            if s.id == sala_id:
                return s
        return None

    def para_dict(self) -> dict[str, Any]:
        return {
            "organizacao": self.organizacao,
            "salas": [s.para_dict() for s in self.salas],
        }


@dataclass
class Incursao:
    id: str
    nome: str
    organizacao: str
    lore_inicial: str
    objetivo: Sala
    tamanho: str = "Média"
    # Teto de nível do grupo: quem está acima deste tier não entra. Sem valor na
    # planilha, a incursão fica aberta a todo mundo em vez de trancar o servidor.
    tier: int = TIER_MAXIMO
    lore_final: Optional[str] = None
    imagem_capa: Optional[str] = None
    recompensa_mes: int = 10
    pontos_conclusao: int = 10

    @property
    def passos(self) -> int:
        """Quantas salas o grupo atravessa antes do objetivo."""
        return TAMANHOS[self.tamanho]

    @property
    def nivel_maximo(self) -> int:
        """O maior nível que ainda pode entrar: tier 3 -> nível 6."""
        return nivel_maximo_do_tier(self.tier)

    @property
    def aberta_a_todos(self) -> bool:
        return self.tier >= TIER_MAXIMO

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "organizacao": self.organizacao,
            "tamanho": self.tamanho,
            "tier": self.tier,
            "lore_inicial": self.lore_inicial,
            "lore_final": self.lore_final,
            "imagem_capa": self.imagem_capa,
            "recompensa_mes": self.recompensa_mes,
            "pontos_conclusao": self.pontos_conclusao,
            "objetivo": self.objetivo.para_dict(),
        }


def _inteiro(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def _monstros_de_dict(bruto: dict[str, Any], onde: str, problemas: list[str]) -> list[Monstro]:
    """Uma entrada de criatura vira N monstros, conforme a quantidade.

    Com quantidade > 1 cada cópia ganha um número no nome ('Lobo 1', 'Lobo 2'),
    para o grupo saber em qual está batendo.
    """
    nome = str(bruto.get("nome") or "").strip()
    ca, ataque, hp = (
        _inteiro(bruto.get("ca")),
        _inteiro(bruto.get("ataque")),
        _inteiro(bruto.get("hp")),
    )
    dano = str(bruto.get("dano") or "").strip()
    quantidade = _inteiro(bruto.get("quantidade"))
    if quantidade is None:
        quantidade = 1

    if not nome:
        problemas.append(f"{onde}: a criatura precisa de um nome.")
    for rotulo, valor in (("ca", ca), ("ataque", ataque), ("hp", hp)):
        if valor is None:
            problemas.append(f"{onde}: criatura '{nome or '?'}' sem '{rotulo}'.")
    if hp is not None and hp <= 0:
        problemas.append(f"{onde}: o HP de '{nome or '?'}' precisa ser maior que zero.")
    if not EXPR_DANO.match(dano):
        problemas.append(f"{onde}: dano '{dano}' fora do formato esperado (ex.: 2d6+3).")
    if not 1 <= quantidade <= MAX_INIMIGOS:
        problemas.append(
            f"{onde}: quantidade de '{nome or '?'}' precisa ser de 1 a {MAX_INIMIGOS}."
        )
        return []
    if not nome or None in (ca, ataque, hp) or not EXPR_DANO.match(dano):
        return []
    if quantidade == 1:
        return [Monstro(nome, ca, ataque, dano, hp)]
    return [Monstro(f"{nome} {n}", ca, ataque, dano, hp) for n in range(1, quantidade + 1)]


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

    pontos_sala = _inteiro(dados.get("pontos_organizacao")) or 0
    if pontos_sala < 0:
        problemas.append(f"{onde}: pontos_organizacao não pode ser negativo.")
        pontos_sala = 0

    # 'monstro' (singular) e o formato antigo: uma criatura so por sala.
    brutos = dados.get("monstros") or []
    if not brutos and dados.get("monstro"):
        brutos = [dados["monstro"]]
    monstros: list[Monstro] = []
    for bruto in brutos:
        monstros.extend(_monstros_de_dict(bruto, onde, problemas))

    if tipo == "Combate":
        if not brutos:
            problemas.append(f"{onde}: sala de Combate precisa de pelo menos uma criatura.")
        elif len(monstros) > MAX_INIMIGOS:
            problemas.append(
                f"{onde}: {len(monstros)} criaturas na mesma sala; o máximo é {MAX_INIMIGOS}."
            )
            monstros = monstros[:MAX_INIMIGOS]
    elif brutos:
        problemas.append(f"{onde}: só salas de Combate têm criatura.")

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
        monstros=monstros,
        recompensa=(str(dados.get("recompensa")).strip() or None) if dados.get("recompensa") else None,
        pontos_organizacao=pontos_sala,
    )


def banco_de_dict(dados: dict[str, Any]) -> BancoDeSalas:
    """Valida e converte o banco de salas de uma Organização."""
    problemas: list[str] = []

    organizacao = _INDICE_ORGS.get(chave_comparacao(str(dados.get("organizacao") or "")))
    if not organizacao:
        problemas.append(
            f"organizacao '{dados.get('organizacao')}' inválida. "
            f"Use uma de: {', '.join(ORGANIZACOES)}."
        )

    brutas = dados.get("salas") or []
    salas = [s for s in (_sala_de_dict(b, "banco", problemas) for b in brutas) if s]

    if len(salas) < OPCOES_POR_PASSO:
        problemas.append(
            f"O banco precisa de pelo menos {OPCOES_POR_PASSO} salas para o sorteio "
            f"montar um passo (tem {len(salas)})."
        )

    vistos: dict[str, int] = {}
    for sala in salas:
        vistos[sala.id] = vistos.get(sala.id, 0) + 1
    for sala_id, quantas in vistos.items():
        if quantas > 1:
            problemas.append(f"sala_id '{sala_id}' aparece {quantas} vezes no banco.")

    if problemas:
        raise ErroDeValidacao(problemas)
    return BancoDeSalas(organizacao=organizacao, salas=salas)


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
            f"organizacao '{dados.get('organizacao')}' inválida. "
            f"Use uma de: {', '.join(ORGANIZACOES)}."
        )

    # 'descricao' era o nome antigo da lore de abertura.
    lore_inicial = str(dados.get("lore_inicial") or dados.get("descricao") or "").strip()
    if not lore_inicial:
        problemas.append("Falta a lore de abertura (lore_inicial).")

    lore_final = str(dados.get("lore_final") or "").strip() or None

    tamanho = _INDICE_TAMANHOS.get(chave_comparacao(str(dados.get("tamanho") or "Média")))
    if not tamanho:
        problemas.append(
            f"tamanho '{dados.get('tamanho')}' inválido. Use "
            + ", ".join(f"{t} ({n} salas)" for t, n in TAMANHOS.items())
            + "."
        )
        tamanho = "Média"

    tier_incursao = _inteiro(dados.get("tier"))
    if tier_incursao is None:
        tier_incursao = TIER_MAXIMO  # sem tier declarado, ninguém fica de fora
    elif not 1 <= tier_incursao <= TIER_MAXIMO:
        problemas.append(
            f"tier '{dados.get('tier')}' inválido: use de 1 a {TIER_MAXIMO} "
            "(um tier a cada 2 níveis: o tier N aceita até o nível 2N)."
        )
        tier_incursao = TIER_MAXIMO

    recompensa = _inteiro(dados.get("recompensa_mes"))
    if recompensa is None or recompensa < 0:
        problemas.append("recompensa_mes precisa ser um número de MEs (ex.: 10).")
        recompensa = 10

    pontos_conclusao = _inteiro(dados.get("pontos_conclusao"))
    if pontos_conclusao is None:
        pontos_conclusao = 10
    elif pontos_conclusao < 0:
        problemas.append("pontos_conclusao não pode ser negativo.")
        pontos_conclusao = 10

    objetivo = None
    if not dados.get("objetivo"):
        problemas.append("Falta a sala de Objetivo.")
    else:
        objetivo = _sala_de_dict(dados["objetivo"], "objetivo", problemas)
        if objetivo and objetivo.tipo != "Combate":
            problemas.append(
                f"objetivo: o desafio final é sempre Combate (veio como '{objetivo.tipo}')."
            )

    if problemas:
        raise ErroDeValidacao(problemas)

    return Incursao(
        id=incursao_id,
        nome=nome,
        organizacao=organizacao,
        lore_inicial=lore_inicial,
        lore_final=lore_final,
        tamanho=tamanho,
        tier=tier_incursao,
        objetivo=objetivo,
        imagem_capa=(str(dados.get("imagem_capa")).strip() or None)
        if dados.get("imagem_capa")
        else None,
        recompensa_mes=recompensa,
        pontos_conclusao=pontos_conclusao,
    )


def carregar(caminho: Path) -> Incursao:
    return de_dict(json.loads(Path(caminho).read_text(encoding="utf-8")))


def carregar_banco(caminho: Path) -> BancoDeSalas:
    return banco_de_dict(json.loads(Path(caminho).read_text(encoding="utf-8")))


def carregar_todas(pasta: Path) -> dict[str, Incursao]:
    """Carrega toda incursão válida da pasta. Uma inválida derruba o carregamento."""
    incursoes = {}
    for arquivo in sorted(Path(pasta).glob("*.json")):
        incursao = carregar(arquivo)
        incursoes[incursao.id] = incursao
    return incursoes


def carregar_bancos(pasta: Path) -> dict[str, BancoDeSalas]:
    """Carrega os bancos de salas, indexados pelo nome da Organização."""
    bancos = {}
    for arquivo in sorted(Path(pasta).glob("*.json")):
        banco = carregar_banco(arquivo)
        bancos[banco.organizacao] = banco
    return bancos
