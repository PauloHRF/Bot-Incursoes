# Combate

Resolvido em `src/motor.py`, que é função pura sobre dados simples: não conhece Discord nem banco. É de propósito — as mecânicas podem mudar sem tocar na camada de comandos, e o playtest pode ser simulado (`tools/simular_combate.py`).

## A ordem

Iniciativa é **1d20 + o save de DES**, rolada uma vez quando o combate abre, para todos de uma vez — personagens e criaturas na mesma lista. Quem está na vez age; quando a lista dá a volta, a rodada vira.

## A ação da rodada

Cada personagem faz **uma** coisa por rodada, e o painel tem os três botões que ela pode ser: **Atacar**, **Habilidade** e **⚗️ Poção**. Escolher qualquer um gasta a rodada — quem bebe não ataca.

Três coisas fogem disso, e as três são a razão de existirem: a **reação** (dispara sozinha no gatilho, sem consumir a vez), o **Quickened Spell** do feiticeiro (a magia sai como ação de bônus e o turno fica livre) e a **Poção da Aceleração** (beber não custa a ação). Ver `mercado.md` para as poções.

## Preparar a ação, e mudar de ideia

Clicar antes da sua vez **guarda** a ação: ela sai quando a iniciativa chegar em você. Isso é o normal, não a exceção — o painel é uma mensagem só para o grupo inteiro, e cada um clica quando vê.

Enquanto a ação está guardada, **clicar de novo troca**. A escolha anterior sai da mesa e a nova entra, e o que a antiga tinha reservado volta: o uso da habilidade, a poção que já havia saído da bolsa. É a mesma devolução de quando a vez não chega (`_devolver_reservas`), pelo mesmo motivo — a ação não aconteceu.

Depois de a ação **sair**, não há o que trocar: dano não se desfaz. Aí o aviso volta a ser o de sempre, dizendo com o que o turno foi gasto.

Isso também é como quem foi substituído retoma a vez: a ação que o grupo escolheu por ele fica guardada como qualquer outra, então ele aparecer e clicar desfaz a do grupo.

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

## A área rola um dado só

O sopro do dragão, a bola de fogo, o estouro que pega a sala inteira: **a rolagem é uma, e todo mundo debaixo dela enfrenta o mesmo número**. O que continua por pessoa é o que é da pessoa — o save, a metade de quem passou, a redução de dano e a vida temporária.

Rolando por alvo, a mesma baforada dava cinco números diferentes, e com cinco alvos a chance de *alguém* tirar perto do máximo virava quase certa: o efeito ficava mais forte só por haver mais gente para acertar. A regra vale nas duas direções — criatura contra o grupo (`motor.usar_habilidade_do_inimigo`) e magia de área contra a sala (`alvos: "todos"`, e o `dano_em_todos` dos Guerreiros Anciões).

**O multiataque é o contrário.** Quando a habilidade rola *ataque* em vez de impor save, cada alvo leva um golpe **seu**, com acerto e dano próprios: ali são vários golpes, não um efeito. O mesmo vale para o alvo extra do feiticeiro, que é uma segunda conjuração de uma magia de alvo único.

## As marcas do painel

Ao lado do HP, o painel acende o que está **ligado** naquele personagem — e os dois estados que tiram alguém da rodada:

- 🛡️ **Protegido** — O dano que chega está sendo cortado.
- 🎯 **Com vantagem** — Os ataques dele saem com vantagem.
- 💠 **Abençoado** — CA a mais, ou cura chegando a cada turno.
- ❗ **Chamando atenção** — Uma habilidade ligada está puxando a atenção dos inimigos.
- ⚰️ **Caído** — Está no chão: fora do combate até alguém levantar com uma cura.
- 😵 **Atordoado** — Perde a vez desta rodada.
- ☠️ **Abatida** — a criatura caiu, e ela não volta.

Nenhuma dessas marcas repete ícone de condição (`condicoes.md`), porque as duas famílias dividem a **mesma linha**. Três repetiam, e o jogador lia a coisa errada sem ter como saber: quem cedeu foram as marcas, porque as condições são o vocabulário da planilha. `/incursao buffs` é a legenda do que estiver aceso na hora.

## Vida temporária (THP)

A THP absorve dano antes do HP, e **empilha**: receber uma nova soma na que já havia, em vez de substituir.

Somar é a regra do Espírito Guardião do xamã — ganhar novos THPs não substitui os antigos, soma-se a eles — e ela vale para todas as fontes porque o xamã ganha THP por gatilho de d20: substituindo, o quarto gatilho da luta não daria nada, e o teto dele ficava em 16 quando o tier 5 pede 20. A habilidade era inalcançável.

Quem está caído não ganha THP — voltar a lutar é outra história.

## Cair

A 0 de HP o personagem cai: perde a vez enquanto estiver no chão e deixa de ser sorteado como alvo. **Não há morte no bot.** O que acaba mal é a incursão: caindo o grupo inteiro, a run encerra em fracasso — e mesmo assim os pontos de participação entram, porque o grupo levou a run até o fim.

**Cura levanta.** Qualquer cura — a apontada em alguém, a que cai no grupo e a que vem por turno — tira do chão quem está a 0, e ele volta com o que a cura deu. A conta é a de sempre, de 0 para cima: nada é somado nem descontado por o alvo estar caído, e a Debilidade corta essa cura como corta as outras. Quem levanta volta a agir na própria vez seguinte.

**E voltar do chão custa 1 ponto de Exaustão.** O preço é de sair do zero, não da cura: cobra igual nas três, inclusive na regeneração por turno, que levanta sem ninguém decidir. Curar quem está de pé não cobra nada.

A Exaustão **não decai com o combate** — só o descanso tira, um ponto por descanso — e com 5 pontos o personagem sai da incursão. Então o custo acumula: cair e voltar várias vezes numa incursão é o caminho mais rápido para ficar fora dela, e segurar o aliado de pé vale mais que levantá-lo depois.

Isso **não** desfaz uma derrota: caindo o grupo inteiro, o combate encerra antes de a rodada virar, e a cura por turno nem chega a rodar. Vida temporária segue sendo outra história — quem está no chão não ganha THP, porque THP não levanta ninguém.

Fora do combate, quem caiu também volta de pé no Descanso.

## Descanso

As duas metades do Descanso não são a mesma conta:

- Quem está **de pé** recebe uma cura de 50% do HP máximo, somada ao que ele tem. É cura de verdade, então a Maldição da Debilidade a corta como corta qualquer outra.
- Quem **caiu** é posto em 50% do HP máximo e volta a lutar. Não é cura somada, é um valor fixado — e por isso nada o reduz.

O Descanso também zera os usos das habilidades de escopo `descanso` e tira um stack de Exaustão.

O Descanso **não** cura tudo, de propósito: ele cura uma fatia e ainda deixa o grupo escolher o que limpar.

### Onde o descanso acontece

O descanso é **parada fixa do caminho**, pelo tamanho da incursão, e não sala sorteada. Ele chega **sem votação**: é sempre a mesma coisa, e escolher entre três cópias dela não é escolher. Os botões de limpeza continuam, porque a limpeza é de cada um — e é a única saída da Exaustão.

| Tamanho | Paradas de descanso |
|---|---|
| Curta | nenhuma |
| Média | 4ª — descanso fixo |
| Longa | 4ª — descanso fixo, 8ª — a Última Vigília |

## A Última Vigília

A segunda parada da Longa, depois da sexta sala, não é o descanso fixo: é uma **escolha**. Falta uma sala para o objetivo, e o grupo decide o que gasta para chegar nela. São **3 trocas** sorteadas de um catálogo de 6, votadas pela maioria como uma sala — a troca vence para o grupo inteiro, não para quem votou.

Toda troca cura mais que o descanso fixo e cobra por isso. A moeda cara é a **Exaustão**: ela não decai com o combate, só sai no descanso fixo, e em 5 pontos tira o personagem da incursão — e a vigília acontece quando falta uma sala.

| Troca | Cura | O que cobra | O que dá além da cura |
|---|---|---|---|
| Recuperar o fôlego | 20% + 10% de THP | nada | — |
| Forçar a marcha | 40% | 1 ponto de Exaustão em cada um | — |
| Queimar as reservas | 50% | 2 pontos de Exaustão em cada um | — |
| Lavar as feridas | 10% | nada | tira **todo debuff** do grupo |
| Revirar o lugar | 15% | nada | paga o ouro de **uma sala** |
| Velar os mortos | — | nada | dá **um buff** ao grupo inteiro |

Três delas não cobram: pagam de outro jeito. **Lavar as feridas** cura pouco e tira todo debuff do grupo (a Exaustão não é debuff e fica); **revirar o lugar** cura pouco e paga o ouro de uma sala, porque o grupo procurou em vez de dormir; **velar os mortos** não cura ninguém e dá ao grupo inteiro um buff da tabela.

A vigília **conta como descanso** para as habilidades de escopo `descanso`, e **não** conta como sala superada: descansar não é vencer nada, e o ouro das salas é por sala vencida.

## Cura

**Toda cura do bot é porcentagem do HP máximo, nunca dado.** Um dado fixo encolhe conforme o grupo sobe de tier: 2d8 é metade da vida no tier 1 e um arranhão no tier 5. A porcentagem vale igual na faixa inteira.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/motor.py`, `src/classes.py`. Não edite à mão: rode o gerador.
