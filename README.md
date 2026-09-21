# Incursões 2.0 — Bot de Discord

Bot de dungeon crawl assíncrono para as Incursões de Sheidrost. Grupos fixos de 5 jogadores
avançam sala a sala votando por botões, resolvendo testes com o modificador real da ficha.
O caminho é sorteado a cada run, de um banco de salas por Organização.

Design completo: `Incursões 2.0 — Bot de Discord (design).md`.

## Estado atual

- [x] **Fase 1** — fichas digitais (vários personagens por jogador, nível, ASI, perícias)
- [x] **Fase 2a** — conteúdo: banco de salas por Organização, incursões com lore, importadores
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
3. Opcional, para que só você possa adicionar o bot — **nesta ordem**, senão o portal recusa:
   aba **Installation** → *Install Context*: apenas **Guild Install**, *Install Link*: **None** → salvar;
   só então aba **Bot** → desligue **Public Bot** → salvar
4. Aba **OAuth2** → **URL Generator** → scopes `bot` + `applications.commands` → permissões:
   *Send Messages*, *Embed Links*, *Attach Files*, *Read Message History*, *Use Slash Commands*
5. Abra a URL gerada e adicione o bot ao seu servidor de testes
6. No Discord, com o Modo Desenvolvedor ligado, clique com o botão direito no servidor → **Copiar ID do servidor** → `GUILD_ID` no `.env`

Não são necessários *privileged intents* (o bot não lê o conteúdo das mensagens).

## Comandos

| Comando | Função |
| --- | --- |
| `/help [comando]` | Lista todos os comandos, com descrição; 🔒 marca os de admin |
| `/ficha registrar` | Cria um personagem: nome, nível, os 6 atributos, CA/ataque/dano/HP e as perícias |
| `/ficha listar [membro]` | Lista todos os personagens de um jogador |
| `/ficha ver [personagem] [membro]` | Mostra a ficha com todos os modificadores calculados |
| `/ficha nivel <n> [personagem]` | Atualiza o nível (proficiência e tier se recalculam sozinhos) |
| `/ficha atributo <attr> <valor> [personagem]` | Atualiza um atributo após um ASI |
| `/ficha pericias [personagem]` | Reabre o seletor de perícias treinadas |
| `/ficha combate <ca> <ataque> <dano> <hp> [personagem]` | Corrige os números de combate |
| `/ficha expertise <perícia> <bônus> [personagem]` | Soma um bônus avulso a uma perícia (0 remove) |
| `/ficha imagem [link] [personagem]` | Associa um retrato ao personagem (sem link, remove) |
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

1. `/incursao entrar <id>` abre o recrutamento no canal, com o gancho da lore. Quem clica em **Entrar** precisa
   ter ao menos um personagem, não estar em outra run e ter cumprido o intervalo desde a
   última incursão.
2. Quem tem mais de um personagem escolhe num menu com qual entra; quem só tem um entra
   direto. O personagem fica preso àquela run: é a ficha dele que rola os testes, ataca e
   leva dano.
3. Ao chegar a 5 jogadores a run começa sozinha; quem abriu pode começar antes com **Começar**.
   Aí o bot posta a **lore de abertura** junto com o grupo — um card por personagem, com
   nível, CA, HP e o retrato de quem tiver — e sorteia o caminho: 3 salas por passo,
   tiradas do banco da Organização.
4. Cada passo mostra as 3 salas sorteadas para ele. Todos votam pelos botões, e a votação fecha
   assim que uma sala junta a **maioria do grupo** (3 de 5) — quem ainda não votou não
   segura o grupo. Enquanto ninguém tem maioria, a votação continua aberta, **sem prazo**:
   a run espera o tempo que precisar. Se todos votarem e der empate (2×2×1), ninguém avança
   até alguém trocar o voto.
5. Na sala, cada jogador rola uma vez pelo botão **Rolar teste**, com a melhor perícia que
   tiver entre as listadas. Quem passa contribui a margem (rolagem + mod − CD) como
   progresso; quem falha contribui 0 e sofre a consequência do tipo da sala.
   A sala encerra quando o alvo é atingido ou quando todos rolaram.
6. Depois de 3, 5 ou 7 salas (conforme o tamanho da incursão), o grupo enfrenta o Objetivo,
   que é sempre um combate. O desfecho vem em dois embeds: um com a vitória, como o grupo
   saiu, os MEs e os pontos de Organização, e outro com a **lore de fecho** — o epílogo só
   existe se o grupo voltar vivo.

Em sala de **Combate**, cada personagem de pé clica em **Atacar** uma vez por rodada
(d20 + bônus de ataque contra a CA do monstro; acertou, rola o dano da arma). Quando
todos atacam, o monstro revida contra um alvo sorteado entre os que estão de pé. Quem
chega a 0 HP fica fora do resto daquele combate.

O combate inteiro acontece **numa mensagem só**: o painel mostra o HP do monstro, o HP de
cada personagem, o log da rodada que acabou e o botão de atacar, e é reescrito a cada
rodada em vez de empilhar mensagens novas. Sala de combate também não posta descrição
antes do painel — ele já traz tudo. Um confronto de dez rodadas ocupa o mesmo espaço no
canal que um de duas.

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

## Avisos no canal

Mexer numa ficha aparece para o grupo: registrar um personagem posta a ficha no canal, e
mudar nível, atributo, perícias, números de combate ou expertise posta uma linha dizendo o
que mudou. Apagar um personagem também avisa. Só a consulta é privada — `/ficha ver` e
`/ficha listar` continuam visíveis apenas para quem pediu.

`/help` monta a lista a partir da própria árvore de comandos do bot, então nunca fica
desatualizada. `/help ficha` filtra por grupo ou por comando.

## Personagens

Cada jogador pode ter vários personagens (até 25) e escolhe qual leva para cada incursão.
Cada um pode ter um **retrato**: `/ficha imagem <link>` guarda a URL, que aparece como
miniatura em `/ficha ver` e no card do personagem na abertura da run. Só `http://` e
`https://` são aceitos — o bot guarda o link, não a imagem, então hospede onde quiser
(inclusive num anexo do próprio Discord, copiando o link da imagem).
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

O balanço (de onde vieram os pontos e quanto a Organização tem agora) vem junto do embed
de desfecho da run, não como mensagem separada. `/organizacao extrato` mostra o histórico,
e `/organizacao ajustar` serve para lançar na mão o que aconteceu na mesa, fora do bot.

**MEs ficam fora do bot.** O embed final mostra quanto cada participante ganhou
(`recompensa_mes` da planilha, 10 por padrão), mas quem registra isso é você, na sua
planilha do Google Sheets — o bot não guarda saldo por jogador.

## Conteúdo: bancos de sala e incursões

O conteúdo vive em dois lugares, e cada um tem sua planilha.

**O banco de salas**, um por Organização, alimenta o sorteio. As salas do meio da
dungeon saem daqui:

```bash
.venv/Scripts/python.exe tools/gerar_modelo_banco.py "Vórtice Oculto"
.venv/Scripts/python.exe tools/importar_banco.py data/planilhas/banco_vortice_oculto.xlsx
```

**A incursão** guarda a lore de abertura, a lore de fecho, o tamanho e a sala final —
nenhuma sala do meio:

```bash
.venv/Scripts/python.exe tools/gerar_modelo_planilha.py minha_incursao.xlsx
.venv/Scripts/python.exe tools/importar_planilha.py minha_incursao.xlsx
```

Os dois modelos já vêm preenchidos com um exemplo jogável: o banco do Vórtice Oculto
(12 salas) e *A Cripta do Vórtice*. Depois de importar, `/incursao recarregar` faz o bot
reler tudo sem reiniciar.

**Quantas salas escrever no banco**: o mínimo é 3 (um passo). Uma dungeon longa tem 7
passos, então 21 salas cobrem uma run inteira sem repetir nenhuma. Com menos que isso o
sorteio reembaralha e pode repetir uma sala em passos diferentes — nunca dentro do mesmo
passo. Uma sala repetida é um desafio novo: as rolagens e o HP do monstro começam do zero
na segunda visita.

Os importadores validam antes de gravar e, se algo estiver errado, listam **todos** os
problemas sem escrever nada. Eles exigem:

- incursão com lore de abertura, tamanho válido (Curta/Média/Longa) e Organização conhecida
- Objetivo sempre do tipo **Combate**, com nome, CA, ataque, dano e HP do monstro
- banco com ao menos 3 salas e `sala_id` único
- salas de Armadilha / Evento / Tesouro com dificuldade, CD, alvo e ao menos uma perícia
- salas de Combate com monstro, e sem CD nem perícia (mecânica própria)
- perícias existentes (com ou sem acento) e pontos não negativos

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
  gerar_modelo_banco.py      cria a planilha do banco de salas de uma Organização
  importar_banco.py          banco -> JSON, com validação
  gerar_modelo_planilha.py   cria a planilha modelo da incursão
  importar_planilha.py       incursão -> JSON, com validação
  simular_combate.py         calibra os números de um combate fora do Discord
data/
  planilhas/    planilhas de autoria das incursões (.xlsx)
  incursoes/    incursões convertidas em JSON — lore, tamanho e sala final
  bancos/       bancos de salas por Organização — o que alimenta o sorteio
assets/         imagens das salas
tests/
  todos.py      roda todas as suítes
  smoke.py      regras, persistência, schema de incursão, carga dos cogs
  test_run.py   uma run inteira simulada, do recrutamento ao objetivo
  test_votacao.py  maioria, votos divididos, empate e restart
  test_combate.py  rodadas, contra-ataque, vitória, derrota total e descanso
  test_pontos.py   crédito de pontos, placar, extrato e ajuste manual
  test_personagens.py  vários personagens, escolha ao entrar e migração do banco
  test_critico_expertise.py  críticos, erro crítico e bônus por perícia
  test_geracao.py  tamanhos, sorteio do caminho e as duas lores
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
