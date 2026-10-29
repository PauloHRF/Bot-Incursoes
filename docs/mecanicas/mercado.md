# Mercado

**Este é o segundo sistema de patrimônio do grupo, e não o mesmo.** A planilha do Google guarda o que os personagens carregam na campanha; isto aqui é a economia das Incursões, que começa de zero e vive dentro do bot. Os dois não se falam, de propósito.

## O ouro

| De onde vem | Quanto | Quem paga |
|---|---|---|
| Cada sala superada | 5 × tier | conclusão **e** desistência |
| Concluir a incursão | 20 × tier | só a conclusão |

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

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/mercado.py`, `src/itens.py`. Não edite à mão: rode o gerador.
