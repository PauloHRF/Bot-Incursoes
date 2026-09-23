"""Montagem das mensagens que o grupo vê durante a run."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import discord

from . import config, retratos
from .incursoes import Incursao, Sala
from .motor import CONSEQUENCIA_FALHA, ResolucaoSala, barra, progresso_da_run
from .rules import fmt, tier

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


def url_de_imagem(valor: Optional[str]) -> Optional[str]:
    """Aceita a URL do retrato de um personagem, ou None.

    Só http(s): o Discord não carrega outra coisa, e caminhos locais de um
    jogador não devem virar anexo do bot.
    """
    if not valor:
        return None
    url = str(valor).strip()
    if len(url) > 500 or " " in url:
        return None
    return url if url.startswith(("http://", "https://")) else None


def _classe_de(personagem: dict) -> str:
    """O nome bonito da classe, ou o que estiver gravado se ela sumiu."""
    from . import classes

    achada = classes.classe(personagem.get("classe"))
    return achada.nome if achada else str(personagem.get("classe") or "sem classe")


def cartao_personagem(personagem: dict, membro) -> discord.Embed:
    """Retrato compacto de um personagem, para a abertura da run."""
    e = discord.Embed(
        title=personagem["nome"],
        description=(
            f"{membro.mention} · {_classe_de(personagem)} · "
            f"tier {tier(personagem['nivel'])}"
        ),
        color=COR_INCURSAO,
    )
    e.add_field(
        name="Combate",
        value=(
            f"CA **{personagem['ca']}** · Ataque **{fmt(personagem['bonus_ataque'])}** · "
            f"HP **{personagem['hp_max']}**"
        ),
        inline=False,
    )
    retrato = url_de_imagem(personagem.get("imagem"))
    if retrato:
        e.set_thumbnail(url=retrato)
    return e


def grupo(personagens: list[dict], membros: list, com_faixa: bool) -> discord.Embed:
    """O grupo inteiro num embed só, para acompanhar a faixa de retratos."""
    e = discord.Embed(title="🎒 O grupo", color=COR_INCURSAO)
    e.description = "\n".join(
        f"**{p['nome']}** — {m.mention} · {_classe_de(p)} T{tier(p['nivel'])} · "
        f"CA {p['ca']} · ⚔️ {fmt(p['bonus_ataque'])} · ❤️ {p['hp_max']}"
        for p, m in zip(personagens, membros)
    )
    if com_faixa:
        e.set_image(url=f"attachment://{retratos.ARQUIVO}")
    return e


async def faixa_do_grupo(personagens: list[dict]) -> Optional[discord.File]:
    """Os retratos lado a lado num PNG só, ou None se não dá para montar."""
    itens = [(p["nome"], url_de_imagem(p.get("imagem"))) for p in personagens]
    if not any(url for _, url in itens):
        return None  # ninguém pôs retrato: uma faixa de iniciais não paga o anexo
    dados = await retratos.faixa(itens)
    if not dados:
        return None
    return discord.File(BytesIO(dados), filename=retratos.ARQUIVO)


async def abertura_do_grupo(
    personagens: list[dict], membros: list
) -> tuple[list[discord.Embed], Optional[discord.File]]:
    """Como o grupo se apresenta no começo da run.

    Com Pillow, um embed só e os retratos lado a lado numa imagem. Sem ela,
    o plano B: um card por personagem, cada um com sua miniatura.
    """
    arquivo = await faixa_do_grupo(personagens)
    if arquivo is not None:
        return [grupo(personagens, membros, com_faixa=True)], arquivo
    sem_retrato = not any(url_de_imagem(p.get("imagem")) for p in personagens)
    if retratos.disponivel() or sem_retrato:
        return [grupo(personagens, membros, com_faixa=False)], None
    return [cartao_personagem(p, m) for p, m in zip(personagens, membros)], None


def exigencia_de_tier(incursao: Incursao) -> str:
    """A linha que diz quem pode entrar nesta incursão."""
    if incursao.aberta_a_todos:
        return "🎚️ Tier livre — qualquer personagem entra"
    return (
        f"🎚️ Tier {incursao.tier} — entra quem for tier {incursao.tier} ou menos"
    )


def chamada(texto: str, limite: int = 400) -> str:
    """O gancho da lore: o primeiro parágrafo, cortado se for longo demais.

    O recrutamento mostra só isto; a lore inteira sai quando a run começa, para
    o mesmo texto não aparecer duas vezes seguidas no canal.
    """
    primeiro = texto.strip().split("\n\n")[0].strip()
    if len(primeiro) <= limite:
        return primeiro
    return primeiro[:limite].rsplit(" ", 1)[0] + "…"


def _rodape(embed: discord.Embed, texto: str) -> discord.Embed:
    embed.set_footer(text=texto)
    return embed


def recrutamento(
    incursao: Incursao, membros: list[discord.abc.User], criador: discord.abc.User
) -> discord.Embed:
    e = discord.Embed(
        title=f"🗺️ {incursao.nome}",
        description=chamada(incursao.lore_inicial),
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    e.add_field(
        name="Caminho",
        value=f"{incursao.tamanho} — {incursao.passos} salas + objetivo",
        inline=True,
    )
    e.add_field(name="Recompensa", value=f"{incursao.recompensa_mes} MEs", inline=True)
    e.add_field(name="Quem pode entrar", value=exigencia_de_tier(incursao), inline=False)
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


def lore_abertura(incursao: Incursao, quantos: int) -> discord.Embed:
    """A mensagem que abre a run, com a lore da incursão."""
    e = discord.Embed(
        title=f"🗺️ {incursao.nome}",
        description=incursao.lore_inicial,
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    e.add_field(
        name="Caminho",
        value=f"{incursao.tamanho} — {incursao.passos} salas até o objetivo",
        inline=True,
    )
    e.add_field(name="Grupo", value=f"{quantos} aventureiro(s)", inline=True)
    if incursao.imagem_capa and incursao.imagem_capa.startswith(("http://", "https://")):
        e.set_image(url=incursao.imagem_capa)
    return _rodape(e, "O caminho é sorteado a cada run: nem o GM sabe o que vem pela frente.")


def lore_fecho(incursao: Incursao) -> discord.Embed:
    """O epílogo, quando o grupo cumpre o objetivo."""
    return discord.Embed(
        title=f"📖 {incursao.nome} — epílogo",
        description=incursao.lore_final,
        color=COR_SUCESSO,
    )


def votacao(
    incursao: Incursao,
    linha: int,
    opcoes: list[Sala],
    votos: dict[int, str],
    total: int,
    passos: int = 3,
) -> discord.Embed:
    maioria = total // 2 + 1
    e = discord.Embed(
        title=f"Sala {linha} de {passos} — para onde o grupo vai?",
        description=(
            f"Cada jogador escolhe uma saída. A votação fecha assim que uma sala "
            f"chegar a **{maioria}** voto(s) — o grupo não espera quem faltar."
        ),
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
    e.add_field(name="Progresso", value=progresso_da_run(linha - 1, passos), inline=False)
    lider = max(contagem.values()) if contagem else 0
    if lider >= maioria:
        rodape = "Maioria formada."
    else:
        rodape = (
            f"{len(votos)} de {total} votaram · faltam {maioria - lider} voto(s) "
            f"numa mesma sala para fechar. Sem prazo: a votação espera."
        )
    return _rodape(e, rodape)


def sala_aberta(
    sala: Sala, linha: int, ja_rolaram: int, total: int, passos: Optional[int] = None
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
        e.add_field(
            name="⚔️ " + (
                sala.monstros[0].nome
                if len(sala.monstros) == 1
                else f"{len(sala.monstros)} criaturas"
            ),
            value="\n".join(
                f"**{m.nome}** — CA **{m.ca}** · Ataque **{fmt(m.ataque)}** · "
                f"Dano **{m.dano}** · HP **{m.hp}**"
                for m in sala.monstros
            ) or "*sem criatura*",
            inline=False,
        )
        rodape = "Sala de combate."
    else:
        rodape = "Sem teste: o grupo recupera o fôlego."

    e.add_field(name="Sala", value=f"{linha} de {passos}" if passos else str(linha), inline=True)
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


def descanso(sala: Sala, curas: Optional[list[str]] = None) -> discord.Embed:
    e = discord.Embed(
        title=f"🔥 {sala.nome}", description=sala.descricao, color=COR_SUCESSO
    )
    if sala.recompensa:
        e.add_field(name="Recuperação", value=sala.recompensa, inline=False)
    if curas:
        e.add_field(name="HP recuperado", value="\n".join(curas), inline=False)
    elif curas is not None:
        e.add_field(name="HP", value="Todos já estavam inteiros.", inline=False)
    return _rodape(e, "Sem teste nesta sala.")


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
        name="Sala",
        value=(
            f"{max(1, run['linha_atual'])} de {incursao.passos}  "
            f"{progresso_da_run(max(0, run['linha_atual'] - 1), incursao.passos)}"
        ),
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


# ------------------------------------------------------------ combate


EMOJI_CRITICO = "💥"
EMOJI_FALHA_CRITICA = "💢"


def linha_golpe(g) -> str:
    """Uma linha de ataque, marcando 20 e 1 naturais."""
    rolagem = f"🎲 {g.d20} {fmt(g.bonus)} = **{g.total}** vs CA {g.ca_alvo}"
    if g.critico:
        return (
            f"{EMOJI_CRITICO} **CRITICO!** {g.atacante} · 🎲 **20** → "
            f"**{g.dano}** de dano (dados dobrados)"
        )
    if g.falha_critica:
        return f"{EMOJI_FALHA_CRITICA} {g.atacante} · 🎲 **1** → erro critico, passa longe"
    if g.acertou:
        return f"⚔️ {g.atacante} · {rolagem} → **{g.dano}** de dano"
    return f"💨 {g.atacante} · {rolagem} → errou"


def resumo_do_golpe(golpes: list[tuple]) -> str:
    """O que o atacante vê depois de clicar: uma linha por golpe do turno."""
    linhas = []
    for golpe, alvo_nome in golpes:
        if golpe.critico:
            linhas.append(
                f"{EMOJI_CRITICO} 🎲 **{golpe.d20}** — **CRITICO!** "
                f"**{golpe.dano}** de dano em {alvo_nome}, com os dados dobrados."
            )
        elif golpe.falha_critica:
            linhas.append(
                f"{EMOJI_FALHA_CRITICA} 🎲 **1 natural** — erro critico, o golpe passa longe."
            )
        elif golpe.acertou:
            linhas.append(
                f"⚔️ 🎲 **{golpe.d20}** {fmt(golpe.bonus)} = **{golpe.total}** vs CA "
                f"{golpe.ca_alvo} — acertou {alvo_nome}, **{golpe.dano}** de dano."
            )
        else:
            linhas.append(
                f"💨 🎲 **{golpe.d20}** {fmt(golpe.bonus)} = **{golpe.total}** vs CA "
                f"{golpe.ca_alvo} — errou {alvo_nome}."
            )
    return "\n".join(linhas) or "Nenhum inimigo de pé para atacar."


# Marcas dos efeitos com prazo, para o grupo ver o que esta ligado.
MARCA_ALVO = "🎯"
MARCA_PROTEGIDO = "🛡️"
MARCA_ABENCOADO = "✨"


def _linha_inimigo(i, marcado: bool = False) -> str:
    """Uma criatura no painel: barra de HP enquanto está de pé."""
    if i.caido:
        return f"☠️ ~~{i.nome}~~ — abatido"
    alvo = f"{MARCA_ALVO} " if marcado else ""
    return (
        f"👹 {alvo}**{i.nome}** {barra(i.hp_atual, i.hp_max, 8)} "
        f"{i.hp_atual}/{i.hp_max} HP · CA {i.ca} · {fmt(i.ataque)} · {i.dano}"
        + (" 💫 *atordoado*" if getattr(i, "atordoado", False) else "")
    )


def _marcas_do_combatente(c) -> str:
    """Os efeitos com prazo que estao valendo naquele personagem."""
    marcas = []
    if getattr(c, "reducao_dano", 0):
        marcas.append(MARCA_PROTEGIDO)
    if getattr(c, "vantagem", False):
        marcas.append(MARCA_ALVO)
    if getattr(c, "ca_extra", 0) or getattr(c, "cura_por_turno", 0):
        marcas.append(MARCA_ABENCOADO)
    return (" " + "".join(marcas)) if marcas else ""


def _linha_hp(c) -> str:
    if c.hp_atual <= 0:
        return f"💀 ~~{c.nome}~~ — caído"
    if getattr(c, "atordoado", False):
        atordoado = " 💫 *atordoado*"
    else:
        atordoado = ""
    # A vida temporaria entra antes do HP, entao aparece separada.
    temporaria = f" +{c.thp} THP" if getattr(c, "thp", 0) else ""
    return (
        f"❤️ {c.nome} — {barra(c.hp_atual, c.hp_max, 6)} "
        f"{c.hp_atual}/{c.hp_max}{temporaria}{_marcas_do_combatente(c)}{atordoado}"
    )


def texto_do_contra_ataque(contra, alvo_nome: str) -> str:
    """A linha do golpe do monstro, marcando 20 e 1 naturais."""
    if contra.critico:
        return (
            f"{EMOJI_CRITICO} **CRITICO!** 🎲 **20** → **{contra.dano}** de dano "
            f"em {alvo_nome} (dados dobrados)"
        )
    if contra.falha_critica:
        return f"{EMOJI_FALHA_CRITICA} 🎲 **1** → erro critico, {alvo_nome} escapa"
    rolagem = f"🎲 {contra.d20} {fmt(contra.bonus)} = **{contra.total}** vs CA {contra.ca_alvo}"
    if contra.acertou:
        return f"{rolagem} → **{contra.dano}** de dano em {alvo_nome}"
    return f"{rolagem} → errou {alvo_nome}"


def texto_da_investida(investida) -> str:
    """A linha da habilidade de uma criatura, com o save de quem foi mirado."""
    save = investida.save
    rolagem = (
        f"🎲 {save.d20} {fmt(save.modificador)} = **{save.total}** "
        f"vs CD {save.cd}"
    )
    quem = investida.alvo.nome if hasattr(investida.alvo, "nome") else investida.alvo
    cabeca = f"✴️ **{investida.inimigo}** · {investida.habilidade}"
    if investida.escapou:
        return f"{cabeca} em {quem} · {rolagem} → resistiu"
    consequencias = []
    if investida.dano:
        consequencias.append(f"**{investida.dano}** de dano")
    if investida.atordoou:
        consequencias.append("**atordoado**")
    pancada = ", ".join(consequencias) or "nada"
    return f"{cabeca} em {quem} · {rolagem} → falhou: {pancada}"


def combate(
    sala: Sala,
    estado,
    ja_atacaram: int,
    *,
    e_objetivo: bool = False,
    recompensa: Optional[str] = None,
    rodada_anterior: Optional[tuple] = None,
    encerrado: bool = False,
) -> tuple[discord.Embed, Optional[discord.File]]:
    """O painel do combate.

    É a única mensagem do confronto: em vez de postar uma mensagem por rodada,
    o bot edita este painel, guardando dentro dele o log da rodada que acabou.
    `rodada_anterior` é (numero, golpes, contra, alvo_nome).
    """
    primeira = estado.rodada == 1 and rodada_anterior is None
    titulo = "🏁" if e_objetivo else "⚔️"
    e = discord.Embed(
        title=f"{titulo} {sala.nome} — rodada {estado.rodada}",
        description=sala.descricao if primeira else None,
        color=COR_FALHA,
    )
    de_pe = len(estado.inimigos_vivos)
    rotulo = (
        estado.inimigos[0].nome
        if len(estado.inimigos) == 1
        else f"Inimigos ({de_pe} de pé de {len(estado.inimigos)})"
    )
    marcados = {
        indice
        for c in estado.combatentes
        for indice in list(getattr(c, "dano_por_alvo", {})) + list(
            getattr(c, "vantagem_contra", set())
        )
    }
    e.add_field(
        name=rotulo,
        value="\n".join(
            _linha_inimigo(i, i.indice in marcados) for i in estado.inimigos
        ),
        inline=False,
    )
    e.add_field(
        name="Grupo",
        value="\n".join(_linha_hp(c) for c in estado.combatentes) or "*ninguém*",
        inline=False,
    )

    if rodada_anterior:
        numero, golpes, revides = rodada_anterior[0], rodada_anterior[1], rodada_anterior[2]
        investidas = rodada_anterior[3] if len(rodada_anterior) > 3 else []
        linhas = [linha_golpe(g) for g in golpes] or ["*ninguém atacou*"]
        for investida in investidas:
            linhas.append(texto_da_investida(investida))
        for contra, atingido in revides:
            linhas.append(
                f"↩️ **{contra.atacante}** · {texto_do_contra_ataque(contra, atingido.nome)}"
            )
        bloco = "\n".join(linhas)
        if len(bloco) > 1024:
            bloco = bloco[:1000].rsplit("\n", 1)[0] + "\n…"
        e.add_field(name=f"Rodada {numero}", value=bloco, inline=False)

    if recompensa and primeira:
        e.add_field(name="Recompensa", value=recompensa, inline=False)

    if not encerrado:
        e.add_field(
            name="Agiram nesta rodada",
            value=f"{ja_atacaram}/{len(estado.ativos)}",
            inline=True,
        )

    arquivo, url = anexo_da_imagem(sala.imagem) if primeira else (None, None)
    if url:
        e.set_image(url=url)
    if encerrado:
        rodape = "Combate encerrado."
    elif len(estado.inimigos) > 1:
        rodape = (
            "Cada personagem de pé ataca um alvo. Quando todos atacarem, "
            "cada inimigo de pé revida."
        )
    else:
        rodape = (
            "Cada personagem de pé ataca uma vez. Quando todos atacarem, o monstro revida."
        )
    return _rodape(e, rodape), arquivo


def _quem_caiu(estado) -> str:
    """Como nomear os inimigos abatidos: um nome, ou quantos eram."""
    if len(estado.inimigos) == 1:
        return f"{estado.inimigos[0].nome} foi derrotado"
    return f"{len(estado.inimigos)} inimigos foram derrotados"


def combate_vencido(sala: Sala, estado) -> discord.Embed:
    e = discord.Embed(
        title=f"⚔️ {_quem_caiu(estado)}",
        description=f"O grupo supera **{sala.nome}** em {estado.rodada} rodada(s).",
        color=COR_SUCESSO,
    )
    e.add_field(
        name="Como o grupo saiu",
        value="\n".join(_linha_hp(c) for c in estado.combatentes),
        inline=False,
    )
    if sala.recompensa:
        e.add_field(name="Recompensa", value=sala.recompensa, inline=False)
    return e


def _campo_pontos(e: discord.Embed, lancamentos: list[dict], total: int, organizacao: str) -> None:
    """Acrescenta o balanço de pontos ao embed de desfecho, em vez de outra mensagem."""
    if not lancamentos:
        return
    ganho = sum(l["pontos"] for l in lancamentos)
    linhas = [f"**+{l['pontos']}** · {l['motivo']}" for l in lancamentos]
    linhas.append(f"**{organizacao}** agora tem **{total}** ponto(s).")
    e.add_field(name=f"Pontos de Organização (+{ganho})", value="\n".join(linhas), inline=False)


def run_fracassada(
    incursao: Incursao,
    estado,
    lancamentos: Optional[list[dict]] = None,
    total_org: int = 0,
) -> discord.Embed:
    e = discord.Embed(
        title="☠️ Incursão fracassada",
        description=(
            "O grupo inteiro caiu diante de "
            + ", ".join(f"**{i.nome}**" for i in estado.inimigos_vivos)
            + ". Ninguém volta com o objetivo."
        ),
        color=COR_FALHA,
    )
    _campo_pontos(e, lancamentos or [], total_org, incursao.organizacao)
    return e


def run_concluida(
    incursao: Incursao,
    membros: list[discord.abc.User],
    estado=None,
    lancamentos: Optional[list[dict]] = None,
    total_org: int = 0,
) -> discord.Embed:
    """O desfecho da run: vitória, como o grupo saiu, recompensa e pontos."""
    e = discord.Embed(
        title=f"🏆 {incursao.nome} — objetivo cumprido",
        description=incursao.objetivo.recompensa
        or f"O grupo entrega o resultado a {incursao.organizacao}.",
        color=COR_SUCESSO,
    )
    if estado is not None:
        e.add_field(
            name=f"{_quem_caiu(estado)} em {estado.rodada} rodada(s)",
            value="\n".join(_linha_hp(c) for c in estado.combatentes),
            inline=False,
        )
    e.add_field(
        name=f"Recompensa ({incursao.recompensa_mes} MEs por participante)",
        value="\n".join(f"{m.mention} — {incursao.recompensa_mes} MEs" for m in membros),
        inline=False,
    )
    _campo_pontos(e, lancamentos or [], total_org, incursao.organizacao)
    return _rodape(e, "Anote os MEs na planilha: o bot não guarda saldo por jogador.")


# ------------------------------------------- pontos de Organizacao

EMOJI_ORG = {
    "Vórtice Oculto": "🌀",
    "Aliança das Sombras": "🌑",
    "Guilda dos Mortos": "💀",
    "Sentinelas do Alvorecer": "🌅",
}


def placar_organizacoes(pontos: dict[str, int], organizacoes: tuple[str, ...]) -> discord.Embed:
    e = discord.Embed(
        title="Pontos das Organizações",
        description="Placar do servidor. Cada incursão credita a Organização a que pertence.",
        color=COR_INCURSAO,
    )
    ranking = sorted(organizacoes, key=lambda o: pontos.get(o, 0), reverse=True)
    medalhas = ("🥇", "🥈", "🥉", "4º")
    for posicao, org in enumerate(ranking):
        valor = pontos.get(org, 0)
        e.add_field(
            name=f"{medalhas[posicao]}  {EMOJI_ORG.get(org, '•')} {org}",
            value=f"**{valor}** ponto(s)",
            inline=False,
        )
    if not any(pontos.values()):
        e.set_footer(text="Nenhuma incursão pontuou ainda.")
    return e


def extrato_pontos(lancamentos: list[dict], organizacao: Optional[str]) -> discord.Embed:
    titulo = f"Extrato — {organizacao}" if organizacao else "Extrato de todas as Organizações"
    e = discord.Embed(title=titulo, color=COR_INCURSAO)
    if not lancamentos:
        e.description = "Nenhum lançamento ainda."
        return e
    linhas = []
    for l in lancamentos:
        quando = str(l["criado_em"])[:10]
        prefixo = "" if organizacao else f"{EMOJI_ORG.get(l['organizacao'], '•')} "
        run = f" (run #{l['run_id']})" if l["run_id"] else ""
        linhas.append(f"`{quando}` {prefixo}**{l['pontos']:+d}** · {l['motivo']}{run}")
    e.description = "\n".join(linhas)
    return e
