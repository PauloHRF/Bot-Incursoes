# Incursões 2.0 — Bot de Discord

Bot de dungeon crawl assíncrono para as Incursões de Sheidrost. Grupos fixos de 5 jogadores
avançam sala a sala votando por botões, resolvendo testes com o modificador real da ficha.

Design completo: `Incursões 2.0 — Bot de Discord (design).md`.

## Estado atual

- [x] **Fase 1** — ficha digital (cadastro, consulta, nível, ASI, perícias, combate)
- [x] **Fase 2a** — formato do conteúdo: planilha da incursão, importador e validação
- [x] **Fase 2b** — runs, salas, votação por botões, testes de perícia
- [ ] **Fase 3** — combate por rodadas (CA / ataque / HP)
- [ ] **Fase 4** — objetivo final e pontuação de Organização
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
| `/ficha registrar` | Cadastra nome, nível, os 6 atributos e as perícias treinadas |
| `/ficha ver [membro]` | Mostra a ficha com todos os modificadores calculados |
| `/ficha nivel <n>` | Atualiza o nível (proficiência e tier se recalculam sozinhos) |
| `/ficha atributo <attr> <valor>` | Atualiza um atributo após um ASI |
| `/ficha pericias` | Reabre o seletor de perícias treinadas |
| `/ficha combate <ca> <ataque> <dano> <hp>` | Define os campos usados nas salas de Combate |
| `/incursao listar` | Mostra as incursões carregadas |
| `/incursao entrar <id>` | Abre o recrutamento de uma incursão no canal |
| `/incursao sala` | Reenvia a mensagem da sala atual |
| `/incursao teste` | Rola o teste da sala (mesmo efeito do botão) |
| `/incursao votar <1-3>` | Vota por comando, se os botões falharem |
| `/incursao status` | Estado da run: linha, sala, quem já rolou |
| `/incursao desistir` | Propõe abandonar a run (precisa de maioria) |
| `/incursao recarregar` | (admin) Relê os JSON de incursão do disco |
| `/config intervalo <dias>` | (admin) Intervalo mínimo entre incursões do mesmo jogador |

## Como uma run acontece

1. `/incursao entrar <id>` abre o recrutamento no canal. Quem clica em **Entrar** precisa
   ter ficha, não estar em outra run e ter cumprido o intervalo desde a última incursão.
2. Ao chegar a 5 jogadores a run começa sozinha; quem abriu pode começar antes com **Começar**.
3. Cada linha mostra as 3 salas daquela linha. Todos votam pelos botões; a votação fecha
   assim que todos votam, ou no prazo (30 min por padrão), pela maioria simples.
   Empate antes do prazo não avança — o grupo destrava trocando um voto. Empate no prazo
   vai a sorteio, e prazo sem nenhum voto mantém a posição e renova.
4. Na sala, cada jogador rola uma vez pelo botão **Rolar teste**, com a melhor perícia que
   tiver entre as listadas. Quem passa contribui a margem (rolagem + mod − CD) como
   progresso; quem falha contribui 0 e sofre a consequência do tipo da sala.
   A sala encerra quando o alvo é atingido ou quando todos rolaram.
5. Depois de três linhas, o grupo chega ao Objetivo.

A run é assíncrona: o estado vive no banco, então o grupo pode levar dias e o bot pode
reiniciar no meio — os botões das mensagens abertas voltam a funcionar sozinhos.

**Para testar à vontade**, rode `/config intervalo 0` uma vez: sem isso, quem entra numa run
fica bloqueado pelos 7 dias de intervalo assim que ela começa. Para recomeçar, encerre a run
atual com `/incursao desistir` (precisa da maioria do grupo) e abra outra com `/incursao entrar`.

**Combate ainda não resolve.** Salas do tipo Combate e o confronto do Objetivo entram na
fase 3; hoje o bot mostra o monstro e o grupo fica parado ali. Para testar o fluxo inteiro,
escolha salas que não sejam de Combate — a incursão de exemplo tem opções sem combate em
todas as três linhas.

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
  cogs/incursao.py  runs: recrutamento, votação, salas, testes
tools/
  gerar_modelo_planilha.py   cria a planilha modelo já preenchida
  importar_planilha.py       planilha -> JSON, com validação
data/
  planilhas/    planilhas de autoria das incursões (.xlsx)
  incursoes/    incursões convertidas em JSON — é o que o bot lê
assets/         imagens das salas
tests/
  todos.py      roda todas as suítes
  smoke.py      regras, persistência, schema de incursão, carga dos cogs
  test_run.py   uma run inteira simulada, do recrutamento ao objetivo
  test_votacao.py  empate, prazo, silêncio e restart
  fakes.py      dublês do Discord usados pelos testes
```

## Pontos a calibrar no playtest

Valores em `src/rules.py` que o documento de design deixou em aberto ou marcou como
ponto de partida:

- `TIERS` — faixas de nível por tier (assumido 1–4 / 5–10 / 11–16 / 17–20)
- `PESO_TIER` — peso de cada tier no alvo do objetivo principal
- `CONSTANTE_OBJETIVO` — o `C` da fórmula do objetivo (design sugere +9 a +10)
