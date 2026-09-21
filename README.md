# Incursões 2.0 — Bot de Discord

Bot de dungeon crawl assíncrono para as Incursões de Sheidrost. Grupos fixos de 5 jogadores
avançam sala a sala votando por botões, resolvendo testes com o modificador real da ficha.

Design completo: `Incursões 2.0 — Bot de Discord (design).md`.

## Estado atual

- [x] **Fase 1** — fichas digitais (vários personagens por jogador, nível, ASI, perícias)
- [x] **Fase 2a** — formato do conteúdo: planilha da incursão, importador e validação
- [x] **Fase 2b** — runs, salas, votação por botões, testes de perícia
- [x] **Fase 3** — combate por rodadas (CA / ataque / HP)
- [x] **Fase 4** — pontuação de Organização
- [ ] **Fase 5** — hospedagem 24/7

## Rodando localmente

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env    # preencha DISCORD_TOKEN e GUILD_ID
.venv/Scripts/python.exe -m src.main
```

Testes, sem precisar conectar no Discord (regras, banco, schema das incursões e
uma run inteira simulada com dublês do Discord):

```bash
.venv/Scripts/python.exe tests/todos.py
```

## Criando a aplicação no Discord

1. https://discord.com/developers/applications → **New Application**
2. Aba **Bot** → **Reset Token** → copie para `DISCORD_TOKEN` no `.env` (o token some da tela; se perder, é só resetar de novo)
4. Opcional, para que só você possa adicionar o bot — **nesta ordem**, senão o portal recusa:
   aba **Installation** → *Install Context*: apenas **Guild Install**, *Install Link*: **None** → salvar;
   só então aba **Bot** → desligue **Public Bot** → salvar
5. Aba **OAuth2** → **URL Generator** → scopes `bot` + `applications.commands` → permissões:
   *Send Messages*, *Embed Links*, *Attach Files*, *Read Message History*, *Use Slash Commands*
6. Abra a URL gerada e adicione o bot ao seu servidor de testes
6. No Discord, com o Modo Desenvolvedor ligado, clique com o botão direito no servidor → **Copiar ID do servidor** → `GUILD_ID` no `.env`

Não são necessários *privileged intents* (o bot não lê o conteúdo das mensagens).

## Comandos

| Comando | Função |
| --- | --- |
| `/ficha registrar` | Cria um personagem: nome, nível, os 6 atributos, CA/ataque/dano/HP e as perícias |
| `/ficha listar [membro]` | Lista todos os personagens de um jogador |
| `/ficha ver [personagem] [membro]` | Mostra a ficha com todos os modificadores calculados |
| `/ficha nivel <n> [personagem]` | Atualiza o nível (proficiência e tier se recalculam sozinhos) |
| `/ficha atributo <attr> <valor> [personagem]` | Atualiza um atributo após um ASI |
| `/ficha pericias [personagem]` | Reabre o seletor de perícias treinadas |
| `/ficha combate <ca> <ataque> <dano> <hp> [personagem]` | Corrige os números de combate |
| `/ficha expertise <perícia> <bônus> [personagem]` | Soma um bônus avulso a uma perícia (0 remove) |
| `/ficha remover <personagem>` | Apaga um personagem seu |
| `/incursao listar` | Mostra as incursões carregadas |
| `/incursao entrar <id> [personagem]` | Abre o recrutamento de uma incursão no canal |
| `/incursao sala` | Reenvia a mensagem da sala atual |
| `/incursao teste` | Rola o teste da sala (mesmo efeito do botão) |
| `/incursao atacar` | Ataca o monstro da sala (mesmo efeito do botão) |
| `/incursao votar <1-3>` | Vota por comando, se os botões falharem |
| `/incursao status` | Estado da run: linha, sala, quem já rolou |
| `/incursao desistir` | Propõe abandonar a run (precisa de maioria) |
| `/incursao recarregar` | (admin) Relê os JSON de incursão do disco |
| `/organizacao placar` | Pontos das quatro Organizações no servidor |
| `/organizacao extrato [org]` | Últimos lançamentos, com o motivo de cada um |
| `/organizacao ajustar <org> <pontos> <motivo>` | (admin) Lança pontos na mão, para correções |
| `/config intervalo <dias>` | (admin) Intervalo mínimo entre incursões do mesmo jogador |

## Como uma run acontece

1. `/incursao entrar <id>` abre o recrutamento no canal. Quem clica em **Entrar** precisa
   ter ao menos um personagem, não estar em outra run e ter cumprido o intervalo desde a
   última incursão.
2. Quem tem mais de um personagem escolhe num menu com qual entra; quem só tem um entra
   direto. O personagem fica preso àquela run: é a ficha dele que rola os testes, ataca e
   leva dano.
3. Ao chegar a 5 jogadores a run começa sozinha; quem abriu pode começar antes com **Começar**.
4. Cada linha mostra as 3 salas daquela linha. Todos votam pelos botões; a votação fecha
   assim que todos votam, ou no prazo (30 min por padrão), pela maioria simples.
   Empate antes do prazo não avança — o grupo destrava trocando um voto. Empate no prazo
   vai a sorteio, e prazo sem nenhum voto mantém a posição e renova.
5. Na sala, cada jogador rola uma vez pelo botão **Rolar teste**, com a melhor perícia que
   tiver entre as listadas. Quem passa contribui a margem (rolagem + mod − CD) como
   progresso; quem falha contribui 0 e sofre a consequência do tipo da sala.
   A sala encerra quando o alvo é atingido ou quando todos rolaram.
6. Depois de três linhas, o grupo enfrenta o Objetivo, que é sempre um combate.

Em sala de **Combate**, cada personagem de pé clica em **Atacar** uma vez por rodada
(d20 + bônus de ataque contra a CA do monstro; acertou, rola o dano da arma). Quando
todos atacam, o monstro revida contra um alvo sorteado entre os que estão de pé. Quem
chega a 0 HP fica fora do resto daquele combate.

O **20 natural** acerta por mais alta que seja a CA e é crítico: os dados de dano são
rolados em dobro, com o modificador entrando uma vez só (2d6+3 vira 4d6+3). O **1 natural**
erra por maior que seja o bônus. Os dois aparecem marcados no log da rodada — 💥 no crítico
e 💢 no erro crítico — e valem tanto para o grupo quanto para o monstro. O monstro cair supera a sala; o grupo
inteiro cair encerra a run em fracasso. A sala de **Descanso** completa o HP de quem
está machucado e devolve os caídos com metade do HP máximo.

A run é assíncrona: o estado vive no banco, então o grupo pode levar dias e o bot pode
reiniciar no meio — os botões das mensagens abertas voltam a funcionar sozinhos.

**Para testar à vontade**, rode `/config intervalo 0` uma vez: sem isso, quem entra numa run
fica bloqueado pelos 7 dias de intervalo assim que ela começa. Para recomeçar, encerre a run
atual com `/incursao desistir` (precisa da maioria do grupo) e abra outra com `/incursao entrar`.

## Personagens

Cada jogador pode ter vários personagens (até 25) e escolhe qual leva para cada incursão.
Os comandos de ficha aceitam o nome no campo `personagem`, com autocompletar; quem só tem
um personagem pode omitir. Dois personagens do mesmo jogador não podem ter o mesmo nome.

**Os limites continuam sendo do jogador, não do personagem**: o intervalo entre incursões
vale para a pessoa (ter três personagens não dá direito a três incursões por semana), e
ninguém participa de duas runs ao mesmo tempo, nem com personagens diferentes.

Bancos criados antes desta mudança são migrados sozinhos na primeira vez que o bot sobe:
cada ficha vira o primeiro personagem daquele jogador, com atributos, perícias, números de
combate e a data da última incursão preservados.

## Perícias e expertise

O modificador de uma perícia sai de **atributo + proficiência (se treinada) + bônus avulso**.
O bônus avulso é o que `/ficha expertise` define, para cobrir item mágico, talento ou
qualquer outra fonte: `/ficha expertise Furtividade 2` soma +2, e `0` remove. Aceita
negativo, serve para perícia não treinada e vale por personagem, não por jogador.

Esse bônus entra em tudo que usa a perícia, inclusive na escolha automática de qual perícia
o personagem usa no teste da sala — um bônus alto pode fazer outra perícia virar a melhor.

## Pontos de Organização

O placar é **do servidor como um todo**, não de cada jogador: cada incursão credita a
Organização a que pertence. Uma run rende pontos em três momentos:

| Quando | Quanto | Onde se configura |
| --- | --- | --- |
| Sala secundária superada | o valor da sala | coluna `pontos_organizacao`, aba Salas |
| Objetivo cumprido | o maior bônus | campo `pontos_conclusao`, aba Incursao |
| Run levada até o fim | `PONTOS_PARTICIPACAO` (padrão 2) | `.env` |

A participação conta mesmo em derrota — o grupo tentou. Desistir não rende participação,
mas os pontos das salas já superadas ficam. Cada motivo entra no placar uma vez só: a run
guarda o lançamento, então reprocessar uma sala não infla o total.

Ao fim da run o bot posta o balanço: de onde vieram os pontos e quanto a Organização tem
agora. `/organizacao extrato` mostra o histórico, e `/organizacao ajustar` serve para
lançar na mão o que aconteceu na mesa, fora do bot.

**MEs ficam fora do bot.** O embed final mostra quanto cada participante ganhou
(`recompensa_mes` da planilha, 10 por padrão), mas quem registra isso é você, na sua
planilha do Google Sheets — o bot não guarda saldo por jogador.

## Conteúdo das incursões

Cada incursão é escrita numa planilha e convertida para JSON, que é o que o bot lê.

```bash
.venv/Scripts/python.exe tools/gerar_modelo_planilha.py minha_incursao.xlsx
.venv/Scripts/python.exe tools/importar_planilha.py minha_incursao.xlsx
```

O modelo já vem preenchido com uma incursão de exemplo jogável
(`data/planilhas/incursao_exemplo.xlsx` → `data/incursoes/vortice_cripta.json`).
Abas: **Leia-me** (instruções), **Incursao** (metadados), **Salas** (as 10 salas),
**Dificuldades** (CD e alvo por dificuldade — calibre aqui, as salas recalculam)
e **Pericias** (os nomes aceitos).

O importador valida antes de gravar e, se algo estiver errado, lista **todos** os
problemas e não escreve nada. Ele exige:

- exatamente 3 linhas de 3 salas, mais 1 sala de Objetivo
- `pontos_organizacao` e `pontos_conclusao` não negativos (vazio vale 0)
- Objetivo sempre do tipo **Combate**, com nome, CA, ataque, dano e HP do monstro
- salas de Armadilha / Evento / Tesouro com dificuldade, CD, alvo e ao menos uma perícia
- salas de Combate com monstro, e sem CD nem perícia (mecânica própria)
- perícias existentes (com ou sem acento) e `sala_id` único

Serve tanto Excel quanto Google Sheets — neste, baixe em *Arquivo → Fazer download →
Microsoft Excel (.xlsx)* antes de importar.

## Estrutura

```
src/
  main.py       ponto de entrada, carrega cogs e sincroniza comandos
  config.py     leitura do .env
  rules.py      proficiência, modificadores, tiers, tabela de perícias
  database.py   SQLite (aiosqlite) — schema e acesso
  cogs/ficha.py comandos de ficha
  incursoes.py  schema das incursões: salas, monstros, validação, carregamento
  motor.py      regras da run (rolagens, margem, progresso) sem nada de Discord
  embeds.py     montagem das mensagens da run
  cogs/incursao.py  runs: recrutamento, votação, salas, testes, combate
  cogs/organizacao.py  placar, extrato e ajuste de pontos
tools/
  gerar_modelo_planilha.py   cria a planilha modelo já preenchida
  importar_planilha.py       planilha -> JSON, com validação
  simular_combate.py         calibra os números de um combate fora do Discord
data/
  planilhas/    planilhas de autoria das incursões (.xlsx)
  incursoes/    incursões convertidas em JSON — é o que o bot lê
assets/         imagens das salas
tests/
  todos.py      roda todas as suítes
  smoke.py      regras, persistência, schema de incursão, carga dos cogs
  test_run.py   uma run inteira simulada, do recrutamento ao objetivo
  test_votacao.py  empate, prazo, silêncio e restart
  test_combate.py  rodadas, contra-ataque, vitória, derrota total e descanso
  test_pontos.py   crédito de pontos, placar, extrato e ajuste manual
  test_personagens.py  vários personagens, escolha ao entrar e migração do banco
  test_critico_expertise.py  críticos, erro crítico e bônus por perícia
  fakes.py      dublês do Discord usados pelos testes
```

## Pontos a calibrar no playtest

Valores em `src/rules.py` que o documento de design deixou em aberto ou marcou como
ponto de partida:

- `TIERS` — faixas de nível por tier (assumido 1–4 / 5–10 / 11–16 / 17–20)
- `PESO_TIER` — peso de cada tier no alvo do objetivo principal
- `CONSTANTE_OBJETIVO` — o `C` da fórmula do objetivo (design sugere +9 a +10)
- `FRACAO_DESCANSO_CAIDO` em `src/motor.py` — quanto do HP máximo um caído recupera (hoje 1/2)

**O combate está fácil demais com os números atuais.** Simulando 2000 confrontos contra o
Guardião do Selo (CA 16, +7, 2d8+4, 58 HP) com cinco personagens de nível 8 (CA 17, +7,
1d8+4, 60 HP): **100% de vitória, 2,8 rodadas, nenhum caído** — e continua 100% mesmo
reduzindo o grupo a dois personagens ou o HP de cada um a 25. A causa é estrutural: o grupo
desfere cinco ataques por rodada e o monstro devolve um. As alavancas para calibrar são
aumentar muito o HP do chefe (na ordem de 200+), dar mais de um ataque por rodada ao
monstro, ou reduzir o dano dos personagens. Para testar números novos sem
abrir o Discord:

```bash
.venv/Scripts/python.exe tools/simular_combate.py data/incursoes/vortice_cripta.json
```
