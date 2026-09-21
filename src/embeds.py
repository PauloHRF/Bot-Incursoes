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
        m = sala.monstro
        e.add_field(
            name=f"⚔️ {m.nome}",
            value=f"CA **{m.ca}** · Ataque **{fmt(m.ataque)}** · Dano **{m.dano}** · HP **{m.hp}**",
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


def _linha_hp(c) -> str:
    if c.hp_atual <= 0:
        return f"💀 ~~{c.nome}~~ — caído"
    return f"❤️ {c.nome} — {barra(c.hp_atual, c.hp_max, 6)} {c.hp_atual}/{c.hp_max}"


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
    m = estado.monstro
    primeira = estado.rodada == 1 and rodada_anterior is None
    titulo = "🏁" if e_objetivo else "⚔️"
    e = discord.Embed(
        title=f"{titulo} {sala.nome} — rodada {estado.rodada}",
        description=sala.descricao if primeira else None,
        color=COR_FALHA,
    )
    e.add_field(
        name=m.nome,
        value=(
            f"{barra(estado.monstro_hp, m.hp, 12)}  **{estado.monstro_hp}**/{m.hp} HP\n"
            f"CA **{m.ca}** · Ataque **{fmt(m.ataque)}** · Dano **{m.dano}**"
        ),
        inline=False,
    )
    e.add_field(
        name="Grupo",
        value="\n".join(_linha_hp(c) for c in estado.combatentes) or "*ninguém*",
        inline=False,
    )

    if rodada_anterior:
        numero, golpes, contra, alvo_nome = rodada_anterior
        linhas = [linha_golpe(g) for g in golpes] or ["*ninguém atacou*"]
        if contra is not None and alvo_nome:
            linhas.append(f"↩️ **{m.nome}** · {texto_do_contra_ataque(contra, alvo_nome)}")
        bloco = "\n".join(linhas)
        if len(bloco) > 1024:
            bloco = bloco[:1000].rsplit("\n", 1)[0] + "\n…"
        e.add_field(name=f"Rodada {numero}", value=bloco, inline=False)

    if recompensa and primeira:
        e.add_field(name="Recompensa", value=recompensa, inline=False)

    if not encerrado:
        e.add_field(
            name="Atacaram nesta rodada",
            value=f"{ja_atacaram}/{len(estado.vivos)}",
            inline=True,
        )

    arquivo, url = anexo_da_imagem(sala.imagem) if primeira else (None, None)
    if url:
        e.set_image(url=url)
    rodape = (
        "Combate encerrado."
        if encerrado
        else "Cada personagem de pé ataca uma vez. Quando todos atacarem, o monstro revida."
    )
    return _rodape(e, rodape), arquivo


def combate_vencido(sala: Sala, estado) -> discord.Embed:
    e = discord.Embed(
        title=f"⚔️ {estado.monstro.nome} foi derrotado",
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
            f"O grupo inteiro caiu diante de **{estado.monstro.nome}**, que fica de pé com "
            f"{estado.monstro_hp}/{estado.monstro.hp} HP. Ninguém volta com o objetivo."
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
            name=f"{estado.monstro.nome} caiu em {estado.rodada} rodada(s)",
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
