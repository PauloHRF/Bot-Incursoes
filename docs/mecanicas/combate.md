# Combate

Resolvido em `src/motor.py`, que é função pura sobre dados simples: não conhece Discord nem banco. É de propósito — as mecânicas podem mudar sem tocar na camada de comandos, e o playtest pode ser simulado (`tools/simular_combate.py`).

## A ordem

Iniciativa é **1d20 + o save de DES**, rolada uma vez quando o combate abre, para todos de uma vez — personagens e criaturas na mesma lista. Quem está na vez age; quando a lista dá a volta, a rodada vira.

## O ataque

**1d20 + acerto** contra a CA do alvo. O acerto e o dano saem da tabela da classe no tier, com o equipamento do mercado já somado.

- **1 natural erra sempre**, qualquer que seja a CA.
- **20 natural acerta sempre, e é crítico.** O crítico dobra os dados de dano, não a constante.
- `critico_em` abaixa o d20 que já conta como crítico — Improved Critical crita com 19.
- `ataques` diz quantos golpes por rodada; Multiattack é a passiva que dá 2.

## A CD das magias do personagem

**8 + o acerto da classe no tier.** Uma conta só, para o jogador não ter de somar nada à mão.

O acerto varia por classe, então a CD também. A faixa em cada tier:

| Tier | Acerto | CD das magias |
|---|---|---|
| T1 | +5–6 | 13–14 |
| T2 | +5–6 | 13–14 |
| T3 | +6–9 | 14–17 |
| T4 | +6–9 | 14–17 |
| T5 | +7–10 | 15–18 |

O número de cada classe está em `docs/FICHAS.md`.

## Os saves das criaturas

A criatura do bestiário traz os saves escritos. A criatura de sala escrita à mão em geral não traz, e aí o bot deduz: **ataque − 3**. Os dois caminhos recebem o ajuste de tier, para o bestiário e o conteúdo escrito à mão não resistirem de formas diferentes.

## Vida temporária (THP)

A THP absorve dano antes do HP, e **empilha**: receber uma nova soma na que já havia, em vez de substituir.

Somar é a regra do Espírito Guardião do xamã — ganhar novos THPs não substitui os antigos, soma-se a eles — e ela vale para todas as fontes porque o xamã ganha THP por gatilho de d20: substituindo, o quarto gatilho da luta não daria nada, e o teto dele ficava em 16 quando o tier 5 pede 20. A habilidade era inalcançável.

Quem está caído não ganha THP — voltar a lutar é outra história.

## Cair

A 0 de HP o personagem cai: perde a vez enquanto estiver no chão e deixa de ser sorteado como alvo. **Não há morte no bot.** O que acaba mal é a incursão: caindo o grupo inteiro, a run encerra em fracasso — e mesmo assim os pontos de participação entram, porque o grupo levou a run até o fim.

**Cura levanta.** Qualquer cura — a apontada em alguém, a que cai no grupo e a que vem por turno — tira do chão quem está a 0, e ele volta com o que a cura deu. A conta é a de sempre, de 0 para cima: nada é somado nem descontado por o alvo estar caído, e a Debilidade corta essa cura como corta as outras. Quem levanta volta a agir na própria vez seguinte.

Isso **não** desfaz uma derrota: caindo o grupo inteiro, o combate encerra antes de a rodada virar, e a cura por turno nem chega a rodar. Vida temporária segue sendo outra história — quem está no chão não ganha THP, porque THP não levanta ninguém.

Fora do combate, quem caiu também volta de pé no Descanso.

## Descanso

As duas metades do Descanso não são a mesma conta:

- Quem está **de pé** recebe uma cura de 50% do HP máximo, somada ao que ele tem. É cura de verdade, então a Maldição da Debilidade a corta como corta qualquer outra.
- Quem **caiu** é posto em 50% do HP máximo e volta a lutar. Não é cura somada, é um valor fixado — e por isso nada o reduz.

O Descanso também zera os usos das habilidades de escopo `descanso` e tira um stack de Exaustão.

O Descanso **não** cura tudo, de propósito: ele cura uma fatia e ainda deixa o grupo escolher o que limpar.

## Cura

**Toda cura do bot é porcentagem do HP máximo, nunca dado.** Um dado fixo encolhe conforme o grupo sobe de tier: 2d8 é metade da vida no tier 1 e um arranhão no tier 5. A porcentagem vale igual na faixa inteira.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/motor.py`, `src/classes.py`. Não edite à mão: rode o gerador.
