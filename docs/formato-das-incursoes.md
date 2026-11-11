# Como escrever uma incursão

Este é o formato que o bot lê hoje. Quem escreve conteúdo escreve **JSON**, e a
régua é o validador do próprio bot — passar nele é passar no bot, não há uma
segunda conferência escondida.

Antes de mandar o arquivo, rode:

```bash
python tools/validar_conteudo.py minha_dungeon.json
```

Isso **não é formalidade**. O bot carrega arquivo por arquivo e pula o
inválido: o resto do catálogo sobe, e a **sua** dungeon é a que não existe. O
aviso sai no log do servidor e na resposta do `/incursao recarregar` — os dois
longe de você. Sem validar antes, você descobre pelo silêncio.

(Já foi pior: um erro de vírgula derrubava o catálogo inteiro, porque o bot
abortava no primeiro arquivo ruim e subia sem incursão nenhuma.)

---

## A primeira coisa a entender: a dungeon não contém as salas dela

São **dois arquivos**, com dois papéis:

| Arquivo | O que é | Quem usa |
| --- | --- | --- |
| `data/incursoes/qualquer_nome.json` | **Uma** incursão: lore, tamanho, tier e a **sala final** | só ela |
| `data/bancos/<organizacao>.json` | O **banco de salas** de uma Organização | todas as incursões dela |

O caminho até o objetivo é **sorteado** do banco da Organização: a cada parada
o grupo recebe **3 salas** para votar, tiradas dali. O arquivo da incursão não
lista as salas do caminho e não escolhe a ordem delas — ele diz quantas paradas
existem (pelo `tamanho`) e o que espera no fim (`objetivo`).

Então há duas coisas diferentes que alguém pode querer escrever:

- **uma incursão nova** numa Organização que já existe → escreva só o arquivo
  de `data/incursoes/`, e ela já sorteia do banco que está lá;
- **salas novas** → elas entram no banco da Organização, e passam a aparecer em
  **todas** as incursões dela.

O nome do arquivo não importa para o bot: a incursão é identificada pelo `id`
de dentro, e o banco pela `organizacao` de dentro. Os nomes atuais são
convenção (`vortice_cripta.json`, `vortice_oculto.json`).

---

## O arquivo da incursão

Exemplo mínimo que carrega — tudo que não está aqui é opcional:

```json
{
  "id": "vortice_agulha",
  "nome": "A Agulha do Vórtice",
  "organizacao": "Vórtice Oculto",
  "tamanho": "Média",
  "tier": 3,
  "lore_inicial": "O que o grupo lê quando a incursão abre.",
  "recompensa_mes": 10,
  "objetivo": {
    "id": "OBJ",
    "nome": "O Coração da Agulha",
    "tipo": "Combate",
    "descricao": "O que o grupo lê ao chegar na sala final.",
    "monstros": [{ "nome": "Behir" }]
  }
}
```

| Campo | Obrigatório | O que aceita |
| --- | --- | --- |
| `id` | **sim** | só minúsculas, números e `_`. É o id que os comandos usam |
| `nome` | **sim** | texto livre |
| `organizacao` | **sim** | uma das quatro (abaixo) |
| `lore_inicial` | **sim** | texto; use `\n\n` para separar parágrafos |
| `recompensa_mes` | **sim** | número ≥ 0: MEs por participante ao concluir |
| `objetivo` | **sim** | uma sala, e ela tem de ser do tipo `Combate` |
| `tamanho` | não (`Média`) | `Curta` (3 salas), `Média` (5), `Longa` (7) |
| `tier` | não (`5`) | 1 a 5. O tier N aceita até o nível 2N |
| `lore_final` | não | o epílogo, lido quando o grupo conclui |
| `pontos_conclusao` | não (`10`) | pontos para a Organização ao concluir |
| `imagem_capa` | não | URL da imagem do cartão de abertura |
| `filtro` | não | quais salas do banco esta incursão sorteia (abaixo) |

### `filtro` — escolher as salas do caminho

Sem o campo, a incursão sorteia o banco inteiro. Com ele, três etapas nesta
ordem:

```json
"filtro": {
  "temas": ["cripta", "arcano"],
  "excluir": ["VO12"]
}
```

| Campo | O que faz |
| --- | --- |
| `temas` | a sala entra se tiver **qualquer** um deles. É OU, não E |
| `incluir` | quando existe, **ele é o pool** — e `temas` não vale junto |
| `excluir` | tira as listadas, sempre por último, inclusive de `incluir` |

**O filtro precisa deixar sala suficiente, e isso é recusa e não aviso.** O
sorteio nunca repete sala: uma Longa atravessa 7, então o pool filtrado precisa
de 7 para a run poder terminar e de 9 para oferecer 3 portas em toda parada.
Abaixo de 7 o arquivo é recusado — e se entrar em `data/` assim mesmo, o bot
tira a dungeon do catálogo em vez de deixá-la travar na parada 4 com o grupo
dentro. Entre 7 e 8 passa com aviso: dungeon apertada de propósito é decisão
sua.

| tamanho | para terminar | para 3 portas sempre |
| --- | --- | --- |
| `Curta` | 3 | 5 |
| `Média` | 5 | 7 |
| `Longa` | 7 | 9 |

Essa conta é a **única** que precisa dos dois arquivos ao mesmo tempo, então
ela só aparece quando o banco da Organização está junto: rodando o validador
na pasta, ou com o arquivo já em `data/`.

Uma armadilha que o validador avisa: **sala sem tema escrito entra em qualquer
filtro.** Num banco ainda não etiquetado, `"temas": ["cripta"]` não tira nada —
o filtro parece funcionar e não filtra. `python tools/relatorio_de_pool.py`
mostra quantas salas de cada tema existem de verdade.

As quatro Organizações: **Vórtice Oculto**, **Aliança das Sombras**, **Guilda
dos Mortos**, **Sentinelas do Alvorecer**. Acento e maiúscula não importam na
hora de escrever — `vortice oculto` é aceito —, mas a Organização tem de ser
uma dessas quatro, porque é ela que diz de qual banco as salas vêm.

Sobre `tier`: sem ele a incursão vale `5`, que é o tier mais alto, e aí ninguém
fica de fora — qualquer nível pode entrar. Com `tier: 3`, só personagens até o
nível 6.

Sobre `tamanho`, e isto importa para escrever a lore: o número de salas **não**
é o número de paradas. O descanso é parada do caminho, e entra sozinho:

| `tamanho` | salas | paradas no total | descansos |
| --- | --- | --- | --- |
| `Curta` | 3 | 3 | nenhum |
| `Média` | 5 | 6 | um normal, depois da 3ª sala |
| `Longa` | 7 | 9 | um normal e uma Última Vigília |

---

## A sala

A mesma estrutura serve para o `objetivo` da incursão e para cada item de
`salas` no banco.

```json
{
  "id": "VO07",
  "nome": "A Ponte de Vidro",
  "tipo": "Armadilha",
  "descricao": "O que o grupo lê ao entrar.",
  "dificuldade": "Média",
  "cd": 13,
  "alvo_progresso": 8,
  "pericias": ["Acrobacia", "Percepção"],
  "temas": ["fortaleza", "arcano"],
  "pontos_organizacao": 2
}
```

| Campo | Obrigatório | O que aceita |
| --- | --- | --- |
| `id` | **sim** | texto; **único** dentro do banco |
| `nome` | **sim** | texto livre |
| `tipo` | **sim** | `Combate`, `Armadilha`, `Evento`, `Tesouro` |
| `descricao` | **sim** | o texto que o grupo lê |
| `dificuldade` | sim, se tem teste | `Fácil`, `Média`, `Difícil` |
| `cd` | sim, se tem teste | número: a CD **no tier 1** (ver abaixo) |
| `alvo_progresso` | sim, se tem teste | número > 0: a soma de margens que vence a sala |
| `pericias` | sim, se tem teste | uma ou mais das 18 (abaixo). Cada jogador rola a melhor que tiver |
| `temas` | não | em que lugares a sala cabe (abaixo). Vazio = cabe em qualquer um |
| `monstros` | sim, se `Combate` | lista de criaturas, no máximo 6 |
| `monstros_por_tier` | alternativa | `{"2": [...], "4": [...]}` |
| `monstros_por_tema` | não | o bando que cada tema encontra (abaixo) |
| `pontos_organizacao` | não (`0`) | pontos ao vencer esta sala |
| `recompensa` | não | texto solto, só mostrado no cartão |
| `imagem` | não | URL |

"Tem teste" são os tipos **Armadilha**, **Evento** e **Tesouro**: a sala se
resolve por rolagem de perícia. `Combate` se resolve na pancada e não usa
`cd`/`pericias`. E **só `Combate` tem criatura** — pôr `monstros` numa sala de
Evento é erro, não enfeite.

As 18 perícias: Acrobacia, Adestrar Animais, Arcanismo, Atletismo, Atuação,
Enganação, Furtividade, História, Intimidação, Intuição, Investigação,
Medicina, Natureza, Percepção, Persuasão, Prestidigitação, Religião,
Sobrevivência.

### Três regras do bot que mudam o que você escreve

**A CD que você escreve é a do tier 1.** O bot soma o ajuste do tier do grupo
por cima. Não escreva "CD 18 porque é tier 5" — escreva a CD como se fosse
tier 1, e o bot sobe. Armadilha ainda ganha **−3** de desconto, de propósito:
passar nela não dá nada, só evita o dano e o debuff, então sem o desconto ela
nunca ganharia uma votação.

**Criatura não é escalada por tier.** O que está escrito na ficha vale como
está — nada é multiplicado. Se a criatura não serve ao tier, use outra (o
bestiário tem 385, de CR 0 a 20) ou escreva `monstros_por_tier`. Já existiu um
multiplicador aqui, e ele transformava cinco Gárgulas de 52 HP em 416 HP numa
sala de tier 2.

**O banco precisa de exatamente uma sala de `Descanso`, e ela não é
sorteada.** O descanso virou parada fixa do caminho, mas a ficção dessa parada
é a sala de Descanso do banco — a Cela do Coveiro da Guilda, a Adega Falsa das
Sombras. Banco sem nenhuma faz o grupo chegar na parada e **seguir sem
descansar**, perdendo a única cura garantida da Média. Da segunda em diante só
a primeira é usada, então escreva uma só. O validador avisa nos dois casos.

### `temas` — em que lugares a sala cabe

Oito temas, e **só estes oito**: `urbano`, `cripta`, `fortaleza`, `arcano`,
`sagrado`, `natureza`, `agua`, `escuridao`. Tema que não está na lista é
recusado pelo validador, de propósito: aceito em silêncio, ele tiraria a sala
do sorteio sem ninguém notar.

**Marque todos os temas em que a sala cabe, e não o "principal".** O tema é
etiqueta, não gaveta. A conta obriga: o maior banco tem 13 salas utilizáveis e
uma Longa atravessa 7 — 9 para oferecer 3 portas em toda parada, porque o
sorteio nunca repete sala. Tema que dividisse o banco em gavetas não daria uma
Longa em gaveta nenhuma. Uma sala com dois ou três temas conta nos três pools.

**Sala sem `temas` cabe em qualquer um.** É por isso que todo arquivo escrito
antes disto continua valendo sem ser tocado.

### `monstros_por_tier`

A mesma sala serve incursões de tiers diferentes, e o que muda entre elas é
**quem mora nela**:

```json
"monstros_por_tier": {
  "2": [{ "nome": "Lobo", "quantidade": 3 }],
  "4": [{ "nome": "Lobo Atroz", "quantidade": 4 }]
}
```

O grupo pega o tier exato quando ele está escrito; senão, o maior tier escrito
**abaixo** dele — conteúdo de tier baixo é jogável por grupo alto, e o
contrário não. As chaves são texto, de `"1"` a `"5"`.

### `monstros_por_tema` — o mesmo lugar, outro bando

A mesma sala pode servir dungeons de temas diferentes com criaturas
diferentes. Dentro de cada tema vale a estrutura por tier de sempre:

```json
"monstros_por_tema": {
  "cripta": { "2": [{ "nome": "Carniçal", "quantidade": 4 }] },
  "natureza": { "2": [{ "nome": "Aranha Gigante", "quantidade": 3 }] }
}
```

A busca tem três degraus: a variante do tema, senão `monstros_por_tier`, senão
`monstros`. Então **escreva variante só onde quer uma** — tema que a sala
carrega sem variante escrita cai no bando padrão, e sala sem
`monstros_por_tema` se comporta como antes do tema existir.

Isso importa porque os dois eixos **multiplicam**: uma sala que já escreve três
tiers, com dois temas, viraria seis listas de criatura.

Duas regras que o validador cobra:

- **o tema da variante tem de estar em `temas` da sala.** Só entra em jogo o
  tema que a sala tem *e* a incursão pediu; variante de um tema que a sala não
  carrega nunca seria escolhida, e morreria calada no arquivo;
- **só sala de `Combate` tem criatura**, aqui como em `monstros`.

Quando a dungeon pede mais de um tema e a sala tem variante para vários, o bot
sorteia — e a escolha é fixa para aquele par de run e sala, então o cartão
mostra o bando com que o combate vai abrir, e um restart não troca o bando no
meio da luta.

---

## A criatura

Duas formas, e a primeira é a que você vai usar quase sempre.

**Pelo nome, do bestiário.** São 385 criaturas com os números do livro:

```json
{ "nome": "Behir" }
{ "nome": "Lobo", "quantidade": 4 }
```

Com `quantidade` maior que 1 cada cópia ganha um número no nome (`Lobo 1`,
`Lobo 2`), para o grupo saber em qual está batendo.

**Escrita à mão**, quando a criatura não existe no livro ou você quer outros
números. Aí `ca`, `ataque`, `hp` e `dano` passam a ser obrigatórios:

```json
{
  "nome": "O Arauto de Pedra",
  "ca": 16, "ataque": 7, "hp": 90, "dano": "2d8+4",
  "ataques": 2,
  "saves": "CON +5, SAB +3",
  "habilidade": {
    "nome": "Olhar Petrificante",
    "save": "CON", "cd": 14,
    "dano": "3d6", "alvos": 2, "atordoa": 1, "cada": 2
  }
}
```

| Campo | Obrigatório | O que aceita |
| --- | --- | --- |
| `nome` | **sim** | se for só o nome, vem do bestiário |
| `ca`, `ataque`, `hp` | sim, fora do bestiário | números; `hp` > 0 |
| `dano` | sim, fora do bestiário | soma de dados: `2d6+3`, `1d10`, `3d8+3+2d6` |
| `quantidade` | não (`1`) | 1 a 6 |
| `ataques` | não (`1`) | 1 a 8 golpes por rodada |
| `golpes` | não | lista de golpes próprios (abaixo) |
| `saves` | não | `"CON +5, SAB +3"` ou `{"CON": 5}` |
| `saves_vantagem` | não | `"FOR, CON"` |
| `habilidade` | não | a ação especial (abaixo) |
| `matilha` | não | `x`, `sim`, `1` ou `true` |
| `regeneracao` | não (`0`) | HP que ela recupera por rodada |

Atributos: `FOR`, `DES`, `CON`, `INT`, `SAB`, `CAR`.

### `golpes` — quando cada golpe é diferente

```json
"golpes": [
  { "nome": "Mordida", "ataque": 10, "dano": "3d10+6" },
  { "nome": "Cauda", "ataque": 10, "dano": "2d8+6" }
]
```

A lista **manda**: ela sobrescreve `ataque`, `dano` e `ataques`. Cada golpe
pode ter um `efeito`, que é uma habilidade sem ritmo — ela sai quando aquele
golpe acerta.

### `habilidade` — a ação especial

| Campo | Obrigatório | O que aceita |
| --- | --- | --- |
| `nome` | **sim** | **sem nome, a criatura simplesmente não tem habilidade** |
| `save` | **sim** | um atributo (`CON`), ou `ATK` |
| `cd` | sim, salvo com `ATK` | número > 0 |
| `dano` | um dos três | soma de dados |
| `atordoa` | um dos três | rodadas de atordoamento em quem falha |
| `debuff` | um dos três | um id, ou lista (abaixo) |
| `alvos` | não (`1`) | 1 a 6 |
| `cada` | não (`2`) | de quantas em quantas rodadas ela sai |
| `recarga` | não | a menor face do d6 que recarrega: *Recharge 5–6* é `5` |
| `metade` | não | metade do dano em quem passa no save |
| `save_repete` | não | o alvo refaz o teste no fim do turno para se livrar |
| `texto` | não | a descrição da ação |

**A habilidade precisa fazer alguma coisa**: ao menos um de `dano`, `atordoa`
ou `debuff`. E cuidado com o `nome`: ele é o interruptor. Uma habilidade sem
nome é descartada **em silêncio**, sem erro de validação.

Com `save: "ATK"` a conta inverte — a criatura rola ataque contra a CA do alvo,
que não rola nada, e a CD não vale. É a pancada física que a armadura apara em
vez de a Constituição aguentar. Com `ATK`, `dano` passa a ser obrigatório.

Debuffs que uma criatura pode deixar: `deterioracao`, `perdicao`,
`perturbacao`, `medo`, `envenenado`, `debilidade`, `letargia`, `fraqueza`,
`tolice`, `moleza`, `introversao`, `insensatez`, `exaustao`. Criatura **não dá
buff** — pedir um é erro de validação, e não silêncio.

---

## O banco de salas

```json
{
  "organizacao": "Vórtice Oculto",
  "salas": [
    { "id": "VO01", "nome": "...", "tipo": "Evento", "...": "..." },
    { "id": "VO02", "nome": "...", "tipo": "Combate", "...": "..." }
  ]
}
```

Duas regras próprias: o banco precisa de **pelo menos 3 salas** (é o número de
opções que cada parada oferece), e os `id` têm de ser **únicos** dentro dele.

Em vez de escrever o JSON do banco à mão, dá para usar a planilha:

```bash
python tools/gerar_modelo_banco.py      # cria a planilha em branco
python tools/importar_banco.py data/planilhas/banco_vortice_oculto.xlsx
```

O importador valida tudo antes de gravar: havendo qualquer problema, nada é
escrito. Para **incursões** não existe planilha — elas são JSON escrito à mão.

---

## Os limites, num lugar só

| O quê | Limite |
| --- | --- |
| Salas por banco | mínimo 3 |
| Criaturas numa sala | máximo 6 |
| `quantidade` de uma criatura | 1 a 6 |
| Golpes por rodada | 1 a 8 |
| Alvos de uma habilidade | 1 a 6 |
| `tier` | 1 a 5 |
| `recarga` | 2 a 6 |
| `nome` (sala e incursão) | máximo 256 caracteres |
| `descricao`, `lore_inicial`, `lore_final` | máximo 4096 caracteres |

Os dois últimos são do Discord, e não do bot: o texto da sala e a lore vão
**direto** para o embed, sem corte. Acima do teto o Discord recusa a mensagem
inteira — a sala quebraria na hora em que o grupo abre a porta, e não na hora
de validar. Por isso são recusa, e não aviso. O validador ainda avisa bem
antes do teto (80 num nome, 600 numa descrição de sala, 1500 numa lore), porque
parede de texto na tela de um celular é ruim muito antes de ser inválida.

## Depois de escrever

1. `python tools/validar_conteudo.py meu_arquivo.json` até sair `[ok]`.
2. Mande o arquivo para quem administra o bot.
3. O arquivo vai para `data/incursoes/` (ou `data/bancos/`), e `/incursao
   recarregar` relê do disco **sem reiniciar** o bot.

O `/incursao recarregar` responde com o erro de validação quando algo está
errado, então ele é a última rede — mas é rede ruim, porque nesse ponto o
arquivo já está em `data/`. Valide antes.
