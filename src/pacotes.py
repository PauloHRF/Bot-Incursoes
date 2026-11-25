"""O arquivo do Estúdio: uma dungeon e as salas novas dela, num JSON só.

Por que um formato a mais, se o bot já lê incursão e banco de salas: quem
escreve fora do repositório não consegue mandar DOIS arquivos que precisam
casar — a dungeon e o banco da Organização dela —, e devolver o banco inteiro
apagaria o trabalho de outro autor que mexeu nele no meio do caminho. O
arquivo leva só o que o autor escreveu.

    {
      "formato": "incursao-do-estudio",
      "versao": 1,
      "organizacao": "Vórtice Oculto",
      "incursao": { ...o mesmo formato de data/incursoes... },
      "salas": [ ...salas novas, no formato do banco... ]
    }

`incursao` pode faltar quando o arquivo só traz salas; `salas` pode ser vazia
quando só traz a dungeon. Os dois juntos vazios não são arquivo nenhum.

A conferência mora aqui, e não no Estúdio, porque são dois lugares que têm de
dizer a MESMA coisa: a página, enquanto o autor escreve, e o bot, quando o
arquivo chegar pelo Discord. Uma régua de cada lado acabaria discordando — e
quem descobriria seria o autor, na hora de enviar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Collection, Mapping, Optional

from . import incursoes as I

FORMATO = "incursao-do-estudio"
VERSAO = 1

# O validador chama a sala final de "objetivo (sala OBJ)", que é o nome do
# campo no arquivo. Quem escreve pelo Estúdio nunca viu esse campo: para ele
# é a sala do chefe, e é assim que a mensagem tem de chegar — aqui, para a
# página e o bot dizerem igual.
_DO_OBJETIVO = re.compile(r"^objetivo \(sala [^)]*\)")

# A sala solta é "a sala (sala VO15)" no validador; no arquivo do Estúdio ela
# é uma entre várias, e o autor a acha pelo código.
_DA_SALA = re.compile(r"^a sala \(sala ([^)]*)\)")


def _da_sala(problema: str, rotulo: str) -> str:
    curto = _DA_SALA.sub(r"sala \1", problema)
    return curto if curto != problema else f"sala {rotulo}: {problema}"


@dataclass(frozen=True)
class Conferencia:
    """O que a conferência achou, e o que ela conseguiu ler."""

    problemas: list[str]
    avisos: list[str] = field(default_factory=list)
    incursao: Optional[I.Incursao] = None
    salas: list[I.Sala] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.problemas


def e_pacote(dados: Any) -> bool:
    """O objeto diz que é um arquivo do Estúdio.

    Pela chave `formato`, e não pela forma: uma incursão solta também tem
    `objetivo`, e um banco também tem `salas`. Adivinhar pelo conteúdo já fez
    o validador ler incursão como banco uma vez.
    """
    return isinstance(dados, dict) and dados.get("formato") == FORMATO


def novo(organizacao: str, incursao: Optional[dict] = None,
         salas: Optional[list] = None) -> dict[str, Any]:
    """Um arquivo do Estúdio montado à mão — para teste e ferramenta."""
    pacote: dict[str, Any] = {
        "formato": FORMATO, "versao": VERSAO, "organizacao": organizacao,
        "salas": list(salas or []),
    }
    if incursao is not None:
        pacote["incursao"] = incursao
    return pacote


def conferir(
    dados: Any,
    bancos: Mapping[str, I.BancoDeSalas],
    ocupadas: Collection[str] = (),
) -> Conferencia:
    """Confere o arquivo inteiro com as regras do bot.

    `bancos` são os bancos que o bot tem, por Organização: as salas novas
    entram na conta do filtro junto com eles, e o id delas não pode repetir
    um id que já está lá. `ocupadas` são os ids de dungeon que este arquivo
    não pode tomar — no Estúdio, as do repositório.
    """
    if not e_pacote(dados):
        return Conferencia(["este arquivo não foi gerado pelo Estúdio de Incursões."])
    versao = dados.get("versao")
    if not isinstance(versao, int) or isinstance(versao, bool):
        return Conferencia(["o arquivo não diz a versão do formato ('versao')."])
    if versao > VERSAO:
        return Conferencia([
            f"o arquivo é da versão {versao} do formato, e aqui só se lê até a "
            f"{VERSAO}. Atualize o bot ou o Estúdio."
        ])
    if versao < 1:
        return Conferencia([f"versão '{versao}' do formato não existe."])

    problemas: list[str] = []
    avisos: list[str] = []

    organizacao = I._INDICE_ORGS.get(
        I.chave_comparacao(str(dados.get("organizacao") or ""))
    )
    if not organizacao:
        problemas.append(
            f"organizacao '{dados.get('organizacao') or ''}' inválida. "
            f"Use uma de: {', '.join(I.ORGANIZACOES)}."
        )

    bruta = dados.get("incursao")
    brutas = dados.get("salas")
    if brutas is None:
        brutas = []
    if bruta is None and not brutas:
        problemas.append("o arquivo não traz dungeon nem sala nenhuma.")
        return Conferencia(problemas)
    if bruta is not None and not isinstance(bruta, dict):
        problemas.append("'incursao' precisa ser um objeto.")
        bruta = None
    if not isinstance(brutas, list):
        problemas.append("'salas' precisa ser uma lista.")
        brutas = []

    incursao = _a_dungeon(bruta, organizacao, ocupadas, problemas) if bruta else None
    salas = _as_salas(brutas, organizacao, bancos, problemas)

    if incursao is not None and organizacao:
        banco = bancos.get(organizacao)
        if banco is None:
            problemas.append(
                f"não há banco de salas de {organizacao} no bot: o caminho não "
                f"teria de onde sortear sala."
            )
        else:
            # As salas novas entram na conta: a dungeon que traz as próprias
            # salas não pode ser recusada por falta delas.
            junto = I.BancoDeSalas(organizacao=organizacao, salas=banco.salas + salas)
            cruzados, avisos_do_filtro = I.conferir_filtro(incursao, junto)
            problemas.extend(cruzados)
            avisos.extend(avisos_do_filtro)

    return Conferencia(problemas, avisos, incursao, salas)


def _a_dungeon(
    bruta: dict[str, Any], organizacao: Optional[str],
    ocupadas: Collection[str], problemas: list[str],
) -> Optional[I.Incursao]:
    # O tier é obrigatório AQUI, e não no arquivo da incursão: lá a falta dele
    # vale tier 5, que é "aberta a todos" — certo para conteúdo antigo, e uma
    # armadilha para quem escreve agora. O chefe, a simulação e quem pode
    # entrar dependem dele, e quem esqueceu não deveria descobrir no jogo.
    if bruta.get("tier") in (None, ""):
        problemas.append("A dungeon precisa dizer o tier (de 1 a 5).")
    try:
        incursao = I.de_dict(bruta)
    except I.ErroDeValidacao as erro:
        problemas.extend(_DO_OBJETIVO.sub("sala do chefe", p) for p in erro.problemas)
        return None
    if organizacao and incursao.organizacao != organizacao:
        problemas.append(
            f"a dungeon é de {incursao.organizacao}, mas o arquivo é de {organizacao}."
        )
    if incursao.id in ocupadas:
        problemas.append(
            f"já existe uma dungeon com o código '{incursao.id}'. Dê outro nome "
            f"a esta para ela ganhar um código próprio."
        )
    return incursao


def _as_salas(
    brutas: list, organizacao: Optional[str],
    bancos: Mapping[str, I.BancoDeSalas], problemas: list[str],
) -> list[I.Sala]:
    existentes = (
        {s.id for s in bancos[organizacao].salas}
        if organizacao and organizacao in bancos else set()
    )
    salas: list[I.Sala] = []
    vistos: set[str] = set()
    for posicao, bruta in enumerate(brutas, start=1):
        if not isinstance(bruta, dict):
            problemas.append(f"a sala {posicao} precisa ser um objeto.")
            continue
        rotulo = str(bruta.get("id") or "").strip() or f"{posicao}"
        try:
            sala = I.sala_de_dict(bruta)
        except I.ErroDeValidacao as erro:
            problemas.extend(_da_sala(p, rotulo) for p in erro.problemas)
            continue
        if sala.id in vistos:
            problemas.append(f"a sala '{sala.id}' aparece duas vezes no arquivo.")
            continue
        if sala.id in existentes:
            problemas.append(
                f"a sala '{sala.id}' já existe no banco de {organizacao}. "
                f"Sala nova precisa de um id que o banco não use."
            )
            continue
        vistos.add(sala.id)
        salas.append(sala)
    return salas
