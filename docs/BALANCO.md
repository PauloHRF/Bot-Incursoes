# Rodada de balanceamento

**Este arquivo é gerado.** Ele sai de `tools/balanco.py`, que mede o jogo
rodando o motor de verdade. Para refazer depois de mexer num número:

```
.venv/Scripts/python.exe tools/balanco.py
```

## Como ler

O **dano por rodada** sai de `motor.atacar_inimigo`, 20 mil rolagens por
célula, contra a CA da criatura típica do tier. Não é fórmula: é o que
acontece na mesa, com 1 natural errando e crítico dobrando dados.

A criatura típica sai do bestiário de 385 — a mediana da faixa de CR que
cada tier encontra, não um número escolhido a dedo:

| Tier | CA | Ataque | Dano/rodada |
|---|---|---|---|
| T1 | 12 | +4 | 6 |
| T2 | 13 | +5 | 10 |
| T3 | 15 | +7 | 13 |
| T4 | 17 | +10 | 17 |
| T5 | 19 | +12 | 21 |

Cada classe é medida no seu **teto**: as escolhas de tier são resolvidas
para maximizar o que está sendo medido, porque é o teto que diz se uma
classe está absurda.

O que esta conta **não** sabe medir: reação que socorre um teste falhado,
vantagem, e efeito que não vira HP. Essas aparecem com valor zero e uma
nota — nunca como "fraca".

## Dano por rodada

| Classe | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| Guerreiro | 6.7 | 10.4 | 19.5 | 21.2 | 23.9 |
| Bárbaro | 6.9 | 9.7 | 19.6 | 18.3 | 20.9 |
| Mago | 4.1 | 8.8 | 8.3 | 14.7 | 18.4 |
| Ladino | 7.3 | 10.6 | 12.4 | 14.2 | 16.7 |
| Bruxo | 4.2 | 6.7 | 10.3 | 12.9 | 16.7 |
| Feiticeiro | 4.2 | 8.9 | 8.2 | 11.5 | 15.4 |
| Artífice | 4.1 | 4.4 | 11.6 | 10.9 | 14.7 |
| Xamã | 4.7 | 5.1 | 10.9 | 12.6 | 14.3 |
| Monge | 4.7 | 5.8 | 12.3 | 12.8 | 14.2 |
| Patrulheiro | 5.9 | 7.4 | 14.0 | 14.8 | 12.8 |
| Druida | 3.4 | 5.1 | 8.2 | 10.8 | 10.6 |
| Clérigo | 3.3 | 3.6 | 6.8 | 9.5 | 9.5 |
| Paladino | 6.6 | 9.5 | 8.9 | 8.4 | 9.0 |
| Bardo | 2.6 | 3.6 | 3.4 | 6.3 | 6.3 |

Espalhamento por tier:

| Tier | Piso | Teto | Razão |
|---|---|---|---|
| T1 | 2.6 (Bardo) | 7.3 (Ladino) | 2.8x |
| T2 | 3.6 (Bardo) | 10.6 (Ladino) | 3.0x |
| T3 | 3.4 (Bardo) | 19.6 (Bárbaro) | 5.8x |
| T4 | 6.3 (Bardo) | 21.2 (Guerreiro) | 3.4x |
| T5 | 6.3 (Bardo) | 23.9 (Guerreiro) | 3.8x |

## Durabilidade: rodadas de pé sob a criatura de referência

| Classe | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| Guerreiro | 8.7 | 11.1 | 11.0 | 8.8 | 8.1 |
| Paladino | 8.7 | 9.8 | 9.7 | 8.0 | 7.4 |
| Bárbaro | 7.7 | 8.6 | 8.8 | 7.5 | 7.0 |
| Patrulheiro | 7.0 | 7.8 | 7.8 | 6.6 | 6.1 |
| Clérigo | 6.3 | 7.8 | 7.7 | 6.3 | 5.8 |
| Monge | 6.3 | 6.9 | 6.9 | 5.8 | 5.3 |
| Xamã | 6.3 | 6.9 | 6.9 | 5.8 | 5.3 |
| Artífice | 7.0 | 6.9 | 6.9 | 5.8 | 5.3 |
| Druida | 6.3 | 6.2 | 6.3 | 5.3 | 5.0 |
| Ladino | 5.7 | 6.2 | 5.8 | 5.0 | 4.6 |
| Bruxo | 5.8 | 5.6 | 5.8 | 5.0 | 4.6 |
| Bardo | 5.8 | 5.8 | 5.8 | 4.9 | 4.5 |
| Mago | 4.2 | 4.5 | 4.6 | 4.0 | 3.8 |
| Feiticeiro | 4.2 | 4.5 | 4.6 | 4.0 | 3.8 |

## Cura devolvida ao grupo, por masmorra Média (HP)

**Tier 3:**

| Classe | HP por masmorra |
|---|---|
| Clérigo | 67 |
| Bardo | 45 |
| Guerreiro | 42 |
| Xamã | 22 |
| Paladino | 19 |
| Artífice | 19 |
| Druida | 19 |
| Bruxo | 18 |

**Tier 5:**

| Classe | HP por masmorra |
|---|---|
| Bardo | 254 |
| Druida | 213 |
| Clérigo | 213 |
| Xamã | 73 |
| Guerreiro | 67 |
| Artífice | 65 |
| Paladino | 42 |
| Bruxo | 29 |

## Ameaça: fatia da atenção das criaturas

Num grupo de cinco onde os outros quatro estão no piso (2).

| Classe | Ameaça | Abertura | 5 rodadas, todos batendo |
|---|---|---|---|
| Guerreiro | 6 | 30.2% | 30.2% |
| Paladino | 6 | 30.2% | 30.2% |
| Bárbaro | 5 | 28.3% | 28.3% |
| Monge | 4 | 26.1% | 26.1% |
| Patrulheiro | 3 | 23.4% | 23.4% |
| Clérigo | 3 | 23.4% | 23.4% |
| Artífice | 3 | 23.4% | 23.4% |
| Ladino | 2 | 20.0% | 20.0% |
| Xamã | 2 | 20.0% | 20.0% |
| Mago | 2 | 20.0% | 20.0% |
| Bruxo | 2 | 20.0% | 20.0% |
| Druida | 2 | 20.0% | 20.0% |
| Feiticeiro | 2 | 20.0% | 20.0% |
| Bardo | 2 | 20.0% | 20.0% |

O uniforme seria 20%. A coluna da direita mantém a ordem da abertura:
a ameaça gerada é proporcional à da classe, então acumular não
desmancha o grupo — o que desloca é a AÇÃO. O mesmo clérigo, no mesmo
time, sai de 18.3% batendo para 23.3% curando, porque
cura e área geram o dobro.

## Perícia: melhor modificador por tier

| Classe | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| Ladino | +10 | +12 | +13 | +15 | +21 |
| Druida | +5 | +10 | +11 | +13 | +14 |
| Monge | +5 | +7 | +8 | +12 | +13 |
| Bárbaro | +5 | +7 | +8 | +10 | +11 |
| Guerreiro | +5 | +7 | +8 | +10 | +11 |
| Patrulheiro | +5 | +7 | +8 | +10 | +11 |
| Paladino | +5 | +7 | +8 | +10 | +11 |
| Xamã | +5 | +7 | +8 | +10 | +11 |
| Clérigo | +5 | +7 | +8 | +10 | +11 |
| Artífice | +5 | +7 | +8 | +10 | +11 |
| Mago | +5 | +7 | +8 | +10 | +11 |
| Bruxo | +5 | +7 | +8 | +10 | +11 |
| Feiticeiro | +5 | +7 | +8 | +10 | +11 |
| Bardo | +5 | +7 | +8 | +10 | +11 |

## Habilidades: valor em HP-equivalente por masmorra

Uso × frequência de recarga. `>>` marca o que está acima de 2,5× a
mediana do tier, e `<<` o que está abaixo de 2,5× para baixo.

### Tier 1 — mediana 14 HP-eq, 28 ativas

|  | Classe | Habilidade | Por masmorra | Conta | De onde vem |
|---|---|---|---|---|---|
| >> | Bárbaro | Rage | 46 | 15 × 3.08 | 9 de dano cortado; dano extra enquanto dura |
|  | Feiticeiro | Chromatic Orb | 26 | 18 × 1.42 | 18 de dano |
|  | Feiticeiro | Burning Hands | 23 | 16 × 1.42 | 16 de dano |
|  | Clérigo | Guiding Bolt | 20 | 14 × 1.42 | 14 de dano |
|  | Mago | Thunderwave | 20 | 14 × 1.42 | 14 de dano |
|  | Artífice | Thunderwave | 20 | 14 × 1.42 | 14 de dano |
|  | Guerreiro | Second Wind | 18 | 6 × 3.08 | 6 de cura |
|  | Xamã | Tradicao xamanica — espiritual | 17 | 12 × 1.42 | 6 de cura; 6 de THP |
|  | Mago | Sleep | 17 | 12 × 1.42 | 12 de dano negado (2 turno(s) de criatura) |
|  | Bardo | Charm Person | 17 | 12 × 1.42 | 12 de dano negado (2 turno(s) de criatura) |
|  | Feiticeiro | Dissonant Whispers | 17 | 12 × 1.42 | 6 de dano; 6 de dano negado (1 turno(s) de criatura) |
|  | Bardo | Dissonant Whispers | 17 | 12 × 1.42 | 6 de dano; 6 de dano negado (1 turno(s) de criatura) |
|  | Mago | Magic Missile | 15 | 10 × 1.42 | 10 de dano |
|  | Druida | Wild Shape — Lobo | 14 | 10 × 1.42 | 10 da forma em 3 rodadas |
|  | Bruxo | Arms of Hadar | 11 | 11 × 1.00 | 11 de dano |
|  | Xamã | Tradicao xamanica — marcial | 10 | 7 × 1.42 | 4 de golpe a mais; 4 de THP |
|  | Druida | Wild Shape — Urso | 9 | 7 × 1.42 | 7 da forma em 3 rodadas |
|  | Clérigo | Command | 9 | 6 × 1.42 | 6 de dano negado (1 turno(s) de criatura) |
|  | Paladino | Cura pelas Maos | 8 | 6 × 1.42 | 6 de cura |
|  | Clérigo | Cure Wounds | 8 | 6 × 1.42 | 6 de cura |
|  | Artífice | Cure Wounds | 8 | 6 × 1.42 | 6 de cura |
|  | Druida | Wild Shape — Aranha | 8 | 6 × 1.42 | 6 da forma em 3 rodadas |
|  | Bruxo | Charm Person | 6 | 6 × 1.00 | 6 de dano negado (1 turno(s) de criatura) |
| << | Monge | Flurry of Blows | 6 | 4 × 1.42 | 4 de golpe a mais |
| << | Bardo | Healing Word | 5 | 4 × 1.42 | 4 de cura |
| << | Patrulheiro | Marca do Cacador | 0 | 0 × 3.08 | efeito que esta conta não cobre (reação, vantagem) |
| << | Artífice | Faerie Fire | 0 | 0 × 1.42 | efeito que esta conta não cobre (reação, vantagem) |
| << | Bruxo | Hex | 0 | 0 × 1.00 | efeito que esta conta não cobre (reação, vantagem) |

### Tier 2 — mediana 0 HP-eq, 3 ativas

|  | Classe | Habilidade | Por masmorra | Conta | De onde vem |
|---|---|---|---|---|---|
|  | Bardo | Inspiracao — no ataque | 0 | 0 × 4.26 | efeito que esta conta não cobre (reação, vantagem) |
|  | Bardo | Inspiracao — na resistencia | 0 | 0 × 4.26 | efeito que esta conta não cobre (reação, vantagem) |
|  | Bardo | Inspiracao — na pericia | 0 | 0 × 4.26 | efeito que esta conta não cobre (reação, vantagem) |

### Tier 3 — mediana 39 HP-eq, 25 ativas

|  | Classe | Habilidade | Por masmorra | Conta | De onde vem |
|---|---|---|---|---|---|
| >> | Druida | Call Lightning | 109 | 77 × 1.42 | 77 de dano |
| >> | Xamã | Danca totemica | 103 | 72 × 1.42 | 2 de cura no grupo; 70 de THP |
|  | Bardo | Aid | 96 | 68 × 1.42 | 22 de cura no grupo; 45 de THP |
|  | Mago | Fireball | 92 | 65 × 1.42 | 65 de dano |
|  | Feiticeiro | Lightning Bolt | 92 | 65 × 1.42 | 65 de dano |
|  | Bruxo | Hypnotic Pattern | 78 | 78 × 1.00 | 78 de dano negado (6 turno(s) de criatura) |
|  | Bardo | Hypnotic Pattern | 78 | 78 × 1.00 | 78 de dano negado (6 turno(s) de criatura) |
|  | Bruxo | Hunger of Hadar | 74 | 74 × 1.00 | 35 de dano; 39 de dano negado (3 turno(s) de criatura) |
|  | Clérigo | Mass Healing Word | 48 | 34 × 1.42 | 34 de cura no grupo |
|  | Guerreiro | Action Surge | 43 | 14 × 3.08 | 14 de golpe a mais |
|  | Paladino | Golpe Divino | 42 | 14 × 3.08 | 14 de golpe a mais |
|  | Druida | Conjure Animals | 40 | 28 × 1.42 | 28 de aliado conjurado |
|  | Mago | Hypnotic Pattern | 39 | 39 × 1.00 | 39 de dano negado (3 turno(s) de criatura) |
|  | Clérigo | Hypnotic Pattern | 39 | 39 × 1.00 | 39 de dano negado (3 turno(s) de criatura) |
|  | Feiticeiro | Grilhoes Planares | 39 | 27 × 1.42 | 14 de dano; 14 sangrando |
|  | Mago | Fly | 33 | 23 × 1.42 | 23 de mira desviada |
|  | Feiticeiro | Haste | 28 | 20 × 1.42 | um ataque a mais enquanto dura |
|  | Clérigo | Spirit Guardians | 22 | 22 × 1.00 | 22 de dano |
|  | Druida | Aura of Vitality | 19 | 14 × 1.42 | 14 de regeneração |
|  | Monge | Stunning Strike | 18 | 13 × 1.42 | 13 de dano negado (1 turno(s) de criatura) |
|  | Bruxo | Healing Light | 18 | 18 × 1.00 | 18 de cura |
| << | Bardo | Invisibility | 11 | 8 × 1.42 | 8 de mira desviada |
| << | Patrulheiro | Rajada do Cacador | 7 | 5 × 1.42 | 5 de golpe a mais |
| << | Ladino | Uncanny Dodge | 0 | 0 × 3.08 | efeito que esta conta não cobre (reação, vantagem) |
| << | Bárbaro | Reckless Attack | 0 | 0 × 3.08 | efeito que esta conta não cobre (reação, vantagem) |

### Tier 4 — mediana 0 HP-eq, 6 ativas

|  | Classe | Habilidade | Por masmorra | Conta | De onde vem |
|---|---|---|---|---|---|
| >> | Bárbaro | Relentless | 42 | 14 × 3.08 | 14 de THP |
|  | Druida | Pressagio | 0 | 0 × 1.42 | efeito que esta conta não cobre (reação, vantagem) |
|  | Artífice | Flash of Genius | 0 | 0 × 1.42 | efeito que esta conta não cobre (reação, vantagem) |
|  | Patrulheiro | Sobrevivente — socorro | 0 | 0 × 1.00 | efeito que esta conta não cobre (reação, vantagem) |
|  | Paladino | Lider Sagrado — socorro | 0 | 0 × 1.00 | efeito que esta conta não cobre (reação, vantagem) |
|  | Bruxo | Dark One's Own Luck | 0 | 0 × 1.00 | efeito que esta conta não cobre (reação, vantagem) |

### Tier 5 — mediana 53 HP-eq, 26 ativas

|  | Classe | Habilidade | Por masmorra | Conta | De onde vem |
|---|---|---|---|---|---|
| >> | Druida | Mass Cure Wounds | 181 | 128 × 1.42 | 128 de cura no grupo |
| >> | Clérigo | Mass Cure Wounds | 181 | 128 × 1.42 | 128 de cura no grupo |
| >> | Bardo | Mass Cure Wounds | 181 | 128 × 1.42 | 128 de cura no grupo |
| >> | Mago | Cone of Cold | 158 | 112 × 1.42 | 112 de dano |
| >> | Feiticeiro | Cone of Cold | 158 | 112 × 1.42 | 112 de dano |
|  | Clérigo | Flame Strike | 108 | 108 × 1.00 | 108 de dano |
|  | Mago | Hold Monster | 89 | 63 × 1.42 | 63 de dano negado (3 turno(s) de criatura) |
|  | Bardo | Otto's Irresistible Dance | 89 | 63 × 1.42 | 63 de dano negado (3 turno(s) de criatura) |
|  | Bruxo | Synaptic Static | 87 | 87 × 1.00 | 87 de dano |
|  | Druida | Conjure Elemental | 66 | 46 × 1.42 | 46 de aliado conjurado |
|  | Bruxo | Hold Monster | 63 | 63 × 1.00 | 63 de dano negado (3 turno(s) de criatura) |
|  | Guerreiro | Action Mastery | 57 | 19 × 3.08 | 19 de golpe a mais |
|  | Bardo | Animate Objects | 53 | 38 × 1.42 | 38 de aliado conjurado |
|  | Xamã | Guerreiros ancioes | 36 | 36 × 1.00 | 36 de cura no grupo |
|  | Artífice | Arcane Jolt — restaurador | 34 | 11 × 3.08 | 11 de cura |
|  | Bruxo | Summon Greater Demon | 33 | 33 × 1.00 | 33 de aliado conjurado |
|  | Paladino | Avatar da Luz | 26 | 26 × 1.00 | 11 de regeneração; dano extra enquanto dura |
|  | Feiticeiro | Dimension Door | 24 | 17 × 1.42 | 17 de mira desviada |
|  | Druida | Antilife Shell | 24 | 17 × 1.42 | 17 de mira desviada |
|  | Artífice | Arcane Jolt — destrutivo | 22 | 7 × 3.08 | 7 de golpe a mais |
| << | Feiticeiro | Polymorph | 21 | 15 × 1.42 | 15 da forma em 3 rodadas |
| << | Monge | Perfect Strike | 19 | 6 × 3.08 | 6 de golpe a mais |
| << | Bárbaro | Brutal Strike | 6 | 6 × 1.00 | 6 de golpe a mais |
| << | Patrulheiro | Cacador Supremo | 0 | 0 × 1.42 | efeito que esta conta não cobre (reação, vantagem) |
| << | Mago | Circle of Power | 0 | 0 × 1.42 | efeito que esta conta não cobre (reação, vantagem) |
| << | Clérigo | Dominate Person | 0 | 0 × 1.42 | efeito que esta conta não cobre (reação, vantagem) |

## O escopo de recarga se autocorrige

Por uso, quem recarrega por incursão é o mais forte; multiplicado pela
frequência, os três escopos encostam. Isto é desenho funcionando.

| Escopo | Ativas | Mediana por uso | Usos/masmorra | Mediana por masmorra |
|---|---|---|---|---|
| combate | 8 | 12 | 3.08 | 38 |
| descanso | 47 | 15 | 1.42 | 21 |
| incursao | 16 | 38 | 1.00 | 38 |

### A mesma magia com disponibilidade diferente

Mesmo nome, mesmo efeito, escopo de recarga diferente entre classes:

| Magia | Classe | Tier | Recarga | Usos/masmorra |
|---|---|---|---|---|
| Charm Person | Bardo | T1 | 1x por descanso | 1.42 |
| Charm Person | Bruxo | T1 | 1x por incursao | 1.00 |
| Hold Monster | Mago | T5 | 1x por descanso | 1.42 |
| Hold Monster | Bruxo | T5 | 1x por incursao | 1.00 |

## Tier que não melhora nada ofensivo

Só HP e CA sobem. Como a CA da criatura de referência sobe junto, o
dano por rodada **cai** nessa passagem.

| Classe | Passagem | Acerto (igual) | Dano (igual) |
|---|---|---|---|
| Patrulheiro | T4 → T5 | +11 | 1d8+5 |

## Testes de sala

As 26 salas de teste do conteúdo caem em faixas fechadas, com
CD e alvo de progresso acoplados:

| CD | Alvo de progresso | Salas | Fatia |
|---|---|---|---|
| 12 | 10 | 6 | 23% |
| 15 | 10 | 16 | 62% |
| 18 | 10 | 4 | 15% |

A CD escrita é a do tier 1. A que o grupo rola sobe com o tier, pelo
mesmo passo do bônus de proficiência (`rules.AJUSTE_DE_CD_POR_TIER`),
e é por isso que a chance fica igual nos cinco tiers — uma sala
difícil quer dizer a mesma coisa em qualquer incursão.

Chance de um grupo de cinco superar a sala, cada um rolando uma vez:

| Tier | Mod típico | Base 12 | Base 15 | Base 18 |
|---|---|---|---|---|
| T1 | +5 | CD 12 · 91% | CD 15 · 69% | CD 18 · 29% |
| T2 | +7 | CD 14 · 91% | CD 17 · 69% | CD 20 · 29% |
| T3 | +8 | CD 15 · 91% | CD 18 · 69% | CD 21 · 29% |
| T4 | +10 | CD 17 · 91% | CD 20 · 69% | CD 23 · 29% |
| T5 | +11 | CD 18 · 90% | CD 21 · 69% | CD 24 · 29% |
