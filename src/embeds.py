"""Montagem das mensagens que o grupo vê durante a run."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import discord

from . import config
from .incursoes import Incursao, Sala
from .motor import CONSEQUENCIA_FALHA, ResolucaoSala, barra, progresso_da_run
from .rules import fmt

COR_INCURSAO = discord.Color.dark_teal()
COR_SALA = discord.Color.dark_gold()
COR_SUCESSO = discord.Color.green()
COR_PARCIAL = discord.Color.orange()
COR_FALHA = discord.Color.dark_red()

EMOJI_OPCAO = ("1️⃣", "2️⃣", "3️⃣")
EMOJI_TIPO = {
    "Combate": "⚔️",
    "Descanso": "🔥",
    "Armadilha": "🕸️",
    "Evento": "🔍",
    "Tesouro": "💰",
}


def anexo_da_imagem(caminho: Optional[str]) -> tuple[Optional[discord.File], Optional[str]]:
    """Resolve a imagem da sala: arquivo local em assets/, URL, ou nada.

    Devolve (arquivo_para_anexar, url_para_o_embed). Imagem ausente não é erro:
    a sala simplesmente aparece sem ilustração.
    """
    if not caminho:
        return None, None
    if caminho.startswith(("http://", "https://")):
        return None, caminho
    local = (config.RAIZ / caminho).resolve()
    try:
        local.relative_to(config.RAIZ.resolve())
    except ValueError:
        return None, None  # caminho apontando para fora do projeto
    if not local.is_file():
        return None, None
    nome = local.name
    return discord.File(local, filename=nome), f"attachment://{nome}"


def _rodape(embed: discord.Embed, texto: str) -> discord.Embed:
    embed.set_footer(text=texto)
    return embed


def recrutamento(
    incursao: Incursao, membros: list[discord.abc.User], criador: discord.abc.User
) -> discord.Embed:
    e = discord.Embed(
        title=f"🗺️ {incursao.nome}",
        description=incursao.descricao,
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    e.add_field(name="Recompensa", value=f"{incursao.recompensa_mes} MEs por participante", inline=True)
    lista = "\n".join(f"{i}. {m.mention}" for i, m in enumerate(membros, start=1)) or "*ninguém ainda*"
    e.add_field(
        name=f"Grupo ({len(membros)}/{config.TAMANHO_GRUPO})",
        value=lista,
        inline=False,
    )
    if incursao.imagem_capa and incursao.imagem_capa.startswith(("http://", "https://")):
        e.set_image(url=incursao.imagem_capa)
    return _rodape(
        e,
        f"Clique em Entrar para participar. A incursão começa sozinha com "
        f"{config.TAMANHO_GRUPO} jogadores — {criador.display_name} pode começar antes.",
    )


def votacao(
    incursao: Incursao, linha: int, opcoes: list[Sala], votos: dict[int, str], faltam: int
) -> discord.Embed:
    e = discord.Embed(
        title=f"Linha {linha} de 3 — para onde o grupo vai?",
        description="Cada jogador escolhe uma saída. A votação fecha assim que todos votarem.",
        color=COR_INCURSAO,
    )
    contagem: dict[str, int] = {}
    for opcao in votos.values():
        contagem[opcao] = contagem.get(opcao, 0) + 1

    for i, sala in enumerate(opcoes):
        quantos = contagem.get(sala.id, 0)
        marcador = f" — **{quantos} voto{'s' if quantos != 1 else ''}**" if quantos else ""
        e.add_field(
            name=f"{EMOJI_OPCAO[i]} {sala.nome}",
            value=f"{EMOJI_TIPO.get(sala.tipo, '•')} {sala.tipo}{marcador}",
            inline=True,
        )
    e.add_field(name="Progresso", value=progresso_da_run(linha - 1), inline=False)
    return _rodape(e, f"Faltam {faltam} voto(s). Prazo: {config.MINUTOS_VOTACAO} minutos.")


def sala_aberta(
    sala: Sala, linha: int, ja_rolaram: int, total: int
) -> tuple[discord.Embed, Optional[discord.File]]:
    e = discord.Embed(
        title=f"{EMOJI_TIPO.get(sala.tipo, '•')} {sala.nome}",
        description=sala.descricao,
        color=COR_SALA,
    )
    if sala.tem_teste:
        e.add_field(
            name="Desafio",
            value=(
                f"**CD {sala.cd}** · progresso necessário: **{sala.alvo_progresso}**\n"
                f"Perícias: {', '.join(sala.pericias)}"
            ),
            inline=False,
        )
        e.add_field(name="Rolaram", value=f"{ja_rolaram}/{total}", inline=True)
        rodape = "Cada jogador rola uma vez, com a melhor perícia que tiver entre as listadas."
    elif sala.e_combate:
        m = sala.monstro
        e.add_field(
            name=f"⚔️ {m.nome}",
            value=f"CA **{m.ca}** · Ataque **{fmt(m.ataque)}** · Dano **{m.dano}** · HP **{m.hp}**",
            inline=False,
        )
        rodape = "Sala de combate."
    else:
        rodape = "Sem teste: o grupo recupera o fôlego."

    e.add_field(name="Linha", value=f"{linha} de 3", inline=True)
    arquivo, url = anexo_da_imagem(sala.imagem)
    if url:
        e.set_image(url=url)
    return _rodape(e, rodape), arquivo


def resultado_sala(resolucao: ResolucaoSala, apelidos: dict[int, str]) -> discord.Embed:
    sala = resolucao.sala
    e = discord.Embed(
        title=f"{EMOJI_TIPO.get(sala.tipo, '•')} {sala.nome} — {'superada' if resolucao.superada else 'atravessada a duras penas'}",
        color=COR_SUCESSO if resolucao.superada else COR_PARCIAL,
    )
    linhas = []
    for r in resolucao.resultados:
        quem = apelidos.get(r.user_id, r.personagem)
        dado = f"🎲 {r.d20} {fmt(r.modificador)} = **{r.total}**"
        if r.passou:
            linhas.append(f"✅ {quem} · {r.pericia} · {dado} → +{r.margem} de progresso")
        else:
            linhas.append(f"❌ {quem} · {r.pericia} · {dado} → 0")
    e.add_field(name="Rolagens", value="\n".join(linhas) or "*ninguém rolou*", inline=False)
    e.add_field(
        name="Progresso da sala",
        value=f"{barra(resolucao.progresso, resolucao.alvo)}  **{resolucao.progresso}** / {resolucao.alvo}",
        inline=False,
    )

    falharam = resolucao.quem_falhou
    if falharam:
        consequencia = CONSEQUENCIA_FALHA.get(sala.tipo, "não contribui")
        nomes = ", ".join(apelidos.get(r.user_id, r.personagem) for r in falharam)
        e.add_field(name="Quem falhou", value=f"{nomes} — {consequencia}.", inline=False)

    if resolucao.superada and sala.recompensa:
        e.add_field(name="Recompensa", value=sala.recompensa, inline=False)
    elif not resolucao.superada:
        e.add_field(
            name="Sem recompensa",
            value="O grupo segue em frente, mas não leva o bônus desta sala.",
            inline=False,
        )
    return e


def descanso(sala: Sala) -> discord.Embed:
    e = discord.Embed(
        title=f"🔥 {sala.nome}", description=sala.descricao, color=COR_SUCESSO
    )
    if sala.recompensa:
        e.add_field(name="Recuperação", value=sala.recompensa, inline=False)
    return _rodape(e, "Sem teste nesta sala.")


def objetivo(incursao: Incursao, monstro_nome: str) -> tuple[discord.Embed, Optional[discord.File]]:
    sala = incursao.objetivo
    e = discord.Embed(
        title=f"🏁 {sala.nome}",
        description=sala.descricao,
        color=COR_FALHA,
    )
    m = sala.monstro
    e.add_field(
        name=f"⚔️ {monstro_nome}",
        value=f"CA **{m.ca}** · Ataque **{fmt(m.ataque)}** · Dano **{m.dano}** · HP **{m.hp}**",
        inline=False,
    )
    e.add_field(
        name="Recompensa",
        value=sala.recompensa or f"{incursao.recompensa_mes} MEs por participante",
        inline=False,
    )
    arquivo, url = anexo_da_imagem(sala.imagem)
    if url:
        e.set_image(url=url)
    return e, arquivo


def status(
    run: dict[str, Any],
    incursao: Incursao,
    membros: list[discord.abc.User],
    sala: Optional[Sala],
    ja_rolaram: int,
) -> discord.Embed:
    rotulos = {
        "recrutando": "montando o grupo",
        "escolhendo": "votando a próxima sala",
        "em_sala": "resolvendo a sala",
        "objetivo": "diante do objetivo",
        "sucesso": "concluída",
        "desistiu": "abandonada",
        "fracasso": "fracassada",
    }
    e = discord.Embed(
        title=f"Run #{run['id']} — {incursao.nome}",
        description=f"Estado: **{rotulos.get(run['status'], run['status'])}**",
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    e.add_field(
        name="Linha",
        value=f"{max(1, run['linha_atual'])} de 3  {progresso_da_run(max(0, run['linha_atual'] - 1))}",
        inline=True,
    )
    if sala:
        detalhe = f"{EMOJI_TIPO.get(sala.tipo, '•')} {sala.nome}"
        if sala.tem_teste:
            detalhe += f" — rolaram {ja_rolaram}/{len(membros)}"
        e.add_field(name="Sala atual", value=detalhe, inline=False)
    e.add_field(
        name=f"Participantes ({len(membros)})",
        value="\n".join(m.mention for m in membros) or "*nenhum*",
        inline=False,
    )
    return e
