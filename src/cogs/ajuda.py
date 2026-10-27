"""Comando /help: lista todos os comandos do bot, com descricao.

A lista e montada a partir da propria arvore de comandos, entao nunca fica
desatualizada quando um comando novo entra.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import embeds as E

# Emoji de cada grupo, so para o embed respirar.
EMOJI_GRUPO = {
    "ficha": "📜",
    "incursao": "🗺️",
    "mercado": "🪙",
    "organizacao": "🏛️",
    "config": "⚙️",
    "help": "❓",
}

ORDEM_GRUPOS = ("ficha", "incursao", "mercado", "organizacao", "config")

# A ordem de dentro de cada grupo, do essencial para o resto. Alfabetica
# deixava `/ficha listar` antes de `/ficha registrar`, que e o primeiro
# comando que alguem roda na vida. Nome que nao esteja aqui vai para o fim
# do proprio grupo, em ordem alfabetica — comando novo aparece, so nao
# aparece na frente.
ORDEM_COMANDOS = (
    "ficha registrar",
    "ficha imagem",
    "ficha upar",
    "ficha ver",
    "ficha listar",
    "ficha voltar",
    "ficha alterar",
    "incursao entrar",
    "incursao desistir",
    "incursao listar",
    "incursao status",
    "incursao votar",
    "mercado vitrine",
    "mercado comprar",
    "mercado equipar",
    "mercado bolsa",
    "organizacao placar",
    "help",
    # O bloco de admin, no fim e nesta ordem.
    "ficha remover",
    "incursao recarregar",
    "organizacao ajustar",
    "organizacao extrato",
    "config intervalo",
)


def _posicao(nome: str) -> int:
    """Onde o comando entra na lista. Desconhecido vai para o fim."""
    return ORDEM_COMANDOS.index(nome) if nome in ORDEM_COMANDOS else len(ORDEM_COMANDOS)

# O que so quem administra usa sai dos grupos e vai para um campo no fim: o
# jogador que abre o /help nao precisa tropecar neles para achar o que usa.
TITULO_ADMIN = "🔒 Administração"


def _e_admin(comando: app_commands.Command) -> bool:
    """True quando o comando (ou o grupo dele) exige permissao de admin."""
    for alvo in (comando, getattr(comando, "parent", None)):
        if alvo is None:
            continue
        permissoes = getattr(alvo, "default_permissions", None)
        if permissoes is not None and permissoes.value:
            return True
    return False


MAX_PARAMETROS = 4


def _assinatura(comando: app_commands.Command) -> str:
    """Monta `/comando <obrigatorio> [opcional]`.

    Comandos com muitos campos (o registrar tem 12) viram uma linha curta, para
    o embed continuar legivel.
    """
    parametros = list(comando.parameters)
    if len(parametros) > MAX_PARAMETROS:
        primeiros = " ".join(f"<{p.name}>" for p in parametros[:2])
        return f"/{comando.qualified_name} {primeiros} … ({len(parametros)} campos)"
    partes = [f"/{comando.qualified_name}"]
    for p in parametros:
        partes.append(f"<{p.name}>" if p.required else f"[{p.name}]")
    return " ".join(partes)


def coletar(tree: app_commands.CommandTree) -> dict[str, list[tuple]]:
    """Agrupa pelo grupo raiz: {grupo: [(assinatura, descricao, admin, nome)]}.

    A ordem de dentro do grupo e a de `ORDEM_COMANDOS`, do essencial para o
    resto — alfabetica punha `/ficha listar` antes de `/ficha registrar`. O
    nome completo vai no fim da tupla porque e por ele que se ordena.
    """
    grupos: dict[str, list[tuple]] = {}
    for comando in tree.walk_commands():
        if isinstance(comando, app_commands.Group):
            continue
        nome = comando.qualified_name
        grupos.setdefault(nome.split(" ")[0], []).append(
            (
                _assinatura(comando),
                comando.description or "—",
                _e_admin(comando),
                nome,
            )
        )
    for lista in grupos.values():
        lista.sort(key=lambda item: (_posicao(item[3]), item[3]))
    return grupos


class Ajuda(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Lista todos os comandos do bot")
    @app_commands.describe(comando="Filtra por um comando ou grupo (ex.: ficha, incursao)")
    async def help(
        self, interaction: discord.Interaction, comando: Optional[str] = None
    ) -> None:
        grupos = coletar(self.bot.tree)
        filtro = (comando or "").lstrip("/").lower().strip()
        if filtro:
            grupos = {
                nome: [c for c in lista if filtro in c[0].lower()]
                for nome, lista in grupos.items()
                if filtro in nome.lower() or any(filtro in c[0].lower() for c in lista)
            }
            grupos = {nome: lista for nome, lista in grupos.items() if lista}

        if not grupos:
            await interaction.response.send_message(
                f"Nenhum comando parecido com `{comando}`. Use `/help` sem filtro para ver todos.",
                ephemeral=True,
            )
            return

        total = sum(len(lista) for lista in grupos.values())
        admins = sum(1 for lista in grupos.values() for c in lista if c[2])
        e = discord.Embed(
            title="Comandos do bot",
            description=(
                "Tudo o que o bot entende. 🔒 marca o que só quem administra o servidor usa."
            ),
            color=E.COR_INCURSAO,
        )

        ordenados = sorted(
            grupos.items(),
            key=lambda item: (
                ORDEM_GRUPOS.index(item[0]) if item[0] in ORDEM_GRUPOS else len(ORDEM_GRUPOS),
                item[0],
            ),
        )
        def campo(titulo: str, itens: list[tuple]) -> None:
            if not itens:
                return
            linhas = [
                f"{'🔒 ' if admin else ''}`{assinatura}`\n{descricao}"
                for assinatura, descricao, admin, _nome in itens
            ]
            valor = "\n".join(linhas)
            if len(valor) > 1024:  # limite de um campo de embed
                valor = valor[:1000].rsplit("\n", 1)[0] + "\n…"
            e.add_field(name=titulo, value=valor, inline=False)

        # Os de admin saem dos grupos e viram um campo no fim: quem abre o
        # /help para jogar nao precisa tropecar neles para achar o que usa.
        de_admin: list[tuple] = []
        for nome, lista in ordenados:
            de_admin += [c for c in lista if c[2]]
            campo(f"{EMOJI_GRUPO.get(nome, '•')} /{nome}", [c for c in lista if not c[2]])
        de_admin.sort(key=lambda item: (_posicao(item[3]), item[3]))
        campo(TITULO_ADMIN, de_admin)

        e.set_footer(
            text=f"{total} comando(s), {admins} só para administradores · /help <comando> filtra"
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ajuda(bot))
