# Condições: os buffs e debuffs da incursão

O que uma sala deixa no personagem. O catálogo é transcrição direta da planilha *Incursões — Buffs/Debuffs*: cada linha dela é um par espelhado (Benção/Perdição, Coragem/Medo…).

**Não há escalonamento por tier.** O número escrito vale na faixa inteira.

## Prazo

**Tudo decai 1 stack por combate**, menos as permanentes (Exaustão), que ficam até o fim da incursão a não ser que o Descanso — ou uma habilidade — as tire.

Os tetos: Deterioração em 10, Exaustão em 5. O resto não tem teto.

## O catálogo (25 condições)

Os valores são **o que um stack faz**, com o sinal já dentro.

### Debuffs (12)

|  | Condição | O que um stack faz | Fonte | Decai | Teto |
|---|---|---|---|---|---|
| 🩸 | Deterioração | HP máximo -10% | Armadilha | sim | 10 |
| 💀 | Perdição | ataque -1; saves -1 | Armadilha | sim | — |
| 💫 | Perturbação | testes -1 | Armadilha | sim | — |
| 😨 | Medo | saves -2 | Armadilha | sim | — |
| 🤢 | Envenenado | ataque -1; testes -1 | Armadilha | sim | — |
| 💔 | Debilidade | cura recebida -10% | Armadilha | sim | — |
| 🐌 | Letargia | iniciativa -2 | Armadilha | sim | — |
| 🥀 | Fraqueza | -2 em Atletismo | Evento | sim | — |
| 🤡 | Tolice | -2 em Arcanismo, História, Investigação, Natureza, Religião | Evento | sim | — |
| 🦥 | Moleza | -2 em Acrobacia, Prestidigitação, Furtividade | Evento | sim | — |
| 🙃 | Introversão | -2 em Enganação, Intimidação, Atuação, Persuasão | Evento | sim | — |
| 🌫 | Insensatez | -2 em Intuição, Medicina, Percepção, Sobrevivência | Evento | sim | — |

### Exaustão (1)

|  | Condição | O que um stack faz | Fonte | Decai | Teto |
|---|---|---|---|---|---|
| 🥵 | Exaustão | ataque -2; testes -2; iniciativa -5 | Evento | não | 5 |

A Exaustão é a única condição com tipo próprio, e merece: ela **não decai com o combate**. Sai no Descanso, ou numa habilidade que a tire.

### Buffs (12)

|  | Condição | O que um stack faz | Fonte | Decai | Teto |
|---|---|---|---|---|---|
| 💚 | Sustento | HP máximo +10% | — | sim | — |
| ✨ | Benção | ataque +1; saves +1 | — | sim | — |
| 🧭 | Orientação | testes +1 | — | sim | — |
| 🦁 | Coragem | saves +2 | — | sim | — |
| 💧 | Purificado | ataque +1; testes +1 | — | sim | — |
| 🌿 | Vigor | cura recebida +10% | — | sim | — |
| ⚡ | Rapidez | iniciativa +2 | — | sim | — |
| 💪 | Potência | +2 em Atletismo | — | sim | — |
| 📖 | Esperteza | +2 em Arcanismo, História, Investigação, Natureza, Religião | — | sim | — |
| 💨 | Pressa | +2 em Acrobacia, Prestidigitação, Furtividade | — | sim | — |
| 💬 | Sociável | +2 em Enganação, Intimidação, Atuação, Persuasão | — | sim | — |
| 👀 | Prudência | +2 em Intuição, Medicina, Percepção, Sobrevivência | — | sim | — |

## O teto tira o personagem da incursão

Chegar ao teto de uma condição **tira o personagem da run**, e só as que têm teto fazem isso:

- **Deterioração** no 10º stack, que é -100% do HP máximo
- **Exaustão** no 5º stack

Cair em combate **não** tira ninguém da incursão — isto tira. Esvaziando o grupo assim, a run fracassa.

Quem chegou ao teto sai **antes** do decaimento do combate: na outra ordem, o decaimento tiraria justamente o stack que estourou.

## Grupos de perícia

Vários buffs e debuffs mexem num grupo de perícias, e não em uma:

| Grupo | Perícias |
|---|---|
| Saber | Arcanismo, História, Investigação, Natureza, Religião |
| Atenção | Intuição, Medicina, Percepção, Sobrevivência |
| Social | Enganação, Intimidação, Atuação, Persuasão |
| Agilidade | Acrobacia, Prestidigitação, Furtividade |
| Atletismo | Atletismo |

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/condicoes.py`. Não edite à mão: rode o gerador.
