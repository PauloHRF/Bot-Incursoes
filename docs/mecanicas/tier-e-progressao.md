# Tier e progressão

O personagem vai do nível 1 ao 10. Cada tier cobre 2 níveis, então são 5 tiers.

O tier é a unidade de tudo: a tabela da classe, as habilidades novas, a CD das salas e o tamanho das criaturas todos leem o tier, não o nível. O nível existe para dar dois passos dentro de cada tier.

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

### O tamanho das criaturas

A criatura escrita no banco também é a do tier 1, e os bancos são compartilhados entre incursões de tiers diferentes. Corpo e dano crescem pela progressão de HP da família d8; CA, ataque e saves sobem pelo mesmo ajuste da CD, acima.

| Tier | Multiplicador de HP e dano | Ajuste de CA, ataque e saves |
|---|---|---|
| T1 | 1x | +0 |
| T2 | 1,6x | +2 |
| T3 | 2,4x | +3 |
| T4 | 3,1x | +5 |
| T5 | 3,8x | +6 |

**O tier que vale é o do grupo, pela mediana — não o da incursão.** Duas razões, e as duas doem se esquecidas:

- A incursão sem tier declarado vale `TIER_MAXIMO` para dizer "aberta a todos" na hora de entrar. Usar isso para escalar daria criatura de tier 5 em toda incursão aberta.
- Pela mediana, e não pelo maior, porque um personagem de tier baixo pode pegar carona numa incursão alta — e escalar pelo maior esmagaria justamente ele.

## Perícias e resistências

Não há tabela separada para save. Um save **forte** usa o mesmo bônus de uma perícia com proficiência, e um save fraco o de uma perícia sem — o que muda por classe é só quais dois atributos são fortes. Expertise dobra o bônus de proficiência naquela perícia.

Os 6 atributos: FOR, DES, CON, INT, SAB, CAR.

As 18 perícias: Acrobacia, Adestrar Animais, Arcanismo, Atletismo, Atuação, Enganação, Furtividade, História, Intimidação, Intuição, Investigação, Medicina, Natureza, Percepção, Persuasão, Prestidigitação, Religião, Sobrevivência.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/rules.py`, `src/classes.py`. Não edite à mão: rode o gerador.
