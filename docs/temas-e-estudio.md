# Temas, filtros e o estúdio do colaborador

O contrato, escrito antes do código. Três decisões já estão tomadas e aparecem
aqui como decididas: a variação por tema troca **só as criaturas**; o filtro
que deixa sala insuficiente é **recusado na validação**; e o estúdio roda **na
máquina do colaborador**.

**O que já está no bot** (passos 1 a 5 da seção 13): o carregamento tolerante
por arquivo, o bestiário com `meta.ambientes`, o campo `temas` na sala, os
tetos de texto, e o **filtro da incursão com a conferência cruzada** — o tema
agora decide sorteio. Quem descreve o formato em vigor é sempre
`docs/formato-das-incursoes.md`.

Mais o **combate por tema** (seção 5), com uma correção de rota: a escolha
entre temas **não** virou coluna em `run_salas`. Ela é semeada por `run:sala`,
como `_trocas_da_parada` já fazia com as trocas do descanso duro — mesma
estabilidade, zero migração.

E o **estúdio** (seção 11), em `tools/estudio.py` com a página em
`tools/estudio/index.html`.

E o **sugeridor de combate** (seção 10), em `tools/sugestor.py`, com painel no
estúdio.

**Nada mais é só contrato.** O que sobrou está na seção 14: a entrega do
arquivo e quem pode escrever.

Uma correção de rota que o código impôs: o campo do filtro se chama `filtro`,
e não `salas` como esta seção 3 dizia. O detector de tipo de arquivo do
validador separa incursão de banco por `"salas"`, e o nome colidia — toda
incursão passava a ser lida como banco.

---

## 1. A conta que decide o desenho todo

O sorteio nunca repete sala. `motor.sortear_passo` tira as visitadas das
candidatas e, se sobrarem menos que `OPCOES_POR_PASSO` (3), o passo sai com
menos portas. Então o banco **depois do filtro** precisa ter:

| tamanho | salas atravessadas | mínimo para terminar | mínimo para 3 portas em toda parada |
|---|---|---|---|
| Curta | 3 | 3 | 5 |
| Média | 5 | 5 | 7 |
| Longa | 7 | 7 | **9** |

(Descanso é parada a mais e não sai do banco: a Média ganha um na parada 4, a
Longa ganha o normal na 4 e o duro na 8. Nenhum dos dois consome sala.)

E o estoque de hoje:

| Organização | salas escritas | utilizáveis |
|---|---|---|
| Vórtice Oculto | 14 | 13 |
| Aliança das Sombras | 12 | 11 |
| Guilda dos Mortos | 12 | 11 |
| Sentinelas do Alvorecer | 12 | 11 |

"Utilizáveis" desconta a sala de Descanso que cada banco tem (`AS05`, `GM05`,
`SA05`, `VO05`): ela **não é sorteada** — é o cenário da parada fixa de
descanso, e por isso tem de continuar existindo. Ela sai desta conta, não do
arquivo.

Uma Longa com escolha de verdade já come 9 das 11.

**Conclusão que molda tudo o que vem depois: o tema não pode ser gaveta.** Dois
temas num banco de 11 dão ~5 e ~6, e nem a Média fecha com 3 portas. Três temas
dão ~4, e nem a Curta.

O tema é **etiqueta**. Uma sala carrega todos os temas em que ela cabe, e a
regra para quem escreve é "marque tudo que serve", não "escolha um". É o que
mantém o pool grande sem escrever 100 salas.

---

## 2. O tema na sala

Campo novo no banco, lista de strings:

```json
{
  "id": "VO02",
  "nome": "Biblioteca Submersa",
  "tipo": "Evento",
  "temas": ["arcano", "agua"],
  "dificuldade": "Média",
  "cd": 13,
  "alvo_progresso": 3,
  "pericias": ["Arcanismo", "Investigação"],
  "descricao": "A água chega na cintura e os livros flutuam fechados."
}
```

`temas` é **lista fechada no código**, do mesmo jeito que `ORGANIZACOES` e
`TIPOS_SALA`. Tema livre em texto é um acidente esperando acontecer: digitado
errado, a sala some do sorteio em silêncio e ninguém é avisado.

Rascunho dos oito, tirado dos nomes das 50 salas que já existem:

| tema | o que ele cobre | salas de hoje que o pegariam |
|---|---|---|
| `urbano` | rua, telhado, casa, comércio | Alçapão do Beco, Mesa de Penhores, Telhado Molhado |
| `cripta` | osso, mortalha, enterro | Portão de Ossos, Vala Comum, Necrotério do Selo |
| `fortaleza` | muro, portão, corrente, escada | Pátio das Estátuas, Sala das Correntes, Ponte de Brasa |
| `arcano` | portal, ritual, selo, biblioteca | Portal Instável, Ritual Interrompido, Sala dos Espelhos Tortos |
| `sagrado` | altar, coro, relicário, oferenda | Altar Profanado, Coro Silenciado, Poço de Oferendas |
| `natureza` | bicho, ninho, mato, criadouro | Canil da Brecha, Ninho de Aberrações, Jardim Petrificado |
| `agua` | alagado, submerso, chuva, poço | Biblioteca Submersa, Poço dos Sudários, Fossa do Gigante |
| `escuridao` | sem luz, eco, aperto, sussurro | Corredor sem Luz, Corredor dos Ecos, Sala dos Sussurros |

Essa lista é para você editar — é a única parte deste documento que é gosto e
não conta.

**Sala sem `temas`** vale como "serve a qualquer tema": ela entra em todo pool.
Assim nenhum arquivo de hoje precisa ser tocado para continuar funcionando, e o
colaborador que não quer pensar em tema não é obrigado.

---

## 3. O filtro na incursão

Campo novo na incursão, com três etapas:

```json
{
  "id": "vortice_cripta",
  "nome": "A Cripta do Vórtice",
  "organizacao": "Vórtice Oculto",
  "tamanho": "Longa",
  "salas": {
    "temas": ["cripta", "arcano"],
    "excluir": ["VO12"]
  }
}
```

As regras, na ordem em que rodam:

1. **`temas`** — a sala entra se tiver **qualquer** um dos temas listados (OU, e
   não E). Exigir todos esvaziaria o pool pela conta da seção 1. Sala sem tema
   nenhum entra sempre.
2. **`incluir`** — quando presente, **ele é o pool**. "Apenas as salas VO03,
   VO07 e VO11" quer dizer exatamente isso, então `temas` passa a ser ignorado.
   O validador avisa se uma sala incluída é fora do tema pedido, sem barrar:
   pode ser de propósito.
3. **`excluir`** — tira as listadas, sempre por último, inclusive de `incluir`.

**Campo `salas` ausente = banco inteiro.** É o "selecionar todas", e é o que
toda incursão de hoje faz sem saber.

O **objetivo** é escrito na própria incursão e nunca sorteado, então nenhuma
etapa do filtro encosta nele. O descanso duro também não: ele não vem de banco.

---

## 4. Quando o filtro deixa pouca sala

Recusa na validação, em dois níveis, porque os dois casos são diferentes:

- **Recusa**: pool abaixo do mínimo para terminar (Longa com menos de 7). A run
  não tem como chegar ao objetivo. O arquivo não entra.
- **Aviso**: pool entre terminar e ter 3 portas sempre (Longa com 7 ou 8). A run
  termina, mas as últimas paradas oferecem menos escolha. Dungeon apertada de
  propósito é decisão de autor; travar na parada 6 não é.

A mensagem diz a conta, não só o veredito:

```
[x] vortice_cripta.json
      o filtro deixa 5 salas do banco do Vórtice Oculto (13 utilizáveis).
      Uma Longa atravessa 7 salas: faltam 2 para a run poder terminar, e 4
      para ter 3 portas em toda parada.
      Temas pedidos: cripta, arcano. Salas que batem: VO01, VO08, VO10,
      VO12, VO14.
```

---

## 5. Combate por tema

`monstros_por_tema` entra como irmão do `monstros_por_tier` que já existe. Os
dois eixos **multiplicam**: as salas de combate do Vórtice já escrevem 3 tiers
(1, 2 e 4), então 2 temas viram 6 listas de criatura na mesma sala.

Para isso não virar imposto, a variante por tema é **esparsa e opcional**, e a
busca tem três degraus:

1. `monstros_por_tema[tema]` — e, dentro dele, a queda por tier que já existe
   (tier exato, senão o maior tier escrito abaixo dele);
2. sem variante daquele tema: cai no `monstros_por_tier` da sala, que é o
   combate padrão;
3. sem nada disso: a lista solta `monstros`.

O autor escreve variante só onde quer uma. Sala sem `monstros_por_tema` se
comporta exatamente como hoje.

```json
{
  "id": "VO07",
  "nome": "Ninho de Aberrações",
  "tipo": "Combate",
  "temas": ["arcano", "natureza", "cripta"],
  "monstros_por_tier": { "2": [ { "nome": "Grick", "quantidade": 3 } ] },
  "monstros_por_tema": {
    "cripta":   { "2": [ { "nome": "Ghoul", "quantidade": 4 } ] },
    "natureza": { "2": [ { "nome": "Aranha Gigante", "quantidade": 3 } ] }
  }
}
```

Essa sala tem combate padrão (Grick), e troca para Ghoul numa dungeon de
cripta e para Aranha numa de natureza.

### A regra de desempate

Falta uma regra que nenhum dos dois eixos precisou até agora: **se a dungeon
pediu dois temas e a sala tem variante dos dois, qual combate sai?**

*Resolvido, e melhor do que esta seção propunha.* A proposta era sortear ao
sortear a sala e **gravar** a escolha numa coluna `tema` em `run_salas` — a
única mudança de banco de dados do documento. Não foi preciso: o projeto já
tinha o padrão certo em `_trocas_da_parada`, que deriva as trocas do descanso
duro de uma semente `run:parada` em vez de gravá-las.

`_tema_da_sala` faz o mesmo com `run:sala`. A mesma sala, na mesma run, dá
sempre o mesmo tema — o cartão mostra o bando com que o combate vai abrir, e
um restart não troca o bando no meio da luta. **Nenhuma migração.**

---

## 6. A conferência cruzada é um tipo novo de validação

Hoje toda validação é **por arquivo**: `de_dict` olha a incursão, `banco_de_dict`
olha o banco, e nenhum dos dois vê o outro. "O filtro desta dungeon deixa sala
suficiente?" é uma pergunta **cruzada**, e não cabe em nenhum dos dois.

Então entra uma função nova — incursão × banco — rodando em três lugares:

- no estúdio, ao vivo, enquanto o colaborador mexe no filtro;
- em `tools/validar_conteudo.py`, que é o que o autor roda antes de mandar;
- no carregamento do bot, que é por onde passa o arquivo copiado à mão.

---

## 7. Os limites de texto, que hoje não existem

Nenhum texto é validado por tamanho. `sala.descricao`, `lore_inicial` e
`lore_final` vão **direto** para `description=` do embed, e `nome` vai para
`title=`, sem corte.

Os limites do Discord são rígidos: título 256, descrição 4096, valor de campo
1024, e 6000 somando o embed inteiro. Acima disso o Discord **recusa a
mensagem** — ou seja, a sala quebra quando os jogadores abrem a porta, no meio
da run.

O conteúdo de hoje está longe do teto:

| texto | maior de hoje | teto do Discord |
|---|---|---|
| `nome` da incursão | 23 | 256 |
| `descricao` da sala | 200 | 4096 |
| `lore_inicial` | 857 | 4096 |
| `lore_final` | 544 | 4096 |

Não é bug de hoje. É a porta que abre quando o autor não é você, e o custo de
não fechá-la é uma run travada na frente de cinco pessoas. Regra proposta:
**recusa** no teto do Discord, **aviso** bem antes dele (600 numa descrição de
sala, 1500 numa lore), porque um muro de texto num celular é ruim muito antes
de ser inválido. E o estúdio mostra o contador ao vivo, que é onde isso
realmente se resolve.

---

## 8. A planilha aguenta sem quebrar

O modelo já tem a aba `Monstros` opcional, chaveada por `(sala_id, tier)`, com
tier vazio significando "qualquer tier". O tema é simétrico:

- aba `Salas`: coluna **`temas`**, separada por vírgula, com validação de
  dados na lista fechada;
- aba `Monstros`: coluna **`tema`**, chave vira `(sala_id, tema, tier)`, vazio
  = combate padrão;
- aba `Incursao` (no modelo de incursão): colunas **`temas`**, **`incluir`** e
  **`excluir`**, separadas por vírgula.

Coluna nova é opcional, como `tier` já é: planilha feita antes continua
importando. Isso importa mais do que parece — significa que o estúdio **não
substitui a planilha**. Os dois escrevem o mesmo JSON, e quem preferir Excel
segue no Excel.

---

## 9. O ambiente: medido, não suposto

O bestiário do bot **não tem ambiente**. O do 5etools tem, e eu medi o
`bestiary-mm.json` contra as nossas 385 criaturas:

- **385 de 385 casam por `nome_en`.** Nenhuma ambiguidade, nenhum nome perdido.
- **315 ganham pelo menos um ambiente. 70 ficam sem nenhum.**
- O vocabulário é fechado, 11 valores:

| ambiente | criaturas na origem |
|---|---|
| forest | 135 |
| underdark | 124 |
| hill | 90 |
| urban | 84 |
| grassland | 84 |
| desert | 79 |
| swamp | 55 |
| mountain | 53 |
| coastal | 48 |
| arctic | 39 |
| underwater | 23 |

### As 70 sem ambiente não são dado faltando

Elas têm padrão, e o padrão é significado:

| tipo | com ambiente | sem ambiente |
|---|---|---|
| fiend | 6 | **29** |
| construct | 2 | **13** |
| dragon | 31 | 10 |
| humanoid | 67 | 5 |
| aberration | 14 | 5 |
| undead | 26 | 4 |
| elemental | 20 | 2 |
| celestial | 3 | 2 |
| beast, monstrosity, giant, plant, fey, ooze | todas | 0 |

O livro não dá ambiente a quem não é nativo de bioma nenhum: demônio, golem,
celestial. Então o tratamento certo não é inventar ambiente para elas — é um
**balde próprio**, "de lugar nenhum: convocado, construído ou de outro plano",
que o sugeridor **oferece sempre**, em qualquer ambiente escolhido. Um demônio
cabe numa cripta tão bem quanto numa floresta, e sem esse balde uma dungeon
`sagrado` ou `arcano` não acha quase nada.

### Tema → ambiente

O que liga os dois vocabulários, e o que faz o estúdio parecer esperto: escolher
o tema já pré-filtra o ambiente.

| tema | ambientes prováveis | balde "de lugar nenhum" |
|---|---|---|
| `urbano` | urban | sim |
| `cripta` | underdark, urban | sim |
| `fortaleza` | hill, mountain, urban | sim |
| `arcano` | underdark | sim |
| `sagrado` | hill, mountain, urban | sim |
| `natureza` | forest, grassland, swamp, hill | não |
| `agua` | coastal, underwater, swamp | não |
| `escuridao` | underdark, forest | sim |

Pré-filtro, não trava: o colaborador pode abrir para os 11 sempre.

---

## 10. O sugeridor de combate

Três eixos, como você pediu — e os três têm de onde sair:

| eixo | de onde vem | estado |
|---|---|---|
| **ambiente** | `environment` do 5etools, 11 valores + o balde | falta o re-import |
| **tipo de bicho** | `meta.tipo`, 14 valores nas 385 | pronto |
| **dificuldade** | CR + `meta.funcao` + `rules.FAIXAS_DE_CR` | pronto, mas ver abaixo |

`FAIXAS_DE_CR` já liga o tier do grupo à faixa de CR que ele encontra: tier 1 →
CR 0 a 1, tier 2 → 2 a 4, tier 3 → 5 a 8, tier 4 → 9 a 13, tier 5 → 14 pra
cima. E `meta.funcao` dá a forma do bando: Minion, Âncora, Boss, Solo.

### A dificuldade do combate é medida, não declarada

Achado que muda o desenho: **sala de combate não tem dificuldade hoje.**
`dificuldade` só é exigida de Armadilha, Evento e Tesouro, porque lá ela define
a CD. Num combate quem define a dificuldade são as criaturas.

Então o sugeridor não deveria *declarar* dificuldade — deveria **procurar** uma
composição que atinja uma taxa de vitória alvo, e mostrar a taxa que mediu. A
etiqueta passa a ser ganha:

| rótulo | taxa de vitória alvo (grupo de 5, no tier da sala) |
|---|---|
| Fácil | 85% a 95% |
| Média | 65% a 80% |
| Difícil | 45% a 60% |

Essas três faixas continuam sendo **proposta minha e esperando calibração**
contra `docs/BALANCO.md`. O que não é proposta é o método: a sugestão se
verifica simulando a si mesma, com o motor de verdade.

E mostra o grupo de 3 junto, não só o de 5: três é o tamanho de mesa comum, e o
`tools/simular_combate.py` já reporta 5, 4, 3 e 2.

### O que a medição disse sobre as faixas

Construído o sugeridor, dá para perguntar se as faixas são alcançáveis. Rodando
as quinze combinações de tier × dificuldade, com grupo de guerreiros no nível
do tier, **quatorze acharam composição dentro da faixa pedida**. A que faltou
foi tier 2 Média.

Então as faixas servem — nenhum tier é incapaz de produzir Fácil, Média e
Difícil, e os números não precisam ser mexidos para o sugeridor funcionar. O
que a calibração ainda decide é outra coisa: se "Média" **deve** mesmo ser 65%
a 80% de vitória para este grupo, ou se o jogo quer outra coisa. Isso é escolha
de design e não sai de medição nenhuma.

Duas observações que a medição entregou de graça, e que valem para quem
escreve:

- **o grupo de 3 cai muito mais do que proporcionalmente.** Um bando medido em
  54% para cinco jogadores deu 0% para três. A mesa de três não está jogando o
  mesmo combate um pouco mais difícil: está jogando outro combate;
- **a escala de uma criatura só é grossa.** Entre quatro e cinco cópias a taxa
  pula faixa inteira, e por isso o sugeridor tenta âncora mais lacaios: é o que
  dá passo pequeno o bastante para cair numa faixa de quinze pontos.

---

## 11. O estúdio

Local, no repositório, aberto por um comando:

```bash
python tools/estudio.py
```

Sobe um servidor em `localhost`, abre a página, e **importa `src.motor`** — é
por isso que ele vive neste repositório e não em outro. Código separado seria
uma segunda cópia das regras, e uma segunda régua sempre acaba discordando da
primeira.

*Construído.* O que ficou de fora desta primeira versão, e está dito na própria
página: a sugestão de combate (seção 10) e a faixa da dungeon inteira — essa
segunda porque ela precisa de uma política de escolha declarada, e um número
sem dizer qual política foi usada seria mentira com número em cima.

O que a página faz:

- **Escrever sala**: campos do tipo certo (CD, perícia e alvo para sala de
  teste; criaturas para combate), temas como fichas clicáveis, contador de
  caracteres ao vivo.
- **Montar o filtro da dungeon** mostrando o pool que ele deixa **contra o
  mínimo do tamanho**, com a conta visível.
- **Sugerir combate** pelos três eixos, e verificar cada sugestão simulando-a.
- **Simular sala**: taxa de vitória, rodadas e quantos caem, para grupos de 5,
  4, 3 e 2. Isso o `simular_combate.py` já faz hoje.
- **Simular a dungeon** como faixa, não como número — ver abaixo.
- **Prever o card**: como a sala fica no embed do Discord, que é onde o texto
  comprido se revela comprido.
- **Exportar o JSON** pronto para mandar.

O que o colaborador precisa instalar: Python, o repositório e as dependências.
É o preço da opção local, e é o que mantém o resto em zero: sem TLS, sem login,
sem porta pública, sem moderação, sem depender de a Leeroy virar Pay As You Go.

### "Probabilidade da dungeon" não existe como número único

E eu não vou fingir que existe. Duas coisas impedem:

- HP, mana e poção **atravessam** as salas sem resetar, então a ordem importa;
- o caminho é sorteado 3 portas por parada, e **os jogadores escolhem**.

Um "73%" sem dizer qual política de escolha foi usada é uma mentira com número
em cima. O que o estúdio mostra é uma **faixa**: escolha aleatória (piso) contra
melhor escolha possível (teto), mais a tabela sala por sala. Para quem está
escrevendo, a tabela vale mais que o número.

### Sala de teste não precisa de Monte Carlo

Armadilha, Evento e Tesouro resolvem por d20 + modificador contra CD, com
`alvo_progresso` sucessos. Isso é fórmula fechada: exata, instantânea, sem
simulação. E lembrando que a CD escrita é a do tier 1, o tier soma o ajuste, e
Armadilha ainda ganha o desconto de 3.

---

## 12. Sugestões

Minhas, para você aceitar ou recusar uma por uma.

**12.1 — Re-importar o bestiário primeiro.** É o passo que desbloqueia o eixo
de ambiente, casa 385 de 385, não muda comportamento nenhum e não depende de
nada. Fazer antes de tudo.

**12.2 — Marcar sala exclusiva.** Hoje escrever sala nova muda **todas** as
incursões daquela Organização, porque o banco é compartilhado. Um campo
`exclusiva: true` manteria a sala fora do sorteio geral, aparecendo só onde uma
dungeon a pedir por `incluir`. É o que permite a sala-assinatura de uma dungeon
sem vazar para as outras quinze — e é provavelmente o que um colaborador vai
querer primeiro, porque ele pensa na dungeon dele.

**12.3 — ~~Reaproveitar as quatro salas de Descanso mortas.~~ Retirada: elas
não estão mortas.** `AS05`, `GM05`, `SA05` e `VO05` não são sorteadas, mas são
o **cenário da parada fixa de descanso** — `_sala_de_descanso` lê a sala de
Descanso do banco, e sem ela o grupo chega na parada e segue sem descansar,
perdendo a única cura garantida da Média. Eu as tinha chamado de conteúdo
morto; era erro meu. O validador agora avisa o contrário: banco **sem** sala de
Descanso é o problema.

**12.4 — Relatório de pool por tema.** *Feito:* `tools/relatorio_de_pool.py`.
Tabela Organização × tema com quantas salas tem e que tamanhos aguenta, mais
uma coluna `etiq.` que separa as salas que carregam o tema de verdade das que
só entram por não ter tema nenhum — sem ela o relatório diria que um banco não
etiquetado cobre os oito temas.

**12.5 — Semente fixa e visível na simulação.** Dois colaboradores comparando
números precisam ver o mesmo número. A semente aparece na tela e vai no JSON
exportado.

**12.6 — Endurecer `carregar_todas` antes de abrir para terceiros.** *Feito.*
Ela estourava no primeiro arquivo inválido, e o `_carregar_tolerante` subia o
bot **sem nenhuma incursão**: uma vírgula errada de um colaborador não tirava a
dungeon dele, tirava o catálogo inteiro do ar. Agora o arquivo ruim fica de
fora sozinho, e aparece no log e no `/incursao recarregar`.

**12.7 — Exportar diff, não só arquivo.** Quando o colaborador mexe num banco
existente, o estúdio mostrar o que mudou (salas novas, salas alteradas) faz a
sua revisão caber em trinta segundos em vez de um diff de 400 linhas de JSON.

**12.8 — Um piso de segurança no export.** Sala cujo combate simulado mata o
grupo de 5 mais de 70% das vezes sai com aviso gritado. Não barro — Difícil é
para ser difícil —, mas ninguém exporta uma máquina de TPK sem saber.

---

## 13. Ordem de implementação

1. ~~`carregar_todas` tolerante (12.6).~~ **Feito.** `carregar_todas_tolerante`
   e `carregar_bancos_tolerante`; o `/incursao recarregar` lista o que ficou de
   fora, porque tolerância silenciosa é conteúdo sumindo sem aviso.
2. ~~Ambiente no bestiário (12.1).~~ **Feito.** `tools/importar_ambientes.py`
   acrescenta `meta.ambientes` às 385 — e é importador separado porque
   re-importar o livro apagaria o `meta` que veio de `importar_fichas.py`.
3. ~~`temas` na sala.~~ **Feito.** Lista fechada, validação, coluna opcional na
   planilha. Ainda sem efeito no sorteio: só é escrito e conferido.
4. ~~Limites de texto (seção 7).~~ **Feito.**
5. ~~O filtro na incursão + a conferência cruzada + o relatório de pool.~~
   **Feito.** `FiltroDeSalas` e `conferir_filtro` em `src/incursoes.py`, a
   conferência rodando no validador e no carregamento, `salas_sorteaveis`
   centralizando a exclusão do Descanso, colunas na planilha da incursão e
   `tools/relatorio_de_pool.py`. Duas decisões que só apareceram no código: a
   chave do campo é `filtro` (ver o topo), e a incursão cujo filtro não fecha
   **sai do catálogo** em vez de travar na parada 4 com o grupo dentro.
6. ~~`monstros_por_tema` + a coluna `tema` em `run_salas`.~~ **Feito, sem a
   coluna.** A variante por tema entrou esparsa (três degraus: tema, tier,
   lista solta), o validador recusa variante de um tema que a sala não carrega
   — senão o combate escrito morre calado —, e a escolha entre temas é semeada
   por `run:sala` em vez de gravada. O cartão da sala e a abertura do combate
   leem o mesmo tema, pela mesma razão que já liam o mesmo tier.
7. ~~O estúdio: página + servidor local, reusando `simular_combate`.~~
   **Feito.** `python tools/estudio.py` sobe em `127.0.0.1` e serve
   `tools/estudio/index.html`. Faz: escrever sala com contador de texto ao
   vivo, montar o filtro vendo o pool contra o mínimo, prever o cartão do
   Discord, medir a sala de combate com o motor do bot e exportar o JSON. Não
   escreve em `data/` — quem decide o que entra é uma pessoa. O que ele **não**
   faz está na seção 11 e é dito na própria página.
8. ~~O sugeridor com busca por taxa alvo.~~ **Feito.** `tools/sugestor.py`,
   com CLI e painel no estúdio. A busca é por bisseção nos dois eixos — qual
   criatura e quantas —, e o veredito de cada medição aponta a direção. As
   faixas de taxa de vitória continuam sendo **proposta minha** e esperando
   calibração; o que foi medido está na seção 10.

Os passos 1 a 4 não mudam nada para quem joga hoje — e é por isso que eles
puderam ir primeiro. Do 5 em diante o tema começa a decidir sorteio.

---

## 14. O que isto não resolve

**A entrega.** Depois de tudo isto, o colaborador ainda produz um JSON e **manda
para você**, que copia para `data/` e roda `/incursao recarregar`. O estúdio
encurta o trabalho dele e a sua revisão (12.7), mas não existe caminho
automático de fora para dentro, e desenhar um é outra conversa — anexo em canal
de admin, pull request no repositório, ou pasta compartilhada, cada um com um
custo e um risco bem diferente.

**Quem pode escrever.** Nada aqui é controle de acesso. Quem recebe o estúdio
pode escrever qualquer coisa; o que impede conteúdo ruim de entrar é a sua
revisão, não o programa.
