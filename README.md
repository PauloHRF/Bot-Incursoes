# Incursões 2.0 — Bot de Discord

Bot de dungeon crawl assíncrono para as Incursões de Sheidrost. Grupos fixos de 5 jogadores
avançam sala a sala votando por botões, resolvendo testes com o modificador real da ficha.
O caminho é sorteado a cada run, de um banco de salas por Organização.

Design completo: `Incursões 2.0 — Bot de Discord (design).md`.

## Estado atual

- [x] **Fase 1** — fichas digitais (vários personagens por jogador, classe, tier, perícias)
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
| `/ficha registrar <nome> <classe> [imagem]` | Cria um personagem no tier 1; as proficiências vêm num menu depois |
| `/ficha listar [membro]` | Lista todos os personagens de um jogador |
| `/ficha ver [personagem] [membro]` | Mostra a ficha com todos os modificadores calculados |
| `/ficha upar [personagem]` | Sobe um tier, e conduz na hora a decisão que o tier trouxer |
| `/ficha pericias [personagem]` | Reabre o menu de proficiências da classe |
| `/ficha voltar [personagem]` | Desce um tier e esquece a decisão daquele tier, para refazer |
| `/ficha imagem [link] [personagem]` | Associa um retrato ao personagem (sem link, remove) |
| `/ficha remover <personagem>` | Apaga um personagem seu |
| `/incursao listar` | Mostra as incursões carregadas |
| `/incursao entrar <id> [personagem]` | Abre o recrutamento de uma incursão no canal |
| `/incursao sala` | Reenvia a mensagem da sala atual |
| `/incursao teste` | Rola o teste da sala (mesmo efeito do botão) |
| `/incursao atacar` | Ataca o primeiro inimigo de pé, na sua vez da iniciativa (mesmo efeito do botão) |
| `/incursao habilidade` | Abre o menu das suas habilidades ativas |
| `/incursao votar <1-3>` | Vota por comando, se os botões falharem |
| `/incursao status` | Estado da run: linha, sala, quem já rolou |
| `/incursao desistir` | Propõe abandonar a run (precisa de maioria) |
| `/incursao recarregar` | (admin) Relê os JSON de incursão do disco |
| `/organizacao placar` | Pontos das quatro Organizações no servidor |
| `/organizacao extrato [org]` | Últimos lançamentos, com o motivo de cada um |
| `/organizacao ajustar <org> <pontos> <motivo>` | (admin) Lança pontos na mão, para correções |
| `/config intervalo <semanas>` | (admin) Semanas entre incursões do mesmo jogador; 0 libera geral |

## Como uma run acontece

1. `/incursao entrar <id>` abre o recrutamento no canal, com o gancho da lore. Quem clica em **Entrar** precisa
   ter ao menos um personagem, não estar em outra run e ter cumprido o intervalo desde a
   última incursão.
2. Quem tem mais de um personagem escolhe num menu com qual entra; quem só tem um entra
   direto. O personagem fica preso àquela run: é a ficha dele que rola os testes, ataca e
   leva dano.
3. Ao chegar a 5 jogadores a run começa sozinha; quem abriu pode começar antes com **Começar**.
   Aí o bot posta a **lore de abertura** junto com o grupo — uma linha por personagem com
   tier, CA, ataque e HP, e os retratos lado a lado numa faixa só.
4. Cada passo sorteia 3 salas do banco da Organização na hora em que abre, deixando de fora
   as que o grupo já atravessou. Todos votam pelos botões, e a votação fecha
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

Em sala de **Combate**, cada personagem de pé ataca uma vez por rodada (d20 + bônus de
ataque contra a CA do alvo; acertou, rola o dano da arma), e **cada inimigo de pé** ataca
um alvo sorteado entre os personagens em pé. Quem chega a 0 HP fica fora do resto daquele
combate.

**Iniciativa.** Quando o combate começa, todo mundo rola **1d20 + modificador de Destreza**
— personagens e criaturas. Como a ficha não tem atributos, o modificador de Destreza é o
**save de DES**: o do personagem sai da classe (maior se DES for um dos saves fortes dela),
o da criatura vem da coluna `saves` da planilha (sem ele, o padrão provisório de ataque − 3).
Empate vai para o maior modificador, e depois para a sorte. A ordem vale o combate inteiro e
fica gravada: um restart não rola de novo.

As ações saem **uma de cada vez, na ordem da iniciativa**. O painel chama todo mundo, e cada
um escolhe ataque ou habilidade quando quiser: se ainda não é a vez dele, a ação **fica
guardada** e sai sozinha quando a vez chegar (se o alvo escolhido tiver caído até lá, vai no
próximo inimigo de pé). A criatura age sozinha quando chega a vez dela. A fila só para em
quem ainda não escolheu nada; passando do último, a rodada vira e recomeça do topo — então
uma criatura com iniciativa maior que a do grupo age antes de alguém clicar. O painel mostra
a ordem com ▶️ na vez atual, ✅ em quem já passou e ⏳ em quem já deixou a ação guardada.

Quem tem **Multiattack** (tier 3 de Bárbaro, Guerreiro, Monge e Patrulheiro) bate duas
vezes por clique: o turno inteiro sai de uma vez, e se o alvo cair no meio o segundo golpe
vai para o próximo inimigo de pé. O painel mostra os dois na mesma linha de log.

Uma sala pode ter **até 6 criaturas**. Com mais de uma de pé, o botão **Atacar** vira um
menu de alvos com o HP de cada uma; sobrando só uma, o botão volta. Cada criatura tem HP
próprio, e a sala só é superada quando a última cai — derrubar uma não encerra nada. Bater
em quem já caiu não gasta o turno: o bot avisa e você escolhe outro alvo. É aqui que um
bando pesa de verdade: cinco lobos batem cinco vezes por rodada.

Cada personagem age **uma vez por rodada: ou ataca, ou usa uma habilidade**, nunca os dois.
Quem já escolheu recebe o aviso dizendo com o que gastou o turno, e o menu ✨ Habilidade nem
abre. Reações (*Relentless*, *Uncanny Dodge*) não contam: disparam sozinhas, fora do turno.
Quem está caído ou atordoado quando a vez chega perde a vez; se tinha guardado uma
habilidade, ela não sai e **o uso volta**.

O canal fica com **um cartão só, o do momento**: a votação some quando o grupo entra na
sala — junto com o "voto registrado" que cada um recebeu —, a sala some quando a próxima
votação abre, e o resumo privado de cada golpe e a marcação da rodada somem quando a rodada
seguinte começa. O caminho inteiro volta no fim,
no campo **Caminho** do desfecho — é lá que se vê por onde o grupo passou.

O bot **marca os jogadores** na hora de agir — quando a votação abre, quando a sala pede
rolagem, quando o combate começa e a cada rodada nova. A chamada da rodada vai numa linha
de texto própria, porque o painel é editado no lugar e edição não notifica ninguém.

O combate inteiro acontece **numa mensagem só**: o painel mostra o HP de cada inimigo, o HP
de cada personagem, a ordem da iniciativa, o log da rodada em andamento e o da que acabou, e
o botão (ou menu) de atacar, e é reescrito a cada ação em vez de empilhar mensagens novas.
O log fica em memória: um restart no meio do combate perde o log, não o combate. Sala de combate também não posta descrição
antes do painel — ele já traz tudo. Um confronto de dez rodadas ocupa o mesmo espaço no
canal que um de duas.

O **20 natural** acerta por mais alta que seja a CA e é crítico: os dados de dano são
rolados em dobro, com o modificador entrando uma vez só (2d6+3 vira 4d6+3). O **1 natural**
erra por maior que seja o bônus. Os dois aparecem marcados no log da rodada — 💥 no crítico
e 💢 no erro crítico — e valem tanto para o grupo quanto para os inimigos. A última criatura
cair supera a sala; o grupo inteiro cair encerra a run em fracasso. A sala de **Descanso** completa o HP de quem
está machucado e devolve os caídos com metade do HP máximo.

A run é assíncrona: o estado vive no banco, então o grupo pode levar dias e o bot pode
reiniciar no meio — os botões das mensagens abertas voltam a funcionar sozinhos.

**Para testar à vontade**, rode `/config intervalo 0` uma vez: sem isso, quem entra numa run
fica bloqueado até a virada da semana assim que ela começa. Para recomeçar, encerre a run
atual com `/incursao desistir` (precisa da maioria do grupo) e abra outra com `/incursao entrar`.

## Avisos no canal

Mexer numa ficha aparece para o grupo: registrar um personagem posta a ficha no canal, e
subir de tier, voltar de tier ou trocar as proficiências posta uma linha dizendo o
que mudou. Apagar um personagem também avisa. Só a consulta é privada — `/ficha ver` e
`/ficha listar` continuam visíveis apenas para quem pediu.

`/help` monta a lista a partir da própria árvore de comandos do bot, então nunca fica
desatualizada. `/help ficha` filtra por grupo ou por comando.

## Personagens

O personagem é **a classe**: ninguém digita atributo nem número de combate. `/ficha registrar
<nome> <classe>` cria no **tier 1**, abre o menu de proficiências que aquela classe concede
e pronto — HP, CA, acerto, dano e os bônus de perícia saem da tabela da classe no tier atual
(`src/classes.py`).

A ficha anda **de tier em tier**: dentro de um tier nada muda, então não existe meio passo.
`/ficha upar` sobe um tier, até o **5**, dizendo o que mudou e abrindo na hora a decisão que
o tier novo trouxer. `/ficha voltar` desce um, para quem upou sem querer — e esquece as
decisões do tier perdido, que o jogador refaz ao subir de novo.

Por isso nada disso fica gravado na ficha: o bot guarda classe, tier, proficiências,
expertises e retrato, e deriva o resto na leitura. Uma ficha nunca fica desatualizada em
relação à tabela — mudar um número em `classes.py` muda todo mundo daquela classe.

**Classes prontas** (as do documento de fichas): Bárbaro, Guerreiro, Ladino, Monge,
Paladino, Patrulheiro e Xamã. **Previstas, ainda sem tabela**: Artífice, Bardo, Bruxo,
Clérigo, Druida, Feiticeiro e Mago — aparecem na lista de classes, mas o bot recusa o
cadastro dizendo o que já dá para jogar.

### Habilidades

Cada tier traz uma ou duas habilidades (`src/habilidades.py`), listadas em `/ficha ver` com
um ícone que diz o que o bot faz com elas:

| Ícone | Tipo | Estado |
| --- | --- | --- |
| ⚙️ | passiva | já vale sozinha, sem ninguém pedir |
| ⚡ | ativa | o jogador aciona pelo botão ou por comando |
| ❓ | escolha | o jogador decide algo ao chegar no tier |

**As passivas que já valem** são as que se resolvem em número: *Reliable Talent* (+5 e
depois +10 em todo teste), *Improved Critical* (crítico com 19), *Golpe Consagrado* (+2 de
dano), *Predador* (+2 contra inimigo com metade ou menos do HP), *Multiattack* (2 golpes por
rodada) e os +2 em listas de perícia do Monge, Patrulheiro, Paladino e Xamã. Quando duas
versões da mesma passiva coexistem, vale a mais forte — o Reliable Talent do tier 5
substitui o do tier 1, não soma.

**As ativas prontas** têm botão: no painel de combate aparece **✨ Habilidade** ao lado de
Atacar, e fora do combate existe `/incursao habilidade`. O menu mostra só o que o personagem
pode usar naquele momento, com quantos usos restam; quem precisa de alvo (um inimigo, três
inimigos, um aliado) recebe um segundo menu antes de gastar o uso. Usar uma delas em
combate **é o turno** daquela rodada, no lugar do ataque. São treze:

| Efeito | Habilidades |
| --- | --- |
| cura | *Second Wind*, *Cura pelas Mãos* |
| golpe no lugar do ataque | *Action Surge*, *Action Mastery*, *Flurry of Blows*, *Perfect Strike*, *Rajada do Caçador*, *Golpe Divino* |
| efeito com prazo | *Rage*, *Reckless Attack*, *Marca do Caçador*, *Caçador Supremo*, *Avatar da Luz* |
| vida temporária | *Tradição xamânica* (dois caminhos), *Dança totêmica*, *Brutal Strike* |
| reação | *Relentless*, *Uncanny Dodge* |
| condição no alvo | *Stunning Strike* |

**Vida temporária (THP)** absorve o dano antes do HP e não empilha — vale sempre a maior,
como em 5e. Some quando um combate novo começa, e aparece no painel como `30/40 +7 THP`.
A *Convocação totêmica* do Xamã se apoia nela: com 18+ no d20 ele ganha 2 THP, e **enquanto
ele tiver THP o grupo inteiro leva +1 em acerto e dano** (+2 e +3 no tier 5). *Relentless*
é uma **reação**: quando o Bárbaro cairia a 0 HP, ele fica com 1 e ganha 1d12+7 de THP,
uma vez por combate.

**Reações não aparecem no menu** — disparam sozinhas no gatilho, porque acontecem no turno do
inimigo, quando ninguém está clicando. O *Uncanny Dodge* do Ladino corta um golpe pela metade,
mas só entra quando o golpe **derrubaria** ou leva **um terço ou mais** do que resta (HP +
THP): não faz sentido queimar o uso do combate inteiro num arranhão. O limiar é um número no
catálogo, fácil de mexer se o grupo achar cedo ou tarde demais.

*Stunning Strike* é a primeira **condição**: o Monge escolhe a habilidade na hora de bater e,
se acertar, o inimigo perde a próxima vez dele — ainda nesta rodada, se ele vem depois na
iniciativa, ou na seguinte, se já agiu. Se errar, **o uso volta** — o documento
pede exatamente isso. E *Martial Arts* soma +1 de acerto a cada golpe certeiro, até +2, já
valendo dentro do próprio turno: com multiataque, o segundo golpe usa o bônus que o primeiro
acabou de render. Errar zera a sequência.

**Efeito com prazo** dura N turnos e conta sozinho: o bot guarda até que rodada ele vale e o
apaga quando a rodada vira. Dá para reduzir dano recebido (Rage), rolar com **vantagem** —
dois d20, fica o melhor —, somar CA e dano, curar uma fração por turno (Avatar da Luz) ou
marcar **um inimigo específico** para levar dano extra só dele (Marca do Caçador, Caçador
Supremo). No painel, quem está sob efeito aparece com 🛡️ (dano reduzido), 🎯 (vantagem) ou
✨ (abençoado), e o inimigo marcado leva 🎯 no nome.

Golpe de habilidade toma o turno, no lugar do ataque. Cura não levanta quem já caiu — isso
é assunto do descanso.

**Os usos recarregam** conforme o escopo declarado: *por combate* zera a cada sala de
combate, *por descanso* zera quando o grupo passa por uma sala de Descanso, e *por incursão*
vale uma vez na run inteira. O contador vive no banco, então sobrevive a reinício do bot.

**Ainda não valem**: as duas que repetem um teste de perícia falhado (*Sobrevivente* do
Patrulheiro e *Líder Sagrado* do Paladino), porque dependem do fluxo da sala e não do
combate. Aparecem na ficha marcadas *(em breve)*.

### Escolhas de tier

Quatro habilidades pedem uma decisão do jogador, e o bot conduz: **Fighting Style** (+1
acerto, +1 CA ou +2 dano), **Expertise** do Ladino (2 perícias no tier 2 e mais 2 no tier 4,
com o bônus de proficiência dobrado), **Primal Knowledge** (2 proficiências a mais, fora da
cota da classe) e a do **Xamã** no tier 3 (Multiattack ou Cântico Benevolente, que soma 4 de
THP quando ele cura).

A decisão é tomada **no próprio `/ficha upar`**: ele anuncia a subida no canal e abre, só
para o dono, o menu da escolha. Se houver mais de uma pendente, uma puxa a próxima até
acabarem. A ficha mostra o que já foi decidido e o que falta, e o
efeito vale na hora: escolher Defensivo muda a CA que aparece no `/ficha ver` e a que o
monstro enfrenta. Expertise só oferece perícias em que o personagem tem proficiência; Primal
Knowledge só oferece as que ele ainda não tem.

Cada jogador pode ter vários personagens (até 25) e escolhe qual leva para cada incursão.
Cada um pode ter um **retrato**: `/ficha imagem <link>` guarda a URL, que aparece como
miniatura em `/ficha ver` e, na abertura da run, numa faixa com o grupo inteiro lado a lado.
Só `http://` e `https://` são aceitos — o bot guarda o link, não a imagem, então hospede
onde quiser (inclusive num anexo do próprio Discord, copiando o link da imagem).

A faixa é montada pelo bot com Pillow (`pip install -r requirements.txt`): ele baixa os
retratos na hora de começar, recorta cada um em quadrado e escreve o nome embaixo. Quem não
tem retrato entra com a inicial. Sem Pillow instalada, ou se nenhum link carregar, a run abre
igual — só sem a faixa.

**A ficha e a faixa buscam a imagem por caminhos diferentes**, e é por isso que um link pode
funcionar numa e não na outra: em `/ficha ver` quem busca é o Discord, e na faixa é o próprio
bot. Por isso o download manda User-Agent de navegador (sem ele muito site responde 403),
aceita `application/octet-stream` (quem valida de verdade é a Pillow, abrindo os bytes) e
segue redirecionamento na mão, checando cada salto — um link público não pode saltar para a
rede interna de quem hospeda. `/ficha imagem` testa o link na hora e avisa, com o motivo, se
o bot não conseguir baixá-lo.
Os comandos de ficha aceitam o nome no campo `personagem`, com autocompletar; quem só tem
um personagem pode omitir. Dois personagens do mesmo jogador não podem ter o mesmo nome.

### Tier

O tier é o degrau do personagem, de **1 a 5** — é o que a ficha mostra e o que `/ficha upar`
sobe. Por baixo o bot ainda guarda um nível (1, 3, 5, 7, 9), porque as tabelas de classe são
indexadas por ele, mas ninguém precisa pensar nisso. O teto é o tier 5 porque é até onde vão
as tabelas de classe; para subir o teto basta acrescentar tiers em `src/classes.py`. Cada incursão declara o tier dela na
planilha, e a regra de entrada é de mão única: **quem está no tier da incursão ou abaixo
entra; quem está acima, não**. Um personagem de tier 2 pode encarar uma incursão de tier 5 a
reboque do grupo, mas um de tier 5 não volta para varrer uma de tier 2. Incursão sem tier na
planilha fica aberta a qualquer personagem.

A regra vale nos três caminhos de entrada: `/incursao entrar`, o botão **Entrar** e o menu de
escolha de personagem — que passa a oferecer só quem cabe. Quem não tem nenhum personagem
elegível recebe o tier da incursão na recusa, e o recrutamento mostra a exigência
antes de alguém clicar.

**Os limites continuam sendo do jogador, não do personagem**: o intervalo entre incursões
vale para a pessoa (ter três personagens não dá direito a três incursões por semana), e
ninguém participa de duas runs ao mesmo tempo, nem com personagens diferentes.

### Intervalo entre incursões

A vaga é semanal e **vira na segunda-feira**, não sete dias depois da última run: quem
entrou no sábado joga de novo na segunda, e a semana do grupo inteiro começa junto.
`/config intervalo <semanas>` muda quantas semanas cada jogador espera (1 é o padrão, 0
libera geral para o playtest). A segunda-feira é contada no horário de Brasília; se o grupo
for de outro fuso, ajuste `FUSO_UTC` no `.env`. Bancos que guardavam o intervalo em dias são
convertidos sozinhos na primeira subida — 7 dias viram 1 semana.

## Perícias e expertise

O modificador de uma perícia sai da **classe**: um bônus fixo do tier, dobrado quando o
personagem tem proficiência naquela perícia (o Ladino no tier 1 tem +3, ou +5 com
proficiência), mais o bônus avulso.
**Expertise** não é mais comando: é a escolha de tier de quem a tem (Ladino nos tiers 2 e
4), e dobra o bônus de proficiência das perícias escolhidas. O bônus avulso por perícia
continua no banco (`definir_bonus_pericia`), para quando houver item mágico — hoje nenhum
comando o define.

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

**A incursão** guarda a lore de abertura, a lore de fecho, o tamanho, o tier e a sala
final — nenhuma sala do meio:

```bash
.venv/Scripts/python.exe tools/gerar_modelo_planilha.py minha_incursao.xlsx
.venv/Scripts/python.exe tools/importar_planilha.py minha_incursao.xlsx
```

Os dois modelos já vêm preenchidos com um exemplo jogável: o banco do Vórtice Oculto
(12 salas) e *A Cripta do Vórtice*. Depois de importar, `/incursao recarregar` faz o bot
reler tudo sem reiniciar.

**Como pôr mais de uma criatura numa sala**: a coluna `monstro_quantidade` repete a mesma
criatura (3 = "Lobo 1", "Lobo 2", "Lobo 3"). Para um bando misto, preencha a aba
**Monstros** — no banco ela tem `sala_id` e é somada à criatura da linha da sala; na
planilha da incursão ela é a escolta do chefe. O limite é 6 criaturas por sala, contando as
duas fontes. Os dois modelos já vêm com exemplos: as Sentinelas de Basalto são duas, o
Guardião Adormecido vem com três Larvas, e o Olho do Vórtice tem dois Acólitos.

**O que uma criatura pode ter** (colunas da aba Monstros, todas opcionais): `ataques` para
multiataque, `saves` (`FOR +5, CON +5`) e `saves_vantagem` para as resistências dela, e um
bloco `habilidade_*` para a ação especial — nome, texto, `save`, `cd`, `dano`, `alvos` e
`atordoa`. A ação toma o turno: na rodada em que a criatura usa, ela não ataca.

Quando ela sai é `habilidade_cada` (2 = rodadas 2, 4, 6…) **ou** `habilidade_recarga`, que é
o *Recharge* da 5e: `5` significa "Recharge 5–6" — sai na primeira rodada e, depois de
gasta, volta quando o d6 da criatura tirar 5 ou mais. A carga fica gravada, então um restart
no meio do combate não devolve a habilidade de graça.

`habilidade_save_repete` marcado com `x` é o "e refaz o save no fim do turno": em vez de
durar um número fixo de rodadas, o atordoamento só acaba quando o alvo passar no teste — e
ele sempre perde ao menos uma vez antes da primeira chance. Quem é preso **perde a próxima
vez que teria**: a desta rodada, se ainda não agiu, ou a da seguinte. Quem já está preso não
é preso de novo por cima, e se o grupo inteiro estiver preso a rodada corre sozinha em vez de
travar.

O dano aceita **soma de parcelas**: `3d8+3+2d6` é o golpe que corta e envenena no mesmo
ataque. Num crítico todos os dados dobram, e os números soltos entram uma vez só.

**Quantas salas escrever no banco**: o caminho é sorteado passo a passo, quando o passo
abre, e **nenhuma sala que o grupo já atravessou volta a ser oferecida**. Uma sala recusada
na votação pode reaparecer mais à frente; a que o grupo entrou, não. Por isso o banco precisa
de pelo menos 3 salas além das que o caminho consome: 9 salas cobrem uma dungeon longa (7
passos) com folga. Se as salas novas acabarem, o passo sai com duas opções em vez de três —
melhor escolher entre duas portas do que voltar para a mesma câmara.

Os importadores validam antes de gravar e, se algo estiver errado, listam **todos** os
problemas sem escrever nada. Eles exigem:

- incursão com lore de abertura, tamanho válido (Curta/Média/Longa) e Organização conhecida
- `tier` de 1 a 5, ou em branco para deixar a incursão aberta a qualquer personagem
- Objetivo sempre do tipo **Combate**, com nome, CA, ataque, dano e HP de cada criatura
- banco com ao menos 3 salas e `sala_id` único
- salas de Armadilha / Evento / Tesouro com dificuldade, CD, alvo e ao menos uma perícia
- salas de Combate com 1 a 6 criaturas, e sem CD nem perícia (mecânica própria)
- perícias existentes (com ou sem acento) e pontos não negativos

Serve tanto Excel quanto Google Sheets — neste, baixe em *Arquivo → Fazer download →
Microsoft Excel (.xlsx)* antes de importar.

## Estrutura

```
src/
  main.py       ponto de entrada, carrega cogs e sincroniza comandos
  config.py     leitura do .env
  rules.py      tiers, bônus de perícia, tabela de perícias
  classes.py    as classes jogáveis e os números de cada tier
  habilidades.py  o catálogo de habilidades por classe e tier
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
  incursoes/    incursões convertidas em JSON — lore, tamanho, tier e sala final
  bancos/       bancos de salas por Organização — o que alimenta o sorteio
assets/         imagens das salas
tests/
  todos.py      roda todas as suítes
  smoke.py      regras, persistência, schema de incursão, carga dos cogs
  test_run.py   uma run inteira simulada, do recrutamento ao objetivo
  test_votacao.py  maioria, votos divididos, empate e restart
  test_combate.py  rodadas, contra-ataque, vitória, derrota total e descanso
  test_bando.py    várias criaturas na mesma sala: alvo, HP separado e revide
  test_habilidades.py  catálogo, passivas aplicadas e multiataque
  test_ativas.py   habilidades ativas: usos, cura e golpes extras
  test_duracao.py  efeitos com prazo: Rage, Marca do Caçador e a virada da rodada
  test_thp.py      vida temporária: absorção, aura totêmica e Relentless
  test_reacoes.py  esquiva, atordoamento e a sequência do Monge
  test_escolhas.py escolhas de tier: Fighting Style, Expertise e companhia
  test_pontos.py   crédito de pontos, placar, extrato e ajuste manual
  test_personagens.py  vários personagens, escolha ao entrar e migração do banco
  test_critico_expertise.py  críticos, erro crítico e bônus por perícia
  test_geracao.py  tamanhos, sorteio do caminho e as duas lores
  test_faixa.py    a faixa com os retratos do grupo na abertura
  test_semana.py   a virada do intervalo na segunda-feira
  test_registro.py cadastro por classe, proficiências, /ficha upar e /ficha voltar
  test_tier.py     quem pode entrar em cada incursão
  fakes.py      dublês do Discord usados pelos testes
```

## Pontos a calibrar no playtest

Valores em `src/rules.py` que o documento de design deixou em aberto ou marcou como
ponto de partida:

- `NIVEIS_POR_TIER` e `NIVEL_MAXIMO` — hoje 2 níveis por tier e teto no nível 10 (5 tiers)
- as tabelas de `src/classes.py` — HP, CA, acerto, dano e perícias de cada classe por tier
- `PESO_TIER` — peso de cada tier no alvo do objetivo principal (hoje o próprio tier)
- `CONSTANTE_OBJETIVO` — o `C` da fórmula do objetivo (design sugere +9 a +10)
- `FRACAO_DESCANSO_CAIDO` em `src/motor.py` — quanto do HP máximo um caído recupera (hoje 1/2)

**Os monstros de exemplo ficaram fracos para as tabelas de classe.** O objetivo é o Guardião
do Selo (CA 16, +7, 2d8+4, 58 HP) mais dois Acólitos (CA 13, +4, 1d8+2, 18 HP). Contra cinco
Guerreiros de nível 8 (CA 20, +9, 1d10+8, 75 HP, que é o que a tabela dá): **100% de vitória,
2,6 rodadas, nenhum caído** — e continua 100% com só dois personagens. Os números do chefe
foram escritos para fichas montadas à mão, mais fracas que as de classe. Recalibrar isso é
tarefa do playtest; o simulador aceita `--classe` e `--nivel` para comparar:

```bash
.venv/Scripts/python.exe tools/simular_combate.py data/incursoes/vortice_cripta.json
```
