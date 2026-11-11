# Simulação e comparação de classes

Os dois comandos usam `tools/simulacao/execucao.py`, que chama os resolvedores
de `src.cogs.incursao`. Iniciativa, ameaça, passivas, reações, usos, condições,
invocações e custo de levantar são os do jogo. A ferramenta escolhe ações;
quem decide seus efeitos continua sendo o bot.

As lutas usam SQLite em memória, não exigem token do Discord nem abrem o
banco de produção. A interface assíncrona do banco é atendida por consultas locais,
sem criar uma thread de banco por luta. As sementes são locais ao contexto;
duas requisições simultâneas do Estúdio não substituem funções globais.

A execução completa custa mais CPU que o modelo anterior de habilidades.
Comece com amostras pequenas; a página e o sugeridor pulam a coleta de
estatísticas detalhadas, mantendo os mesmos combates e resultados de vitória.

## Medir uma sala

```bash
python tools/simular_combate.py data/incursoes/vortice_cripta.json --classe druida --nivel 6 --escolha forma_t1=lobo --repeticoes 100 --semente 42
```

O comando e a função `simular(monstros, tamanho, args, rng)` conservam a
interface usada pelo Estúdio e pelo sugeridor. As medidas agora incluem as
passivas antes ausentes da execução independente. Resultados antigos podem
mudar mesmo sem alterar o balanceamento do jogo.

O comando de auditoria original também continua disponível:

```bash
python tools/simular_balanceamento.py --classe guerreiro --tier 3 --simulacoes 100 --seed 42 --csv resultado.csv
```

Nesse modo são cinco personagens da mesma classe contra uma criatura sorteada
da faixa de CR. Cada classe recebe o mesmo conjunto de encontros e sementes;
o número de ações de uma luta não muda o inimigo da próxima.

## Comparar contribuição ao grupo

```bash
python tools/simular_balanceamento.py --comparar --simulacoes 10 --seed 20261111 --relatorio resultados
python tools/simular_balanceamento.py --comparar --tier 3 --grupos 3 5 --classes guerreiro xama druida --simulacoes 20 --relatorio resultados_t3
```

O candidato ocupa somente a última vaga. Por padrão, os grupos de cinco usam
Guerreiro/Patrulheiro/Mago/Clérigo e Bárbaro/Ladino/Feiticeiro/Xamã nas outras
quatro posições. Os trios usam Guerreiro/Clérigo e Bárbaro/Mago nas duas
primeiras posições. Uma classe pode aparecer mais de uma vez no grupo.

São quatro encontros por tier, com as fichas reais do bestiário e quantidades
explícitas em `tools/simulacao/cenarios.json`. Eles são uma bateria de teste
com pesos iguais; não representam a frequência das salas em produção. Os
níveis são 1, 3, 5, 7 e 9, o primeiro nível de cada tier.

`--simulacoes` é o número **por candidato, grupo-base e encontro**. Uma
comparação completa de 14 classes, cinco tiers, dois grupos-base, quatro
encontros e dez repetições executa 5.600 lutas. Use poucas repetições para
conferir uma configuração e aumente para confirmar diferenças pequenas.

Para definir uma composição específica:

```bash
python tools/simular_balanceamento.py --comparar --grupos 3 --base guerreiro,clerigo --tier 3 --simulacoes 20
```

`--base` pode repetir para testar várias composições do mesmo tamanho. O
candidato não entra na semente; filtrar ou reordenar as classes não altera
os confrontos de quem permanece na comparação.

## Builds e encontros próprios

Um arquivo de builds permite comparar duas escolhas da mesma classe:

```json
{
  "urso": {"classe": "druida", "escolhas": {"forma_t1": "urso"}},
  "lobo": {"classe": "druida", "escolhas": {"forma_t1": "lobo"}}
}
```

```bash
python tools/simular_balanceamento.py --comparar --builds builds.json --simulacoes 20 --relatorio formas
```

As escolhas declaradas substituem as automáticas. Escolhas de tiers futuros
passam a valer quando o tier é alcançado; IDs e opções inexistentes são
recusados antes da primeira luta. O restante da build e a prioridade das
ações vêm de `tools/simulacao/politica.py`. Essa política é determinística,
simples e não representa jogadas ótimas de todos os arquétipos.

Um arquivo de cenários usa as mesmas entradas de criaturas de uma sala:

```json
{
  "3": [
    {"id": "gigantes", "monstros": [{"nome": "Gigante da Pedra", "quantidade": 2}]},
    {"id": "dragao", "monstros": [{"nome": "Dragão Verde Jovem"}]}
  ]
}
```

```bash
python tools/simular_balanceamento.py --comparar --tier 3 --cenarios cenarios.json --simulacoes 20 --relatorio meus_encontros
```

## Resultados e interpretação

`--relatorio PASTA` grava:

- `por_cenario.csv`: resultados por build, tier, composição e encontro,
  incluindo escolhas, sementes, vitórias, HP restante, cura, THP e recursos;
- `resumo.csv`: taxa reunida por build e tamanho de grupo;
- `experimento.json`: configuração, escolhas, hash do código e medidas completas;
- `relatorio.md`: resumo e limites da comparação.

`--csv ARQUIVO` exporta somente a tabela detalhada. Para gerar um gráfico:

```bash
python -m pip install -r requirements-simulacao.txt
python tools/simular_balanceamento.py --comparar --tier 3 --simulacoes 10 --grafico comparacao.png --relatorio resultados
```

As vitórias têm intervalo aproximado de 95% pelo método de Wilson. Esse
intervalo mede variação dos sorteios, não incerteza sobre encontros, builds
ou decisões dos jogadores. Diferenças pequenas pedem mais amostras e outros
grupos-base. O CSV por cenário ajuda a distinguir uma vantagem constante de
um encontro particularmente favorável.

Todos começam com HP e recursos completos, sem equipamento ou poções na
comparação de classes. As medidas são do grupo inteiro. HP restante usa o
HP máximo inicial como referência, inclusive se alguém for ejetado ou
perder HP máximo por condições. Dano é HP efetivamente removido por ação;
overkill fica de fora. Cura e THP medem as variações efetivas por resolução;
não são uma pontuação individual da classe candidata.

Combates sem vencedor no limite de 50 rodadas são contabilizados como não
vitórias e aparecem em `limites`. A auditoria original mantém seu limite de
40 rodadas. Não há rodada extra de ataques ou regeneração depois do limite.

Perícias, equipamentos e desgaste ao atravessar várias salas exigem
experimentos próprios. O medidor do Anel do Mestre reutiliza a mesma
execução, com o anel equipado pelo sistema de inventário real.
