# Bestiário

385 criaturas prontas que uma sala pode chamar **só pelo nome**: a sala que diz apenas "Lobo" recebe os números do livro no lugar das colunas vazias.

O arquivo `data/bestiario.json` sai de `tools/importar_bestiario.py`, que lê o Monster Manual no formato do 5etools e padroniza o que o bot entende. Cada entrada já vem no formato que a sala lê.

## A busca

Aceita o nome em português e o original em inglês, com ou sem acento.

## O que vem de cada criatura

- CA, HP e os golpes (nome, ataque, dano)
- os saves escritos — e quando faltam, o bot deduz de `ataque − 3`
- o CR, que é como o `BALANCO.md` escolhe a criatura típica de cada tier

Os números do livro são os do tier 1, como todo conteúdo: a escala por tier do grupo é aplicada na hora de abrir o combate (ver `tier-e-progressao.md`).

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/bestiario.py`, `data/bestiario.json`. Não edite à mão: rode o gerador.
