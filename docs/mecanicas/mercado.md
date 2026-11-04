# Mercado

**Este é o segundo sistema de patrimônio do grupo, e não o mesmo.** A planilha do Google guarda o que os personagens carregam na campanha; isto aqui é a economia das Incursões, que começa de zero e vive dentro do bot. Os dois não se falam, de propósito.

## O ouro

| De onde vem | Quanto | Quem paga |
|---|---|---|
| Cada sala superada | 5 × tier | conclusão **e** desistência |
| Sala de **Combate** do caminho | 10 × tier (2× uma sala) | conclusão **e** desistência |
| Concluir a incursão | 20 × tier | só a conclusão |

**A sala de Combate paga dobrado**, e isso é regra de desenho: ela é a única que cobra HP, e o HP não volta entre salas. Enquanto ela pagava igual à de Tesouro, desviar do combate era sempre a jogada certa — e era isso que a mesa fazia, de propósito, para chegar inteira ao objetivo. O objetivo fica fora da dobra: ele não é escolha de ninguém, e quem paga por ele é o bônus de conclusão. O Tesouro que virou emboscada de Mímico também fica fora — a emboscada é castigo por falhar no baú.

**A incursão paga uma vez, no fim.** As salas do caminho não pagam por si: elas ficam registradas, e o fecho conta quantas foram superadas. O que muda é qual fecho paga o quê:

- **Concluída:** paga as salas superadas **e** o bônus de ter fechado.
- **Abandonada** pelo grupo: paga as salas superadas; o bônus do fecho fica para trás, e os MEs também. O grupo atravessou o que atravessou — o que ele não fez foi terminar.
- **Fracassada**, com o grupo inteiro no chão: não paga nada, nem o das salas já atravessadas.

Desistir paga mais que cair, então: é a diferença entre voltar e ser carregado de volta.

**Recebe todo mundo que passou pela run**, e não só quem estava de pé no fim: quem caiu no objetivo e quem foi ejetado por Exaustão no meio do caminho jogaram a incursão e levam o mesmo que os outros. Fica de fora quem desistiu **antes** de ela começar.

Escala por tier porque os preços não escalam: um item lendário custa 900 em qualquer tier, e é o ouro que chega mais rápido lá em cima.

## A vitrine

**6 itens, por personagem, por semana.** Vira na **segunda-feira**, o mesmo dia da vaga de incursão.

Nada disso é guardado: a prateleira é **derivada** de (personagem, semana) por um sorteio semeado. É a mesma escolha que a ficha já faz ao derivar CA e dano da classe em vez de gravá-los — o que é derivado não envelhece. Em troca, o bot não precisa de tabela de estoque, nem de rotina em segundo plano para repor a loja, nem de quem lembre de rodá-la.

É **por personagem**: dois jogadores na mesma semana veem vitrines diferentes.

## Raridade e preço

| Raridade | Preço | Peso no sorteio |
|---|---|---|
| Comum | 80 | 50% |
| Incomum | 180 | 30% |
| Raro | 400 | 15% |
| Lendário | 900 | 5% |

O peso é a fatia do sorteio de **uma** vaga. A prateleira é sorteada sem repetição nas 6 vagas, então a proporção que aparece numa vitrine não é exatamente essa — é para lá que ela tende.

## Os slots

**Cada slot manda num número só.** É daí que vem a contenção: não existe regra de teto nem limite a conferir em tempo de execução — o slot já impede empilhar cinco fontes do mesmo bônus, porque só cabe uma armadura. Equipar um tira o que estava no lugar.

| Slot | Domina | Itens no catálogo |
|---|---|---|
| Armadura | `ca`, `thp_na_cura` | 7 |
| Arma | `acerto`, `dano_extra`, `dano_bonus`, `critico_em` | 7 |
| Botas | `bonus_iniciativa`, `bonus_teste` | 7 |
| Capacete/capa | `bonus_save`, `bonus_save_atributo` | 7 |
| Anel | `ameaca`, `bonus_cura_pct`, `dano_ferido`, `thp_ao_derrubar` | 7 |

`DOMINIO` não é comentário: um teste varre o catálogo e reprova o item que escapar do domínio do slot dele. Sem isso o domínio seria uma intenção — e ele já pegou dois itens errados.

## As poções

Prateleira própria, de **3 vagas**: as 2 de vida estão **sempre** em cartaz, e a terceira é sorteada por semana e por personagem, como a de equipamento. São 50 poções no catálogo.

**Até 3 de cada tipo na bolsa.** É a contenção delas, no lugar do slot: o equipamento é único por personagem porque o slot impede o stack, e a poção empilha — sem um teto, ouro guardado viraria estoque e a incursão longa deixaria de cobrar o HP que ela cobra.

**Beber é a ação da rodada**: quem bebe não ataca. A única exceção é a Poção da Aceleração, que não custa a ação — é disso que ela vive, e não do número de golpes.

| Família | O que faz | X | Preço | Gasta a ação |
|---|---|---|---|---|
| Poção de Vida | Recupera 30% (Menor) ou 50% do HP máximo de quem bebe. | — | 40 · 80 | sim |
| Poção da Aceleração | +X golpes por rodada, e beber não gasta a ação da rodada. | 1 · 2 · 3 | 50 · 100 · 180 | não |
| Poção de Resistência | Corta 2X do dano de cada golpe recebido, depois da resistência. | 1 · 2 · 3 | 50 · 100 · 180 | sim |
| Poção do Dano | +X de dano em cada golpe. | 1 · 2 · 3 | 50 · 100 · 180 | sim |
| Poção de Mana | Devolve um uso já gasto de uma habilidade de tier X. | 1 · 2 · 3 | 80 · 160 · 280 | sim |
| Poção de buff | X stacks de um buff da tabela — uma poção para cada um dos 12. | 1 · 2 · 3 | 50 · 100 · 180 | sim |

As de prazo (Aceleração, Resistência, Dano) valem **3 turnos**, e beber a segunda da mesma família renova a primeira em vez de somar com ela — o efeito é gravado pela família, como as habilidades.

O sorteio da vaga que sobra é **por família** e só depois por poção. As 36 de buff são três quartos do catálogo: sorteando direto, três de cada quatro semanas trariam buff e a de Mana apareceria uma vez por ano.

A de buff empilha uma condição da tabela de buffs (`condicoes.md`), e o nível são os **stacks** — então o prazo dela é o da tabela, que decai 1 por combate, e não os 3 turnos das outras. A de Mana devolve um uso **já gasto** de uma habilidade daquele tier, escolhida por quem bebe; sem nada gasto, ela não é bebida.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/mercado.py`, `src/itens.py`, `src/consumiveis.py`. Não edite à mão: rode o gerador.
