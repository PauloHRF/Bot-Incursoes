# Consequências: o que a sala faz com o grupo

`src/consequencias.py` é módulo puro: ele **decide, não grava**. Devolve o nome da condição, o dano ou o prêmio, e quem chama (o cog) é que persiste — é o único que tem banco.

## Por tipo de sala

**A sala é do grupo, nos dois sentidos.** Vencida, não castiga ninguém — nem quem rolou mal. Perdida, castiga **todos que a encararam** — inclusive quem rolou bem. O dado de cada um decide o PROGRESSO da sala; o desfecho dela é do grupo.

Quem encarou a sala é quem **rolou** nela. Uma sala só se perde quando todos os de pé rolaram — é a única forma de uma sala perdida fechar —, e quem está caído não encarou nada: cobrar de quem não pôde rolar seria cobrar duas vezes pela mesma queda.

E é **um sorteio só para o grupo inteiro**: é uma armadilha que disparou, não cinco. O dano continua por cabeça, porque é porcentagem do máximo de cada um.

### Armadilha

- **Grupo venceu:** desarmada. Ninguém se machuca nela, nem quem falhou a própria rolagem.
- **Grupo perdeu:** todos que rolaram levam **−20% do HP máximo** e o **mesmo** debuff de Armadilha, sorteado uma vez.

### Evento

- **Grupo venceu:** um prêmio sorteado. Os 12 buffs do catálogo são sempre candidatos — são o piso. A Cura (+20% do HP) entra no bolo só se alguém estiver machucado, e a Graça só se alguém carregar debuff: não faz sentido oferecer cura a um grupo inteiro nem perdão a um grupo limpo.
- **Grupo perdeu:** todos que rolaram pegam o **mesmo** castigo, sorteado uma vez: um debuff de Evento, ou um ponto de Exaustão.

A Graça tira **um stack de um debuff de alguém** do grupo, sorteado entre todos. Ela não é condição: não tem stack nem prazo, acontece na hora.

### Tesouro

- **Grupo venceu:** o **texto de recompensa escrito na sala** — e não um item do mercado. Os itens de tesouro vivem na planilha do grupo, não no bot; a economia do bot é a do mercado (ver `mercado.md`).
- **Grupo perdeu:** não leva nada — e tem 35% de chance de acordar o que fingia ser um baú. Acordando, **2 Mímicos** entram e a sala vira combate, em vez de devolver o grupo à votação.

### Combate e Descanso

- **Combate** não tem teste de perícia: resolve na iniciativa. Quem cai sofre dano e fica fora do resto do combate.
- **Descanso** não tem como falhar: cura uma fatia e cada um limpa uma condição sua. Ver `combate.md`.

## Os debuffs de cada fonte

O sorteio não é do catálogo inteiro: cada fonte tem a lista dela.

| Fonte | Debuffs sorteáveis |
|---|---|
| Armadilha | Deterioração, Perdição, Perturbação, Medo, Envenenado, Debilidade, Letargia |
| Evento | Fraqueza, Tolice, Moleza, Introversão, Insensatez, Exaustão |

## Sair da incursão

Acumulando stacks até o **teto** de uma condição, o personagem sai da incursão. O teto é por condição, e só as que têm um tiram alguém:

- **Deterioração** no 10º stack, que é -100% do HP máximo
- **Exaustão** no 5º stack

As outras não tiram ninguém, por mais stacks que juntem. É a única coisa que tira alguém de uma run em andamento — **cair em combate não tira**. Esvaziando o grupo assim, a run fracassa.

A ordem importa: quem chegou ao teto sai **antes** do decaimento do combate. Na outra ordem o decaimento tiraria justamente o stack que estourou.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/consequencias.py`, `src/condicoes.py`. Não edite à mão: rode o gerador.
