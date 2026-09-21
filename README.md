# Incursões 2.0 — Bot de Discord

Bot de dungeon crawl assíncrono para as Incursões de Sheidrost. Grupos fixos de 5 jogadores
avançam sala a sala votando por botões, resolvendo testes com o modificador real da ficha.

Design completo: `Incursões 2.0 — Bot de Discord (design).md`.

## Estado atual

- [x] **Fase 1** — ficha digital (cadastro, consulta, nível, ASI, perícias, combate)
- [ ] **Fase 2** — runs, salas, votação por botões, testes de perícia
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

Teste rápido, sem precisar conectar no Discord:

```bash
.venv/Scripts/python.exe tests/smoke.py
```

## Criando a aplicação no Discord

1. https://discord.com/developers/applications → **New Application**
2. Aba **Bot** → **Reset Token** → copie para `DISCORD_TOKEN` no `.env` (o token some da tela; se perder, é só resetar de novo)
3. Aba **Installation** → *Install link*: **None**. Aba **Bot** → desligue **Public Bot** (só você adiciona o bot)
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

## Estrutura

```
src/
  main.py       ponto de entrada, carrega cogs e sincroniza comandos
  config.py     leitura do .env
  rules.py      proficiência, modificadores, tiers, tabela de perícias
  database.py   SQLite (aiosqlite) — schema e acesso
  cogs/ficha.py comandos de ficha
data/
  incursoes/    definições das incursões em JSON (fase 2)
assets/         imagens das salas
tests/smoke.py  teste de fumaça de regras, persistência e carga dos cogs
```

## Pontos a calibrar no playtest

Valores em `src/rules.py` que o documento de design deixou em aberto ou marcou como
ponto de partida:

- `TIERS` — faixas de nível por tier (assumido 1–4 / 5–10 / 11–16 / 17–20)
- `PESO_TIER` — peso de cada tier no alvo do objetivo principal
- `CONSTANTE_OBJETIVO` — o `C` da fórmula do objetivo (design sugere +9 a +10)
