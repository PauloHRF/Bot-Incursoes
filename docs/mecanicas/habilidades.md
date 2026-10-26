# Habilidades: a gramática do catálogo

145 habilidades em 14 classes: 19 passivas, 88 ativas e 38 escolhas. O conteúdo de cada uma está em `docs/FICHAS.md`; aqui está a regra de como elas funcionam.

## A forma de cada classe

Não há uma forma só, e a tabela é gerada do catálogo em vez de afirmada: as classes de magia ganham **três magias para escolher** nos tiers ímpares, e as marciais ganham uma habilidade por tier.

| Classe | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| Artífice | 3 magias + 1 escolha | 1 escolha | 1 escolha | 1 ativa | 2 ativas + 1 passiva |
| Bardo | 3 magias + 1 escolha | 3 magias + 1 escolha | 3 magias + 1 escolha | 1 passiva + 1 escolha | 3 magias + 1 escolha |
| Bruxo | 3 magias + 1 escolha | 1 escolha | 3 magias + 1 escolha | 1 ativa + 1 escolha | 3 magias + 1 escolha |
| Bárbaro | 1 ativa | 1 escolha | 1 ativa + 1 passiva | 1 ativa | 1 ativa |
| Clérigo | 3 magias + 1 escolha | 2 escolhas | 3 magias + 1 escolha | 1 escolha | 3 magias + 1 escolha |
| Druida | 3 magias + 1 escolha | 1 escolha | 3 magias + 1 escolha | 1 ativa + 1 escolha | 3 magias + 1 escolha |
| Feiticeiro | 3 magias + 1 escolha | 1 escolha | 3 magias + 1 escolha | 1 escolha | 3 magias + 1 escolha |
| Guerreiro | 1 ativa | 1 escolha | 1 ativa + 1 passiva | 1 passiva | 1 ativa |
| Ladino | 1 passiva | 1 escolha | 1 ativa | 1 escolha | 1 passiva |
| Mago | 3 magias + 1 escolha | 1 passiva | 3 magias + 1 escolha | 1 escolha | 3 magias + 1 escolha |
| Monge | 1 ativa | 1 passiva | 1 ativa + 1 passiva | 1 passiva | 1 ativa |
| Paladino | 1 ativa | 1 passiva | 1 ativa | 1 ativa + 1 passiva | 1 ativa |
| Patrulheiro | 1 ativa | 1 passiva | 1 ativa + 1 passiva | 1 ativa + 1 passiva | 1 ativa |
| Xamã | 2 ativas | 1 passiva | 1 ativa + 1 escolha | 1 passiva | 1 ativa + 1 passiva |

"escolha" é o que destrava: ela não faz nada sozinha, e o que ela libera aparece como ativa ou passiva depois de o jogador decidir.

## Os três tipos

- **Passiva** — vale sempre, sem clicar. Entra num dicionário de efeitos que o motor lê.
- **Ativa** — o jogador aciona. Tem `usos`, dizendo quantas vezes e com que frequência zera.
- **Escolha** — não faz nada sozinha: destrava outra. `exige_escolha=(escolha, opção)` é o que prende uma ativa (ou outra escolha) atrás de uma decisão do jogador.

## Quando os usos zeram

| Escopo | Zera | Ativas com ele | Usos por masmorra Média |
|---|---|---|---|
| `combate` | a cada sala de combate | 12 | 3,08 |
| `descanso` | a cada sala de Descanso, e no começo da run | 56 | 1,42 |
| `incursao` | uma vez por run | 20 | 1 |

Os números da direita vêm de `tools/balanco.py`, que é quem os mede — importados de lá, e não copiados, para os dois documentos não poderem discordar. É o que torna os escopos comparáveis: uma habilidade `por incursao` precisa bater **3,1x mais forte** que uma `por combate` para valer o mesmo. Ver `docs/BALANCO.md`.

## Como duas fontes do mesmo bônus se juntam

A regra da casa é **`max()`**: duas fontes do mesmo bônus não empilham. Um anel de +2 de acerto e uma passiva de +2 dão +2, não +4.

Três exceções, e cada uma tem motivo:

| Chaves | Como juntam | Por quê |
|---|---|---|
| `bonus_cura_pct` | **somam** | com os dois em 10%, o Especialista do tier 4 não acrescentava nada a quem pegou o Curandeiro do tier 2 — uma escolha que não escolhe |
| `dano_bonus`, `dano_magia`, `dado_inspiracao` | vale o de **maior média** | são dados, e `max()` de string compararia alfabeticamente |
| `critico_em` | vale o **menor** | critar com 19 é melhor que com 20 |

**Chave fora da lista conhecida é descartada em silêncio.** É a pegadinha do módulo: um efeito novo escrito com o nome errado simplesmente não acontece, sem erro nenhum. Por isso existem testes que varrem o catálogo inteiro conferindo os nomes — eles já pegaram três bugs reais que nenhum teste de comportamento pegava.

## As 33 chaves de efeito

Um efeito com qualquer uma destas vale sozinho, sem código novo no cog:

`acerto`, `alvos_extra`, `ameaca`, `ataques`, `aura_save`, `bichinho_cura`, `bonus_cura_pct`, `bonus_iniciativa`, `bonus_pericia`, `bonus_save`, `bonus_save_atributo`, `bonus_sem_treino`, `bonus_teste`, `ca`, `cd_magia`, `critico_em`, `cura_limpa_controle`, `dado_inspiracao`, `dano_bonus`, `dano_extra`, `dano_ferido`, `dano_magia`, `escudo_arcano`, `expertise`, `flash_bonus`, `forma_lunar`, `infusao`, `magia_rapida`, `save_com_desvantagem`, `sequencia`, `thp_ao_derrubar`, `thp_na_cura`, `totem`

## As ações

A `acao` de uma ativa diz o que ela faz. O tipo escolhe o resolvedor:

| Tipo | O que é |
|---|---|
| `golpes` | bate, como o ataque da rodada (é o padrão) |
| `save` | o alvo rola resistência; `alvos: "todos"` é área, `metade: true` reduz no sucesso |
| `cura` | devolve HP, sempre em porcentagem do máximo |
| `grupo` | buff ou cura no grupo inteiro |
| `duracao` | liga um efeito com prazo em rodadas |
| `invocar` | traz um aliado, que entra como combatente comum e age na vez dele |
| `forma` | veste o corpo de outro bicho (Wild Shape, Polymorph) |

## Uma regra que o catálogo não garante sozinho

**Todo dado que a habilidade rola tem de estar escrito no texto dela.** Mudar o dado na `acao` e esquecer o texto passa por toda a suíte, porque a mecânica fica certa e só a promessa ao jogador é que mente — aconteceu com o Cone of Cold, em quatro lugares. Há um conferidor para isso em `tests/test_habilidades.py`.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/habilidades.py`, `src/classes.py`. Não edite à mão: rode o gerador.
