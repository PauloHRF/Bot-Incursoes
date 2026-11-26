# Criaturas

**Este arquivo é gerado.** Ele sai de `tools/gerar_criaturas_md.py`, que lê o
bestiário. Para refazer depois de importar criaturas novas:

```
.venv/Scripts/python.exe tools/gerar_criaturas_md.py
```

São **683 criaturas**, e uma sala pode chamar qualquer uma delas
**só pelo nome** — os números saem daqui no lugar das colunas vazias. A regra
de como isso funciona está em [mecanicas/bestiario.md](mecanicas/bestiario.md);
aqui estão as fichas.

385 são do *Monster Manual* (`data/bestiario.json`) e 298 dos
livros de 2024 (`data/criaturas/`, uma por livro, com o livro nas notas).

## Como ler

**Os números valem como estão escritos.** Nada aqui é multiplicado por tier:
a criatura de 52 HP tem 52 HP em qualquer incursão. O tier está em QUEM a sala
chama — cada sala de combate tem uma lista por tier, e se a criatura não serve
ao tier o conteúdo usa outra, que é para isso que estas 683 existem. (Havia um
multiplicador até aqui: ele batia em cima de fichas já em força cheia de
*Monster Manual* e dizimava o grupo — cinco Gárgulas de 52 HP viravam 416 HP
numa sala de tier 2.)

**O agrupamento é por faixa de CR**, que é a tabela que decide a dificuldade do
jogo: `tools/balanco.py` tira dela a criatura típica de cada tier, e é contra
essa criatura que as 14 classes são medidas. O campo `meta.tier` de cada entrada
do JSON **não** é isto — ele vem do arquivo de origem e discorda desta tabela em
um terço do bestiário. Quem manda na dificuldade é a faixa de CR.

**Golpes por rodada** é a lista inteira: a criatura dá todos eles a cada
rodada, e `×2` quer dizer o mesmo golpe duas vezes. Quem monta a criatura usa
`ataques = len(golpes)` — o `num_acoes` do JSON não é lido por ninguém.

**Habilidade com `rec. N+` sai carregada**: ela cai na **rodada 1** e só volta
quando o d6 da criatura tirar N ou mais. É a surpresa que mais pega quem monta
objetivo — um Golpe Poderoso de 5d6 em 3 alvos abre o combate, não o fecha.

**Traços do livro que o motor não implementa** ficam no campo `fora` de cada
entrada do JSON (invisibilidade, voo, mudança de forma, regeneração condicional).
Eles não valem em jogo: o que vale é o que está nas colunas abaixo.

| Tier | Faixa de CR | Criaturas |
|---|---|---|
| 1 | CR 0 a 1 | 176 |
| 2 | CR 2 a 4 | 172 |
| 3 | CR 5 a 8 | 145 |
| 4 | CR 9 a 13 | 92 |
| 5 | CR 14 ou mais | 98 |

## Tier 1 — CR 0 a 1

176 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Aarakocra** | 1/4 | 12 | 13 | Garra +4 1d4+2 | — | minion |
| **Abutre Gigante** *(Giant Vulture)* | 1 | 10 | 22 | Bico +4 2d4+2 | — | matilha · minion, âncora |
| **Acólito** *(Acolyte)* | 1/4 | 10 | 9 | Clava +2 1d4 | — | minion |
| **Alce** *(Elk)* | 1/4 | 10 | 13 | Aríete +5 1d6+3 | **Investida Selvagem** · 3d6 · rola ataque · metade quem resiste · *rec. 6+, sai na rodada 1* | minion |
| **Andarilho do Vazio** *(Voidwalker)* | 1 | 16 | 38 | Sombras Devoradoras +6 1d4+4 | — | livro WoW |
| **Aranha Gigante** *(Giant Spider)* | 1 | 14 | 26 | Mordida +5 1d8+3 + envenenado (save CON CD 12) | **Teia** · save FOR CD 13 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Aranha-Lobo Gigante** *(Giant Wolf Spider)* | 1/4 | 13 | 11 | Mordida +3 1d6+1 + envenenado (save CON CD 12) | — | minion |
| **Armadura Animada** *(Animated Armor)* | 1 | 18 | 33 | Pancada +4 1d6+2 | — | minion, âncora |
| **Bandido** *(Bandit)* | 1/8 | 12 | 11 | Cimitarra +3 1d6+1 | **Golpe Certeiro** · 2d6+4 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Batedor** *(Scout)* | 1/2 | 13 | 16 | Espada Curta +4 1d6+2 | — | minion |
| **Bico-de-Machado** *(Axe Beak)* | 1/4 | 11 | 19 | Bico +4 1d8+2 | — | minion |
| **Broto Toma-Corpos** *(Bodytaker Podling)* | 1/2 | 12 | 26 | Pancada +5 1d6+3 | — | livro RHW |
| **Bugbear** | 1 | 16 | 27 | Maça Estrela +4 2d8+2 | **Golpe Poderoso** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Bullywug** | 1/4 | 15 | 11 | Mordida +3 1d4+1 | — | minion |
| **Cabeça da Morte** *(Death's Head)* | 1/2 | 16 | 17 | Mordida +3 1d4+1+2d6 | — | livro RHW |
| **Cabeça da Morte Aberrante** *(Aberrant Death's Head)* | 1 | 16 | 24 | Mordida Rasga-Mente +3 1d4+1+1d6 + medo (save SAB CD 15) | — | livro RHW |
| **Cabeça da Morte Petrificante** *(Petrifying Death's Head)* | 1 | 16 | 21 | Mordida Petrificante +3 1d4+1+1d6 + efeito (save CON CD 11) | — | livro RHW |
| **Cabra Gigante** *(Giant Goat)* | 1/2 | 11 | 19 | Aríete +5 2d4+3 | **Investida Selvagem** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Camelo** *(Camel)* | 1/8 | 9 | 15 | Mordida +5 1d4 | **Investida Selvagem** · 2d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Capanga** *(Thug)* | 1/2 | 11 | 32 | Maça +4 1d6+2 | **Golpe Certeiro** · 2d6 · rola ataque · *rec. 6+, sai na rodada 1* | matilha · minion |
| **Caranguejo Gigante** *(Giant Crab)* | 1/8 | 15 | 13 | Garra +3 1d6+1 | — | minion |
| **Carniçal** *(Ghoul)* | 1 | 12 | 22 | Mordida +2 2d6+2 + letargia (save CON CD 12) | **Garras Paralisantes** · save CON CD 12 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Carrionete** *(Carrionette)* | 1 | 15 | 17 | Agulha de Prata +4 1+1d6 + envenenado (save CAR CD 11) | **Troca de Almas** · save CAR CD 11 · atordoa 1 · *rec. 5+, sai na rodada 1* | livro RHW |
| **Cavalo de Guerra** *(Warhorse)* | 1/2 | 11 | 19 | Cascos +6 2d6+4 | **Investida Selvagem** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Cavalo de Montaria** *(Riding Horse)* | 1/4 | 10 | 13 | Cascos +5 2d4+3 | **Investida Selvagem** · 3d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Cavalo de Tração** *(Draft Horse)* | 1/4 | 10 | 19 | Cascos +6 2d4+4 | **Investida Selvagem** · 4d6 · rola ataque · metade quem resiste · *rec. 6+, sai na rodada 1* | minion |
| **Centopeia Gigante** *(Giant Centipede)* | 1/4 | 13 | 4 | Mordida +4 1d4+2 + envenenado (save CON CD 12) | — | minion |
| **Chacalobisomem** *(Jackalwere)* | 1/2 | 12 | 18 | Mordida +4 1d4+2 | **Olhar Soporífero** · save SAB CD 12 · deixa letargia · *rec. 5+, sai na rodada 1* | matilha · minion |
| **Chefe Goblin** *(Goblin Boss)* | 1 | 17 | 21 | Cimitarra +4 1d6+2 | **Bomba de Veneno** · 3d6 · save CON CD 12 · em 3 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Chicote Kuo-toa** *(Kuo-toa Whip)* | 1 | 11 | 65 | Mordida +4 1d4+2 | — | âncora, boss |
| **Cobra Constritora** *(Constrictor Snake)* | 1/4 | 12 | 13 | Mordida +4 1d6+2 | **Contrair** · 2d6 · save FOR CD 12 · atordoa 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Cobra de Fogo** *(Fire Snake)* | 1 | 14 | 22 | Mordida +3 1d4+1+1d6 | — | minion, âncora |
| **Cobra Venenosa** *(Poisonous Snake)* | 1/8 | 13 | 2 | Mordida +5 1d6+1 + envenenado (save CON CD 12) | **Investida Selvagem** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Cobra Venenosa Gigante** *(Giant Poisonous Snake)* | 1/4 | 14 | 11 | Mordida +6 1d4+4 + envenenado (save CON CD 12) | **Contrair** · 2d6 · save FOR CD 12 · atordoa 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Cobra Voadora** *(Flying Snake)* | 1/8 | 14 | 5 | Mordida +6 3d4 | — | minion |
| **Cocatriz** *(Cockatrice)* | 1/2 | 11 | 27 | Mordida +3 1d4+1 | **Mordida Petrificante** · save CON CD 11 · deixa letargia · *rec. 5+, sai na rodada 1* | minion |
| **Contrabandista Boromar** *(Boromar Smuggler)* | 1/2 | 13 | 27 | Espada Curta +4 1d6+2+1d4 | — | livro EFA |
| **Coruja Gigante** *(Giant Owl)* | 1/4 | 12 | 19 | Garras +3 2d6+1 | — | minion |
| **Crocodilo** *(Crocodile)* | 1/2 | 12 | 19 | Mordida +4 1d10+2 | — | minion |
| **Cultista** *(Cultist)* | 1/8 | 12 | 9 | Cimitarra +3 1d6+1 | **Golpe Certeiro** · 2d6+4 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Cultista de Demogorgon** *(Cultist of Demogorgon)* | 1/8 | 12 | 9 | Foice Ritual +4 1d4+2+1 | — | livro WttHC |
| **Cão da Morte** *(Death Dog)* | 1 | 12 | 39 | Mordida +4 1d6+2 + deterioracao (save CON CD 12) | — | minion, âncora |
| **Cão Intermitente** *(Blink Dog)* | 1/4 | 13 | 22 | Mordida +3 1d6+1 | — | minion |
| **Democão** *(Demodog)* | 1 | 14 | 27 | Mordida +5 1d10+3 | — | matilha · livro WttHC |
| **Demomorcego** *(Demobat)* | 1/2 | 13 | 21 | Mordida +5 2d6+3 | — | livro WttHC |
| **Desossado** *(Boneless)* | 1 | 12 | 22 | Sufocar +4 2d4+2 + perdicao (save CON CD 16) | **Carne Desfiada** · save SAB CD 11 · em 3 · deixa medo · *rec. 6+, sai na rodada 1* | livro RHW |
| **Diabrete** *(Imp)* | 1 | 13 | 10 | Ferrão +5 1d4+3 + envenenado (save CON CD 12) | — | minion |
| **Diabrete Trapaceiro** *(Imp Trickster)* | 1 | 13 | 21 | Ferroada +5 1d6+3+2d6 | — | livro WttHC |
| **Diabrete Vil** *(Fel Imp)* | 1 | 13 | 21 | Seta de Fogo Vil +4 2d6 ×2 | — | livro WoW |
| **Doninha Gigante** *(Giant Weasel)* | 1/8 | 13 | 9 | Mordida +5 1d4+3 | — | minion |
| **Dragão Feérico (Amarelo)** *(Faerie Dragon (Yellow))* | 1 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Laranja)** *(Faerie Dragon (Orange))* | 1 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Vermelho)** *(Faerie Dragon (Red))* | 1 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dretch** | 1/4 | 11 | 18 | Mordida +2 1d6 | **Chamas Infernais** · 1d6 · save DES CD 11 · em 2 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Drow** | 1/4 | 15 | 13 | Espada Curta +4 1d6+2 + envenenado (save CON CD 12) | **Golpe Envenenado** · 2d6 · save CON CD 12 · deixa envenenado · *rec. 5+, sai na rodada 1* | minion |
| **Drow de Lolth** *(Drow of Lolth)* | 1/4 | 15 | 13 | Besta de Mão Drow +4 1d4+2 + envenenado (save CON CD 12) | — | livro FRAiF |
| **Dríade** *(Dryad)* | 1 | 11 | 22 | Clava +2 1d4 | **Fascinar** · save SAB CD 14 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Duergar** | 1 | 16 | 26 | Picareta de Guerra +4 1d8+2 | — | minion, âncora |
| **Duodrone** | 1/4 | 15 | 11 | Soco +2 1d4 | **Sobrecarga** · 1d6 · rola ataque · *rec. 4+, sai na rodada 1* | minion |
| **Eco** *(Echo)* | 1/2 | 13 | 22 | Clava +4 1d4+2 ×2 | — | livro PL |
| **Eco Vazio** *(Empty Echo)* | 1/2 | 13 | 22 | Pancada +4 1d8+2 | **Grito Estático** · 2d4 · save CON CD 11 · em 3 · *rec. 6+, sai na rodada 1* | livro PL |
| **Enxame de Membros de Zumbi** *(Swarm of Zombie Limbs)* | 1 | 12 | 26 | Carne Podre +4 2d6+2 + envenenado (save CON CD 16) | — | livro RHW |
| **Enxame de Ratos Corrompidos** *(Swarm of Corrupted Rats)* | 1 | 12 | 27 | Mordida +4 2d4+2 | — | livro WttHC |
| **Espada Voadora** *(Flying Sword)* | 1/4 | 17 | 17 | Espada Longa +3 1d8+1 | — | minion |
| **Espantalho** *(Scarecrow)* | 1 | 11 | 36 | Garra +3 2d4+1 | **Olhar Aterrorizante** · save SAB CD 11 · deixa medo · atordoa 1 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Espectro** *(Specter)* | 1 | 12 | 22 | Drenar Vida +4 3d6 + deterioracao, exaustao (save CON CD 12) | — | minion, âncora |
| **Espectro de Springvale** *(Springvale's Specter)* | 1 | 12 | 13 | Drenar Vida +4 2d6 + deterioracao (save CON CD 16) | **Gritos do Passado** · 2d6 · save CON CD 12 · em 3 · *a cada 2 rodadas* | livro WoW |
| **Espião** *(Spy)* | 1 | 12 | 27 | Espada Curta +4 1d6+2 | — | minion, âncora |
| **Esporo de Gás** *(Gas Spore)* | 1/2 | 5 | 1 | Toque +0 1 | — | minion |
| **Esqueleto** *(Skeleton)* | 1/4 | 13 | 13 | Espada Curta +4 1d6+2 | **Toque da Morte** · 2d6 · save CON CD 12 · *rec. 5+, sai na rodada 1* | minion |
| **Esqueleto de Cavalo de Guerra** *(Warhorse Skeleton)* | 1/2 | 13 | 22 | Cascos +6 2d6+4 | — | minion |
| **Filhote de Dragão de Cobre** *(Copper Dragon Wyrmling)* | 1 | 16 | 22 | Mordida +4 1d10+2 | **Armas de Sopro** · 4d8 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Latão** *(Brass Dragon Wyrmling)* | 1 | 16 | 16 | Mordida +4 1d10+2 | **Armas de Sopro** · 4d6 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Profundo** *(Deep Dragon Wyrmling)* | 1 | 15 | 27 | Dilacerar +4 1d8+2 | **Sopro de Pesadelo** · 2d6 · save SAB CD 11 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Filhote de Phaerimm** *(Phaerimm Hatchling)* | 1/4 | 12 | 13 | Ferrão +3 1d4+1 ×2 | — | livro FRAiF |
| **Flizzlebin** | 1 | 12 | 38 | Confete Ofuscante +5 2d6+3 | — | livro WttHC |
| **Flumph** | 1/8 | 12 | 7 | Tentáculos +4 1d4+2+1d4 | **Explosão Psíquica** · 3d6 · save INT CD 12 · em 2 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion |
| **Fungo Violeta** *(Violet Fungus)* | 1/4 | 5 | 18 | Toque Apodrecido +2 1d8 + deterioracao (save CON CD 12) | **Vinhas Constritoras** · 2d6 · save FOR CD 10 · em 2 | minion |
| **Gavião-Sanguinário** *(Blood Hawk)* | 1/8 | 12 | 7 | Bico +4 1d4+2 | — | matilha · minion |
| **Girino Slaad** *(Slaad Tadpole)* | 1/8 | 12 | 10 | Mordida +4 1d4+2 + perturbacao (save INT CD 12) | **Explosão Psíquica** · 3d6 · save INT CD 12 · em 2 · atordoa 1 · *rec. 5+, sai na rodada 1* | minion |
| **Glóbulo de Gosma Cinzenta** *(Gray Ooze Glob)* | 1/2 | 9 | 19 | Pseudópode +3 2d8+1 | — | livro HotB |
| **Gnoll** | 1/2 | 15 | 22 | Mordida +4 1d4+2 | **Golpe Certeiro** · 2d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Gnomo das Profundezas (Svirfneblin)** *(Deep Gnome (Svirfneblin))* | 1/2 | 15 | 16 | Picareta de Guerra +4 1d8+2 | — | vantagem em INT · vantagem em SAB · vantagem em CAR · minion |
| **Goblin** | 1/4 | 15 | 7 | Cimitarra +4 1d6+2 | **Bomba de Veneno** · 2d6 · save CON CD 12 · em 2 · deixa envenenado · *rec. 5+, sai na rodada 1* | minion |
| **Gosma Cinzenta** *(Gray Ooze)* | 1/2 | 8 | 22 | Pseudópode +3 1d6+1+2d6 + deterioracao (save CON CD 12) | — | minion |
| **Grimlock** | 1/4 | 11 | 11 | Clava de Osso Espinhosa +5 1d4+3+1d4 | — | minion |
| **Guarda** *(Guard)* | 1/8 | 16 | 11 | Lança +3 1d6+1 | **Golpe Certeiro** · 2d6+4 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Guardião do Povo-Lagarto** *(Lizardfolk Warden)* | 1 | 15 | 32 | Mordida +4 1d6+2+1d6 · Pique de Osso +4 1d10+2 | — | livro HotB |
| **Guerreiro Tribal** *(Tribal Warrior)* | 1/8 | 12 | 11 | Lança +3 1d6+1 | — | matilha · minion |
| **Harpia** *(Harpy)* | 1 | 11 | 38 | Garras +3 2d4+1 | **Canção Sedutora** · save SAB CD 11 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Hiena Gigante** *(Giant Hyena)* | 1 | 12 | 45 | Mordida +5 2d6+3 | — | minion, âncora |
| **Hipogrifo** *(Hippogriff)* | 1 | 11 | 19 | Bico +5 1d10+3 | — | minion, âncora |
| **Hobgoblin** | 1/2 | 18 | 11 | Espada Longa +3 1d8+1 | **Golpe Certeiro** · 2d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Jacko** | 1 | 13 | 22 | Adaga Envenenada +5 1d4+3+1d6 ×2 | — | livro HotB |
| **Javali** *(Boar)* | 1/4 | 11 | 11 | Presa +3 1d6+1 | — | matilha · minion |
| **K-Nine** | 1 | 14 | 22 | Mordida +5 1d10+3 | — | matilha · livro PL |
| **Kenku** | 1/4 | 13 | 13 | Espada Curta +5 1d6+3 + perturbacao (save SAB CD 12) | — | minion |
| **Kobold** | 1/8 | 12 | 5 | Adaga +4 1d4+2 | — | matilha · minion |
| **Kobold Alado** *(Winged Kobold)* | 1/4 | 13 | 7 | Adaga +5 1d4+3 | — | matilha · minion |
| **Kuo-toa** | 1/4 | 13 | 18 | Mordida +3 1d4+1 | — | minion |
| **Lagarto Gigante** *(Giant Lizard)* | 1/4 | 12 | 19 | Mordida +4 1d8+2 | — | minion |
| **Leão** *(Lion)* | 1 | 12 | 26 | Mordida +5 1d8+3 | **Bote** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Lobo** *(Wolf)* | 1/4 | 13 | 11 | Mordida +4 2d4+2 | **Investida Selvagem** · 3d6 · rola ataque · *rec. 6+, sai na rodada 1* | matilha · minion |
| **Lobo Atroz** *(Dire Wolf)* | 1 | 14 | 37 | Mordida +5 2d6+3 | **Investida Selvagem** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Lâmina-Ferrão Vulkoori** *(Vulkoori Stingblade)* | 1/2 | 14 | 27 | Lâmina-Ferrão +4 1d6+2+1d4 | — | livro EFA |
| **Macaco** *(Ape)* | 1/2 | 12 | 19 | Soco +5 1d6+3 | — | minion |
| **Magmin** | 1/2 | 14 | 9 | Toque +4 2d6+1d6 | — | minion |
| **Manes** | 1/8 | 9 | 9 | Garras +2 2d4 | **Chamas Infernais** · 2d6 · save DES CD 11 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Manto Negro** *(Darkmantle)* | 1/2 | 11 | 22 | Esmagar +5 1d6+3 | **Nuvem de Escuridão** · save DES CD 13 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Mastim** *(Mastiff)* | 1/8 | 12 | 5 | Mordida +3 1d6+1 | — | minion |
| **Mecanostrider** *(Mechanostrider)* | 1/2 | 13 | 34 | Bicada +4 2d4+2 | — | livro WoW |
| **Meio-Ogro (Ogrilhão)** *(Half-Ogre (Ogrillon))* | 1 | 12 | 30 | Machado de Batalha +5 2d8+3 | — | minion, âncora |
| **Mephit de Fumaça** *(Smoke Mephit)* | 1/4 | 12 | 22 | Garras +4 1d4+2 | — | minion |
| **Mephit de Gelo** *(Ice Mephit)* | 1/2 | 11 | 21 | Garras +3 1d4+1+1d4 | **Sopro Gélido** · 2d4 · save DES CD 10 · em 2 · deixa letargia, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Lama** *(Mud Mephit)* | 1/4 | 11 | 27 | Socos +3 1d6+1 | **Mud Breath** · save DES CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Magma** *(Magma Mephit)* | 1/2 | 11 | 22 | Garras +3 1d4+1+1d4 | **Sopro de Fogo** · 2d6 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Poeira** *(Dust Mephit)* | 1/2 | 12 | 17 | Garras +4 1d4+2 | **Blinding Breath** · save DES CD 10 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Vapor** *(Steam Mephit)* | 1/4 | 10 | 21 | Garras +2 1d4+1d4 | **Sopro de Vapor** · 1d8 · save DES CD 10 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Monodrone** | 1/8 | 15 | 5 | Adaga +3 1d4+1 | — | minion |
| **Monstro da Ferrugem** *(Rust Monster)* | 1/2 | 14 | 27 | Mordida +3 1d8+1 | — | minion |
| **Morcego Gigante** *(Giant Bat)* | 1/4 | 13 | 22 | Mordida +4 1d6+2 | — | minion |
| **Mula** *(Mule)* | 1/8 | 10 | 11 | Cascos +2 1d4+2 | — | minion |
| **Murloc Coletor** *(Murloc Forager)* | 1 | 13 | 32 | Lâmina Serrilhada +4 1d6+2 ×2 | **Rajada Fria** · 2d4+3 · save FOR CD 13 · *a cada 2 rodadas* | livro WoW |
| **Myconid Adulto** *(Myconid Adult)* | 1/2 | 12 | 22 | Soco +2 2d4+2d4 | **Esporos** · save CON CD 11 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Narthus** | 1 | 13 | 22 | Maça Vil +4 1d6+2+1d6 ×2 | — | livro HotB |
| **Nobre** *(Noble)* | 1/8 | 15 | 9 | Rapieira +3 1d8+1 + perturbacao (save SAB CD 12) | — | minion |
| **Noggle Mago Selvagem** *(Noggle Wild Mage)* | 1 | 13 | 22 | Bastão Noggle +5 1d4+3+1d4 ×2 | — | livro LFL |
| **Noggle Saqueador** *(Noggle Ransacker)* | 1/4 | 12 | 13 | Golpe Sabotador +4 1d8+2 | — | livro LFL |
| **Orc** | 1/2 | 13 | 15 | Machado Grande +5 1d12+3 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Pantera** *(Panther)* | 1/4 | 12 | 13 | Mordida +4 1d6+2 | **Investida Selvagem** · 3d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Perfurador** *(Piercer)* | 1/2 | 15 | 22 | Queda +3 1d6+6d6 | — | minion |
| **Pixie** | 1/4 | 15 | 1 | Golpe +5 1d8+3 | **Fascinar** · 3d6 · save SAB CD 12 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Povo-Lagarto** *(Lizardfolk)* | 1/2 | 15 | 22 | Mordida +4 1d6+2 | — | minion |
| **Praga de Agulhas** *(Needle Blight)* | 1/4 | 12 | 11 | Garras +3 2d4+1 | **Vinhas Constritoras** · 2d6 · save FOR CD 11 · em 2 | minion |
| **Praga de Gravetos** *(Twig Blight)* | 1/8 | 13 | 4 | Garras +3 1d4+1 | **Vinhas Constritoras** · 2d6 · save FOR CD 11 · em 2 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion |
| **Praga de Vinhas** *(Vine Blight)* | 1/2 | 12 | 26 | Constrição +4 2d6+2 | **Entangling Plants** · save FOR CD 12 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Praga de Vinhas Enredadora** *(Vine Blight Tangler)* | 1/2 | 12 | 19 | Vinha Constritora +4 1d10+2 | **Vinhas Enredadoras** · save FOR CD 12 · atordoa 1 · *rec. 5+, sai na rodada 1* | livro WttHC |
| **Pral** | 1 | 14 | 52 | Rapieira +5 1d8+3 | — | livro HotB |
| **Pseudodragão** *(Pseudodragon)* | 1/4 | 13 | 7 | Mordida +4 1d4+2 + envenenado (save CON CD 12) | **Sopro Elemental** · 2d6 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Pteranodonte** *(Pteranodon)* | 1/4 | 13 | 13 | Mordida +3 2d4+1 | **Investida Selvagem** · 2d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Pônei** *(Pony)* | 1/8 | 10 | 11 | Cascos +4 2d4+2 | **Investida Selvagem** · 2d6+2 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Quadrone** | 1 | 16 | 22 | Soco +3 1d4+1 | — | minion, âncora |
| **Quasit** | 1 | 13 | 7 | Garra +4 1d4+3 | **Amedrontar** · save SAB CD 13 · deixa medo · *rec. 5+, sai na rodada 1* | minion |
| **Rato Corrompido** *(Corrupted Rat)* | 0 | 10 | 1 | Mordida +2 1 | — | livro WttHC |
| **Rato Corrompido Gigante** *(Giant Corrupted Rat)* | 1/2 | 13 | 18 | Mordida +5 1d6+3+2d4 | — | livro WttHC |
| **Rato Gigante** *(Giant Rat)* | 1/8 | 12 | 7 | Mordida +4 1d4+2 | — | matilha · minion |
| **Rilly June** | 1/2 | 12 | 13 | Forcado de Feno +4 1d8+2 ×2 | **Xô, Fora Daqui!** · 3d6 · save SAB CD 11 · deixa medo · metade quem resiste · *rec. 6+, sai na rodada 1* | livro WttHC |
| **Rufião Tarkanan** *(Tarkanan Ruffian)* | 1 | 13 | 32 | Lança +4 1d8+2 | — | livro EFA |
| **Rã Gigante** *(Giant Frog)* | 1/4 | 11 | 18 | Mordida +3 1d6+1 | — | minion |
| **Sahuagin** | 1/2 | 12 | 22 | Mordida +3 1d4+1 | — | minion |
| **Sapo Gigante** *(Giant Toad)* | 1 | 11 | 39 | Mordida +4 1d10+2+1d10 | **Engolir** · save FOR CD 12 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Saqueador Daask** *(Daask Raider)* | 1 | 15 | 33 | Socar +5 1d4+3 | — | matilha · livro EFA |
| **Saqueador Kuo-toa** *(Kuo-toa Marauder)* | 1/2 | 12 | 22 | Cortador Salgado +4 2d6+2 | — | livro HotB |
| **Servo de Esporos Quaggoth** *(Quaggoth Spore Servant)* | 1 | 13 | 45 | Garra +5 1d6+3 | — | minion, âncora |
| **Soldado Zhentilar** *(Zhentilar Soldier)* | 1 | 13 | 22 | Espada Curta +4 1d6+2+1d4 ×2 | **Derrubar** · 1d4+2 · save FOR CD 12 · *a cada 2 rodadas* | livro FRAiF |
| **Sombra** *(Shadow)* | 1/2 | 12 | 16 | Drenar Força +4 2d6+2 + perturbacao, exaustao (save CON CD 12) | **Toque Drenante** · 4d6 · save CON CD 12 · deixa perturbacao, exaustao · *rec. 5+, sai na rodada 1* | minion |
| **Sprite** | 1/4 | 15 | 2 | Espada Longa +2 1 + envenenado, exaustao (save CON CD 12) | **Fascinar** · 3d6 · save SAB CD 12 · em 2 · *rec. 5+, sai na rodada 1* | minion |
| **Sprite Escaramuçador** *(Sprite Skirmisher)* | 1/4 | 15 | 10 | Arco Encantador +6 1 + efeito (save CON CD 18) | — | livro HotB |
| **Stirge** | 1/8 | 14 | 2 | Sugar Sangue +5 1d4+3 + exaustao (save CON CD 12) | — | regenera 3/rodada · minion |
| **Sátiro** *(Satyr)* | 1/2 | 14 | 31 | Aríete +3 2d4+1 | — | minion |
| **Tartaruga-Dragão Pandarena** *(Pandarian Dragon Turtle)* | 1/2 | 17 | 30 | Mordida +5 1d8+3 | — | livro WoW |
| **Texugo Gigante** *(Giant Badger)* | 1/4 | 10 | 13 | Mordida +3 1d6+1 | — | minion |
| **Thri-kreen** | 1 | 15 | 33 | Mordida +3 1d6+1 + envenenado (save CON CD 12) | — | minion, âncora |
| **Tigre** *(Tiger)* | 1 | 12 | 37 | Mordida +5 1d10+3 | **Bote** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Tridrone** | 1/2 | 15 | 16 | Soco +3 1d4+1 | — | minion |
| **Tritão** *(Merfolk)* | 1/8 | 11 | 11 | Lança +2 1d6 | — | minion |
| **Troglodita** *(Troglodyte)* | 1/4 | 11 | 13 | Mordida +4 1d4+2 | **Golpe Poderoso** · 1d8+2 · rola ataque · *rec. 4+, sai na rodada 1* | minion |
| **Urso-Negro** *(Black Bear)* | 1/2 | 11 | 19 | Mordida +4 1d6+2 | **Investida Selvagem** · 2d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Urso-Pardo** *(Brown Bear)* | 1 | 11 | 34 | Mordida +6 1d8+4 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Vespa Gigante** *(Giant Wasp)* | 1/2 | 12 | 13 | Ferrão +4 1d6+2 + envenenado (save CON CD 12) | — | minion |
| **Vinx** | 1/4 | 13 | 11 | Espada Curta +4 1d6+2 ×2 | — | livro HotB |
| **Worg** | 1/2 | 13 | 26 | Mordida +5 2d6+3 | — | minion |
| **Yuan-ti Sangue-Puro** *(Yuan-ti Pureblood)* | 1 | 11 | 40 | Cimitarra +3 1d6+1 + envenenado (save CON CD 12) | — | minion, âncora |
| **Zumbi** *(Zombie)* | 1/4 | 8 | 22 | Pancada +3 1d6+1 + perturbacao (save CON CD 12) | **Toque da Morte** · 2d6 · save CON CD 13 · *rec. 5+, sai na rodada 1* | minion |
| **Águia Gigante** *(Giant Eagle)* | 1 | 13 | 26 | Bico +5 1d6+3 | — | minion, âncora |
| **Ícone Infernal** *(Fiendish Icon)* | 1 | 13 | 22 | Pancada +4 1d4+2 ×2 | **Erupção Ígnea** · 2d6 · save DES CD 11 · em 3 · *a cada 2 rodadas* | livro ABH |

## Tier 2 — CR 2 a 4

172 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Alce Gigante** *(Giant Elk)* | 2 | 14 | 42 | Aríete +6 2d6+4 | **Investida Selvagem** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Alossauro** *(Allosaurus)* | 2 | 13 | 51 | Mordida +6 2d10+4 | **Bote** · 5d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Andarilho da Névoa** *(Mist Wanderer)* | 3 | 13 | 52 | Rajada Radiante +5 2d10+3 ×2 | — | livro RHW |
| **Ankheg** | 2 | 14 | 39 | Mordida +5 2d6+3+1d6 | **Jato de Ácido** · 3d6 · save DES CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Anquilossauro** *(Ankylosaurus)* | 3 | 15 | 68 | Cauda +7 4d6+4 | **Golpe Poderoso** · 6d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Aranea** | 2 | 14 | 66 | Mordida +5 1d6+3+1d4 ×2 | — | livro FRAiF |
| **Aranha de Fase** *(Phase Spider)* | 3 | 13 | 32 | Mordida +4 1d10+2 + envenenado (save CON CD 13) | — | minion, âncora |
| **Artífice Cannith** *(Cannith Artificer)* | 4 | 16 | 71 | Maça Aríete +6 3d6+4 ×2 | — | livro EFA |
| **Azer** | 2 | 17 | 39 | Martelo de Guerra +5 1d8+3 | — | minion, âncora |
| **Banshee** | 4 | 12 | 58 | Toque Corruptor +4 3d6+2 | **Lamento Mortal** · 6d6 · save CON CD 13 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Baron Ashbury** | 4 | 16 | 82 | Rajada de Dor +4 1d10+2 ×2 | **Asfixiar** · 4d8 · save CON CD 13 · em 3 · metade quem resiste · *rec. 6+, sai na rodada 1* | livro WoW |
| **Basilisco** *(Basilisk)* | 3 | 15 | 52 | Mordida +5 2d6+3+2d6 | **Olhar Petrificante** · save CON CD 13 · deixa letargia · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Batedor Phaerimm** *(Phaerimm Scout)* | 2 | 13 | 44 | Ferrão +3 1d6+1+2d8 ×2 | — | livro NF |
| **Berserker** | 2 | 13 | 67 | Machado Grande +5 1d12+3 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Berserker Enferrujado** *(Rusted Berserker)* | 4 | 16 | 82 | Espada Grande +6 2d6+4 + envenenado (save CON CD 18) ×2 | — | livro FRAiF |
| **Boca Balbuciante** *(Gibbering Mouther)* | 2 | 9 | 67 | Mordidas +2 5d6 | **Blinding Spittle** · save DES CD 13 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Bruxa do Mar** *(Sea Hag)* | 2 | 14 | 52 | Garras +5 2d6+3 | **Olhar Horripilante** · save SAB CD 13 · em 3 · deixa medo, exaustao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Bruxa Verde** *(Green Hag)* | 3 | 17 | 82 | Garras +6 2d8+4 + perturbacao (save SAB CD 13) | **Maldição** · save SAB CD 14 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Capitão Bandido** *(Bandit Captain)* | 2 | 15 | 65 | Cimitarra +5 1d6+3 | **Golpe Certeiro** · 3d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Capitão Hobgoblin** *(Hobgoblin Captain)* | 3 | 17 | 39 | Montante +4 2d6+2 + perturbacao (save SAB CD 13) | **Bomba de Veneno** · 4d6 · save CON CD 13 · em 3 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cavaleiro** *(Knight)* | 3 | 18 | 52 | Montante +5 2d6+3 | **Golpe Certeiro** · 4d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cavaleiro da Garra Esmeralda** *(Emerald Claw Knight)* | 2 | 18 | 52 | Mangual +5 1d8+3 ×2 | — | livro EFA |
| **Centauro** *(Centaur)* | 2 | 12 | 45 | Pique +6 1d10+4 | — | minion, âncora |
| **Chefe Bugbear** *(Bugbear Chief)* | 3 | 17 | 65 | Maça Estrela +5 2d8+3 | — | âncora, boss |
| **Chefe de Guerra Orc** *(Orc War Chief)* | 4 | 16 | 93 | Machado Grande +6 1d12+4+1d8 | **Golpe Poderoso** · 5d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Chuul** | 4 | 16 | 93 | Pinça +6 2d6+4 + envenenado (save CON CD 13) | — | minion, âncora |
| **Clamador do Vazio** *(Voidcaller)* | 3 | 16 | 49 | Rajada do Vazio +6 1d6+4 ×2 | — | livro WoW |
| **Cobra Constritora Gigante** *(Giant Constrictor Snake)* | 2 | 12 | 60 | Mordida +6 2d6+4 | **Contrair** · 5d6 · save FOR CD 14 · atordoa 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Comandante da Garra Esmeralda** *(Emerald Claw Commander)* | 4 | 20 | 78 | Mangual +6 1d8+4 ×2 | — | livro EFA |
| **Couatl** | 4 | 19 | 97 | Mordida +8 1d6+5 + envenenado (save CON CD 13) | — | minion, âncora |
| **Cria de Demogorgon** *(Demogorgon Spawn)* | 2 | 15 | 44 | Garra +5 1d6+3 ×2 | — | regenera 5/rodada · livro WttHC |
| **Crânio Flamejante** *(Flameskull)* | 4 | 13 | 40 | Raio de Fogo +5 3d6 + perturbacao (save CON CD 13) | **Bola de Fogo** · 8d6 · save DES CD 13 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cubo Gelatinoso** *(Gelatinous Cube)* | 2 | 6 | 84 | Pseudópode +4 3d6 | **Engolfar** · 4d6 · save DES CD 15 · deixa perturbacao · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Cão Infernal** *(Hell Hound)* | 3 | 15 | 45 | Mordida +5 1d8+3+2d6 | **Sopro de Fogo** · 6d6 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Cérebro no Pote** *(Brain in a Jar)* | 3 | 11 | 55 | Rajada Disruptiva +6 2d6+4 ×2 | **Rajada Mental** · 4d6 · save INT CD 14 · em 3 · atordoa 1 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Demônio das Sombras** *(Shadow Demon)* | 4 | 13 | 66 | Garras +5 2d6+3+4d6+3 | **Escuridão Aterrorizante** · save SAB CD 13 · em 2 · deixa medo · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Devorador de Intelecto** *(Intellect Devourer)* | 2 | 12 | 21 | Garras +4 2d4+2 | **Devorar Intelecto** · save INT CD 12 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Diabo Barbado** *(Bearded Devil)* | 3 | 13 | 52 | Barba +5 1d8+2 + deterioracao (save CON CD 13) | — | minion, âncora |
| **Diabo Ceifador** *(Harvester Devil)* | 3 | 14 | 65 | Lâmina Infernal +5 1d6+3+2d6 ×2 | **Contrato Compulsório** · save CAR CD 14 · atordoa 2 · *rec. 6+, sai na rodada 1* | livro ABH |
| **Diabo Espinhoso** *(Spined Devil)* | 2 | 13 | 22 | Mordida +2 2d4 + deterioracao (save CON CD 12) | — | minion, âncora |
| **Donzela-Cisne** *(Swanmay)* | 3 | 14 | 71 | Bico +6 1d6+4 ×2 | — | livro FRAiF |
| **Doppelganger** | 3 | 14 | 52 | Pancada +6 1d6+4 | **Ler Mentes** · save SAB CD 14 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Azul)** *(Faerie Dragon (Blue))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Verde)** *(Faerie Dragon (Green))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Violeta)** *(Faerie Dragon (Violet))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Índigo)** *(Faerie Dragon (Indigo))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Druida** *(Druid)* | 2 | 11 | 27 | Cajado +2 1d6+1d8 | **Emaranhar** · save FOR CD 12 · em 2 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Eco Despedaçado** *(Shattered Echo)* | 3 | 13 | 60 | Pancada +6 2d10+4 ×2 | **Grito Sobrenatural** · 2d8 · save CON CD 13 · em 3 · deixa medo · *rec. 6+, sai na rodada 1* | livro PL |
| **Elefante** *(Elephant)* | 4 | 12 | 76 | Chifrada +8 3d8+6 | **Investida Selvagem** · 7d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Enxame de Gremishkas** *(Swarm of Gremishkas)* | 2 | 14 | 31 | Mordidas em Enxame +4 3d6+2+2d6 | — | livro RHW |
| **Enxame de Insetos Infestantes** *(Swarm of Infesting Insects)* | 2 | 13 | 33 | Infestação +4 4d4+2 + perdicao, exaustao, deterioracao, envenenado (save CON CD 11) | — | livro RHW |
| **Enxame de Insetos Vorazes** *(Swarm of Ravenous Insects)* | 3 | 13 | 39 | Mordidas Vorazes +4 4d8+2 + envenenado (save CON CD 16) | — | livro RHW |
| **Escorpião Gigante** *(Giant Scorpion)* | 3 | 15 | 52 | Garra +4 1d8+2 + envenenado (save CON CD 13) | — | minion, âncora |
| **Escriba Sivis** *(Sivis Scribe)* | 3 | 15 | 56 | Sigilo Explosivo +5 3d6+3 ×2 | — | livro EFA |
| **Espectador** *(Spectator)* | 3 | 14 | 39 | Mordida +1 1d6-1 + perturbacao (save INT CD 13) | **Raio Ocular** · save SAB CD 12 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Espreitador da Carniça** *(Carrion Stalker)* | 3 | 15 | 55 | Tentáculo +5 2d4+3 ×2 · Ferrão +5 2d6 + envenenado (save CON CD 13) | — | livro RHW |
| **Esqueleto de Minotauro** *(Minotaur Skeleton)* | 2 | 12 | 67 | Machado Grande +6 2d12+4 | — | minion, âncora |
| **Esqueleto de Strahd** *(Strahd Skeleton)* | 4 | 16 | 65 | Espada Longa Vampírica +5 1d8+3+2d6 + deterioracao (save CON CD 17) ×2 | **Golpe de Escudo** · 2d6+3 · save FOR CD 13 · *a cada 2 rodadas* | livro RHW |
| **Ettercap** | 2 | 13 | 44 | Mordida +4 1d8+2+1d8 + envenenado (save CON CD 12) | **Teia** · save FOR CD 12 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Ettin** | 4 | 12 | 85 | Machado de Batalha +7 2d8+5 + perturbacao (save DES CD 13) | — | minion, âncora |
| **Executor Orien** *(Orien Enforcer)* | 4 | 16 | 55 | Adaga +6 2d4+4+2d6 ×3 | **Gaiola de Relâmpagos** · 3d8 · save CON CD 13 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro EFA |
| **Fantasma** *(Ghost)* | 4 | 11 | 45 | Toque Murchador +5 4d6+3 | **Possession** · save CAR CD 13 · em 3 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Fanático do Culto** *(Cult Fanatic)* | 2 | 13 | 33 | Adaga +4 1d4+2 | **Comando Sombrio** · save SAB CD 12 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Fera Deslocadora** *(Displacer Beast)* | 3 | 13 | 85 | Tentáculo +6 1d6+4+1d6 + perturbacao (save SAB CD 13) | — | minion, âncora |
| **Figura de Cera** *(Waxwork)* | 3 | 14 | 52 | Faca de Escultor +5 2d6+3 ×2 | — | livro RHW |
| **Filhote de Dragão Azul** *(Blue Dragon Wyrmling)* | 3 | 17 | 52 | Mordida +5 1d10+3+1d6 | **Sopro de Relâmpago** · 4d10 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Branco** *(White Dragon Wyrmling)* | 2 | 16 | 32 | Mordida +4 1d10+2+1d4 | **Sopro Gélido** · 5d8 · save CON CD 12 · em 2 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Bronze** *(Bronze Dragon Wyrmling)* | 2 | 17 | 32 | Mordida +5 1d10+3 | **Armas de Sopro** · 3d10 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Ouro** *(Gold Dragon Wyrmling)* | 3 | 17 | 60 | Mordida +6 1d10+4 | **Armas de Sopro** · 4d10 · save DES CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Prata** *(Silver Dragon Wyrmling)* | 2 | 17 | 45 | Mordida +6 1d10+4 | **Armas de Sopro** · 4d8 · save CON CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Espiritual** *(Spirit Dragon Wyrmling)* | 2 | 16 | 52 | Dilacerar +4 2d6+2+1d6 | **Sopro Ruinoso** · 3d8 · save CON CD 12 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Filhote de Dragão Negro** *(Black Dragon Wyrmling)* | 2 | 17 | 33 | Mordida +4 1d10+2+1d4 | **Sopro Ácido** · 5d8 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Verde** *(Green Dragon Wyrmling)* | 2 | 17 | 38 | Mordida +4 1d10+2+1d6 | **Sopro Venenoso** · 6d6 · save CON CD 11 · em 2 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Vermelho** *(Red Dragon Wyrmling)* | 4 | 17 | 75 | Mordida +6 1d10+4+1d6 | **Sopro de Fogo** · 7d6 · save DES CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Fogo-Fátuo** *(Will-o'-Wisp)* | 2 | 19 | 22 | Choque +4 2d8 | — | minion, âncora |
| **Foreman Rhahk'Zor** | 3 | 13 | 76 | Punho +6 2d6+4 | **Malho Redemoinho** · 1d12+4 · save DES CD 14 · em 3 · *rec. 5+, sai na rodada 1* | livro WoW |
| **Furbolg Totêmico** *(Furbolg Totemic)* | 4 | 13 | 71 | Bordão +4 1d8+2+1d10 ×2 | — | livro WoW |
| **Geist Vingativo** *(Vengeful Geist)* | 3 | 14 | 66 | Garra +6 2d6+4 | — | matilha · livro ICC |
| **Geleia Ocre** *(Ochre Jelly)* | 2 | 8 | 45 | Pseudópode +4 2d6+2+1d6 | — | minion, âncora |
| **Gennifer Weathermay-Foxgrove** | 3 | 14 | 44 | Adaga Abençoada +4 1d4+2+2d8 ×2 | **Proteção Esotérica** · 4d8 · save CON CD 13 · em 3 · atordoa 1 · *rec. 6+, sai na rodada 1* | livro RHW |
| **Gilnid** | 4 | 15 | 90 | Maça Abrasadora +6 1d6+4+1d6 ×2 | — | livro WoW |
| **Gosma da Pestilência** *(Plagueworks Ooze)* | 4 | 7 | 67 | Pseudópode Grudento +5 4d6+3 | — | livro ICC |
| **Grell** | 3 | 12 | 55 | Tentáculos +4 1d10+2 + envenenado (save CON CD 13) | **Tentáculos Paralisantes** · save CON CD 12 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Gremishka** | 2 | 14 | 31 | Mordida +4 1d6+2+2d6 | — | livro RHW |
| **Grick** | 2 | 14 | 27 | Tentáculos +4 2d6+2 | — | minion, âncora |
| **Grifo** *(Griffon)* | 2 | 12 | 59 | Bico +6 1d8+4 | — | minion, âncora |
| **Guarda Nimblewright** *(Nimblewright Guard)* | 3 | 16 | 67 | Cimitarra +6 1d6+4 ×3 | — | livro FRAiF |
| **Guarda Vil** *(Felguard)* | 4 | 17 | 60 | Machado de Batalha Vil +5 2d8+3+2d6 ×2 | — | matilha · livro WoW |
| **Guerreiro Githyanki** *(Githyanki Warrior)* | 3 | 17 | 49 | Montante +4 2d6+2+2d6 | — | minion, âncora |
| **Gárgula** *(Gargoyle)* | 2 | 15 | 52 | Mordida +4 1d6+2 | — | minion, âncora |
| **Hendrik von Aubrecker** | 3 | 15 | 65 | Pancada +6 1d8+4 ×2 | **Agulha Entorpecente** · 2d6 · save CON CD 14 · metade quem resiste · *a cada 2 rodadas* | livro PL |
| **Herdeiro Lyrandar** *(Lyrandar Scion)* | 4 | 13 | 60 | Raio Trovejante +6 2d6+4+2d8 ×2 | — | livro EFA |
| **Herdeiro Vadalis** *(Vadalis Heir)* | 4 | 14 | 52 | Cimitarra +5 1d6+3+1d6 ×4 | — | matilha · livro EFA |
| **Homem-Corvo** *(Wereraven)* | 2 | 12 | 54 | Arranhão +4 2d4+2 ×2 | — | livro RHW |
| **Homem-Javali** *(Wereboar)* | 4 | 10 | 78 | Presas +5 2d6+3 + perdicao (save SAB CD 13) | — | minion, âncora |
| **Homem-Rato** *(Wererat)* | 2 | 12 | 33 | Mordida +4 1d4+2 + perdicao (save SAB CD 12) | — | minion, âncora |
| **Homem-Tigre** *(Weretiger)* | 4 | 12 | 120 | Cimitarra +5 1d6+3 + perdicao (save SAB CD 13) | **Bote** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Horror da Névoa** *(Mist Horror)* | 3 | 13 | 45 | Rasgo Mental +5 1d10+3 ×2 | **Incutir Pavor** · save SAB CD 13 · em 3 · deixa medo · *rec. 4+, sai na rodada 1* | livro RHW |
| **Horror Elmado** *(Helmed Horror)* | 4 | 20 | 60 | Espada Longa +6 1d8+4 | — | minion, âncora |
| **Horror Gancho** *(Hook Horror)* | 3 | 15 | 75 | Gancho +6 2d6+4 | — | minion, âncora |
| **Investigador Medani** *(Medani Inquisitive)* | 3 | 14 | 45 | Cajado Torto +4 1d8+2 ×3 | **Olho Inquisitivo** · 3d6 · save SAB CD 13 · metade quem resiste · *a cada 2 rodadas* | livro EFA |
| **Ivlis** | 2 | 13 | 49 | Rajada do Caos +4 2d6 ×3 | **Comando Sinistro** · save SAB CD 12 · atordoa 1 · *rec. 5+, sai na rodada 1* | livro HotB |
| **Javali Gigante** *(Giant Boar)* | 2 | 12 | 42 | Presa +5 2d6+3 | **Investida Selvagem** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Korex** | 2 | 13 | 52 | Faca Rançosa +5 2d4+3+2d6 + envenenado (save CON CD 17) | **Flauta Hipnótica** · 4d6 · save SAB CD 12 · atordoa 1 · metade quem resiste · *a cada 2 rodadas* | livro WttHC |
| **Laurie Weathermay-Foxgrove** | 3 | 16 | 65 | Teia Fina +6 1d8+4+1d6 ×2 | — | livro RHW |
| **Lobisomem** *(Werewolf)* | 3 | 11 | 58 | Lança +4 1d6+2 + perdicao (save SAB CD 13) | — | minion, âncora |
| **Lobo do Inverno** *(Winter Wolf)* | 3 | 13 | 75 | Mordida +6 2d6+4 | **Sopro Gélido** · 4d8 · save DES CD 12 · em 2 · deixa letargia, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Lâmia** *(Lamia)* | 4 | 13 | 97 | Garras +5 2d10+3 + perdicao (save SAB CD 13) | **Toque Encantador** · save SAB CD 13 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Lívido** *(Ghast)* | 2 | 13 | 36 | Mordida +3 2d8+3 + letargia, exaustao (save CON CD 12) | **Garras Paralisantes** · save CON CD 13 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Magen Caldeirão** *(Caldron Magen)* | 4 | 20 | 67 | Punho Estendido +6 1d8+4+1d10 ×2 | — | livro NF |
| **Mantícora** *(Manticore)* | 3 | 14 | 68 | Mordida +5 1d8+3 | **Rajada de Espinhos** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Merrow** | 2 | 13 | 45 | Mordida +6 1d8+4 | — | minion, âncora |
| **Merrow Língua-Dupla** *(Merrow Doublespeaker)* | 4 | 14 | 67 | Cauda Espinhosa +6 3d6+4 ×3 | — | livro LFL |
| **Minotauro** *(Minotaur)* | 3 | 14 | 76 | Machado Grande +6 2d12+4 | **Investida Selvagem** · 6d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Monge Githzerai** *(Githzerai Monk)* | 2 | 14 | 38 | Ataque Desarmado +4 1d8+2+2d8 | — | minion, âncora |
| **Monitor Kuo-toa** *(Kuo-toa Monitor)* | 3 | 13 | 65 | Mordida +6 1d4+2 + perturbacao (save INT CD 13) | — | minion, âncora |
| **Monstruosidade Pustulenta** *(Pustulant Monstrosity)* | 2 | 9 | 57 | Pancada +6 1d8+4 | **Cuspir Praga** · 1d6 · save DES CD 14 · deixa envenenado · *a cada 2 rodadas* | livro WoW |
| **Montaria Nimblewright** *(Nimblewright Steed)* | 2 | 16 | 47 | Cascos +6 1d8+3 | — | livro FRAiF |
| **Murloc Oráculo** *(Murloc Oracle)* | 3 | 15 | 54 | Cajado de Coral +5 1d6+3+1d6 ×2 | — | livro WoW |
| **Myconid Soberano** *(Myconid Sovereign)* | 2 | 13 | 60 | Soco +3 3d4+1+3d4 | **Esporos** · save CON CD 12 · em 3 · deixa perturbacao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Médico Jorasco** *(Jorasco Medic)* | 4 | 16 | 58 | Rajada Radiante +5 2d6 + perdicao (save CAR CD 17) ×2 | — | livro EFA |
| **Mímico** *(Mimic)* | 2 | 12 | 58 | Pseudópode +5 1d8+3 | **Aderência** · save FOR CD 13 · deixa perturbacao · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Múmia** *(Mummy)* | 3 | 11 | 58 | Punho Apodrecido +5 2d6+3+3d6 + deterioracao (save CON CD 13) | **Olhar Terrível** · save SAB CD 13 · atordoa 1 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Naga Ossuária (Espiritual)** *(Bone Naga (Spirit))* | 4 | 15 | 58 | Mordida +5 2d6+3+3d6 + perturbacao (save CON CD 13) | — | minion, âncora |
| **Naga Ossuária (Guardiã)** *(Bone Naga (Guardian))* | 4 | 15 | 58 | Mordida +5 2d6+3+3d6 | — | minion, âncora |
| **Nothic** | 2 | 15 | 45 | Garra +4 1d6+3 | **Olhar Apodrecido** · 3d6 · save CON CD 13 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Ogro** *(Ogre)* | 2 | 11 | 59 | Clava Grande +6 2d8+4 | **Golpe Poderoso** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Olho de Gruumsh Orc** *(Orc Eye of Gruumsh)* | 2 | 16 | 45 | Lança +5 1d6+3+1d8 | **Maldição de Gruumsh** · save SAB CD 13 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Orog** | 2 | 18 | 42 | Machado Grande +6 1d12+4 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Paladino Zhentilar de Bane** *(Zhentilar Paladin of Bane)* | 4 | 18 | 58 | Lâmina da Perdição +5 1d8+3+2d6 ×3 | — | livro FRAiF |
| **Pentadrone** | 2 | 16 | 32 | Braço +4 1d6+2 | **Paralysis Gas** · save CON CD 11 · em 2 · atordoa 1 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Peritonte** *(Peryton)* | 2 | 13 | 33 | Chifrada +5 1d8+3 | — | minion, âncora |
| **Pesadelo** *(Nightmare)* | 3 | 13 | 68 | Cascos +6 2d8+4+2d6 | — | minion, âncora |
| **Poltergeist** | 2 | 12 | 22 | Pancada Brutal +4 3d6 | — | minion, âncora |
| **Presa de Yeenoghu Gnoll** *(Gnoll Fang of Yeenoghu)* | 4 | 14 | 65 | Mordida +5 1d6+3 | — | âncora, boss |
| **Pudim Negro** *(Black Pudding)* | 4 | 7 | 85 | Pseudópode +5 1d6+3+4d8 + deterioracao, perturbacao (save CON CD 13) | — | minion, âncora |
| **Pégaso** *(Pegasus)* | 2 | 12 | 59 | Cascos +6 2d6+4 | — | minion, âncora |
| **Quaggoth** | 2 | 13 | 45 | Garra +5 1d6+3 | — | minion, âncora |
| **Rainha Lagarto** *(Lizard Queen)* | 4 | 15 | 78 | Mordida +5 1d6+3 | — | âncora, boss |
| **Rastejante da Carniça** *(Carrion Crawler)* | 2 | 13 | 51 | Tentáculos +8 1d4+2 + envenenado (save CON CD 12) | — | minion, âncora |
| **Rei Lagarto** *(Lizard King)* | 4 | 15 | 78 | Mordida +5 1d6+3 | — | âncora, boss |
| **Rinoceronte** *(Rhinoceros)* | 2 | 11 | 45 | Chifrada +7 2d8+5 | **Investida Selvagem** · 5d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Sacerdote** *(Priest)* | 2 | 13 | 27 | Maça +2 1d6 | **Guardiões Espirituais** · 3d8 · save SAB CD 13 · em 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Sacerdote do Veneno Vulkoori** *(Vulkoori Venom Priest)* | 2 | 15 | 44 | Cajado Venenoso +4 2d6+2 + envenenado (save CON CD 16) | — | livro EFA |
| **Sacerdotisa Sahuagin** *(Sahuagin Priestess)* | 2 | 12 | 33 | Mordida +3 1d4+1 | — | âncora, boss |
| **Senhor da Matilha Gnoll** *(Gnoll Pack Lord)* | 2 | 15 | 49 | Glaive +5 1d10+3 | **Golpe Poderoso** · 5d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Serpente Polar** *(Polar Serpent)* | 3 | 14 | 58 | Mordida +6 1d8+4+1d6 | **Constrição** · 1d6+2d6 · save FOR CD 14 · atordoa 1 · *a cada 2 rodadas* | livro FRAiF |
| **Sneed's Shredder** | 4 | 16 | 93 | Serra a Vapor +6 1d10+4 ×2 | **Aterrorizar** · save SAB CD 13 · deixa medo · *rec. 5+, sai na rodada 1* | livro WoW |
| **Solucionador Ghallanda** *(Ghallanda Troubleshooter)* | 3 | 14 | 78 | Adaga Envenenada +5 1d4+3 + envenenado (save CON CD 17) ×2 | — | livro EFA |
| **Strigoi** | 4 | 16 | 52 | Garra +5 2d6+3 ×2 · Probóscide +5 1d4+3+2d6 + deterioracao (save CON CD 17) | **Enxame Protetor** · 1d6 · save CON CD 13 · deixa envenenado · *rec. 6+, sai na rodada 1* | livro RHW |
| **Sátiro Espreita-Sombra** *(Shadowstalker Satyr)* | 2 | 15 | 55 | Lâmina Vil +5 1d6+3+1d4 ×2 | — | livro WoW |
| **Sátiro Juravil** *(Felsworn Satyr)* | 4 | 15 | 78 | Garra +5 2d6+3+1d6 ×2 | — | livro WoW |
| **Súcubo** *(Succubus)* | 4 | 15 | 66 | Garra +5 1d6+3 | **Beijo Drenante** · 3d6 · save CON CD 15 · em 3 · deixa exaustao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Tapete Sufocante** *(Rug of Smothering)* | 2 | 12 | 33 | Sufocar +5 0 | **Sufocar** · 3d6 · save FOR CD 13 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Thonot Quaggoth** *(Quaggoth Thonot)* | 3 | 13 | 45 | Garra +5 1d6+3 | — | âncora, boss |
| **Tigre-Dente-de-Sabre** *(Saber-Toothed Tiger)* | 2 | 12 | 52 | Mordida +6 1d10+5 | **Bote** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Urso-Coruja** *(Owlbear)* | 3 | 13 | 59 | Bico +7 1d10+5 + perturbacao (save SAB CD 13) | — | minion, âncora |
| **Urso-das-Cavernas** *(Cave Bear)* | 2 | 12 | 42 | Mordida +7 1d8+5 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Urso-Polar** *(Polar Bear)* | 2 | 12 | 42 | Mordida +7 1d8+5 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Veterano** *(Veteran)* | 3 | 17 | 58 | Espada Longa +5 1d8+3 | — | minion, âncora |
| **Wight** | 3 | 14 | 45 | Espada Longa +4 1d8+2 + deterioracao, exaustao (save CON CD 13) | — | âncora, boss |
| **Wight Bebedor de Vida** *(Wight Lifedrinker)* | 3 | 14 | 82 | Espada Necrótica +4 1d8+2+1d8 ×2 | **Beber Vida** · 1d8+2 · save CON CD 13 · *rec. 5+, sai na rodada 1* | livro HotB |
| **Xamã Povo-Lagarto** *(Lizardfolk Shaman)* | 2 | 13 | 27 | Mordida +4 1d6+2 | — | âncora, boss |
| **Yeti** | 3 | 12 | 51 | Garra +6 1d6+4+1d6 | **Olhar Gélido** · save CON CD 14 · deixa letargia · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Yuan-ti Malison (Tipo 1)** *(Yuan-ti Malison (Type 1))* | 3 | 12 | 66 | Mordida +5 1d4+3+2d6 + envenenado (save CON CD 13) | — | minion, âncora |
| **Yuan-ti Malison (Tipo 2)** *(Yuan-ti Malison (Type 2))* | 3 | 12 | 66 | Mordida +5 1d4+3+2d6 + envenenado (save CON CD 13) | — | minion, âncora |
| **Yuan-ti Malison (Tipo 3)** *(Yuan-ti Malison (Type 3))* | 3 | 12 | 66 | Constrição +5 2d6+3 + envenenado (save CON CD 13) | — | minion, âncora |
| **Zumbi de Ogro** *(Ogre Zombie)* | 2 | 8 | 85 | Maça Estrela +6 2d8+4 | — | minion, âncora |
| **Zumbi Propagador da Praga** *(Zombie Plague Spreader)* | 4 | 10 | 78 | Pancada +5 1d6+3+2d8 ×2 | **Miasma Virulento** · 4d6 · save CON CD 12 · em 3 · metade quem resiste · *rec. 6+, sai na rodada 1* | livro RHW |
| **Árvore das Cabeças da Morte** *(Death's Head Tree)* | 4 | 15 | 95 | Pancada +6 2d10+4 ×2 | **Cabeça Explosiva** · 3d6 · save DES CD 14 · em 3 · deixa envenenado · metade quem resiste · *a cada 2 rodadas* | livro RHW |
| **Árvore Desperta** *(Awakened Tree)* | 2 | 13 | 59 | Pancada +6 3d6+4 | — | minion, âncora |
| **Íncubo** *(Incubus)* | 4 | 15 | 66 | Garra +5 1d6+3 | **Beijo Drenante** · 3d6 · save CON CD 15 · em 3 · deixa exaustao · *rec. 5+, sai na rodada 1* | âncora, boss |

## Tier 3 — CR 5 a 8

145 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Abominação Yuan-ti** *(Yuan-ti Abomination)* | 7 | 15 | 127 | Mordida +7 1d6+4+3d6 + envenenado (save CON CD 15) · Constrição +7 2d6+4 | **Contrair** · 6d8 · save FOR CD 15 · em 4 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Agente da Marca da Sombra** *(Shadow-Marked Agent)* | 7 | 17 | 132 | Faca Sombria +8 2d4+5+4d6 ×2 | — | livro EFA |
| **Agente Phaerimm** *(Phaerimm Agent)* | 8 | 15 | 123 | Ferrão do Pavor +7 1d6+4+2d12 ×3 | — | livro FRAiF |
| **Aku'mai** | 8 | 14 | 149 | Mordida +7 1d10+4 ×3 | **Bile Cáustica** · 2d8+1d8 · save DES CD 16 · em 3 · *rec. 5+, sai na rodada 1* | livro WoW |
| **Aparição** *(Wraith)* | 5 | 13 | 67 | Drenar Vida +6 4d8+3 + deterioracao, exaustao (save CON CD 14) ×2 | — | âncora, boss |
| **Arquissacerdote Kuo-toa** *(Kuo-toa Archpriest)* | 6 | 13 | 97 | Cetro +6 1d6+3+4d6 · Ataque Desarmado +6 1d4+3 | **Maldição** · save SAB CD 14 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Assassino** *(Assassin)* | 8 | 15 | 78 | Espada Curta +6 1d6+3 + envenenado (save CON CD 15) · Besta Leve +6 1d8+3 | **Golpe Certeiro** · 3d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Barlgura** | 5 | 15 | 68 | Mordida +7 2d6+4 · Soco +7 1d10+4 | — | âncora, boss |
| **Baron Silverlaine** | 5 | 12 | 54 | Pancada de Objeto +5 2d4+2 | **Empurrão Telecinético** · 2d6+2 · save FOR CD 13 · *a cada 2 rodadas* | livro WoW |
| **Barão Sahuagin** *(Sahuagin Baron)* | 5 | 16 | 76 | Mordida +7 2d4+4 · Garras +7 2d6+4 | — | âncora, boss |
| **Bruxa da Noite** *(Night Hag)* | 5 | 17 | 112 | Garras +7 2d8+4 ×2 | **Assombrar Pesadelos** · save SAB CD 15 · em 3 · deixa exaustao, perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Bulette** | 5 | 17 | 94 | Mordida +7 4d12+4 ×2 | **Salto Devastador** · 9d10 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cambion** | 5 | 19 | 82 | Raio de Fogo +7 3d6 · Lança +7 1d6+4 | **Raio de Fogo** · 4d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Canisvil** *(Felhound)* | 5 | 15 | 84 | Mordida +6 3d6+3 · Tentáculos Agarradores +6 2d8+3 | **Beber Magia** · 3d6 · save CON CD 13 · *a cada 2 rodadas* | livro WoW |
| **Captain Greenskin** | 5 | 16 | 66 | Arpão Envenenado +6 1d8+3+2d6 ×3 | — | livro WoW |
| **Cavaleiro Githyanki** *(Githyanki Knight)* | 8 | 18 | 91 | Montante de Prata +9 2d6+6+3d6 + perturbacao (save SAB CD 15) ×2 | **Golpe Poderoso** · 7d8 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Caçador Tharashk** *(Tharashk Hunter)* | 6 | 16 | 97 | Espada Curta +7 2d6+4 ×3 | — | livro EFA |
| **CEO Viktra Mordenheim** | 7 | 15 | 123 | Bastão Elétrico +6 2d8+3 ×2 | **Seringa** · 4d4+2d10+3d6 · save CON CD 16 · deixa envenenado · *a cada 2 rodadas* | livro PL |
| **Chasme** | 6 | 15 | 84 | Probóscide +5 4d6+2+7d6 ×2 | **Zumbido Soporífero** · save CON CD 13 · em 3 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Ciclope** *(Cyclops)* | 6 | 14 | 138 | Clava Grande +9 3d8+6 · Pedra +9 4d10+6 | **Golpe Sísmico** · 7d8 · save DES CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Colosso Nimblewright** *(Nimblewright Hulk)* | 7 | 18 | 104 | Pancada Paralisante +7 2d10+4 ×4 | — | livro FRAiF |
| **Colosso Umbral** *(Umber Hulk)* | 5 | 18 | 93 | Garra +8 1d8+5 · Mandíbulas +8 2d8+5 | **Olhar Confuso** · save SAB CD 16 · em 3 · deixa perturbacao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Commander Springvale** | 5 | 18 | 66 | Golpe Maléfico +6 2d6+3 ×2 | **Escudo do Pérfido** · 4d10 · save DES CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Coágulo de Zumbis** *(Zombie Clot)* | 6 | 12 | 104 | Pancada +8 3d6+5 ×2 | **Sepultura de Carne** · 3d10+3d6 · save FOR CD 16 · atordoa 1 · *rec. 5+, sai na rodada 1* | livro RHW |
| **Cria de Vampiro** *(Vampire Spawn)* | 5 | 15 | 82 | Mordida +6 1d6+3+2d6 + deterioracao (save CON CD 14) · Garras +6 2d4+3 | — | regenera 10/rodada · âncora, boss |
| **Criação** *(Created)* | 5 | 9 | 127 | Pancada +7 2d8+4+1d8 ×2 | **Defeito** · 3d8+3d8 · save CON CD 15 · em 3 · deixa envenenado · metade quem resiste · *rec. 6+, sai na rodada 1* | livro PL |
| **Crocodilo Gigante** *(Giant Crocodile)* | 5 | 14 | 85 | Mordida +8 3d10+5 + deterioracao (save CON CD 14) · Cauda +8 2d8+5 | **Contrair** · 7d8 · save FOR CD 16 · em 3 · atordoa 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cultista de Bhaal** *(Cultist of Bhaal)* | 7 | 16 | 144 | Lâmina Amaldiçoada +7 3d6+4 ×3 | — | livro FRAiF |
| **Dardew** | 5 | 19 | 105 | Garra Flamejante +7 1d8+4+2d6 ×2 | **Acorde Poderoso** · 3d6+3 · save CON CD 14 · *a cada 2 rodadas* | livro WttHC |
| **Demodragão** *(Demodragon)* | 5 | 16 | 102 | Mordida +7 2d6+4+1d8 ×2 | **Sopro Ácido** · 4d10 · save DES CD 13 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | regenera 10/rodada · livro WttHC |
| **Devorador de Mentes** *(Mind Flayer)* | 7 | 15 | 71 | Tentáculos +7 2d10+4 · Extrair Cérebro +7 10d10 | **Rajada Mental** · 4d8+4 · save INT CD 15 · em 4 · deixa perturbacao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Devorador de Mentes Arcanista** *(Mind Flayer Arcanist)* | 8 | 15 | 71 | Tentáculos +7 2d10+4 ×2 | **Rajada Mental** · 4d8+4 · save INT CD 15 · em 4 · deixa perturbacao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Devorador de Mentes Vampiro** *(Vampire Mind Flayer)* | 5 | 15 | 85 | Garra +7 1d8+4+3d6 ×3 · Tentáculos +7 2d6+4 | **Explosão Mental** · save INT CD 15 · em 3 · atordoa 2 · *rec. 5+, sai na rodada 1* | livro RHW |
| **Diabo Acorrentado** *(Chain Devil)* | 8 | 16 | 85 | Corrente +8 2d6+4 + deterioracao (save CON CD 15) ×2 | **Máscara Perturbadora** · save SAB CD 15 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Diabo Farpado** *(Barbed Devil)* | 5 | 15 | 110 | Cauda +6 2d6+3 + deterioracao (save CON CD 14) · Garra +6 1d6+3 | **Lançar Chama** · 5d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragonete da Revoada Azul** *(Blue Dragonflight Whelp)* | 7 | 16 | 120 | Dilacerar +7 4d6+4 ×3 | **Sopro Congela-Magia** · 9d6 · save CON CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragonete da Revoada Verde** *(Green Dragonflight Whelp)* | 6 | 16 | 127 | Dilacerar +7 3d6+4 ×3 | **Sopro de Gás Esmeralda** · 4d6+4d6 · save CON CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragonete da Revoada Vermelha** *(Red Dragonflight Whelp)* | 8 | 16 | 135 | Dilacerar +7 5d6+4 ×3 | **Sopro de Fogo Arrasador** · 12d6 · save DES CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão Branco Jovem** *(Young White Dragon)* | 6 | 17 | 133 | Mordida +7 2d10+4+1d8 · Garra +7 2d6+4 | **Sopro Gélido** · 10d8 · save CON CD 15 · em 3 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Bronze Jovem** *(Young Bronze Dragon)* | 8 | 18 | 142 | Mordida +8 2d10+5 + perturbacao (save CON CD 15) · Garra +8 2d6+5 | **Armas de Sopro** · 10d10 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Cobre Jovem** *(Young Copper Dragon)* | 7 | 17 | 119 | Mordida +7 2d10+4 · Garra +7 2d6+4 | **Armas de Sopro** · 9d8 · save DES CD 14 · em 4 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Latão Jovem** *(Young Brass Dragon)* | 6 | 17 | 110 | Mordida +7 2d10+4 · Garra +7 2d6+4 | **Armas de Sopro** · 12d6 · save DES CD 14 · em 3 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Espiritual Jovem** *(Young Spirit Dragon)* | 8 | 17 | 152 | Dilacerar +7 3d6+4+2d6 ×3 | **Sopro Ruinoso** · 8d8 · save CON CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Negro Jovem** *(Young Black Dragon)* | 7 | 18 | 127 | Mordida +7 2d10+4+1d8 · Garra +7 2d6+4 | **Sopro Ácido** · 11d8 · save DES CD 14 · em 4 · deixa deterioracao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Profundo Jovem** *(Young Deep Dragon)* | 5 | 16 | 93 | Dilacerar +7 2d6+4+1d6 ×3 | **Sopro de Pesadelo** · 4d10 · save SAB CD 14 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Verde Jovem** *(Young Green Dragon)* | 8 | 18 | 136 | Mordida +7 2d10+4+2d6 · Garra +7 2d6+4 | **Sopro Venenoso** · 12d6 · save CON CD 14 · em 4 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Drider** | 6 | 19 | 123 | Espada Longa +6 1d8+3 + envenenado (save CON CD 14) · Arco Longo +6 1d8+3+1d8 | **Teia** · save FOR CD 15 · em 3 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Edwin VanCleef** | 5 | 16 | 93 | Cimitarra +7 1d6+4 ×3 | — | livro WoW |
| **Elemental da Terra** *(Earth Elemental)* | 5 | 17 | 126 | Pancada +8 2d8+5 ×2 | **Golpe Sísmico** · 5d8 · save DES CD 16 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental da Água** *(Water Elemental)* | 5 | 14 | 114 | Pancada +7 2d8+4 ×2 | **Whelm** · 2d8+4+2d8+4 · save FOR CD 15 · em 3 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental do Ar** *(Air Elemental)* | 5 | 15 | 90 | Pancada +8 2d8+5 ×2 | **Redemoinho** · 3d8+2+1d6 · save FOR CD 13 · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental do Fogo** *(Fire Elemental)* | 5 | 13 | 102 | Toque +6 2d6+3+1d10 ×2 | **Explosão de Chamas** · 6d8 · save DES CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Encarnação da Transitoriedade** *(Incarnation of Transience)* | 7 | 16 | 142 | Mordida +8 2d8+5 ×3 | **Debandada Espectral** · 4d8 · save DES CD 16 · metade quem resiste · *a cada 2 rodadas* | livro LFL |
| **Espreitador Invisível** *(Invisible Stalker)* | 6 | 14 | 104 | Pancada +6 2d6+3 + perturbacao (save SAB CD 14) ×2 | — | âncora, boss |
| **Espreitador Manto** *(Cloaker)* | 8 | 14 | 78 | Mordida +6 2d6+3 + perturbacao (save SAB CD 15) · Cauda +6 1d8+3 | **Gemido** · save SAB CD 14 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Ez d'Avenir** | 8 | 14 | 120 | Lâmina do Caçador +7 1d8+4+2d10 ×3 | — | livro RHW |
| **Fomoriano** *(Fomorian)* | 8 | 14 | 149 | Clava Grande +9 3d8+6 ×2 | **Mau-Olhado** · save SAB CD 17 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Furbolg Ursa** | 5 | 13 | 110 | Azagaia +7 2d6+4 ×3 | **Pisão Trovejante** · 2d6 · save CON CD 14 · *a cada 2 rodadas* | livro WoW |
| **Galeb Duhr** | 6 | 16 | 85 | Pancada +8 2d6+5 ×2 | — | âncora, boss |
| **Gelihast** | 5 | 15 | 78 | Cimitarra +7 1d6+4 ×4 | **Rede Grudenta** · save DES CD 15 · atordoa 1 · *a cada 2 rodadas* | livro WoW |
| **Gerta von Aubrecker** | 5 | 14 | 84 | Criopistola +6 3d8+3 ×3 | **Criocanhão** · 8d8 · save CON CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro PL |
| **Ghamoo-Ra** | 7 | 17 | 126 | Garra +7 1d8+4 ×2 · Mordida +7 2d10+4 | **Giro da Carapaça** · 6d6 · save DES CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Gigante da Colina** *(Hill Giant)* | 5 | 13 | 105 | Clava Grande +8 3d8+5 · Pedra +8 3d10+5 | **Golpe Sísmico** · 6d8 · save DES CD 16 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gigante da Pedra** *(Stone Giant)* | 7 | 17 | 126 | Clava Grande +9 3d8+6 + perturbacao (save DES CD 15) · Pedra +9 4d10+6 | **Golpe Sísmico** · 6d8 · save DES CD 17 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gigante de Lorwyn** *(Lorwyn Giant)* | 6 | 13 | 115 | Espada de Pedra +8 3d10+5 ×2 | — | livro LFL |
| **Gigante de Shadowmoor** *(Shadowmoor Giant)* | 8 | 14 | 172 | Clava de Árvore +9 2d10+6 ×3 | **Cataclismo de Magia Selvagem** · 8d6 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro LFL |
| **Gigante do Gelo** *(Frost Giant)* | 8 | 15 | 138 | Machado Grande +9 3d12+6 + exaustao (save CON CD 15) · Pedra +9 4d10+6 | **Golpe Sísmico** · 9d8 · save DES CD 17 · em 5 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gladiador** *(Gladiator)* | 5 | 16 | 112 | Lança +7 2d6+4 + perturbacao (save SAB CD 14) · Escudada +7 2d4+4 | **Escudada** · save FOR CD 18 · em 3 · atordoa 1 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Golem de Carne** *(Flesh Golem)* | 5 | 9 | 93 | Pancada +7 2d8+4 + perturbacao (save DES CD 14) ×2 | **Golpe Poderoso** · 5d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Grick Alfa** *(Grick Alpha)* | 7 | 18 | 75 | Cauda +7 2d6+4 + deterioracao (save CON CD 15) · Tentáculos +7 4d8+4 | — | âncora, boss |
| **Guardião Kundarak** *(Kundarak Warden)* | 5 | 14 | 82 | Chicote Arcano +6 3d6+3 ×2 | **Glifo Algemador** · save FOR CD 14 · atordoa 1 · *rec. 6+, sai na rodada 1* | livro EFA |
| **Guardião Protetor** *(Shield Guardian)* | 7 | 17 | 142 | Soco +7 2d6+4 + exaustao (save CON CD 15) ×2 | — | regenera 10/rodada · âncora, boss |
| **Guerreiro de Elite Drow** *(Drow Elite Warrior)* | 5 | 18 | 71 | Espada Curta +7 1d6+4+3d6 + envenenado (save CON CD 14) · Besta de Mão +7 1d6+4 | **Golpe Certeiro** · 6d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Guerreiro de Elite Drow de Lolth** *(Drow Elite Warrior of Lolth)* | 5 | 18 | 71 | Espada Curta +7 2d6+4+3d6 ×2 | — | livro FRAiF |
| **Górgona** *(Gorgon)* | 5 | 19 | 114 | Chifrada +8 2d12+5 · Cascos +8 2d10+5 | **Petrifying Breath** · save CON CD 13 · em 3 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Hezrou** | 8 | 16 | 136 | Mordida +7 2d10+4 · Garras +7 2d6+4 | **Fedor** · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Hidra** *(Hydra)* | 8 | 15 | 172 | Mordida +8 1d10+5 + perturbacao (save SAB CD 15) ×2 | **Golpe Poderoso** · 5d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Homem-Serpe** *(Werewyvern)* | 8 | 16 | 152 | Azagaia +7 4d6+4 ×3 | — | livro FRAiF |
| **Homem-Urso** *(Werebear)* | 5 | 10 | 135 | Garra +7 2d8+4 + perdicao (save SAB CD 14) · Machado Grande +7 1d12+4 | **Golpe Poderoso** · 5d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Horror Indizível** *(Unspeakable Horror)* | 8 | 13 | 126 | Ataque Fantasmagórico +8 4d6 ×3 | — | regenera 10/rodada · livro RHW |
| **Horror Pustulento** *(Pustulating Horror)* | 7 | 9 | 152 | Pancada +7 2d8+4 ×2 | **Cuspir Praga** · 3d6 · save DES CD 15 · deixa envenenado · *a cada 2 rodadas* | livro ICC |
| **Infiltrador do Sonho Sombrio** *(Dreaming Dark Infiltrator)* | 7 | 15 | 104 | Lâmina Mental +7 3d6+4 ×3 | **Maldição Mental** · 4d6 · save SAB CD 15 · metade quem resiste · *a cada 2 rodadas* | livro EFA |
| **Inquisidor da Espada** *(Inquisitor of the Sword)* | 8 | 16 | 120 | Espada Longa Prateada +7 2d8+4+1d8 ×3 | — | livro RHW |
| **Inquisidor do Fogo Mental** *(Inquisitor of the Mind Fire)* | 8 | 16 | 104 | Espada Longa Prateada +8 2d8+5+1d8 + medo (save SAB CD 20) ×3 | **Comando do Inquisidor** · save SAB CD 16 · em 3 · atordoa 1 · *rec. 5+, sai na rodada 1* | livro RHW |
| **Inquisidor do Tomo** *(Inquisitor of the Tome)* | 8 | 14 | 88 | Lâmina de Energia +7 4d8+4 ×3 | **Implodir** · 6d8 · save DES CD 15 · em 3 · metade quem resiste · *rec. 4+, sai na rodada 1* | livro RHW |
| **Ivan Dilisnya** | 5 | 12 | 90 | Pata Dianteira +7 2d6+4 ×2 | **Engenhoca Mortal** · 3d8 · save DES CD 15 · *a cada 2 rodadas* | livro RHW |
| **Ivana Boritsi** | 5 | 17 | 104 | Toque Tóxico +7 1d8+4 ×2 | **Perfume Sufocante** · 3d8 · save CON CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Karas Chembryl** | 8 | 17 | 104 | Adaga do Pavor +8 2d4+5+1d8 ×2 | — | livro FRAiF |
| **Lady Sarevess** | 8 | 16 | 135 | Rajada de Relâmpago +7 4d6 ×3 | — | livro WoW |
| **Laçador** *(Roper)* | 5 | 20 | 93 | Tentáculo +7 0 · Mordida +7 4d8+4 | **Tentáculos** · save FOR CD 15 · em 3 · deixa perturbacao · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Lord Godfrey** | 6 | 16 | 104 | Pistola com Lâmina +6 2d10+3 + medo (save SAB CD 18) ×2 | **Rajada de Pistola** · 8d6 · save DES CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Lord Walden** | 6 | 16 | 97 | Lasca de Gelo +7 2d10 ×2 | **Frascos Alquímicos** · 2d6+1d6 · save CON CD 15 · em 3 · deixa envenenado · metade quem resiste · *a cada 2 rodadas* | livro WoW |
| **Macaco Gigante** *(Giant Ape)* | 7 | 12 | 157 | Soco +9 3d10+6 + perturbacao (save CON CD 15) · Pedra +9 7d6+6 | **Arremesso de Pedra** · 7d8 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Magen Terrano** *(Terran Magen)* | 8 | 21 | 121 | Punho-Martelo +6 3d8+3+3d8 ×2 | — | livro NF |
| **Magen Virvos** *(Virvos Magen)* | 6 | 21 | 110 | Rajada Psíquica +6 6d6 ×2 | — | livro NF |
| **Mago** *(Mage)* | 6 | 12 | 40 | Adaga +5 1d4+2 + perturbacao (save INT CD 14) ×2 | **Bola de Fogo** · 8d6 · save DES CD 17 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mago Drow** *(Drow Mage)* | 7 | 12 | 45 | Cajado +2 1d6-1 + perturbacao (save SAB CD 15) ×2 | **Relâmpago** · 8d6 · save DES CD 14 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mago Drow de Lolth** *(Drow Mage of Lolth)* | 7 | 15 | 81 | Rajada Abissal +6 4d8+3 ×3 | — | livro FRAiF |
| **Mamute** *(Mammoth)* | 6 | 13 | 126 | Chifrada +10 4d8+7 · Pisão +10 4d10+7 | **Investida Selvagem** · 9d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Marechal Sentinela** *(Sentinel Marshal)* | 6 | 16 | 110 | Espada Longa +7 2d8+4 ×3 | — | livro EFA |
| **Medusa** | 6 | 15 | 127 | Cabelo de Serpentes +5 1d4+2+4d6 · Espada Curta +5 1d6+2 | **Olhar Petrificante** · save CON CD 14 · em 3 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Merrow Arengador** *(Merrow Haranguer)* | 5 | 14 | 90 | Cetro de Coral +7 2d10+4 ×3 | **Invectiva** · 4d6 · save SAB CD 15 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro LFL |
| **Mezzoloth** | 5 | 18 | 75 | Garras +7 2d4+4 · Tridente +7 1d6+4 | — | âncora, boss |
| **Monte Cambaleante** *(Shambling Mound)* | 5 | 15 | 136 | Pancada +7 2d8+4 + perturbacao (save DES CD 14) ×2 | **Engolfar** · 5d8 · save FOR CD 15 · em 3 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mother Lorinda** | 8 | 18 | 105 | Marca da Mãe +7 1d8+4+1d10 ×2 | **Semblante da Mãe** · save SAB CD 14 · deixa medo · *rec. 6+, sai na rodada 1* | livro RHW |
| **Naga Bruxa do Mar** *(Naga Sea Witch)* | 7 | 14 | 136 | Rajada de Relâmpago +7 5d6 ×3 | — | livro WoW |
| **Naga Espiritual** *(Spirit Naga)* | 8 | 15 | 75 | Mordida +7 1d6+4 + envenenado (save CON CD 15) ×2 | **Raio Elétrico** · 8d6 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Naga Mirmidão** *(Naga Myrmidon)* | 5 | 18 | 112 | Lâmina do Oceano +7 2d8+4 ×3 · Tridente +7 2d8+4 ×2 | — | livro WoW |
| **Necricor** *(Necrichor)* | 7 | 14 | 85 | Rajada Necrótica +6 2d8+3+2d10 + envenenado (save CON CD 18) ×2 | **Marionete de Sangue** · save CON CD 15 · atordoa 1 · *rec. 6+, sai na rodada 1* | livro RHW |
| **Nightgaunt** | 8 | 16 | 136 | Garra +8 2d8+5+3d6 ×2 | **Cócegas** · save SAB CD 16 · atordoa 1 · *a cada 2 rodadas* | livro RHW |
| **Oni** | 7 | 16 | 110 | Garra +7 1d8+4 + perturbacao (save DES CD 15) · Glaive +7 2d10+4 | **Cone Gélido** · 8d8 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Orador da Forca** *(Gallows Speaker)* | 6 | 13 | 75 | Lâminas Giratórias +6 3d6+3+3d4 ×2 | **Vento Uivante** · 4d8 · save CON CD 15 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Otyugh** | 5 | 14 | 114 | Mordida +6 2d8+3 + perturbacao (save SAB CD 14) · Tentáculo +6 1d8+3+1d8 | — | âncora, boss |
| **Planta Toma-Corpos** *(Bodytaker Plant)* | 7 | 16 | 138 | Vinha +7 3d8+4 ×3 | **Vagem Aprisionadora** · save FOR CD 15 · deixa perdicao · atordoa 1 · *a cada 2 rodadas* | livro RHW |
| **Pároco** *(Curate)* | 6 | 12 | 97 | Radiância Celestial +7 4d8 ×3 | — | livro HotB |
| **Quimera** *(Chimera)* | 6 | 14 | 114 | Mordida +7 2d6+4 + perturbacao (save SAB CD 14) · Chifres +7 1d12+4 | **Sopro de Fogo** · 7d8 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Redemoinho Místico** *(Eldritch Eddy)* | 6 | 11 | 144 | Golpe Abrasador +6 3d6+3 ×2 | — | livro NF |
| **Remorhaz Jovem** *(Young Remorhaz)* | 5 | 14 | 93 | Mordida +6 3d10+4+2d6 ×2 | — | âncora, boss |
| **Retalhador Implacável** *(Relentless Slasher)* | 8 | 15 | 91 | Faca do Retalhador +7 2d4+4+6d6 ×2 | — | livro RHW |
| **Revenante** *(Revenant)* | 5 | 13 | 136 | Soco +7 2d6+4+4d6 ×2 | **Olhar Vingativo** · save SAB CD 15 · em 3 · atordoa 2 · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Rudolph van Richten** | 5 | 13 | 105 | Bengala-Espada de Prata +5 1d6+2+2d4 + envenenado (save CON CD 17) ×3 | **Repelir o Mal** · 4d8 · save CAR CD 15 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Rudolph von Aubrecker** | 6 | 15 | 112 | Taser +6 4d6 + efeito (save CON CD 18) | — | livro PL |
| **Sacerdote de Osybus** *(Priest of Osybus)* | 6 | 12 | 60 | Lâmina da Alma +7 2d4+4 + efeito (save CON CD 19) ×2 | — | livro RHW |
| **Sacerdotisa Drow de Lolth** *(Drow Priestess of Lolth)* | 8 | 16 | 71 | Flagelo +5 1d6+2+5d6 ×2 | **Maldição** · save SAB CD 18 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Salamandra** *(Salamander)* | 5 | 15 | 90 | Lança +7 2d6+4 · Cauda +7 2d6+4+2d6 | — | âncora, boss |
| **Senhor da Guerra Hobgoblin** *(Hobgoblin Warlord)* | 6 | 20 | 97 | Azagaia +9 1d6+3 · Espada Longa +9 1d8+3 | — | âncora, boss |
| **Serpe** *(Wyvern)* | 6 | 13 | 110 | Mordida +7 2d6+4 + envenenado (save CON CD 14) · Ferrão +7 2d6+4 | — | âncora, boss |
| **Slaad Azul** *(Blue Slaad)* | 7 | 15 | 123 | Mordida +8 2d6+5 + perturbacao (save SAB CD 15) · Garra +8 2d6+5 | — | regenera 10/rodada · âncora, boss |
| **Slaad Verde** *(Green Slaad)* | 8 | 16 | 127 | Mordida +7 2d6+4 + perturbacao (save SAB CD 15) · Garra +7 1d6+4 | **Bola de Fogo** · 8d6 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Slaad Vermelho** *(Red Slaad)* | 5 | 14 | 93 | Mordida +6 2d4+3 + deterioracao, perturbacao (save CON CD 14) · Garra +6 1d8+3 | — | regenera 10/rodada · âncora, boss |
| **Subchefe Boromar** *(Boromar Underboss)* | 8 | 16 | 104 | Lâmina Envenenada +7 2d8+4+2d6 + envenenado (save CON CD 19) ×3 | — | livro EFA |
| **Tecedor de Espinhos Javaliano** *(Quilboar Thornweaver)* | 7 | 17 | 104 | Cajado de Espinhos +7 2d8+4 ×3 | — | livro WoW |
| **Tiranossauro Rex** *(Tyrannosaurus Rex)* | 8 | 13 | 136 | Mordida +10 4d12+7 + deterioracao (save CON CD 15) · Cauda +10 3d8+7 | **Golpe Poderoso** · 8d10 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Tricerátopo** *(Triceratops)* | 5 | 13 | 95 | Chifrada +9 4d8+6 · Pisão +9 3d10+6 | **Investida Selvagem** · 9d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Troll** | 5 | 15 | 84 | Mordida +7 1d6+4 + medo (save SAB CD 14) · Garra +7 2d6+4 | **Golpe Poderoso** · 4d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Twilight Lord Kelris** | 7 | 16 | 120 | Rajada Mental +8 2d10+5 ×3 | — | livro WoW |
| **Unicórnio** *(Unicorn)* | 5 | 12 | 67 | Cascos +7 2d6+4 · Chifre +7 1d8+4 ×2 | — | âncora, boss |
| **Vampiro Nosferatu** *(Vampire Nosferatu)* | 8 | 16 | 85 | Mordida +8 1d8+5+2d10 + deterioracao (save CON CD 20) · Garra +8 1d8+5 ×2 | **Jorro de Sangue** · 6d8 · save CON CD 16 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | regenera 10/rodada · livro RHW |
| **Veterano Meio-Dragão Vermelho** *(Half-Red Dragon Veteran)* | 5 | 18 | 65 | Espada Longa +5 1d8+3 + perturbacao (save SAB CD 14) · Espada Curta +5 1d6+3 | **Sopro de Fogo** · 7d6 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Viktra Mordenheim** | 7 | 15 | 123 | Bastão Elétrico +6 2d8+3 ×2 | **Seringa** · 4d4+2d10+3d6 · save CON CD 16 · deixa envenenado · *a cada 2 rodadas* | livro RHW |
| **Vrock** | 6 | 15 | 104 | Bico +6 2d6+3 · Garras +6 2d10+3 | **Esporos** · 1d10 · save CON CD 14 · em 3 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Wilfred Godefroy** | 6 | 12 | 72 | Pancada de Objeto +6 2d6+3 ×2 | — | livro RHW |
| **Xorn** | 5 | 19 | 73 | Garra +6 1d6+3 · Mordida +6 3d6+3 | — | âncora, boss |
| **Zerth Githzerai** *(Githzerai Zerth)* | 6 | 17 | 84 | Ataque Desarmado +7 2d6+4+3d8 ×2 | — | âncora, boss |
| **Zumbi Beholder** *(Beholder Zombie)* | 5 | 15 | 93 | Mordida +3 4d6 + medo, perturbacao (save SAB CD 14) ×2 | — | âncora, boss |

## Tier 4 — CR 9 a 13

92 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Aboleth** | 10 | 17 | 135 | Tentáculo +9 2d6+5 · Cauda +9 3d6+5 ×3 | **Escravizar Mente** · save SAB CD 17 · em 4 · deixa perturbacao, deterioracao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Abominação** *(Abomination)* | 12 | 14 | 168 | Cutelo +9 3d10+5+2d6 ×2 · Esmagar +9 3d10+5 + efeito (save CON CD 21) | **Consumir Vida** · 2d10 · save CON CD 16 · *a cada 2 rodadas* | livro WoW |
| **Adam** | 12 | 18 | 161 | Pancada +10 2d6+6+2d6 ×2 | **Esmagar** · 2d6+6+2d6 · save FOR CD 18 · atordoa 1 · *a cada 2 rodadas* | livro PL |
| **Alzzin the Wildshaper** | 13 | 18 | 204 | Garra Vil +12 1d8+7+2d6 ×2 | **Enervação** · 4d8 · save CON CD 19 · *a cada 2 rodadas* | livro WoW |
| **Andarilho das Sombras Umbragen** *(Umbragen Shadow Walker)* | 9 | 14 | 162 | Rajada Lúgubre +9 2d8+5 ×3 | **Capuz Sombrio** · 4d6 · save SAB CD 17 · deixa perdicao · *a cada 2 rodadas* | livro EFA |
| **Arcanaloth** | 12 | 17 | 104 | Garras +7 2d4+3 ×3 | **Maldição Arcana** · save SAB CD 17 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | boss |
| **Arcanist Doan** | 10 | 15 | 165 | Explosão Arcana +9 3d8+5 ×3 | **Detonar** · 7d10 · save DES CD 17 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro WoW |
| **Arquimago** *(Archmage)* | 12 | 12 | 99 | Adaga +6 1d4+2 + perturbacao (save SAB CD 16) ×3 | **Bola de Fogo** · 8d6 · save DES CD 21 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Assassino Mental do Sonho Sombrio** *(Dreaming Dark Mindkiller)* | 11 | 19 | 180 | Sussurro de Pesadelo +9 5d8+5 + medo (save SAB CD 21) ×2 | **Medo Primordial** · 10d6 · save SAB CD 17 · em 3 · deixa medo · metade quem resiste · *rec. 6+, sai na rodada 1* | livro EFA |
| **Beemote Enferrujado** *(Rusted Behemoth)* | 9 | 18 | 157 | Pancada +10 4d6+6 ×3 | — | livro FRAiF |
| **Behir** | 11 | 17 | 168 | Mordida +10 3d10+6 + perturbacao (save SAB CD 16) · Constrição +10 2d10+6+2d10+6 ×2 | **Sopro de Relâmpago** · 12d10 · save DES CD 16 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Biha Babir** | 12 | 17 | 229 | Rajada Marinha +10 2d10+6 ×2 | — | livro FRAiF |
| **Bloodmage Thalnos** | 9 | 15 | 153 | Seta Sombria +9 3d10+5 ×3 | **Vendaval Espiritual** · 6d8 · save DES CD 17 · em 3 · atordoa 1 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Brutamontes Daask** *(Daask Bruiser)* | 9 | 17 | 150 | Socar +9 2d6+5 ×3 | **Olhar Feroz** · save SAB CD 14 · deixa medo · *a cada 2 rodadas* | livro EFA |
| **Chakuna** | 11 | 16 | 210 | Arranhão +8 2d8+4 ×3 | — | livro RHW |
| **Cho'Rush the Observer** | 9 | 11 | 133 | Cajado do Relâmpago +11 3d10 ×2 | — | livro WoW |
| **Colosso Implacável** *(Relentless Juggernaut)* | 12 | 16 | 168 | Lâmina do Carrasco +10 3d8+6 ×2 | — | regenera 10/rodada · livro RHW |
| **Condenado** *(The Damned)* | 12 | 16 | 170 | Garra Ceifadora +9 3d10+5+2d8 ×2 | — | livro ICC |
| **Cultista de Bane** *(Cultist of Bane)* | 9 | 16 | 142 | Manopla +8 3d8+4 ×3 | — | livro FRAiF |
| **Cultista de Myrkul** *(Cultist of Myrkul)* | 11 | 16 | 204 | Rajada Necrótica +9 5d10 ×3 | — | livro FRAiF |
| **Dao** | 11 | 18 | 187 | Soco +10 2d8+6 · Marreta +10 4d6+6 ×2 | **Golpe Sísmico** · 5d8 · save DES CD 19 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Demônio da Cripta Nerubiano** *(Nerubian Crypt Fiend)* | 13 | 17 | 187 | Garra +12 4d10+7+2d6 ×3 | **Teia Necrótica** · 2d10+2d10 · save DES CD 20 · atordoa 1 · *a cada 2 rodadas* | livro WoW |
| **Deva** | 10 | 17 | 136 | Maça +8 1d6+4+4d8 ×3 | **Luz Radiante** · 9d8 · save CON CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Diabo Chifrudo** *(Horned Devil)* | 11 | 18 | 178 | Forcado +10 2d8+6 + deterioracao (save CON CD 16) · Cauda +10 1d8+6 ×2 | — | âncora, boss |
| **Diabo Orador** *(Speaker Devil)* | 12 | 17 | 189 | Alabarda Trovejante +9 2d10+5+4d6 ×2 | **Palavra de Desfazer** · 4d10 · save CON CD 18 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro ABH |
| **Diabo Ósseo** *(Bone Devil)* | 9 | 19 | 142 | Garra +8 1d8+4 · Ferrão +8 2d8+4+5d6 | **Ferrão Venenoso** · 4d6 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Djinni** | 11 | 17 | 161 | Cimitarra +9 2d6+5+1d6 ×3 | **Redemoinho** · 6d8 · save FOR CD 18 · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Draco da Revoada Azul** *(Blue Dragonflight Drake)* | 13 | 19 | 187 | Dilacerar +13 7d6+8 ×3 | **Sopro Congela-Magia** · 17d6 · save CON CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Draco da Revoada Verde** *(Green Dragonflight Drake)* | 12 | 19 | 225 | Dilacerar +12 5d6+8 ×3 | **Sopro de Gás Esmeralda** · 7d6+7d6 · save CON CD 19 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragonete da Revoada Bronze** *(Bronze Dragonflight Whelp)* | 10 | 17 | 172 | Dilacerar +8 6d6+4 ×3 | **Sopro de Areia Escaldante** · 7d6+7d6 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragonete da Revoada Negra** *(Black Dragonflight Whelp)* | 9 | 16 | 165 | Dilacerar +8 4d6+4 ×3 | **Sopro de Magma** · 6d8+6d8 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão Azul Jovem** *(Young Blue Dragon)* | 9 | 18 | 152 | Mordida +9 2d10+5+1d10 · Garra +9 2d6+5 | **Sopro de Relâmpago** · 10d10 · save DES CD 16 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Branco Adulto** *(Adult White Dragon)* | 13 | 18 | 200 | Mordida +11 2d10+6+1d8 · Garra +11 2d6+6 ×3 | **Sopro Gélido** · 12d8 · save CON CD 19 · em 5 · deixa medo, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Latão Adulto** *(Adult Brass Dragon)* | 13 | 18 | 172 | Mordida +11 2d10+6 · Garra +11 2d6+6 ×3 | **Armas de Sopro** · 13d6 · save DES CD 18 · em 5 · deixa medo, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Ouro Jovem** *(Young Gold Dragon)* | 10 | 18 | 178 | Mordida +10 2d10+6 · Garra +10 2d6+6 ×2 | **Armas de Sopro** · 10d10 · save DES CD 17 · em 4 · deixa perturbacao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Prata Jovem** *(Young Silver Dragon)* | 9 | 18 | 168 | Mordida +10 2d10+6 · Garra +10 2d6+6 | **Armas de Sopro** · 12d8 · save CON CD 17 · em 4 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Profundo Adulto** *(Adult Deep Dragon)* | 11 | 17 | 161 | Dilacerar +9 2d8+5+1d10 ×3 | **Sopro de Pesadelo** · 7d10 · save SAB CD 15 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Vermelho das Sombras Jovem** *(Young Red Shadow Dragon)* | 13 | 18 | 178 | Mordida +11 2d10+6+1d6 · Garra +11 2d6+6 ×2 | **Shadow Breath** · 16d6 · save DES CD 18 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Dragão Vermelho Jovem** *(Young Red Dragon)* | 10 | 18 | 178 | Mordida +10 2d10+6+1d6 · Garra +10 2d6+6 ×2 | **Sopro de Fogo** · 16d6 · save DES CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dullahan** | 10 | 15 | 127 | Lâmina Decapitadora +8 1d10+4+2d10 ×2 | **Lamento sem Cabeça** · 2d12 · save CON CD 15 · em 3 · deixa medo · metade quem resiste · *a cada 2 rodadas* | livro RHW |
| **Ebonbane** | 13 | 17 | 130 | Corte de Chama Sombria +9 1d10+4+3d6 ×3 | **Portador Digno** · 8d8 · save CAR CD 17 · *a cada 2 rodadas* | livro RHW |
| **Efreeti** | 11 | 17 | 200 | Cimitarra +10 2d6+6+2d6 · Lançar Chama +7 5d6 ×2 | **Muralha de Fogo** · 8d8 · save DES CD 19 · em 4 · deixa exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Encarnação da Vivacidade** *(Incarnation of Vibrance)* | 10 | 14 | 230 | Vinha +9 3d8+5 ×2 | **Explosão Radiante** · 2d8+5 · save CON CD 17 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro LFL |
| **Ente** *(Treant)* | 9 | 16 | 138 | Pancada +10 3d6+6 + perturbacao (save DES CD 16) · Pedra +10 4d10+6 | **Vinhas Constritoras** · save FOR CD 18 · em 4 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Erínia** *(Erinyes)* | 12 | 18 | 153 | Espada Longa +8 1d8+4 · Arco Longo +7 1d8+3+3d8 ×2 | **Flecha Envenenada** · 4d6 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | boss |
| **Esporo de Moander** *(Spore of Moander)* | 12 | 19 | 230 | Gavinha +10 1d10+6+3d6 ×4 | **Consumir** · 5d6 · save FOR CD 18 · deixa perdicao · atordoa 1 · *a cada 2 rodadas* | livro FRAiF |
| **Fera de Malar** *(Beast of Malar)* | 11 | 17 | 168 | Mordida +9 4d8+5 ×3 | — | regenera 20/rodada · livro FRAiF |
| **Gigante da Tempestade** *(Storm Giant)* | 13 | 16 | 230 | Montante +14 6d6+9 · Pedra +14 4d12+9 ×2 | **Raio** · 12d8 · save DES CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Gigante das Nuvens** *(Cloud Giant)* | 9 | 14 | 200 | Maça Estrela +12 3d8+8 · Pedra +12 4d10+8 | **Golpe Sísmico** · 8d8 · save DES CD 20 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gigante do Fogo** *(Fire Giant)* | 9 | 18 | 162 | Montante +11 6d6+7 · Pedra +11 4d10+7 | **Golpe Sísmico** · 9d10 · save DES CD 19 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Ginoesfinge** *(Gynosphinx)* | 11 | 17 | 136 | Garra +8 2d8+4 ×4 | **Rugido** · save SAB CD 16 · em 5 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Glabrezu** | 9 | 17 | 157 | Pinça +9 2d10+5 · Soco +9 2d4+2 | **Palavra de Poder** · save CON CD 17 · em 4 · atordoa 2 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Golem de Argila** *(Clay Golem)* | 9 | 14 | 133 | Pancada +8 2d10+5 + deterioracao (save CON CD 16) ×2 | — | âncora, boss, solo |
| **Golem de Pedra** *(Stone Golem)* | 10 | 17 | 178 | Pancada +10 3d8+6 + perturbacao (save DES CD 16) ×3 | **Slow** · save SAB CD 17 · em 4 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Guarda Apocalíptico** *(Doomguard)* | 11 | 16 | 180 | Garra Vil +9 4d6+5+3d6 ×2 · Chifrada +9 6d6+5 | **Pisada de Guerra** · 9d8 · save FOR CD 17 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro WoW |
| **Guerreiro Nerubiano** *(Nerubian Warrior)* | 11 | 17 | 199 | Mordida +11 3d10+7+2d10 · Garra +11 3d10+7 ×2 | **Fio de Teia** · 2d10+2d8 · save DES CD 19 · atordoa 1 · *a cada 2 rodadas* | livro WoW |
| **Gug** | 12 | 16 | 250 | Garra +10 3d10+6 ×2 | **Mastigar** · 3d6 · save DES CD 18 · atordoa 1 · *a cada 2 rodadas* | matilha · livro RHW |
| **High Inquisitor Sally Whitemane** | 13 | 16 | 130 | Cajado Sagrado +10 4d10+5 ×2 | — | livro WoW |
| **Houndmaster Loksey** | 9 | 16 | 170 | Machadinha +9 1d6+5 ×2 | — | livro WoW |
| **Illyanna Ravenoak** | 11 | 18 | 127 | Cimitarra +10 1d6+6+2d4 ×3 | — | livro WoW |
| **Infernal** | 12 | 18 | 195 | Pancada +11 2d8+7+2d8 ×2 | **Arremessar Fogo Vil** · 4d6+4d6 · save DES CD 19 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Jiangshi** | 9 | 16 | 119 | Pancada +8 2d8+4 ×3 | **Consumir Energia** · 4d8 · save CON CD 16 · metade quem resiste · *a cada 2 rodadas* | livro RHW |
| **Loup Garou** | 13 | 17 | 187 | Espada Longa +12 2d10+7+1d6 ×2 | — | livro RHW |
| **Luniscante** *(Moonkin)* | 11 | 17 | 153 | Garra Enluarada +9 2d12+5+2d6 ×3 | — | livro WoW |
| **Madam Eva** | 10 | 15 | 117 | Adaga Amaldiçoada +9 2d4+5+6d6 ×3 | **Visões Apocalípticas** · 7d6+7d6 · save SAB CD 17 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Manshoon** | 13 | 15 | 214 | Rajada Arcana +11 4d12+6 ×3 | — | livro FRAiF |
| **Marid** | 11 | 17 | 229 | Tridente +10 2d6+6 + perturbacao (save SAB CD 16) ×3 | **Onda de Água** · 6d6 · save FOR CD 20 · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mi-Go** | 9 | 16 | 120 | Pinça +9 4d8+5+3d10 ×2 | **Raio Atordoante** · 4d10+3d6 · save DES CD 17 · atordoa 1 · *rec. 4+, sai na rodada 1* | livro RHW |
| **Monstro de Mordenheim** *(Mordenheim's Monster)* | 12 | 18 | 161 | Pancada +10 2d6+6+2d6 ×2 | **Esmagar** · 2d6+6+2d6 · save FOR CD 18 · atordoa 1 · *a cada 2 rodadas* | livro RHW |
| **Naga Guardiã** *(Guardian Naga)* | 10 | 18 | 127 | Mordida +8 1d8+4 + envenenado (save CON CD 16) ×3 | **Cuspe Venenoso** · 4d6 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Naga Sereia** *(Naga Siren)* | 9 | 15 | 123 | Seta Gélida +9 4d6+5 ×3 | — | livro WoW |
| **Nalfeshnee** | 13 | 18 | 184 | Mordida +10 5d10+5 · Garra +10 3d6+5 ×2 | **Horror Nimbus** · save SAB CD 15 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | boss |
| **Nycaloth** | 9 | 18 | 123 | Garra +9 2d6+5 · Machado Grande +9 2d12+5 | — | âncora, boss |
| **Observador** *(Beholder)* | 13 | 18 | 180 | Mordida +5 4d6 ×4 | **Raios Oculares** · 5d8 · save DES CD 17 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Queen Forfallen** | 10 | 16 | 153 | Machado Grande +9 2d12+5 + envenenado (save CON CD 21) ×3 | **Aperto da Ferrugem** · save CON CD 16 · deixa envenenado · atordoa 2 · *a cada 2 rodadas* | livro FRAiF |
| **Rakshasa** | 13 | 16 | 110 | Garra +7 2d6+2 ×3 | **Maldição** · save SAB CD 18 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | boss |
| **Remorhaz** | 11 | 17 | 195 | Mordida +11 6d10+7+3d6 ×3 | **Calor Irradiante** · 14d10 · save CON CD 19 · em 5 · deixa exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Roca** *(Roc)* | 11 | 15 | 248 | Bico +13 4d8+9 · Garras +13 4d6+9 ×2 | **Mergulho** · 9d10 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Saidra d'Honaire** | 9 | 13 | 90 | Rajada Necrótica +7 2d10+3 ×3 | **Drenar Vida** · 8d6 · save CON CD 15 · deixa deterioracao · metade quem resiste · *a cada 2 rodadas* | livro RHW |
| **Saqueador Tarkanan** *(Tarkanan Marauder)* | 11 | 16 | 247 | Golpe Aberrante +7 3d6+3 ×3 | **Rasgar o Espaço** · save CON CD 17 · em 3 · deixa perdicao · *a cada 2 rodadas* | livro EFA |
| **Scarlet Commander Mograine** | 13 | 20 | 221 | Golpe do Cruzado +10 1d8+5+6d8 + perdicao (save CAR CD 22) ×2 | — | livro WoW |
| **Servo do Trono** *(Servant of the Throne)* | 12 | 17 | 195 | Rajada Gélida +9 4d10+5 ×3 | — | livro ICC |
| **Shoggoth** | 11 | 15 | 172 | Pseudópode +10 2d8+6+2d10 ×3 | **Rajada de Sucção** · 4d10 · save FOR CD 18 · atordoa 1 · metade quem resiste · *rec. 4+, sai na rodada 1* | livro RHW |
| **Slaad Cinzento** *(Gray Slaad)* | 9 | 18 | 127 | Mordida +7 1d6+3 + perturbacao (save INT CD 16) · Garras +7 1d10+3 | — | regenera 10/rodada · âncora, boss |
| **Slaad da Morte** *(Death Slaad)* | 10 | 18 | 170 | Mordida +9 1d8+5+2d6 · Garras +9 1d10+5+2d6 ×2 | **Maldição Caótica** · save SAB CD 17 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Sumo Sacerdote Fala-Morte** *(Deathspeaker High Priest)* | 10 | 17 | 180 | Rajada Sombria +10 2d10+6 ×2 | **Acerto Sombrio** · 6d10 · rola ataque · *rec. 5+, sai na rodada 1* | livro ICC |
| **Ultroloth** | 13 | 19 | 153 | Espada Longa +8 1d8+3 ×3 | **Olhar Aterrorizante** · save SAB CD 17 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | boss |
| **Vampiro** *(Vampire)* | 13 | 16 | 144 | Mordida +9 1d6+4+3d6 + deterioracao, exaustao (save CON CD 16) · Ataque Desarmado +9 1d8+4 ×3 | **Encanto Vampírico** · save SAB CD 17 · em 4 · deixa perturbacao · *rec. 5+, sai na rodada 1* | regenera 20/rodada · boss |
| **Vampiro Guardião** *(Vampire Warden)* | 10 | 18 | 190 | Garra +9 2d8+5+2d6 ×2 | **Mordida** · 1d4+5+2d6 · save CON CD 16 · deixa deterioracao · *a cada 2 rodadas* | livro ABH |
| **Vladeska Drakov** | 12 | 18 | 170 | Pique +8 2d10+4 ×2 | **Fogo de Artilharia** · 3d8+3d8 · save DES CD 15 · em 3 · metade quem resiste · *rec. 6+, sai na rodada 1* | livro RHW |
| **Yeti Abominável** *(Abominable Yeti)* | 9 | 15 | 137 | Garra +11 2d6+7+2d6 ×2 | **Sopro Gélido** · 10d8 · save CON CD 18 · em 5 · deixa letargia, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Yochlol** | 10 | 15 | 136 | Pancada +6 1d6+2+6d6 ×3 | **Toque Venenoso** · 8d10 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |

## Tier 5 — CR 14 ou mais

98 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Abveku** | 14 | 17 | 209 | Garra Ceifadora +11 3d8+6 ×4 | **Dança Hipnotizante** · save SAB CD 18 · em 3 · atordoa 2 · *rec. 5+, sai na rodada 1* | livro AUD |
| **Alleria Windrunner** | 21 | 19 | 433 | Adaga do Vazio +13 2d4+6+4d6 ×4 | **Garra do Vazio** · 10d10 · save INT CD 21 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Anciente da Guerra** *(Ancient of War)* | 14 | 18 | 200 | Pancada +13 4d12+8 ×3 | **Fúria da Natureza** · 5d10+10d10 · save DES CD 17 · em 3 · deixa perdicao · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Androesfinge** *(Androsphinx)* | 17 | 17 | 199 | Garra +12 2d10+6 ×4 | **Rugido** · save SAB CD 20 · em 5 · deixa medo · *rec. 5+, sai na rodada 1* | boss, solo |
| **Anduin Wrynn** | 20 | 18 | 348 | Shalamayne +14 2d10+8+2d12 ×4 | **Saraivada Radiante** · 7d12 · save DES CD 19 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Ankhtepot** | 17 | 17 | 202 | Rajada de Energia Negativa +11 6d6+5 ×4 | — | livro RHW |
| **Anub'arak** | 22 | 24 | 216 | Garra Gélida +15 2d12+8+2d12 ×2 | — | livro WoW |
| **Arauto Val'kyr** *(Val'kyr Herald)* | 14 | 18 | 168 | Lança do Ceifador +11 2d6+6+6d8 ×2 | **Essência Cortada** · 4d8 · save CAR CD 19 · metade quem resiste · *rec. 4+, sai na rodada 1* | livro ICC |
| **Azalin Rex** | 23 | 20 | 390 | Rajada Mística +12 4d12+5 ×3 | — | livro RHW |
| **Balor** | 19 | 19 | 262 | Espada Longa +14 3d8+8+3d8 · Chicote +14 2d6+8+3d6 ×2 | **Explosão de Chamas** · 11d10 · save DES CD 22 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Blood-Queen Lana'thel** | 23 | 16 | 315 | Mordida Sanguinária +13 2d8+6+2d8 + deterioracao (save CON CD 25) ×2 | — | livro ICC |
| **Cavaleiro da Morte** *(Death Knight)* | 17 | 20 | 180 | Espada Longa +11 1d8+5 ×3 | **Bola de Fogo Infernal** · 10d6+10d6 · save DES CD 19 · em 4 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Coisa Ancestral** *(Elder Thing)* | 14 | 16 | 209 | Tentáculo Calmante +10 2d8+5 + efeito (save CON CD 22) ×2 | **Esporos Raspa-Mente** · 10d10+3d6 · save INT CD 18 · em 3 · metade quem resiste · *rec. 6+, sai na rodada 1* | livro RHW |
| **Cthulhu** | 25 | 19 | 385 | Garra Mística +17 2d8+9+2d8 ×3 | **Tentáculo** · 6d6+3d8 · save CON CD 25 · metade quem resiste · *a cada 2 rodadas* | livro RHW |
| **Cão da Praga** *(Plague-Dog)* | 14 | 16 | 189 | Dilacerar +11 4d6+6+4d6 ×2 | **Dizimar** · 7d8+30 · save CON CD 17 · em 3 · metade quem resiste · *rec. 6+, sai na rodada 1* | matilha · livro ICC |
| **Deathbringer Saurfang** | 21 | 20 | 266 | Lâmina de Runa Sangrenta +13 2d6+6+1d8 ×3 | **Sangue Fervente** · 10d12 · save CON CD 21 · deixa exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **Demilich** | 18 | 20 | 80 | Golpe +9 2d8+7 ×4 | **Howl** · save CON CD 15 · em 4 · deixa exaustao, deterioracao · *rec. 5+, sai na rodada 1* | boss, solo |
| **Diabo do Gelo** *(Ice Devil)* | 14 | 18 | 180 | Mordida +10 2d6+5+3d6 · Garras +10 2d4+5+3d6 ×2 | **Wall of Ice** · 10d6+5d6 · save DES CD 17 · em 4 · deixa exaustao, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Draco da Revoada Bronze** *(Bronze Dragonflight Drake)* | 17 | 20 | 275 | Dilacerar +14 9d6+8 ×3 | **Sopro de Areia Escaldante** · 11d6+11d6 · save DES CD 21 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Draco da Revoada Negra** *(Black Dragonflight Drake)* | 16 | 19 | 275 | Dilacerar +13 7d6+8 ×3 | **Sopro de Magma** · 10d6+10d6 · save DES CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Draco da Revoada Vermelha** *(Red Dragonflight Drake)* | 15 | 19 | 250 | Dilacerar +13 7d6+8 ×3 | **Sopro de Fogo Arrasador** · 20d6 · save DES CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dracolich Azul Adulto** *(Adult Blue Dracolich)* | 17 | 19 | 225 | Mordida +13 2d10+7+1d10 · Garra +13 2d6+7 ×3 | **Sopro de Relâmpago** · 12d10 · save DES CD 20 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Azul Adulto** *(Adult Blue Dragon)* | 16 | 19 | 225 | Mordida +12 2d10+7+1d10 · Garra +12 2d6+7 ×3 | **Sopro de Relâmpago** · 12d10 · save DES CD 19 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão da Revoada Azul** *(Blue Dragonflight Dragon)* | 20 | 21 | 296 | Dilacerar +15 5d6+9 ×3 | **Sopro Congela-Magia** · 17d6 · save CON CD 22 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão da Revoada Bronze** *(Bronze Dragonflight Dragon)* | 23 | 22 | 370 | Dilacerar +16 9d6+9 ×3 | **Sopro de Areia Escaldante** · 11d6+11d6 · save DES CD 23 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão da Revoada Negra** *(Black Dragonflight Dragon)* | 22 | 21 | 351 | Dilacerar +16 7d6+9 ×3 | **Sopro de Magma** · 10d6+10d6 · save DES CD 23 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão da Revoada Verde** *(Green Dragonflight Dragon)* | 19 | 21 | 222 | Dilacerar +15 5d6+9 ×3 | **Sopro de Gás Esmeralda** · 7d6+7d6 · save CON CD 22 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão da Revoada Vermelha** *(Red Dragonflight Dragon)* | 21 | 21 | 296 | Dilacerar +16 6d6+9 ×3 | **Sopro de Fogo Arrasador** · 20d6 · save DES CD 23 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro WoW |
| **Dragão de Bronze Adulto** *(Adult Bronze Dragon)* | 15 | 19 | 212 | Mordida +12 2d10+7 · Garra +12 2d6+7 ×3 | **Armas de Sopro** · 12d10 · save DES CD 19 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Cobre Adulto** *(Adult Copper Dragon)* | 14 | 18 | 184 | Mordida +11 2d10+6 · Garra +11 2d6+6 ×3 | **Armas de Sopro** · 12d8 · save DES CD 18 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Ouro Adulto** *(Adult Gold Dragon)* | 17 | 19 | 256 | Mordida +14 2d10+8 · Garra +14 2d6+8 ×3 | **Armas de Sopro** · 12d10 · save DES CD 21 · em 5 · deixa medo, perturbacao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Prata Adulto** *(Adult Silver Dragon)* | 16 | 19 | 243 | Mordida +13 2d10+8 · Garra +13 2d6+8 ×3 | **Armas de Sopro** · 13d8 · save CON CD 20 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Enferrujado** *(Rusted Wyrm)* | 14 | 20 | 231 | Mordida +12 4d10+7 ×2 | **Sopro de Vapor** · 7d12 · save DES CD 19 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Espiritual Adulto** *(Adult Spirit Dragon)* | 15 | 18 | 207 | Dilacerar +11 2d8+6+2d6 ×3 | **Sopro Ruinoso** · 14d8 · save CON CD 18 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Espiritual Ancião** *(Ancient Spirit Dragon)* | 22 | 21 | 420 | Dilacerar +15 2d10+8+2d8 ×3 | **Sopro Ruinoso** · 16d8 · save CON CD 22 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Gélido** *(Frost Wyrm)* | 17 | 20 | 162 | Dilacerar +13 2d10+7+1d8 ×3 | **Sopro Congelante** · 6d12 · save CON CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **Dragão Negro Adulto** *(Adult Black Dragon)* | 14 | 19 | 195 | Mordida +11 2d10+6+1d8 · Garra +11 2d6+6 ×3 | **Sopro Ácido** · 12d8 · save DES CD 18 · em 5 · deixa medo, deterioracao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Profundo Ancião** *(Ancient Deep Dragon)* | 18 | 20 | 247 | Dilacerar +12 2d10+6+1d10 ×3 | **Sopro de Pesadelo** · 8d10 · save SAB CD 20 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Dragão Verde Adulto** *(Adult Green Dragon)* | 15 | 19 | 207 | Mordida +11 2d10+6+2d6 · Garra +11 2d6+6 ×3 | **Sopro Venenoso** · 16d6 · save CON CD 18 · em 5 · deixa medo, envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Vermelho Adulto** *(Adult Red Dragon)* | 17 | 19 | 256 | Mordida +14 2d10+8+2d6 · Garra +14 2d6+8 ×3 | **Sopro de Fogo** · 18d6 · save DES CD 21 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Emissário Maior da Cria Estelar** *(Greater Star Spawn Emissary)* | 21 | 15 | 304 | Bocarra Açoitante +14 4d12+7+4d8 ×2 | **Bile Sobrenatural** · 12d8 · save DES CD 23 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Emissário Menor da Cria Estelar** *(Lesser Star Spawn Emissary)* | 19 | 19 | 241 | Bocarra Açoitante +11 2d10+5+3d8 ×3 | **Inverter Carne** · 4d10+7 · save CON CD 21 · *a cada 2 rodadas* | livro RHW |
| **Festergut** | 17 | 14 | 207 | Garra +11 6d10+5+4d6 ×2 | **Gás Vil** · 10d6 · save CON CD 19 · em 3 · deixa envenenado · atordoa 1 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **General Sem-Rosto N'raqi** *(N'raqi Faceless General)* | 21 | 21 | 325 | Pinça +15 2d6+8+4d8 ×2 | **Rajada Mental** · 6d6+8 · save INT CD 23 · em 3 · atordoa 1 · metade quem resiste · *rec. 4+, sai na rodada 1* | livro WoW |
| **Golem de Ferro** *(Iron Golem)* | 16 | 20 | 210 | Pancada +13 3d8+7 · Espada +13 3d10+7 ×2 | **Sopro Venenoso** · 10d8 · save CON CD 19 · em 5 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Goristro** | 17 | 19 | 310 | Chifrada +13 7d10+7 + perturbacao (save SAB CD 16) · Soco +13 3d8+7 ×2 | **Investida Selvagem** · 13d10 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | boss, solo |
| **Hadronox** | 18 | 20 | 232 | Mordida +14 2d10+8+2d6 ×2 | **Veneno Sanguessuga** · 4d6 · save CON CD 19 · em 3 · deixa envenenado · *rec. 5+, sai na rodada 1* | livro WoW |
| **Harkon Lukas** | 14 | 15 | 187 | Patada +10 2d10+5 ×2 | **Apresentação Cativante** · save SAB CD 17 · em 3 · atordoa 1 · *a cada 2 rodadas* | livro RHW |
| **Hazlik** | 14 | 16 | 154 | Rajada Arcana +10 3d10+5 ×3 | **Surto de Magia Selvagem** · 2d12+3d6 · save CON CD 18 · deixa perdicao · *a cada 2 rodadas* | livro RHW |
| **Illidan Stormrage** | 24 | 20 | 430 | Choque de Chamas +14 4d10 · Glaive de Guerra +14 2d10+7+3d12 ×2 | **Rajada Sombria** · 8d6 · save DES CD 22 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro WoW |
| **Immol'thar** | 16 | 17 | 192 | Mordida +12 2d10+7+1d8 ×2 | **Pisotear** · 3d12 · save FOR CD 20 · metade quem resiste · *a cada 2 rodadas* | livro WoW |
| **Jaina Proudmoore** | 22 | 17 | 450 | Cajado de Antonidas +14 2d6+7+4d8 ×3 | **Lança Estilhaçante** · 8d8 · save DES CD 22 · *rec. 5+, sai na rodada 1* | livro WoW |
| **King Gordok** | 15 | 16 | 189 | Lâmina Bárbara +12 4d6+7 ×2 | — | livro WoW |
| **Krik'thir the Gatewatcher** | 17 | 20 | 231 | Garra +14 2d10+8 ×2 | **Teia Mental** · 5d10 · save INT CD 20 · atordoa 1 · metade quem resiste · *a cada 2 rodadas* | matilha · livro WoW |
| **Lady Deathwhisper** | 21 | 20 | 150 | Seta Sombria +13 3d12+6 ×3 | — | livro ICC |
| **Lich King Arthas** | 25 | 20 | 500 | Frostmourne +18 2d6+10+2d12 + efeito (save CON CD 23) ×2 | — | livro WoW |
| **Lord Marrowgar** | 21 | 21 | 345 | Machado do Trono de Gelo +14 1d12+7+1d12 · Corte de Osso +14 2d10+7 ×2 | **Cemitério de Espinhos de Osso** · 4d6 · save DES CD 21 · em 3 · atordoa 1 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **Lord Soth of Sithicus** | 19 | 18 | 228 | Marca do Renegado +12 1d8+6+3d8 ×3 | **Fogo Cataclísmico** · 7d6+7d6 · save DES CD 19 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Marilith** | 16 | 18 | 189 | Espada Longa +9 2d8+4 · Cauda +9 2d10+4 ×2 | **Golpe Poderoso** · 6d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | boss |
| **Phaerimm Ancião** *(Phaerimm Elder)* | 14 | 17 | 218 | Açoite Mental +9 6d8+4 ×3 | — | livro NF |
| **Planetar** | 16 | 19 | 200 | Montante +12 4d6+7+5d8 ×3 | **Luz Radiante** · 14d10 · save CON CD 20 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Prince Keleseth** | 18 | 16 | 475 | Golpe Sepulcral +12 1d8+6+4d8 ×2 | **Dreno Sanguíneo** · 4d6 · save CON CD 20 · deixa deterioracao · *a cada 2 rodadas* | livro ICC |
| **Prince Taldaram** | 18 | 16 | 475 | Golpe Sepulcral +12 1d8+6+4d8 ×2 | **Fagulhas Cintilantes** · 7d8 · save DES CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **Prince Tortheldrin** | 15 | 17 | 178 | Glaive de Guerra +9 1d6+4+3d6 ×3 | **Impacto Arcano** · 8d6 · save FOR CD 18 · *a cada 2 rodadas* | livro WoW |
| **Prince Valanar** | 18 | 16 | 475 | Golpe Sepulcral +12 1d8+6+4d8 ×2 | **Bomba Cinética** · 12d6 · save DES CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **Professor Putricide, Phase 1** | 20 | 17 | 299 | Debater-se +12 2d12+6 ×2 | **Gerar Gosma Volátil** · 12d12 · save DES CD 20 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro ICC |
| **Ragnaros** | 23 | 20 | 296 | Esmagamento de Sulfuras +15 4d6+8+4d6 + efeito (save DES CD 23) ×2 | **Explosão de Magma** · 12d6 · save DES CD 23 · em 3 · metade quem resiste · *rec. 4+, sai na rodada 1* | livro WoW |
| **Ramya Vasavadan** | 15 | 18 | 190 | Lâmina do Pavor +10 2d6+5+2d8 ×3 | **Fogo Vingativo** · 8d6+8d6 · save DES CD 17 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro RHW |
| **Rebento dos Três Mortos** *(Dead Three Scion)* | 16 | 17 | 221 | Toque da Morte +12 4d8+7 ×2 | — | livro FRAiF |
| **Rendelith** | 18 | 20 | 294 | Martelo de Pedra +13 4d6+7 ×2 | — | livro AUD |
| **Rotface** | 17 | 14 | 250 | Garra +12 6d10+6+4d6 ×2 | **Jato de Lodo** · 4d12 · save DES CD 20 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro ICC |
| **Sammaster (Dracolich Form)** | 22 | 20 | 276 | Dilacerar +14 2d10+7+4d8 ×3 | **Sopro Corrosivo** · 8d12 · save CON CD 20 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Sammaster (Lich Form)** | 22 | 18 | 322 | Rajada Corrosiva +13 5d12+6 ×3 | — | livro FRAiF |
| **Sarrukh Reerguido** *(Arisen Sarrukh)* | 18 | 18 | 273 | Tridente +12 6d8+6 ×3 | **Teleporte Venenoso** · 4d10 · save CON CD 20 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro AUD |
| **Sarrukh Tirano** *(Sarrukh Tyrant)* | 17 | 19 | 256 | Mordida +12 2d6+6+3d8 ×2 | — | livro AUD |
| **Scarlet Champion Herod** | 18 | 17 | 209 | Machado Grande +11 2d12+5+4d6 ×3 | — | livro WoW |
| **Sem-Rosto N'raqi** *(N'raqi Faceless One)* | 15 | 16 | 209 | Tentáculo +12 4d10+7 ×3 | **Armadilha Mental** · 4d12 · save INT CD 20 · em 3 · atordoa 1 · *rec. 4+, sai na rodada 1* | livro WoW |
| **Senhor das Múmias** *(Mummy Lord)* | 15 | 17 | 97 | Punho Apodrecido +9 3d6+4+6d6 ×4 | **Olhar Terrível** · save SAB CD 17 · em 4 · deixa deterioracao, medo · *rec. 5+, sai na rodada 1* | boss |
| **Senhor do Abismo** *(Pit Lord)* | 20 | 20 | 362 | Glaive de Guerra Vil +14 3d10+8+3d8 ×3 | **Chuva de Fogo Vil** · 8d6+8d6 · save DES CD 21 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro WoW |
| **Shivarra** | 16 | 17 | 199 | Lâmina Vil +10 2d10+5+2d6 ×6 | — | livro WoW |
| **Sindragosa** | 23 | 20 | 367 | Dilacerar +14 2d10+7+1d8 ×3 | **Sopro Congelante** · 8d12 · save CON CD 22 · em 3 · atordoa 1 · metade quem resiste · *rec. 5+, sai na rodada 1* | livro ICC |
| **Sister Svalna** | 16 | 19 | 262 | Lança de Osso +12 2d6+7+4d8 ×3 | **Onda Divina** · 7d6 · save DES CD 20 · em 3 · metade quem resiste · *a cada 2 rodadas* | livro ICC |
| **Strahd von Zarovich** | 15 | 16 | 204 | Golpe Mortal +9 1d8+4+4d6 ×2 | **Mordida** · 1d6+4+3d6 · save CON CD 17 · deixa deterioracao · *a cada 2 rodadas* | livro RHW |
| **Sylvanas Windrunner** | 23 | 20 | 475 | Adaga Sombria +14 2d4+7+4d8 ×3 | **Lamento da Banshee** · 10d8 · save CON CD 22 · em 3 · *rec. 6+, sai na rodada 1* | livro WoW |
| **Szass Tam** | 23 | 20 | 397 | Toque Paralisante +13 3d6+6 + efeito (save CON CD 25) ×3 | — | livro AUD |
| **Tartaruga-Dragão** *(Dragon Turtle)* | 17 | 20 | 341 | Mordida +13 3d12+7 · Garra +13 2d8+7 ×2 | **Sopro de Vapor** · 15d6 · save CON CD 18 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Thrall** | 22 | 19 | 475 | Dra'gora +13 2d10+6 ×3 | **Corrente de Relâmpagos** · 8d8 · save DES CD 21 · *rec. 4+, sai na rodada 1* | livro WoW |
| **Tirano da Morte** *(Death Tyrant)* | 14 | 19 | 187 | Mordida +5 4d6 ×4 | **Raio Negativo** · 5d8 · save CON CD 17 · em 4 · deixa deterioracao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Tirion Fordring** | 15 | 18 | 202 | Ashbringer +13 2d6+8+5d10 ×3 | — | livro ICC |
| **Valindra Shadowmantle** | 21 | 20 | 315 | Rajada Mística +12 4d12+5 ×3 | **Agarrão Mortal** · 6d12+6d12 · save DES CD 20 · em 3 · atordoa 2 · *rec. 5+, sai na rodada 1* | livro FRAiF |
| **Vampiro Conjurador** *(Vampire Spellcaster)* | 15 | 16 | 144 | Mordida +9 1d6+4+3d6 + deterioracao (save CON CD 16) · Ataque Desarmado +9 1d8+4 ×3 | **Encanto Vampírico** · save SAB CD 17 · em 4 · deixa perturbacao · *rec. 5+, sai na rodada 1* | regenera 20/rodada · boss |
| **Vampiro Guerreiro** *(Vampire Warrior)* | 15 | 18 | 144 | Montante +9 2d6+4 + deterioracao (save CON CD 16) · Ataque Desarmado +9 1d8+4 ×3 | **Golpe Poderoso** · 5d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | regenera 20/rodada · boss |
| **Vampiro Infernalista** *(Vampire Infernalist)* | 14 | 16 | 172 | Garra de Fogo Infernal +9 2d8+4+3d6 ×2 | **Mordida** · 1d4+4+3d10 · save CON CD 18 · deixa deterioracao · *a cada 2 rodadas* | livro ABH |
| **Venomante Nerubiano** *(Nerubian Venomancer)* | 14 | 18 | 209 | Garra Venenosa +12 2d12+7+2d10 ×3 | **Explosão de Teia** · 6d12 · save DES CD 20 · em 3 · atordoa 1 · *rec. 5+, sai na rodada 1* | livro WoW |
| **Verme Púrpura** *(Purple Worm)* | 15 | 18 | 247 | Mordida +14 3d8+9 · Ferrão da Cauda +14 3d6+9 ×2 | **Ferrão Venenoso** · 8d8 · save CON CD 22 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | solo |
| **Xelnene Thrul** | 17 | 17 | 208 | Rajada Arcana +11 5d10+5 ×4 | — | livro AUD |
| **Yithiano** *(Yithian)* | 15 | 14 | 180 | Pinça +9 4d6+4 ×3 | **Sorver** · 3d6+5 · save INT CD 18 · deixa deterioracao · *a cada 2 rodadas* | livro RHW |
| **Zlan** | 18 | 18 | 199 | Pancada +11 3d4+5+4d10 ×3 | — | livro FRAiF |

---

Gerado por `tools/gerar_criaturas_md.py` a partir de `data/bestiario.json`
e de `data/criaturas/`.
Não edite à mão: rode o gerador.
