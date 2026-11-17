"""O que o jogador vê quando o bot quebra no meio de um clique.

Sem isto, a exceção de um comando ou de um botão ia só para o log — o
discord.py registra e segue — e o jogador ficava com a tela que sobrasse:
"o aplicativo não respondeu", ou, depois de um `defer`, o "pensando..."
pendurado para sempre, sem saber se o clique valeu, se deve clicar de novo ou
se a mesa travou.

Duas portas, e as duas terminam em `avisar`: o tratador da árvore de comandos
(`main.IncursoesBot`) e o `on_error` de `ViewDoBot`, a base de toda view do
bot. Comando de barra e botão quebram por caminhos diferentes no discord.py,
e só cobrir um deixaria metade dos cliques no escuro.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import discord

log = logging.getLogger("incursoes.falha")

# Não promete o que não sabe. O erro pode ter vindo antes de qualquer coisa
# ser gravada ou depois de metade dela — dizer "nada aconteceu" seria mentir
# em parte das vezes. O que é certo é que ficou registrado.
AVISO = (
    "⚠️ Algo deu errado do lado do bot, e o erro ficou registrado. "
    "Se a mesa parou de andar, avise quem administra."
)


def _onde(interaction: discord.Interaction, item: Optional[Any]) -> str:
    """Uma linha para o log dizer de qual clique veio a falha."""
    comando = getattr(interaction, "command", None)
    if comando is not None:
        return f"/{getattr(comando, 'qualified_name', comando)}"
    custom_id = getattr(item, "custom_id", None)
    if custom_id:
        return f"componente {custom_id}"
    return type(item).__name__ if item is not None else "interação"


async def avisar(
    interaction: discord.Interaction, erro: BaseException, item: Optional[Any] = None
) -> None:
    """Registra a falha e fecha a interação com o aviso, pela porta que sobrar.

    Três estados possíveis, e cada um tem a sua porta:

    - **sem resposta ainda** — responde, em privado;
    - **adiada com "pensando..."** (`deferred_channel_message`) — o aviso
      preenche o próprio "pensando...", que senão ficaria lá para sempre;
    - **já respondida de outro jeito** — inclusive o `defer` de botão que
      edita o cartão, onde preencher a original escreveria o erro em cima do
      painel do grupo — vai num followup privado.

    Falhar ao avisar não pode virar uma segunda exceção: quem chama é o
    tratador de erro, e não há mais ninguém depois dele.
    """
    original = getattr(erro, "original", None) or erro
    usuario = getattr(getattr(interaction, "user", None), "id", None)
    log.error(
        "falha em %s (usuário %s, canal %s)",
        _onde(interaction, item), usuario, getattr(interaction, "channel_id", None),
        exc_info=(type(original), original, original.__traceback__),
    )
    resposta = interaction.response
    try:
        if not resposta.is_done():
            await resposta.send_message(AVISO, ephemeral=True)
        elif getattr(resposta, "type", None) == (
            discord.InteractionResponseType.deferred_channel_message
        ):
            await interaction.edit_original_response(content=AVISO, embed=None, view=None)
        else:
            await interaction.followup.send(AVISO, ephemeral=True)
    except discord.HTTPException:
        # O token venceu (15 min), ou o Discord recusou: o log ja tem tudo.
        pass


class ViewDoBot(discord.ui.View):
    """A base de toda view do bot: um botão que quebra fecha a interação.

    O `on_error` padrão do discord.py só registra. Sem nada mais, o clique
    que quebrava deixava o jogador com "esta interação falhou" — ou com o
    "pensando..." eterno, nos botões que adiam a resposta.
    """

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: Any, /
    ) -> None:
        await avisar(interaction, error, item)
