# Bestiário

683 criaturas prontas que uma sala pode chamar **só pelo nome**: a sala que diz apenas "Lobo" recebe os números do livro no lugar das colunas vazias.

São duas fontes, lidas juntas por `bestiario.carregar()`:

- `data/bestiario.json`, as 385 do *Monster Manual*, que saíram da tabela de fichas do grupo (`tools/importar_fichas.py`) mais `tools/importar_ambientes.py`;
- `data/criaturas/<livro>.json`, um arquivo por livro de 2024 do 5etools, que sai de `tools/importar_livro.py` — com a tabela fixa de condição e a CD de 12 + ataque para a condição que o livro impõe sem teste.

Cada entrada já vem no formato que a sala lê.

## A busca

Aceita o nome em português e o original em inglês, com ou sem acento.

## O que vem de cada criatura

- CA, HP e os golpes (nome, ataque, dano)
- os saves escritos — e quando faltam, o bot deduz de `ataque − 3`
- o CR, que é como o `BALANCO.md` escolhe a criatura típica de cada tier

**Os números valem como estão escritos.** Nada é multiplicado por tier: a criatura de 52 HP tem 52 HP em qualquer incursão, e o tier está em QUEM a sala chama (ver `tier-e-progressao.md`).

**As fichas em si estão em [../CRIATURAS.md](../CRIATURAS.md)**: as criaturas uma por uma, com CA, HP, golpes por rodada e habilidade, agrupadas pela faixa de CR que decide qual tier as encontra. Aqui está a regra; lá está o conteúdo.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/bestiario.py`, `data/bestiario.json`, `data/criaturas/`. Não edite à mão: rode o gerador.
