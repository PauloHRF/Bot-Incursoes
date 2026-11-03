# Tier e progressão

O personagem vai do nível 1 ao 10. Cada tier cobre 2 níveis, então são 5 tiers.

O tier é a unidade de tudo: a tabela da classe, as habilidades novas, a CD das salas e QUEM mora em cada sala de combate todos leem o tier, não o nível. O nível existe para dar dois passos dentro de cada tier.

| Tier | Níveis | Bônus de proficiência | Bônus sem proficiência |
|---|---|---|---|
| T1 | 1–2 | +5 | +3 |
| T2 | 3–4 | +5 | +3 |
| T3 | 5–6 | +7 | +4 |
| T4 | 7–8 | +7 | +4 |
| T5 | 9–10 | +8 | +4 |

Os dois bônus são **iguais em toda classe** — é a progressão da casa, e não um número de classe. O que muda por classe é HP, CA, acerto, dano e quantas perícias ela treina: de 3–7 no tier 5 (ver `docs/FICHAS.md`).

## O que o tier escala

### A CD das salas

A CD escrita no banco é a do tier 1. O tier soma um ajuste que segue o próprio bônus de proficiência, para a chance de passar ficar onde está em toda a faixa:

| Tier | Ajuste de CD | CD 12 no T1 | CD 15 no T1 | CD 18 no T1 |
|---|---|---|---|---|
| T1 | +0 | 12 | 15 | 18 |
| T2 | +2 | 14 | 17 | 20 |
| T3 | +3 | 15 | 18 | 21 |
| T4 | +5 | 17 | 20 | 23 |
| T5 | +6 | 18 | 21 | 24 |

Sem esse ajuste a sala de tier 5 seria trivial, porque o grupo chega lá com o bônus muito maior do que quando a CD foi escrita. Com ele, a taxa de sucesso é idêntica nos cinco tiers.

### As criaturas NÃO escalam

A CD escala porque a perícia do personagem cresce devagar. A criatura não: **a ficha dela vale como está escrita**, e o tier está em QUEM mora na sala. Cada sala de combate tem uma lista por tier (`monstros_por_tier`), e a sala escolhe a do tier da incursão — ou a do maior tier escrito abaixo dele, que é o que faz conteúdo de tier baixo continuar jogável por grupo alto.

Antes havia um multiplicador por tier (1,0 · 1,6 · 2,4 · 3,1 · 3,8 de HP e dano, mais o ajuste da CD em CA e ataque). A conta vinha da curva de HP da família d8 e parecia certa, mas batia em cima de fichas já escritas em força cheia de *Monster Manual*: cinco Gárgulas de 52 HP viravam 416 HP numa sala de tier 2, e as cinco salas de combate de um banco dizimavam o grupo **sempre** — 0% de vitória com o grupo de HP cheio. A mesa sentiu isso antes de a conta mostrar, e passou a evitar combate para chegar inteira ao objetivo.

O bestiário tem 385 criaturas de CR 0 a 20 (ver `CRIATURAS.md`): se uma não serve ao tier, o conteúdo usa outra. Faixa de CR por tier, como `bestiario.tier_do_cr` lê:

| Tier | Faixa de CR |
|---|---|
| T1 | 0 a 1 |
| T2 | 2 a 4 |
| T3 | 5 a 8 |
| T4 | 9 a 13 |
| T5 | 14+ |

A faixa é ponto de partida, não garantia: ela vem do livro, e o que vale é a medição contra a mesa deste bot (`tools/simular_combate.py --tier`). A sala do caminho é calibrada para **cobrar HP sem ameaçar dizimar** — vitória ≥ 95% e 55% a 75% do HP restante —, porque quem decide a run é o objetivo.

## Perícias e resistências

Não há tabela separada para save. Um save **forte** usa o mesmo bônus de uma perícia com proficiência, e um save fraco o de uma perícia sem — o que muda por classe é só quais dois atributos são fortes. Expertise dobra o bônus de proficiência naquela perícia.

Os 6 atributos: FOR, DES, CON, INT, SAB, CAR.

As 18 perícias: Acrobacia, Adestrar Animais, Arcanismo, Atletismo, Atuação, Enganação, Furtividade, História, Intimidação, Intuição, Investigação, Medicina, Natureza, Percepção, Persuasão, Prestidigitação, Religião, Sobrevivência.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/rules.py`, `src/classes.py`. Não edite à mão: rode o gerador.
