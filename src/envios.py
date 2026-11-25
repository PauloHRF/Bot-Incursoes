"""O conteúdo que chega pelo Discord: quem pode mexer em quê, e o que entra.

O autor manda o arquivo do Estúdio (`src/pacotes.py`) pelo `/incursao enviar`,
e ele entra no ar na hora, nos dois servidores, sem passar por ninguém. Isso
só é seguro com quatro regras, e as quatro moram aqui, longe do Discord, para
dar para testar sem ele:

1. **O repositório é intocável.** Dungeon e sala de `data/` não mudam por
   envio — nem com o mesmo código. Quem as muda é quem mexe no repositório.
2. **Cada autor mexe só no que ele mesmo enviou.** Reenviar o próprio arquivo
   atualiza; tocar no código de outro autor é recusado.
3. **O que uma run em andamento usa não muda.** O bot lê a dungeon e as salas
   a cada passo, sem cópia do começo da run: trocar o chefe ou a sala atual no
   meio deixaria a run lutando outra coisa, ou travada. O envio que mexe no
   que está em uso é recusado com o pedido de esperar; o que só acrescenta
   passa sempre.
4. **Envio só acrescenta e atualiza.** Sala que estava no bot e não veio no
   arquivo continua no bot: um autor que limpou o navegador e reenviou só as
   salas novas não pode apagar as antigas sem perceber.

A conferência do conteúdo em si — o que é sala válida, se o filtro fecha — é
a de `pacotes.conferir`, a mesma que o Estúdio mostra ao autor enquanto ele
escreve. Aqui só se monta o mundo contra o qual ela confere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Collection, Mapping, Optional, Sequence

from . import incursoes as I, pacotes

INCURSAO = "incursao"
SALA = "sala"


@dataclass(frozen=True)
class Enviado:
    """Uma dungeon ou uma sala que veio pelo Discord, como está guardada."""

    tipo: str
    organizacao: str
    id: str
    autor_id: int
    dados: dict[str, Any]


@dataclass(frozen=True)
class EmUso:
    """O que as runs em andamento estão usando agora.

    `salas` são pares (Organização, código da sala): o código só é único
    dentro do banco de uma Organização.
    """

    incursoes: frozenset[str] = frozenset()
    salas: frozenset[tuple[str, str]] = frozenset()


@dataclass
class Plano:
    """O que um envio faria: os problemas, ou o que gravar."""

    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    gravar: list[Enviado] = field(default_factory=list)
    novas: list[str] = field(default_factory=list)
    atualizadas: list[str] = field(default_factory=list)
    iguais: list[str] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.problemas


def _organizacao(dados: dict[str, Any]) -> Optional[str]:
    return I._INDICE_ORGS.get(I.chave_comparacao(str(dados.get("organizacao") or "")))


def _salas_enviadas(
    enviados: Sequence[Enviado], organizacao: str, fora: Collection[str] = ()
) -> list[I.Sala]:
    """As salas enviadas de uma Organização, já lidas, menos as de `fora`.

    Sala que não lê mais (o bestiário mudou embaixo dela, por exemplo) fica de
    fora da conta: quem conta com ela é avisado no carregamento, e não aqui.
    """
    salas = []
    for e in enviados:
        if e.tipo != SALA or e.organizacao != organizacao or e.id in fora:
            continue
        try:
            salas.append(I.sala_de_dict(e.dados))
        except I.ErroDeValidacao:
            continue
    return salas


def planejar(
    dados: Any,
    *,
    autor_id: int,
    incursoes_do_repositorio: Collection[str],
    bancos_do_repositorio: Mapping[str, I.BancoDeSalas],
    enviados: Sequence[Enviado],
    em_uso: EmUso = EmUso(),
) -> Plano:
    """Confere um envio contra o bot como ele está, e diz o que gravar."""
    plano = Plano()
    if not pacotes.e_pacote(dados):
        # A conferência diz isso melhor do que qualquer regra daqui, e sem
        # ela não há organização nem códigos para olhar.
        plano.problemas = pacotes.conferir(dados, bancos_do_repositorio).problemas
        return plano

    organizacao = _organizacao(dados)
    bruta = dados.get("incursao") if isinstance(dados.get("incursao"), dict) else None
    brutas = [s for s in (dados.get("salas") or []) if isinstance(s, dict)] \
        if isinstance(dados.get("salas"), list) else []
    por_chave = {(e.tipo, e.organizacao, e.id): e for e in enviados}
    dungeons_enviadas = {e.id: e for e in enviados if e.tipo == INCURSAO}

    # Quem é dono de cada código que o arquivo traz.
    incursao_id = str(bruta.get("id") or "").strip() if bruta else ""
    if incursao_id in incursoes_do_repositorio:
        plano.problemas.append(
            f"a dungeon '{incursao_id}' é do repositório do bot, e não muda por "
            f"envio. Dê outro nome à sua para ela ganhar um código próprio."
        )
    existente = dungeons_enviadas.get(incursao_id)
    if existente and existente.autor_id != autor_id:
        plano.problemas.append(
            f"a dungeon '{incursao_id}' foi enviada por outra pessoa, e só quem "
            f"a enviou pode atualizá-la. Dê outro nome à sua."
        )
    minhas_salas: set[str] = set()
    for s in brutas:
        sala_id = str(s.get("id") or "").strip()
        dono = por_chave.get((SALA, organizacao, sala_id)) if organizacao else None
        if dono is None:
            continue
        if dono.autor_id != autor_id:
            plano.problemas.append(
                f"a sala '{sala_id}' foi enviada por outra pessoa, e só quem a "
                f"enviou pode atualizá-la."
            )
        else:
            minhas_salas.add(sala_id)

    # O mundo contra o qual o arquivo se confere: os bancos do repositório,
    # mais o que já veio pelo Discord — menos as salas deste autor que o
    # arquivo traz de novo, que são atualização, e não código repetido.
    bancos = dict(bancos_do_repositorio)
    if organizacao in bancos:
        bancos[organizacao] = I.BancoDeSalas(
            organizacao=organizacao,
            salas=list(bancos[organizacao].salas)
            + _salas_enviadas(enviados, organizacao, fora=minhas_salas),
        )
    ocupadas = (set(incursoes_do_repositorio) | set(dungeons_enviadas)) - {incursao_id}
    conferencia = pacotes.conferir(dados, bancos, ocupadas=ocupadas)
    plano.problemas.extend(conferencia.problemas)
    plano.avisos.extend(conferencia.avisos)
    if plano.problemas:
        return plano

    # O que muda de fato, e se algo disso está em uso por uma run.
    itens = [(SALA, s.id, b) for s, b in zip(conferencia.salas, brutas)]
    if conferencia.incursao is not None:
        itens.append((INCURSAO, conferencia.incursao.id, bruta))
    for tipo, codigo, corpo in itens:
        rotulo = f"{'a dungeon' if tipo == INCURSAO else 'a sala'} '{codigo}'"
        antes = (
            dungeons_enviadas.get(codigo) if tipo == INCURSAO
            else por_chave.get((SALA, organizacao, codigo))
        )
        if antes is not None and antes.dados == corpo:
            plano.iguais.append(rotulo)
            continue
        if antes is not None:
            em_uso_agora = (
                codigo in em_uso.incursoes if tipo == INCURSAO
                else (organizacao, codigo) in em_uso.salas
            )
            if em_uso_agora:
                plano.problemas.append(
                    f"há uma run em andamento usando {rotulo}. Envie de novo "
                    f"quando ela acabar — mudar no meio deixaria o grupo "
                    f"jogando outra coisa."
                )
                continue
            plano.atualizadas.append(rotulo)
        else:
            plano.novas.append(rotulo)
        plano.gravar.append(Enviado(tipo, organizacao, codigo, autor_id, corpo))
    if plano.problemas:
        plano.gravar = []
    return plano


def mesclar(
    incursoes_do_repositorio: Mapping[str, I.Incursao],
    bancos_do_repositorio: Mapping[str, I.BancoDeSalas],
    enviados: Sequence[Enviado],
) -> tuple[dict[str, I.Incursao], dict[str, I.BancoDeSalas], list[str]]:
    """O catálogo do bot: o repositório, mais o que veio pelo Discord.

    O repositório ganha sempre: um código que exista nos dois é o de `data/`,
    e o enviado fica de fora com o problema dito. Não acontece por envio — o
    envio recusa código do repositório —, mas acontece se alguém puser no
    repositório, depois, um código que um autor já usava.
    """
    incursoes = dict(incursoes_do_repositorio)
    problemas: list[str] = []
    salas_por_org: dict[str, list[I.Sala]] = {}
    for e in enviados:
        if e.tipo != SALA:
            continue
        banco = bancos_do_repositorio.get(e.organizacao)
        if banco is None:
            problemas.append(f"sala enviada {e.id}: não há banco de {e.organizacao}.")
            continue
        if banco.sala(e.id) is not None:
            problemas.append(
                f"sala enviada {e.id}: o repositório tem uma sala com o mesmo "
                f"código em {e.organizacao}, e vale a do repositório."
            )
            continue
        try:
            salas_por_org.setdefault(e.organizacao, []).append(I.sala_de_dict(e.dados))
        except I.ErroDeValidacao as erro:
            problemas.append(f"sala enviada {e.id}: {'; '.join(erro.problemas)}")
    bancos = {
        org: I.BancoDeSalas(organizacao=org, salas=list(b.salas) + salas_por_org.get(org, []))
        for org, b in bancos_do_repositorio.items()
    }
    for e in enviados:
        if e.tipo != INCURSAO:
            continue
        if e.id in incursoes_do_repositorio:
            problemas.append(
                f"dungeon enviada {e.id}: o repositório tem uma dungeon com o "
                f"mesmo código, e vale a do repositório."
            )
            continue
        try:
            incursoes[e.id] = I.de_dict(e.dados)
        except I.ErroDeValidacao as erro:
            problemas.append(f"dungeon enviada {e.id}: {'; '.join(erro.problemas)}")
    return incursoes, bancos, problemas
