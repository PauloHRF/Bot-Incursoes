"""Montagem das mensagens que o grupo vê durante a run."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Optional, Sequence

import discord

from . import config, retratos
from .incursoes import DESCANSOS_DO_CAMINHO, Incursao, Sala, com_artigo
from .motor import (
    ResolucaoSala,
    barra,
    dobrar_dados,
    progresso_da_run,
)
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


def resumo_do_caminho(incursao) -> str:
    """O que o caminho tem: as salas, e as paradas de descanso pelo tamanho.

    A Longa para duas vezes para descansar e a Curta nenhuma, e isso muda a
    conta de quem escolhe entre elas — dizer só o número de salas escondia
    metade do caminho.
    """
    descansos = len(DESCANSOS_DO_CAMINHO.get(incursao.passos, {}))
    salas = f"{incursao.passos} salas"
    if not descansos:
        return f"{salas} até o objetivo, sem descanso"
    # Por extenso: "2 descansos" ao lado de "um descanso" fica desalinhado, e
    # o caminho nunca tem mais de dois.
    quais = {1: "um descanso", 2: "dois descansos"}.get(
        descansos, f"{descansos} descansos"
    )
    return f"{salas} e {quais} até o objetivo"


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


def titulo_da_incursao(incursao: Incursao) -> str:
    """O nome com o tier colado: `Tumba Afogada (T4)`.

    O tier anda junto do nome em todo cartão porque é ele que decide o que
    o grupo vai encontrar: quem entra, a CD das salas e o tamanho do
    debuff. Ler o nome sem ele é ler metade.

    Incursão aberta diz isso em vez de dar um número. O campo `tier` nunca
    vem vazio — sem valor na planilha ele fica em `TIER_MAXIMO`, para a
    incursão aceitar todo mundo em vez de trancar o servidor —, então quem
    responde "é aberta?" é `aberta_a_todos`, a mesma propriedade que a
    linha de exigência usa. Comparar com `None` nunca dava certo: uma
    incursão aberta saía rotulada "(T5)".
    """
    if incursao.aberta_a_todos:
        return f"{incursao.nome} (tier livre)"
    return f"{incursao.nome} (T{incursao.tier})"


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
        title=f"🗺️ {titulo_da_incursao(incursao)}",
        description=chamada(incursao.lore_inicial),
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    # So o tamanho: quantas salas a run tem nao muda a decisao de entrar, e o
    # "+ objetivo" era vocabulario de quem escreve conteudo.
    e.add_field(name="Caminho", value=incursao.tamanho, inline=True)
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
        title=f"🗺️ {titulo_da_incursao(incursao)}",
        description=incursao.lore_inicial,
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    e.add_field(
        name="Caminho",
        value=f"{incursao.tamanho} — {resumo_do_caminho(incursao)}",
        inline=True,
    )
    e.add_field(name="Grupo", value=f"{quantos} aventureiro(s)", inline=True)
    if incursao.imagem_capa and incursao.imagem_capa.startswith(("http://", "https://")):
        e.set_image(url=incursao.imagem_capa)
    return _rodape(e, "O caminho é sorteado a cada run: nem o GM sabe o que vem pela frente.")


def lore_fecho(incursao: Incursao) -> discord.Embed:
    """O epílogo, quando o grupo cumpre o objetivo."""
    return discord.Embed(
        title=f"📖 {titulo_da_incursao(incursao)} — epílogo",
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
        title=f"Parada {linha} de {passos} — para onde o grupo vai?",
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
            f"numa mesma sala para fechar."
        )
    return _rodape(e, rodape)


def sala_aberta(
    sala: Sala,
    linha: int,
    rolaram: Sequence[str] = (),
    faltam: Sequence[str] = (),
    passos: Optional[int] = None,
    tier: Optional[int] = None,
    tema: Optional[str] = None,
) -> tuple[discord.Embed, Optional[discord.File]]:
    """O cartão da sala, reescrito a cada rolagem.

    `rolaram` e `faltam` são nomes de PERSONAGEM, como no resultado da sala:
    quem joga com dois não se reconheceria por apelido de Discord. Antes aqui
    só vinha o par de números ("3/5"), e o grupo ficava esperando sem saber
    de quem — o nome é o que faz alguém ser cobrado.
    """
    e = discord.Embed(
        title=f"{EMOJI_TIPO.get(sala.tipo, '•')} {sala.nome}",
        description=sala.descricao,
        color=COR_SALA,
    )
    if sala.tem_teste:
        e.add_field(
            name="Desafio",
            value=(
                f"**CD {sala.cd_efetiva(tier)}** · progresso necessário: "
                f"**{sala.alvo_progresso}**\n"
                f"Perícias: {', '.join(sala.pericias)}"
            ),
            inline=False,
        )
        linhas = []
        if rolaram:
            linhas.append("🎲 " + " · ".join(f"**{n}**" for n in rolaram))
        if faltam:
            linhas.append("⏳ faltam " + ", ".join(f"**{n}**" for n in faltam))
        e.add_field(
            name=f"Rolaram {len(rolaram)}/{len(rolaram) + len(faltam)}",
            # O dado de cada um fica para o fecho da sala: aqui só se diz
            # QUEM já rolou. O resultado aparecendo rolagem a rolagem tiraria
            # a virada do `resultado_sala`, que mostra tudo de uma vez.
            value="\n".join(linhas) or "*ninguém ainda*",
            inline=False,
        )
        rodape = "Cada jogador rola uma vez, com a melhor perícia que tiver entre as listadas."
    elif sala.e_combate:
        # Quem mora na sala depende do tier do grupo e do tema da dungeon: a
        # mesma sala tem uma lista por tier e pode ter uma por tema, e nada é
        # esticado por multiplicador. O `tema` vem de quem chama, já sorteado
        # pela run, para o cartão mostrar o bando que o combate vai abrir.
        criaturas = sala.monstros_do_tier(tier, tema)
        e.add_field(
            name="⚔️ " + (
                criaturas[0].nome
                if len(criaturas) == 1
                else f"{len(criaturas)} criaturas"
            ),
            value="\n".join(
                f"**{m.nome}** {barra(m.hp, m.hp, 8)} — CA **{m.ca}** · {golpes_da_criatura(m)}"
                for m in criaturas
            ) or "*sem criatura*",
            inline=False,
        )
        rodape = "Sala de combate."
    else:
        rodape = "Sem teste: o grupo recupera o fôlego."

    e.add_field(
        name="Parada",
        value=f"{linha} de {passos}" if passos else str(linha),
        inline=True,
    )
    arquivo, url = anexo_da_imagem(sala.imagem)
    if url:
        e.set_image(url=url)
    return _rodape(e, rodape), arquivo


def resultado_sala(
    resolucao: ResolucaoSala,
    desfecho: Optional[Any] = None,
) -> discord.Embed:
    """O que a sala cobrou e quem respondeu.

    Os nomes aqui sao dos PERSONAGENS, e nao os apelidos de Discord: a sala e
    a ficha que entrou nela, nao a conta que clicou. Quem joga com dois
    personagens nao conseguiria distinguir as rolagens de outra forma.
    """
    sala = resolucao.sala
    e = discord.Embed(
        title=f"{EMOJI_TIPO.get(sala.tipo, '•')} {sala.nome} — {'superada' if resolucao.superada else 'atravessada a duras penas'}",
        color=COR_SUCESSO if resolucao.superada else COR_PARCIAL,
    )
    linhas = []
    for r in resolucao.resultados:
        quem = r.personagem
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
        # Só os nomes. O campo anunciava aqui o que a falha custa, tirado de
        # `motor.CONSEQUENCIA_FALHA`, e aquilo estava errado das duas formas:
        # na sala VENCIDA o motor não cobra de ninguém, nem de quem rolou mal,
        # e na sala PERDIDA ele cobra de TODOS que a encararam, não só destes
        # (ver `_quem_encarou`, no cog). O grupo lia uma maldição que ninguém
        # tinha levado.
        #
        # Nenhum texto no lugar: o que cada um levou DE VERDADE está logo
        # abaixo, no painel da condição, com o stack por cabeça e o prazo. A
        # regra de dobrar ou não dobrar o dado a mesa já sabe de cor — a tela
        # só precisa dizer quem é quem.
        e.add_field(
            name="Quem falhou",
            value=", ".join(r.personagem for r in falharam),
            inline=False,
        )

    if resolucao.superada and sala.recompensa:
        e.add_field(name="Recompensa", value=sala.recompensa, inline=False)
    elif not resolucao.superada:
        e.add_field(
            name="Sem recompensa",
            value="O grupo segue em frente, mas não leva o bônus desta sala.",
            inline=False,
        )

    # O que a sala deixou: dano, debuff, maldição, buff ou o baú que acordou.
    if desfecho is not None and desfecho.linhas:
        e.add_field(
            name="O que fica", value="\n".join(desfecho.linhas)[:1024], inline=False
        )
    # A benção ou a maldição tem painel próprio: ela é o que o grupo leva para
    # as próximas salas, e virava uma linha no meio das outras.
    if desfecho is not None and getattr(desfecho, "condicao", None):
        nome, valor = painel_da_condicao(desfecho.condicao)
        e.add_field(name=nome, value=valor, inline=False)
    return e


def painel_da_condicao(aplicada: Any) -> tuple[str, str]:
    """O painel da condição que a sala deixou: o quê, em quem, e por quanto tempo.

    Devolve (título, corpo) em vez de mexer no embed para o teste poder ler as
    duas partes sem montar um embed inteiro.

    As três coisas que faltavam na linha antiga:
      - **quem ficou com quanto**, porque o stack é por cabeça;
      - o **prazo**, que é a única regra que o jogador não tem como adivinhar
        (tudo decai 1 stack por combate, menos a Exaustão);
      - o **teto**, quando alguém chega perto de ser tirado da incursão por
        ele — a Exaustão em 5 e a Deterioração em 10 expulsam, e sem aviso o
        personagem simplesmente desaparecia do grupo na sala seguinte.
    """
    from . import condicoes

    condicao = condicoes.POR_ID[aplicada.cid]
    stacks = aplicada.stacks
    maior = max(stacks.values()) if stacks else 1
    titulo = f"{condicao.icone} {condicao.nome}" + (
        " — o grupo inteiro" if len(stacks) > 1 else ""
    )
    linhas = [f"**{condicao.texto}**"]
    if stacks:
        linhas.append(
            " · ".join(
                f"{nome}{f' ×{quantos}' if quantos > 1 else ''}"
                for nome, quantos in stacks.items()
            )
        )
    # O efeito somado só entra quando há mais de um stack: com um, repetiria a
    # linha de cima com outras palavras. Uma linha por nível empilhado, e não
    # por pessoa — depois de um Evento o grupo todo está no mesmo número.
    for nivel in sorted({q for q in stacks.values() if q > 1}, reverse=True):
        somado = condicoes.efeito_somado(aplicada.cid, nivel)
        if somado:
            linhas.append(f"*Em ×{nivel} isso vale {somado}.*")
    # O prazo é a regra que o jogador não tem como adivinhar — menos na
    # Exaustão, a única que não decai, cujo próprio texto do catálogo já diz
    # que ela só sai no descanso. Repetir ali era a terceira vez na mesma tela.
    if condicao.decai:
        linhas.append("*Decai 1 stack a cada combate.*")
    if condicao.teto:
        perto = [
            f"**{nome}** ({quantos}/{condicao.teto})"
            for nome, quantos in stacks.items()
            if quantos >= condicao.teto - 1
        ]
        if perto:
            linhas.append(
                f"⚠️ A {condicao.nome} tira da incursão em **{condicao.teto}**: "
                + ", ".join(perto)
                + "."
            )
    return titulo, "\n".join(linhas)[:1024]


LIMPEZAS = {
    "debuff": "1 stack de um debuff seu",
    "exaustao": "1 ponto de Exaustão — que não passa de outro jeito",
}


def descanso(
    sala: Sala,
    curas: Optional[list[str]] = None,
    limpezas: Optional[set[str]] = None,
    faltam: int = 0,
) -> discord.Embed:
    e = discord.Embed(
        title=f"🔥 {sala.nome}", description=sala.descricao, color=COR_SUCESSO
    )
    if sala.recompensa:
        e.add_field(name="Recuperação", value=sala.recompensa, inline=False)
    # `curas` agora e uma linha por personagem do grupo, montada por quem
    # tem o banco na mao. Ela vem em TODO desenho do cartao — inclusive nos
    # de depois de uma limpeza, que antes passavam `None` e caiam fora dos
    # dois ramos: o campo do HP desaparecia no primeiro clique.
    if curas:
        e.add_field(name="Como o grupo saiu", value="\n".join(curas), inline=False)
    if limpezas:
        restam = (
            f"\n\n**{faltam}** ainda {'precisa' if faltam == 1 else 'precisam'} escolher."
            if faltam
            else ""
        )
        e.add_field(
            name="Cada um tira uma coisa",
            value="\n".join(f"• {LIMPEZAS[c]}" for c in LIMPEZAS if c in limpezas)
            + "\n\nA escolha é de cada personagem, e vale **uma** por cabeça."
            + restam,
            inline=False,
        )
        return _rodape(e, "Sem teste nesta sala — cada um escolhe o que limpar.")
    return _rodape(e, "Sem teste nesta sala.")


def descanso_duro(
    sala: Sala,
    trocas: list,
    votos: dict[int, str],
    total: int,
    parada: int = 0,
    paradas: int = 0,
) -> discord.Embed:
    """A última vigília: três trocas, e a maioria decide por todos.

    O descanso normal não tem tela de escolha porque ele é sempre o mesmo —
    escolher entre três cópias da mesma coisa não é escolher. Aqui há o que
    decidir, então ele é votado como uma sala.
    """
    e = discord.Embed(
        title=f"🌙 {sala.nome}",
        description=sala.descricao,
        color=COR_SALA,
    )
    contagem: dict[str, int] = {}
    for escolhida in votos.values():
        contagem[escolhida] = contagem.get(escolhida, 0) + 1
    for i, troca in enumerate(trocas):
        quantos = contagem.get(troca.id, 0)
        marcador = (
            f" — **{quantos} voto{'s' if quantos != 1 else ''}**" if quantos else ""
        )
        e.add_field(
            name=f"{EMOJI_OPCAO[i]} {troca.nome}{marcador}",
            value=troca.texto,
            inline=False,
        )
    if parada and paradas:
        e.add_field(
            name="Parada",
            value=f"{parada} de {paradas}",
            inline=True,
        )
    lider = max(contagem.values()) if contagem else 0
    alvo = total // 2 + 1
    rodape = (
        "Maioria formada."
        if lider >= alvo
        else f"{len(votos)} de {total} votaram · a troca vale para o grupo inteiro."
    )
    return _rodape(e, rodape)


def descanso_duro_feito(troca, linhas: list) -> discord.Embed:
    """O que a troca escolhida fez com o grupo.

    Fica no canal depois que o cartao da escolha sai: e o registro do preco
    que o grupo aceitou pagar, e a Exaustao daqui dura o resto da incursao.
    """
    e = discord.Embed(
        title=f"🌙 A Última Vigília — {troca.nome}",
        description=troca.texto,
        color=COR_SUCESSO,
    )
    if linhas:
        e.add_field(
            name="O que ficou", value="\n".join(linhas)[:1024], inline=False
        )
    return e


def buffs(
    condicoes_do_grupo: Optional[dict[int, dict[str, int]]] = None,
    nomes: Optional[dict[int, str]] = None,
    estado=None,
) -> discord.Embed:
    """O que cada emoji ACESO agora quer dizer, e em quem ele está.

    Agrupado por emoji, e não por pessoa, porque é essa a pergunta que ele
    responde: "o que é esse símbolo no painel?". Procurar por pessoa obriga a
    achar primeiro de quem é a linha, que é justamente o que quem pergunta
    não sabe.

    Só entra o que está aceso. O catálogo inteiro não responde nada: a
    pergunta nasce de olhar a linha de alguém e não reconhecer uma marca.

    Um emoji continua podendo juntar dois sentidos aqui, e os dois saem no
    mesmo campo. Hoje nenhum junta — nenhuma marca repete ícone de condição,
    e há teste guardando isso —, mas o formato não depende disso para ler
    bem, e é o que segura o dia em que o vocabulário crescer.
    """
    from . import condicoes

    quem_e = nomes or {}
    # {emoji: [[nome, texto, [quem, ...]], ...]} — ordem de insercao, que e a
    # ordem do catalogo e depois a do painel.
    entradas: dict[str, list[list[Any]]] = {}

    def anotar(emoji: str, nome: str, texto: str, quem: str) -> None:
        linhas = entradas.setdefault(emoji, [])
        for item in linhas:
            if item[0] == nome:
                item[2].append(quem)
                return
        linhas.append([nome, texto, [quem]])

    for condicao in condicoes.CATALOGO:
        for user_id, carregadas in sorted((condicoes_do_grupo or {}).items()):
            stacks = (carregadas or {}).get(condicao.id, 0)
            if stacks <= 0:
                continue
            quem = quem_e.get(user_id, f"<@{user_id}>")
            if stacks > 1:
                # Com mais de um stack o texto do catalogo (que e de UM) ja nao
                # serve: vai a conta feita ao lado do nome.
                somado = condicoes.efeito_somado(condicao.id, stacks)
                quem = f"{quem} ×{stacks}" + (f" ({somado})" if somado else "")
            anotar(condicao.icone, condicao.nome, condicao.texto, quem)

    for c in getattr(estado, "combatentes", None) or ():
        # Quem esta no chao aparece so como caido, como no painel: as marcas
        # dele nao estao valendo coisa nenhuma enquanto ele nao se levanta.
        tabela = ESTADOS if c.hp_atual <= 0 else ESTADOS + MARCAS
        for emoji, nome, texto, aceso in tabela:
            if aceso(c):
                anotar(emoji, nome, texto, c.nome)

    e = discord.Embed(title="O que o grupo carrega agora", color=COR_INCURSAO)
    if not entradas:
        e.description = (
            "Nenhum emoji aceso: ninguém carrega condição de sala, e nada "
            "está ligado no combate."
        )
        return e
    e.description = (
        "Cada emoji que está na tela agora, o que ele faz e quem o tem."
    )
    for emoji, itens in list(entradas.items())[:25]:
        e.add_field(
            name=f"{emoji} " + " / ".join(nome for nome, _t, _q in itens),
            value="\n".join(
                f"**{nome}** — {texto}\n{', '.join(quem)}"
                for nome, texto, quem in itens
            )[:1024],
            inline=False,
        )
    return e


def linha_de_condicoes(carregadas: dict[str, int]) -> str:
    """As condições de um personagem em linha: '😨 Medo ×2 · 🐌 Letargia'."""
    from . import condicoes

    rotulos = [
        condicoes.rotulo(cid, stacks)
        for cid, stacks in sorted(carregadas.items())
        if stacks > 0 and cid in condicoes.POR_ID
    ]
    return " · ".join(rotulos)


def status(
    run: dict[str, Any],
    incursao: Incursao,
    membros: list[discord.abc.User],
    sala: Optional[Sala],
    ja_rolaram: int,
    condicoes_do_grupo: Optional[dict[int, dict[str, int]]] = None,
    nomes: Optional[dict[int, str]] = None,
) -> discord.Embed:
    rotulos = {
        "recrutando": "montando o grupo",
        "escolhendo": "votando a próxima sala",
        "em_sala": "resolvendo a sala",
        "objetivo": "diante do objetivo",
        "sucesso": "concluída",
        "desistiu": "abandonada",
        "fracasso": "fracassada",
        "encerrada": "encerrada por quem administra",
    }
    e = discord.Embed(
        title=f"Run #{run['id']} — {titulo_da_incursao(incursao)}",
        description=f"Estado: **{rotulos.get(run['status'], run['status'])}**",
        color=COR_INCURSAO,
    )
    e.add_field(name="Organização", value=incursao.organizacao, inline=True)
    e.add_field(
        name="Sala",
        value=(
            f"{max(1, run['linha_atual'])} de {incursao.paradas}  "
            f"{progresso_da_run(max(0, run['linha_atual'] - 1), incursao.paradas)}"
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
    # O que cada um carrega de sala: sem isto o grupo joga com penalidade
    # invisivel e nao entende por que o dado parou de obedecer.
    if condicoes_do_grupo:
        linhas = []
        for user_id, carregadas in sorted(condicoes_do_grupo.items()):
            texto = linha_de_condicoes(carregadas)
            if not texto:
                continue
            quem = (nomes or {}).get(user_id, f"<@{user_id}>")
            linhas.append(f"**{quem}** · {texto}")
        if linhas:
            e.add_field(
                name="O que o grupo carrega",
                value="\n".join(linhas)[:1024],
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
            # Sem "(dados dobrados)": o 💥 e o **20** já dizem o que houve, e
            # dobrar os dados no crítico é regra que a mesa sabe de cor.
            f"{EMOJI_CRITICO} **CRITICO!** {g.atacante} · 🎲 **20** → "
            f"**{g.dano}** de dano"
        )
    if g.falha_critica:
        return f"{EMOJI_FALHA_CRITICA} {g.atacante} · 🎲 **1** → erro critico, passa longe"
    if g.acertou and not g.dano:
        # Dano zero só sai do corte plano da Poção de Resistência: a fração do
        # Rage nunca passa de "metade, no mínimo 1". Então a linha pode dizer
        # o que aconteceu em vez de mostrar um 0 sem explicação.
        return f"🛡️ {g.atacante} · {rolagem} → acertou, e a resistência segurou"
    if g.acertou:
        return f"⚔️ {g.atacante} · {rolagem} → **{g.dano}** de dano"
    return f"💨 {g.atacante} · {rolagem} → errou"


def abertura_do_dano(golpe) -> list[str]:
    """De onde saiu cada pedaço do dano, uma linha por fonte.

    Só no resumo privado, e não na linha do painel: o painel é reescrito a
    cada ação e carrega o grupo inteiro — detalhe por fonte ali deixaria o
    log duas vezes mais longo para todos.

    Um golpe de fonte única não ganha abertura: repetir "arma 1d8+4 → 12"
    embaixo de "12 de dano" não diz nada que a linha de cima já não diga.
    """
    partes = getattr(golpe, "partes", None) or []
    if len(partes) < 2:
        return []
    linhas = []
    for parte in partes:
        if not parte.expressao:
            # Numero solto: a passiva que da +3 nao tem dado para mostrar.
            linhas.append(f"⤷ {parte.rotulo} {fmt(parte.valor)}")
            continue
        rolado = (
            dobrar_dados(parte.expressao) if golpe.critico
            else parte.expressao
        )
        linhas.append(f"⤷ {parte.rotulo} {rolado} → **{parte.valor}**")
    return linhas


def resumo_do_golpe(golpes: list[tuple]) -> str:
    """O que o atacante vê depois de clicar: uma linha por golpe do turno."""
    linhas = []
    for golpe, alvo_nome in golpes:
        if golpe.critico:
            linhas.append(
                f"{EMOJI_CRITICO} 🎲 **{golpe.d20}** — **CRITICO!** "
                f"**{golpe.dano}** de dano em {alvo_nome}."
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
        linhas += abertura_do_dano(golpe)
    return "\n".join(linhas) or "Nenhum inimigo de pé para atacar."


# Marcas dos efeitos com prazo, para o grupo ver o que esta ligado.
#
# NENHUMA delas pode repetir o ícone de uma condição de `condicoes.CATALOGO`:
# as duas famílias dividem a MESMA linha de HP, e repetir faz o jogador ler a
# coisa errada. Três repetiam — ✨ era Benção e era Abençoado, 🩸 era
# Deterioração e era ameaça, 💫 era Perturbação e era atordoado —, e quem
# cedeu foram as marcas, porque as condições são o vocabulário da planilha,
# que a mesa já decorou. `tests/test_telas.py` guarda a regra.
MARCA_ALVO = "🎯"
MARCA_PROTEGIDO = "🛡️"
MARCA_ABENCOADO = "💠"
# Ameaça acima da da classe: alguma habilidade LIGADA está chamando a
# atenção. Não acende pelo que o personagem gerou agindo — isso todo mundo
# faz, e a marca em todos não diria nada (ver `Combatente.ameaca_gerada`).
MARCA_AMEACA = "❗"
# Caído e atordoado também são marcas, e também precisavam de nome: o painel,
# a ordem da iniciativa e as linhas do log escreviam cada um o seu, então
# trocar um deixava os outros para trás.
MARCA_CAIDO = "⚰️"
MARCA_ATORDOADO = "😵"
# A criatura que cai está ABATIDA, e o personagem fica caído: a criatura não
# volta, e é por isso que são dois símbolos e não um.
MARCA_ABATIDO = "☠️"


def golpes_da_criatura(m) -> str:
    """O que a criatura faz na vez dela: 'Mordida +10 2d10+6, 2× Garra +10 2d6+6'."""
    golpes = getattr(m, "golpes", None) or []
    if not golpes:
        vezes = f"{m.ataques}× " if getattr(m, "ataques", 1) > 1 else ""
        return f"{vezes}Ataque **{fmt(m.ataque)}** · Dano **{m.dano}**"
    grupos: list[list] = []
    for g in golpes:
        chave = (g.nome, g.ataque, g.dano)
        if grupos and grupos[-1][0] == chave:
            grupos[-1][1] += 1
        else:
            grupos.append([chave, 1])
    return ", ".join(
        f"{f'{n}× ' if n > 1 else ''}{nome} **{fmt(ataque)}** {dano}"
        for (nome, ataque, dano), n in grupos
    )


def _linha_inimigo(i, marcado: bool = False) -> str:
    """Uma criatura no painel: barra de HP enquanto está de pé."""
    if i.caido:
        return f"{MARCA_ABATIDO} ~~{i.nome}~~ — abatido"
    alvo = f"{MARCA_ALVO} " if marcado else ""
    return (
        f"👹 {alvo}**{i.nome}** {barra(i.hp_atual, i.hp_max, 8)} "
        f"· CA {i.ca} · "
        + (
            f"{len(i.golpes)} golpes"
            if getattr(i, "golpes", None)
            else f"{fmt(i.ataque)} · {i.dano}"
        )
        + (f" {MARCA_ATORDOADO} *atordoado*"
           if getattr(i, "atordoado", False) else "")
    )


# Cada marca e cada estado do painel, com o que querem dizer e como se sabe que
# estao acesos. UMA tabela, porque o painel e o `/incursao buffs` leem dela: a
# marca que alguem acrescentar aparece explicada nos dois, em vez de acender no
# painel sem ninguem saber o que e. A ORDEM e a do painel.
MARCAS: tuple[tuple[str, str, str, Any], ...] = (
    (
        MARCA_PROTEGIDO, "Protegido",
        "O dano que chega está sendo cortado.",
        lambda c: getattr(c, "reducao_dano", 0) or getattr(c, "reducao_plana", 0),
    ),
    (
        MARCA_ALVO, "Com vantagem",
        "Os ataques dele saem com vantagem.",
        lambda c: getattr(c, "vantagem", False),
    ),
    (
        MARCA_ABENCOADO, "Abençoado",
        "CA a mais, ou cura chegando a cada turno.",
        lambda c: getattr(c, "ca_extra", 0) or getattr(c, "cura_por_turno", 0),
    ),
    (
        MARCA_AMEACA, "Chamando atenção",
        "Uma habilidade ligada está puxando a atenção dos inimigos.",
        lambda c: getattr(c, "ameaca_extra", 0) > 0,
    ),
)

# Os dois estados que o painel escreve com palavra ao lado, em vez de marca
# solta. Ficam fora de `MARCAS` para nao mudarem a linha do painel, e entram no
# `/incursao buffs` porque sao emoji que o grupo tem na tela.
ESTADOS: tuple[tuple[str, str, str, Any], ...] = (
    (
        MARCA_CAIDO, "Caído",
        "Está no chão: fora do combate até alguém levantar com uma cura.",
        lambda c: c.hp_atual <= 0,
    ),
    (
        MARCA_ATORDOADO, "Atordoado",
        "Perde a vez desta rodada.",
        lambda c: getattr(c, "atordoado", False),
    ),
)


def _marcas_do_combatente(c) -> str:
    """Os efeitos com prazo que estao valendo naquele personagem."""
    marcas = [emoji for emoji, _nome, _texto, aceso in MARCAS if aceso(c)]
    return (" " + "".join(marcas)) if marcas else ""


def linha_de_ameaca(combatentes) -> str:
    """Quanto da atenção dos inimigos cada um está puxando.

    É a Ameaça já passada pela curva e normalizada, que é o número que decide
    de verdade — a ameaça crua não diz nada sozinha, porque o que importa é a
    comparação com o resto do grupo.

    As fatias ANDAM durante o combate: cada ação gera ameaça, então quem cura
    e quem estoura área vai puxando atenção. É de propósito que o painel
    mostre isso rodada a rodada.

    **Com os fatores**, e não só com a ameaça crua. Sem eles a linha mentia
    exatamente para quem gastou uma ação se protegendo: o mago com Fly lia
    25% e era sorteado com 6%. O painel promete ser o número que decide, e o
    número que decide inclui o fator — é por ele que `sortear_alvo` passa.
    """
    from . import ameaca

    de_pe = [c for c in combatentes if c.hp_atual > 0]
    if len(de_pe) < 2:
        return ""
    fatias = ameaca.porcentagens(
        ameaca.de_quem(de_pe), ameaca.fatores_de(de_pe)
    )
    partes = [
        f"{c.nome} {fatia:.0f}%{MARCA_AMEACA if c.ameaca_extra > 0 else ''}"
        for c, fatia in sorted(zip(de_pe, fatias), key=lambda par: -par[1])
    ]
    return " · ".join(partes)


def _linha_hp(c, carregadas: Optional[dict[str, int]] = None) -> str:
    if c.hp_atual <= 0:
        return f"{MARCA_CAIDO} ~~{c.nome}~~ — caído"
    if getattr(c, "atordoado", False):
        atordoado = f" {MARCA_ATORDOADO} *atordoado*"
    else:
        atordoado = ""
    # A vida temporaria entra antes do HP, entao aparece separada.
    temporaria = f" +{c.thp} THP" if getattr(c, "thp", 0) else ""
    # As condicoes de sala entram so com o icone: o nome inteiro estouraria a
    # linha, e /incursao status mostra o detalhe.
    marcas = ""
    if carregadas:
        from . import condicoes

        icones = [
            condicoes.POR_ID[cid].icone + (f"×{stacks}" if stacks > 1 else "")
            for cid, stacks in sorted(carregadas.items())
            if stacks > 0 and cid in condicoes.POR_ID
        ]
        marcas = ("  " + " ".join(icones)) if icones else ""
    return (
        f"❤️ {c.nome} — {barra(c.hp_atual, c.hp_max, 6)} "
        f"{c.hp_atual}/{c.hp_max}{temporaria}{_marcas_do_combatente(c)}{atordoado}"
        f"{marcas}"
    )


def texto_do_contra_ataque(contra, alvo_nome: str) -> str:
    """A linha do golpe do monstro, marcando 20 e 1 naturais."""
    if contra.critico:
        return (
            f"{EMOJI_CRITICO} **CRITICO!** 🎲 **20** → **{contra.dano}** de dano "
            f"em {alvo_nome}"
        )
    if contra.falha_critica:
        return f"{EMOJI_FALHA_CRITICA} 🎲 **1** → erro critico, {alvo_nome} escapa"
    rolagem = f"🎲 {contra.d20} {fmt(contra.bonus)} = **{contra.total}** vs CA {contra.ca_alvo}"
    if contra.acertou:
        return f"{rolagem} → **{contra.dano}** de dano em {alvo_nome}"
    return f"{rolagem} → errou {alvo_nome}"


def texto_da_investida(investida) -> str:
    """A linha da habilidade de uma criatura, com a rolagem de quem foi mirado.

    Na habilidade de resistência quem rola é o alvo, contra a CD; na de ataque
    é a criatura, contra a CA. A linha diz qual das duas foi.
    """
    from . import condicoes

    quem = investida.alvo.nome if hasattr(investida.alvo, "nome") else investida.alvo
    cabeca = f"✴️ **{investida.inimigo}** · {investida.habilidade}"
    if investida.ataque is not None:
        contra = investida.ataque
        rolagem = (
            f"🎲 {contra.d20} {fmt(contra.bonus)} = **{contra.total}** "
            f"vs CA {contra.ca_alvo}"
        )
        if not contra.acertou:
            return f"{cabeca} em {quem} · {rolagem} → errou"
        critico = " **crítico!**" if contra.critico else ""
        return f"{cabeca} em {quem} · {rolagem} →{critico} **{investida.dano}** de dano"

    save = investida.save
    rolagem = (
        f"🎲 {save.d20} {fmt(save.modificador)} = **{save.total}** "
        f"vs CD {save.cd}"
    )
    if investida.escapou:
        if investida.dano:
            return f"{cabeca} em {quem} · {rolagem} → resistiu: **{investida.dano}** de dano (metade)"
        return f"{cabeca} em {quem} · {rolagem} → resistiu"
    consequencias = []
    if investida.dano:
        consequencias.append(f"**{investida.dano}** de dano")
    if investida.atordoou:
        consequencias.append("**atordoado**")
    consequencias += [
        f"**{condicoes.rotulo(cid)}**"
        for cid in investida.debuffs
        if cid in condicoes.POR_ID
    ]
    pancada = ", ".join(consequencias) or "nada"
    return f"{cabeca} em {quem} · {rolagem} → falhou: {pancada}"


def _linha_iniciativa(
    posicao: int, entrada: dict, estado, vez: int, turnos: dict, encerrado: bool
) -> str:
    """Uma linha da ordem: quem é, o que rolou e em que pé está nesta rodada."""
    rolagem = f"`{entrada['d20'] + entrada['modificador']:>2}`"
    if entrada["tipo"] == "inimigo":
        quem = estado.inimigo(entrada["alvo_id"])
        emoji = "👹"
    else:
        quem = estado.combatente(entrada["alvo_id"])
        emoji = "🧝"
    nome = entrada["nome"]
    if quem is not None and quem.caido:
        # A lista mistura criatura e personagem, entao ela diz QUAL dos dois
        # caiu: a criatura esta abatida e nao volta, o personagem esta no chao
        # e uma cura o levanta.
        caiu = MARCA_ABATIDO if entrada["tipo"] == "inimigo" else MARCA_CAIDO
        return f"{caiu} {rolagem} ~~{nome}~~"
    if encerrado:
        return f"{emoji} {rolagem} {nome}"
    if posicao < vez:
        marca = "✅"
    elif posicao == vez:
        marca = "▶️"
    else:
        marca = "▫️"
    extra = ""
    if getattr(quem, "atordoado", False):
        quando = "perdeu" if posicao < vez else "perde"
        extra = f" — {MARCA_ATORDOADO} {quando} a vez"
    elif entrada["tipo"] != "inimigo" and posicao >= vez:
        turno = (turnos or {}).get(entrada["alvo_id"])
        if turno is not None:
            extra = " — ação guardada ⏳"
        elif posicao == vez:
            extra = " — **sua vez de escolher**"
    return f"{marca} {rolagem} {emoji} {nome}{extra}"


def _bloco(linhas: list[str], vazio: str) -> str:
    bloco = "\n".join(linhas) or vazio
    if len(bloco) > 1024:
        # O fim da rodada importa mais que o começo: corta por cima.
        bloco = "…\n" + bloco[-1000:].split("\n", 1)[-1]
    return bloco


def combate(
    sala: Sala,
    estado,
    *,
    ordem: Optional[list[dict]] = None,
    vez: int = 0,
    turnos: Optional[dict] = None,
    registro: Optional[list[str]] = None,
    anterior: Optional[tuple] = None,
    e_objetivo: bool = False,
    recompensa: Optional[str] = None,
    encerrado: bool = False,
    condicoes_do_grupo: Optional[dict[int, dict[str, int]]] = None,
) -> tuple[discord.Embed, Optional[discord.File]]:
    """O painel do combate.

    É a única mensagem do confronto: em vez de postar uma mensagem por rodada,
    o bot edita este painel. Ele mostra a ordem da iniciativa com a vez atual,
    o log da rodada em andamento (`registro`) e o da que acabou (`anterior`,
    como (numero, linhas)).
    """
    primeira = estado.rodada == 1 and not registro and not anterior
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
        value="\n".join(
            _linha_hp(c, (condicoes_do_grupo or {}).get(c.user_id))
            for c in estado.combatentes
        )
        or "*ninguém*",
        inline=False,
    )

    atencao = linha_de_ameaca(estado.combatentes)
    if atencao:
        e.add_field(name=f"{MARCA_AMEACA} Ameaça", value=atencao, inline=False)

    if ordem:
        e.add_field(
            name="Iniciativa",
            value=_bloco(
                [
                    _linha_iniciativa(p, entrada, estado, vez, turnos, encerrado)
                    for p, entrada in enumerate(ordem)
                ],
                "*sem ordem*",
            ),
            inline=False,
        )

    if anterior:
        numero, linhas = anterior
        e.add_field(
            name=f"Rodada {numero}", value=_bloco(linhas, "*ninguém agiu*"), inline=False
        )
    if registro:
        rotulo_rodada = (
            f"Rodada {estado.rodada}" if encerrado else f"Rodada {estado.rodada} (em andamento)"
        )
        e.add_field(name=rotulo_rodada, value=_bloco(registro, "—"), inline=False)

    if recompensa and primeira:
        e.add_field(name="Recompensa", value=recompensa, inline=False)

    arquivo, url = anexo_da_imagem(sala.imagem) if primeira else (None, None)
    if url:
        e.set_image(url=url)
    if encerrado:
        rodape = "Combate encerrado."
    else:
        rodape = (
            "Escolha ataque ou habilidade quando quiser: as ações saem uma de cada "
            "vez, na ordem da iniciativa (1d20 + Destreza). Cada criatura age na vez dela."
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


def descanso_fechado(
    sala: Sala, linhas: Optional[list[str]] = None
) -> discord.Embed:
    """O que fica no canal depois que o descanso fecha.

    O cartão do descanso tem botões, e cartão sai do canal quando o passo
    seguinte abre — só que o passo seguinte abre no MESMO instante em que o
    descanso fecha. Sem esta mensagem o grupo via o HP e o perdia na mesma
    batida.

    Todo outro tipo de sala já deixava um `resultado_sala` atrás de si. O
    descanso era o único que não deixava nada, porque ele não tem rolagem e
    chegava em `_concluir_sala` sem resolução nenhuma.

    **E ele leva a Recuperação junto.** Esse campo só existia no cartão com
    botões, então o que o descanso devolveu — o texto da sala e os usos das
    habilidades *por descanso* — sumia do canal junto com os botões. Era a
    informação mais valiosa da sala depois do HP, e a única que não voltava.
    """
    e = discord.Embed(
        title=f"🏕️ {sala.nome} — o grupo descansou", color=COR_SUCESSO
    )
    recuperado = ["As habilidades **por descanso** voltaram a ter uso."]
    if sala.recompensa:
        recuperado.insert(0, sala.recompensa)
    e.add_field(name="Recuperação", value="\n".join(recuperado), inline=False)
    if linhas:
        e.add_field(name="Como o grupo saiu", value="\n".join(linhas), inline=False)
    return e


def campo_ouro(e: discord.Embed, ouro: Optional[list[tuple[str, int]]]) -> None:
    """O ouro que a incursao pagou, uma linha por personagem.

    So aqui, no fecho: por sala seria uma linha a cada passo, e o grupo nao
    precisa acompanhar centavo por centavo — precisa saber com quanto saiu.
    """
    if not ouro:
        return
    linhas = [f"**+{quanto}** · {nome}" for nome, quanto in ouro if quanto]
    if not linhas:
        return
    total = sum(q for _n, q in ouro)
    e.add_field(
        name=f"Ouro da incursao (+{total})",
        value="\n".join(linhas) + "\nGaste com `/mercado vitrine`.",
        inline=False,
    )


def campo_caminho(
    e: discord.Embed, caminho: Optional[list[tuple[Sala, bool]]]
) -> None:
    """O histórico da run: por onde o grupo passou, na ordem, e como saiu.

    É o que sobra no canal — as mensagens de cada passo somem quando o passo
    seguinte abre, e o caminho inteiro reaparece aqui, no fim.
    """
    if not caminho:
        return
    # Passou ou falhou, e nao a dificuldade: a dificuldade e a CD escrita no
    # banco, numero de quem monta a sala. Quem le o fecho quer saber em qual
    # sala o grupo se deu mal.
    # Descanso nao leva ✅ nem ❌: nao ha o que vencer numa parada de
    # descanso, e o ❌ dizia que o grupo tinha falhado em descansar.
    linhas = [
        f"{i}. {'➖' if s.tipo == 'Descanso' else ('✅' if venceu else '❌')}"
        f" {EMOJI_TIPO.get(s.tipo, '•')} **{s.nome}**"
        for i, (s, venceu) in enumerate(caminho, start=1)
    ]
    bloco = "\n".join(linhas)
    if len(bloco) > 1024:
        bloco = bloco[:1000].rsplit("\n", 1)[0] + "\n…"
    e.add_field(name=f"Caminho ({len(caminho)} sala(s))", value=bloco, inline=False)


def run_fracassada(
    incursao: Incursao,
    lancamentos: Optional[list[dict]] = None,
    total_org: int = 0,
    caminho: Optional[list[tuple[Sala, bool]]] = None,
    sala: Optional[Sala] = None,
    ouro: Optional[list[tuple[str, int]]] = None,
) -> discord.Embed:
    """O fecho de uma run perdida: onde o grupo caiu.

    A sala, e nao a lista de criaturas de pe: "caiu em Ninho dos Cães" conta
    a historia, e "caiu diante de Cão Infernal 1, Cão Infernal 2, Cão
    Infernal 3, Cão Infernal 4" so conta o numero de cães.
    """
    onde = f" em **{sala.nome}**" if sala else ""
    e = discord.Embed(
        title=f"☠️ {titulo_da_incursao(incursao)} — fracassada",
        description=(
            f"O grupo inteiro caiu{onde}. Ninguém volta com o objetivo."
        ),
        color=COR_FALHA,
    )
    campo_caminho(e, caminho)
    campo_ouro(e, ouro)
    # A incursao paga de uma vez, no fecho, e so quando e concluida. Dizer
    # isso aqui evita a conversa de "mas eu passei quatro salas".
    e.add_field(
        name="Ouro",
        value=(
            "**Nada.** A incursao paga no fecho, e so quando e concluida — "
            "as salas do caminho nao pagam por si."
        ),
        inline=False,
    )
    _campo_pontos(e, lancamentos or [], total_org, incursao.organizacao)
    return e


def run_desistida(
    incursao: Incursao,
    onde: Optional[Sala] = None,
    passo: int = 0,
    lancamentos: Optional[list[dict]] = None,
    total_org: int = 0,
    caminho: Optional[list[tuple[Sala, bool]]] = None,
    ouro: Optional[list[tuple[str, int]]] = None,
    perdido: int = 0,
) -> discord.Embed:
    """O desfecho de uma run abandonada pelo grupo.

    Antes a desistência só mandava uma linha de texto: não havia cartão, e
    o grupo saía sem ver por onde passou nem com o que ficou. Era o único
    dos três fechos sem embed.

    `perdido` é o ouro do fecho que ficou para trás — o preço de desistir,
    dito com número.

    **O custo mora na descrição, e não num campo próprio.** Ele era o campo
    "Ficou para trás", e o cartão terminava dizendo duas vezes a mesma coisa
    da mesma forma ("as salas pagaram; o fecho, não" e, no rodapé, "o que
    atravessou valeu; o que faltava, não"). Essa construção — ponto e vírgula
    com o segundo termo sem verbo — é português escrito formal: uma vez passa,
    duas no mesmo cartão viram maneirismo.

    **Não diz quantos votaram.** Desistir precisa da maioria, e o cartão é o
    desfecho, não a ata: o número do voto interessava enquanto a votação
    estava aberta.
    """
    lugar = f" em **{onde.nome}**" if onde else ""
    quanto = f", na parada {passo} de {incursao.paradas}" if passo else ""
    # Com `perdido` em 0 a frase perde essa metade em vez de dizer "0 de ouro".
    sem = [f"os **{incursao.recompensa_mes} MEs** por participante"]
    if perdido:
        sem.append(f"os **{perdido}** de ouro do fecho")
    e = discord.Embed(
        title=f"🏳️ {titulo_da_incursao(incursao)} — abandonada",
        description=(
            f"O grupo deu meia-volta{lugar}{quanto}. Sai sem "
            + " e sem ".join(sem)
            + ", que dependiam de concluir. O que as salas pagaram, o grupo leva."
        ),
        color=COR_FALHA,
    )
    campo_caminho(e, caminho)
    campo_ouro(e, ouro)
    _campo_pontos(e, lancamentos or [], total_org, incursao.organizacao)
    # A Organizacao entra como COMPLEMENTO, e nao como sujeito. Posta no
    # comeco ela cobrava duas concordancias — "A Alianca" contra "O Vortice",
    # e "as Sentinelas FICAM" contra "a Guilda FICA" — e ainda uma maiuscula
    # no artigo. Assim `com_artigo` resolve tudo numa chamada.
    return _rodape(
        e, f"A notícia chega até {com_artigo(incursao.organizacao)}."
    )


def run_encerrada(
    incursao: Incursao,
    onde: Optional[Sala] = None,
    passo: int = 0,
    lancamentos: Optional[list[dict]] = None,
    total_org: int = 0,
    caminho: Optional[list[tuple[Sala, bool]]] = None,
    ouro: Optional[list[tuple[str, int]]] = None,
    pagou: bool = False,
    vaga_devolvida: bool = False,
) -> discord.Embed:
    """O desfecho de uma run encerrada na mão por quem administra.

    Irmão do `run_desistida`, e separado dele de propósito: ali o grupo
    decidiu, aqui alguém decidiu PELO grupo. O cartão tem de dizer as duas
    coisas que o grupo não escolheu — se o que as salas pagaram ficou, e se a
    vaga da semana voltou —, senão a pergunta sobra para o canal.

    Sem citar quem encerrou: o `/help` marca o comando como de admin, e quem
    usou aparece na mensagem do comando. O cartão é o desfecho da run.
    """
    lugar = f" em **{onde.nome}**" if onde else ""
    quanto = f", na parada {passo} de {incursao.paradas}" if passo else ""
    e = discord.Embed(
        title=f"🛑 {titulo_da_incursao(incursao)} — encerrada",
        description=(
            f"A incursão foi encerrada por quem administra{lugar}{quanto}. "
            + (
                "O que as salas pagaram, o grupo leva."
                if pagou
                else "Nada foi pago: a run sai como se não tivesse acontecido."
            )
            + (
                " A vaga da semana voltou, e o grupo pode entrar em outra."
                if vaga_devolvida
                else " A vaga da semana segue gasta."
            )
        ),
        color=COR_FALHA,
    )
    campo_caminho(e, caminho)
    if pagou:
        campo_ouro(e, ouro)
        _campo_pontos(e, lancamentos or [], total_org, incursao.organizacao)
    return e


def run_concluida(
    incursao: Incursao,
    membros: list[discord.abc.User],
    estado=None,
    lancamentos: Optional[list[dict]] = None,
    total_org: int = 0,
    caminho: Optional[list[tuple[Sala, bool]]] = None,
    ouro: Optional[list[tuple[str, int]]] = None,
) -> discord.Embed:
    """O desfecho da run: vitória, como o grupo saiu, recompensa e pontos."""
    e = discord.Embed(
        title=f"🏆 {titulo_da_incursao(incursao)} — objetivo cumprido",
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
    campo_caminho(e, caminho)
    e.add_field(
        name=f"Recompensa ({incursao.recompensa_mes} MEs por participante)",
        value="\n".join(f"{m.mention} — {incursao.recompensa_mes} MEs" for m in membros),
        inline=False,
    )
    campo_ouro(e, ouro)
    _campo_pontos(e, lancamentos or [], total_org, incursao.organizacao)
    return e


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
    # Posicao em numero, e nao medalha: o placar e de quatro Organizacoes e
    # corre o ano inteiro, entao o ouro-prata-bronze dava ar de podio fechado
    # a uma tabela que muda toda semana.
    posicoes = ("1º", "2º", "3º", "4º")
    for posicao, org in enumerate(ranking):
        valor = pontos.get(org, 0)
        e.add_field(
            name=f"{posicoes[posicao]}  {EMOJI_ORG.get(org, '•')} {org}",
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
