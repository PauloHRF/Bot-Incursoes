# Incursões e salas

## A forma de uma incursão

Uma incursão guarda a lore de abertura, a lore de fecho, o tamanho e a **sala final**. As salas do meio não são escritas nela: são sorteadas do banco da Organização quando a run começa, então duas runs da mesma incursão percorrem caminhos diferentes.

| Tamanho | Passos até o objetivo |
|---|---|
| Curta | 3 |
| Média | 5 |
| Longa | 7 |

A cada passo o grupo vota entre **3 salas** sorteadas do banco. **Não há prazo:** a run espera indefinidamente, mas não espera quem falta depois que o resultado já está decidido.

A apuração, em ordem:


- Uma opção com **mais da metade do grupo** fecha a votação na hora: não há por que esperar quem ainda não votou.
- Todos tendo votado sem maioria absoluta, **vale a mais votada**.
- Todos tendo votado com **empate**, ninguém avança: o bot pede que alguém troque o voto. Trocar é permitido a qualquer momento.
- Faltando voto e sem maioria ainda, espera — ainda dá para virar.

As 4 Organizações, cada uma com o seu banco de salas: Vórtice Oculto, Aliança das Sombras, Guilda dos Mortos, Sentinelas do Alvorecer.

## Os tipos de sala

| Tipo | Pede teste de perícia? | O que a falha custa |
|---|---|---|
| Combate | não | sofre dano e fica fora do resto do combate |
| Descanso | não | — |
| Armadilha | sim | leva dano e sai com um debuff |
| Evento | sim | carrega uma maldição ou um ponto de Exaustão pelo resto da incursão |
| Tesouro | sim | não leva o item — e pode ter acordado o que dormia no baú |

## A CD de uma sala

Três coisas num lugar só, e as três são regra do bot e não conteúdo:

- A CD escrita no banco é a do tier 1.
- O tier soma o ajuste (ver `tier-e-progressao.md`).
- **Armadilha ganha desconto de 3.**

O desconto da Armadilha é de propósito: passar nela não dá nada, só evita o dano e o debuff. Sem o desconto ela nunca competiria na votação contra um Tesouro.

Com o desconto **e** a regra de que vencer poupa o grupo, a Armadilha é a sala mais branda do caminho — e é para ser: ela é a única que não oferece nada em troca do risco.

As faixas, e o que cada tipo de sala pode receber:

| Tipo de sala | CD 12 | CD 15 | CD 18 | Total |
|---|---|---|---|---|
| Armadilha | 5 | 4 | — | 9 |
| Evento | 1 | 8 | — | 9 |
| Tesouro | — | 4 | 4 | 8 |
| **Todas** | **6** | **16** | **4** | **26** |

São as salas escritas hoje nos 4 bancos, contadas por CD. As três faixas, escritas no tier 1, são 12, 15, 18.

A regra em uma linha, para quem escrever sala nova: **Armadilha nunca é difícil** (já tem desconto, e falhar ali custa dano, não recompensa) e **Tesouro nunca é fácil** (falhar custa o tesouro, que é o motivo de entrar). Evento fica no meio.

## Como se passa numa sala

Cada personagem rola **a melhor perícia que a sala aceita** — o bot escolhe, o jogador não precisa procurar.

O que a sala pede não é um número de acertos: é um `alvo_progresso`, e o progresso é a **soma das margens**. A margem de uma rolagem é quanto ela passou da CD, e nunca é negativa:

```
margem = max(0, d20 + modificador + ajuda - CD)
```

Então falhar não subtrai, só não contribui — e passar com folga carrega quem falhou. É o que faz um grupo de cinco atravessar uma sala em que dois erraram.

A sala para de aceitar rolagens quando o alvo é atingido **ou** quando todos já rolaram. Quem some não trava a run.

Um personagem de fora pode somar na rolagem de outro depois do d20 — é o Flash of Genius do artífice, e ele entra tanto para passar quanto para a margem.

## Combate

Uma sala de combate chama até **6 criaturas**, por nome do bestiário ou escritas na própria sala. Ver `combate.md` e `bestiario.md`.

## Vaga de incursão

Um jogador entra numa incursão a cada **1 semana(s)**, e a conta é feita **pela segunda-feira**, não por 7 dias corridos: quem entrou no sábado joga de novo na segunda, e a semana do grupo inteiro vira junto.

É o mesmo dia em que a vitrine do mercado vira. Dois calendários no mesmo jogo seria pedir confusão.

O intervalo sai da variável de ambiente `INTERVALO_SEMANAS`; em 0 a entrada fica sempre liberada, que é o modo de teste.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/incursoes.py`, `src/motor.py`, `src/mercado.py`. Não edite à mão: rode o gerador.
