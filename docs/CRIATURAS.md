# Criaturas

**Este arquivo é gerado.** Ele sai de `tools/gerar_criaturas_md.py`, que lê o
bestiário. Para refazer depois de importar criaturas novas:

```
.venv/Scripts/python.exe tools/gerar_criaturas_md.py
```

São **385 criaturas**, e uma sala pode chamar qualquer uma delas
**só pelo nome** — os números saem daqui no lugar das colunas vazias. A regra
de como isso funciona está em [mecanicas/bestiario.md](mecanicas/bestiario.md);
aqui estão as fichas.

## Como ler

**Os números são os do tier 1**, como todo conteúdo do bot. Quem escala é o
combate, na hora de abrir, pelo tier do GRUPO que entrou: HP e dano crescem
pelo mesmo multiplicador do HP do grupo, e CA, ataque e saves sobem pelo
ajuste do bônus de proficiência. Uma criatura de 52 HP aqui tem 182 no tier 4.

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
| 1 | CR 0 a 1 | 131 |
| 2 | CR 2 a 4 | 114 |
| 3 | CR 5 a 8 | 76 |
| 4 | CR 9 a 13 | 40 |
| 5 | CR 14 ou mais | 24 |

## Tier 1 — CR 0 a 1

131 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Aarakocra** | 1/4 | 12 | 13 | Garra +4 1d4+2 | — | minion |
| **Abutre Gigante** *(Giant Vulture)* | 1 | 10 | 22 | Bico +4 2d4+2 | — | matilha · minion, âncora |
| **Acólito** *(Acolyte)* | 1/4 | 10 | 9 | Clava +2 1d4 | — | minion |
| **Alce** *(Elk)* | 1/4 | 10 | 13 | Aríete +5 1d6+3 | **Investida Selvagem** · 3d6 · rola ataque · metade quem resiste · *rec. 6+, sai na rodada 1* | minion |
| **Aranha Gigante** *(Giant Spider)* | 1 | 14 | 26 | Mordida +5 1d8+3 + envenenado (save CON CD 12) | **Teia** · save FOR CD 13 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Aranha-Lobo Gigante** *(Giant Wolf Spider)* | 1/4 | 13 | 11 | Mordida +3 1d6+1 + envenenado (save CON CD 12) | — | minion |
| **Armadura Animada** *(Animated Armor)* | 1 | 18 | 33 | Pancada +4 1d6+2 | — | minion, âncora |
| **Bandido** *(Bandit)* | 1/8 | 12 | 11 | Cimitarra +3 1d6+1 | **Golpe Certeiro** · 2d6+4 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Batedor** *(Scout)* | 1/2 | 13 | 16 | Espada Curta +4 1d6+2 | — | minion |
| **Bico-de-Machado** *(Axe Beak)* | 1/4 | 11 | 19 | Bico +4 1d8+2 | — | minion |
| **Bugbear** | 1 | 16 | 27 | Maça Estrela +4 2d8+2 | **Golpe Poderoso** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Bullywug** | 1/4 | 15 | 11 | Mordida +3 1d4+1 | — | minion |
| **Cabra Gigante** *(Giant Goat)* | 1/2 | 11 | 19 | Aríete +5 2d4+3 | **Investida Selvagem** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Camelo** *(Camel)* | 1/8 | 9 | 15 | Mordida +5 1d4 | **Investida Selvagem** · 2d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Capanga** *(Thug)* | 1/2 | 11 | 32 | Maça +4 1d6+2 | **Golpe Certeiro** · 2d6 · rola ataque · *rec. 6+, sai na rodada 1* | matilha · minion |
| **Caranguejo Gigante** *(Giant Crab)* | 1/8 | 15 | 13 | Garra +3 1d6+1 | — | minion |
| **Carniçal** *(Ghoul)* | 1 | 12 | 22 | Mordida +2 2d6+2 + letargia (save CON CD 12) | **Garras Paralisantes** · save CON CD 12 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
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
| **Coruja Gigante** *(Giant Owl)* | 1/4 | 12 | 19 | Garras +3 2d6+1 | — | minion |
| **Crocodilo** *(Crocodile)* | 1/2 | 12 | 19 | Mordida +4 1d10+2 | — | minion |
| **Cultista** *(Cultist)* | 1/8 | 12 | 9 | Cimitarra +3 1d6+1 | **Golpe Certeiro** · 2d6+4 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Cão da Morte** *(Death Dog)* | 1 | 12 | 39 | Mordida +4 1d6+2 + debilidade (save CON CD 12) | — | minion, âncora |
| **Cão Intermitente** *(Blink Dog)* | 1/4 | 13 | 22 | Mordida +3 1d6+1 | — | minion |
| **Diabrete** *(Imp)* | 1 | 13 | 10 | Ferrão +5 1d4+3 + envenenado (save CON CD 12) | — | minion |
| **Doninha Gigante** *(Giant Weasel)* | 1/8 | 13 | 9 | Mordida +5 1d4+3 | — | minion |
| **Dragão Feérico (Amarelo)** *(Faerie Dragon (Yellow))* | 1 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Laranja)** *(Faerie Dragon (Orange))* | 1 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Vermelho)** *(Faerie Dragon (Red))* | 1 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dretch** | 1/4 | 11 | 18 | Mordida +2 1d6 | **Chamas Infernais** · 1d6 · save DES CD 11 · em 2 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Drow** | 1/4 | 15 | 13 | Espada Curta +4 1d6+2 + envenenado (save CON CD 12) | **Golpe Envenenado** · 2d6 · save CON CD 12 · deixa envenenado · *rec. 5+, sai na rodada 1* | minion |
| **Dríade** *(Dryad)* | 1 | 11 | 22 | Clava +2 1d4 | **Fascinar** · save SAB CD 14 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Duergar** | 1 | 16 | 26 | Picareta de Guerra +4 1d8+2 | — | minion, âncora |
| **Duodrone** | 1/4 | 15 | 11 | Soco +2 1d4 | **Sobrecarga** · 1d6 · rola ataque · *rec. 4+, sai na rodada 1* | minion |
| **Espada Voadora** *(Flying Sword)* | 1/4 | 17 | 17 | Espada Longa +3 1d8+1 | — | minion |
| **Espantalho** *(Scarecrow)* | 1 | 11 | 36 | Garra +3 2d4+1 | **Olhar Aterrorizante** · save SAB CD 11 · deixa medo · atordoa 1 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Espectro** *(Specter)* | 1 | 12 | 22 | Drenar Vida +4 3d6 + deterioracao, exaustao (save CON CD 12) | — | minion, âncora |
| **Espião** *(Spy)* | 1 | 12 | 27 | Espada Curta +4 1d6+2 | — | minion, âncora |
| **Esporo de Gás** *(Gas Spore)* | 1/2 | 5 | 1 | Toque +0 1 | — | minion |
| **Esqueleto** *(Skeleton)* | 1/4 | 13 | 13 | Espada Curta +4 1d6+2 | **Toque da Morte** · 2d6 · save CON CD 12 · *rec. 5+, sai na rodada 1* | minion |
| **Esqueleto de Cavalo de Guerra** *(Warhorse Skeleton)* | 1/2 | 13 | 22 | Cascos +6 2d6+4 | — | minion |
| **Filhote de Dragão de Cobre** *(Copper Dragon Wyrmling)* | 1 | 16 | 22 | Mordida +4 1d10+2 | **Armas de Sopro** · 4d8 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Latão** *(Brass Dragon Wyrmling)* | 1 | 16 | 16 | Mordida +4 1d10+2 | **Armas de Sopro** · 4d6 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Flumph** | 1/8 | 12 | 7 | Tentáculos +4 1d4+2+1d4 | **Explosão Psíquica** · 3d6 · save INT CD 12 · em 2 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion |
| **Fungo Violeta** *(Violet Fungus)* | 1/4 | 5 | 18 | Toque Apodrecido +2 1d8 + deterioracao (save CON CD 12) | **Vinhas Constritoras** · 2d6 · save FOR CD 10 · em 2 | minion |
| **Gavião-Sanguinário** *(Blood Hawk)* | 1/8 | 12 | 7 | Bico +4 1d4+2 | — | matilha · minion |
| **Girino Slaad** *(Slaad Tadpole)* | 1/8 | 12 | 10 | Mordida +4 1d4+2 + tolice (save INT CD 12) | **Explosão Psíquica** · 3d6 · save INT CD 12 · em 2 · atordoa 1 · *rec. 5+, sai na rodada 1* | minion |
| **Gnoll** | 1/2 | 15 | 22 | Mordida +4 1d4+2 | **Golpe Certeiro** · 2d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Gnomo das Profundezas (Svirfneblin)** *(Deep Gnome (Svirfneblin))* | 1/2 | 15 | 16 | Picareta de Guerra +4 1d8+2 | — | vantagem em INT · vantagem em SAB · vantagem em CAR · minion |
| **Goblin** | 1/4 | 15 | 7 | Cimitarra +4 1d6+2 | **Bomba de Veneno** · 2d6 · save CON CD 12 · em 2 · deixa envenenado · *rec. 5+, sai na rodada 1* | minion |
| **Gosma Cinzenta** *(Gray Ooze)* | 1/2 | 8 | 22 | Pseudópode +3 1d6+1+2d6 + deterioracao (save CON CD 12) | — | minion |
| **Grimlock** | 1/4 | 11 | 11 | Clava de Osso Espinhosa +5 1d4+3+1d4 | — | minion |
| **Guarda** *(Guard)* | 1/8 | 16 | 11 | Lança +3 1d6+1 | **Golpe Certeiro** · 2d6+4 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Guerreiro Tribal** *(Tribal Warrior)* | 1/8 | 12 | 11 | Lança +3 1d6+1 | — | matilha · minion |
| **Harpia** *(Harpy)* | 1 | 11 | 38 | Garras +3 2d4+1 | **Canção Sedutora** · save SAB CD 11 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Hiena Gigante** *(Giant Hyena)* | 1 | 12 | 45 | Mordida +5 2d6+3 | — | minion, âncora |
| **Hipogrifo** *(Hippogriff)* | 1 | 11 | 19 | Bico +5 1d10+3 | — | minion, âncora |
| **Hobgoblin** | 1/2 | 18 | 11 | Espada Longa +3 1d8+1 | **Golpe Certeiro** · 2d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Javali** *(Boar)* | 1/4 | 11 | 11 | Presa +3 1d6+1 | — | matilha · minion |
| **Kenku** | 1/4 | 13 | 13 | Espada Curta +5 1d6+3 + introversao (save SAB CD 12) | — | minion |
| **Kobold** | 1/8 | 12 | 5 | Adaga +4 1d4+2 | — | matilha · minion |
| **Kobold Alado** *(Winged Kobold)* | 1/4 | 13 | 7 | Adaga +5 1d4+3 | — | matilha · minion |
| **Kuo-toa** | 1/4 | 13 | 18 | Mordida +3 1d4+1 | — | minion |
| **Lagarto Gigante** *(Giant Lizard)* | 1/4 | 12 | 19 | Mordida +4 1d8+2 | — | minion |
| **Leão** *(Lion)* | 1 | 12 | 26 | Mordida +5 1d8+3 | **Bote** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Lobo** *(Wolf)* | 1/4 | 13 | 11 | Mordida +4 2d4+2 | **Investida Selvagem** · 3d6 · rola ataque · *rec. 6+, sai na rodada 1* | matilha · minion |
| **Lobo Atroz** *(Dire Wolf)* | 1 | 14 | 37 | Mordida +5 2d6+3 | **Investida Selvagem** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Macaco** *(Ape)* | 1/2 | 12 | 19 | Soco +5 1d6+3 | — | minion |
| **Magmin** | 1/2 | 14 | 9 | Toque +4 2d6+1d6 | — | minion |
| **Manes** | 1/8 | 9 | 9 | Garras +2 2d4 | **Chamas Infernais** · 2d6 · save DES CD 11 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Manto Negro** *(Darkmantle)* | 1/2 | 11 | 22 | Esmagar +5 1d6+3 | **Nuvem de Escuridão** · save DES CD 13 · em 2 · deixa insensatez · *rec. 5+, sai na rodada 1* | minion |
| **Mastim** *(Mastiff)* | 1/8 | 12 | 5 | Mordida +3 1d6+1 | — | minion |
| **Meio-Ogro (Ogrilhão)** *(Half-Ogre (Ogrillon))* | 1 | 12 | 30 | Machado de Batalha +5 2d8+3 | — | minion, âncora |
| **Mephit de Fumaça** *(Smoke Mephit)* | 1/4 | 12 | 22 | Garras +4 1d4+2 | — | minion |
| **Mephit de Gelo** *(Ice Mephit)* | 1/2 | 11 | 21 | Garras +3 1d4+1+1d4 | **Sopro Gélido** · 2d4 · save DES CD 10 · em 2 · deixa letargia, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Lama** *(Mud Mephit)* | 1/4 | 11 | 27 | Socos +3 1d6+1 | **Mud Breath** · save DES CD 11 · deixa moleza · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Magma** *(Magma Mephit)* | 1/2 | 11 | 22 | Garras +3 1d4+1+1d4 | **Sopro de Fogo** · 2d6 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Poeira** *(Dust Mephit)* | 1/2 | 12 | 17 | Garras +4 1d4+2 | **Blinding Breath** · save DES CD 10 · em 2 · deixa insensatez · *rec. 5+, sai na rodada 1* | minion |
| **Mephit de Vapor** *(Steam Mephit)* | 1/4 | 10 | 21 | Garras +2 1d4+1d4 | **Sopro de Vapor** · 1d8 · save DES CD 10 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Monodrone** | 1/8 | 15 | 5 | Adaga +3 1d4+1 | — | minion |
| **Monstro da Ferrugem** *(Rust Monster)* | 1/2 | 14 | 27 | Mordida +3 1d8+1 | — | minion |
| **Morcego Gigante** *(Giant Bat)* | 1/4 | 13 | 22 | Mordida +4 1d6+2 | — | minion |
| **Mula** *(Mule)* | 1/8 | 10 | 11 | Cascos +2 1d4+2 | — | minion |
| **Myconid Adulto** *(Myconid Adult)* | 1/2 | 12 | 22 | Soco +2 2d4+2d4 | **Esporos** · save CON CD 11 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Nobre** *(Noble)* | 1/8 | 15 | 9 | Rapieira +3 1d8+1 + introversao (save SAB CD 12) | — | minion |
| **Orc** | 1/2 | 13 | 15 | Machado Grande +5 1d12+3 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Pantera** *(Panther)* | 1/4 | 12 | 13 | Mordida +4 1d6+2 | **Investida Selvagem** · 3d6 · rola ataque · *rec. 6+, sai na rodada 1* | minion |
| **Perfurador** *(Piercer)* | 1/2 | 15 | 22 | Queda +3 1d6+6d6 | — | minion |
| **Pixie** | 1/4 | 15 | 1 | Golpe +5 1d8+3 | **Fascinar** · 3d6 · save SAB CD 12 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion |
| **Povo-Lagarto** *(Lizardfolk)* | 1/2 | 15 | 22 | Mordida +4 1d6+2 | — | minion |
| **Praga de Agulhas** *(Needle Blight)* | 1/4 | 12 | 11 | Garras +3 2d4+1 | **Vinhas Constritoras** · 2d6 · save FOR CD 11 · em 2 | minion |
| **Praga de Gravetos** *(Twig Blight)* | 1/8 | 13 | 4 | Garras +3 1d4+1 | **Vinhas Constritoras** · 2d6 · save FOR CD 11 · em 2 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion |
| **Praga de Vinhas** *(Vine Blight)* | 1/2 | 12 | 26 | Constrição +4 2d6+2 | **Entangling Plants** · save FOR CD 12 · em 2 · deixa moleza · *rec. 5+, sai na rodada 1* | minion |
| **Pseudodragão** *(Pseudodragon)* | 1/4 | 13 | 7 | Mordida +4 1d4+2 + envenenado (save CON CD 12) | **Sopro Elemental** · 2d6 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion |
| **Pteranodonte** *(Pteranodon)* | 1/4 | 13 | 13 | Mordida +3 2d4+1 | **Investida Selvagem** · 2d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Pônei** *(Pony)* | 1/8 | 10 | 11 | Cascos +4 2d4+2 | **Investida Selvagem** · 2d6+2 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Quadrone** | 1 | 16 | 22 | Soco +3 1d4+1 | — | minion, âncora |
| **Quasit** | 1 | 13 | 7 | Garra +4 1d4+3 | **Amedrontar** · save SAB CD 13 · deixa medo · *rec. 5+, sai na rodada 1* | minion |
| **Rato Gigante** *(Giant Rat)* | 1/8 | 12 | 7 | Mordida +4 1d4+2 | — | matilha · minion |
| **Rã Gigante** *(Giant Frog)* | 1/4 | 11 | 18 | Mordida +3 1d6+1 | — | minion |
| **Sahuagin** | 1/2 | 12 | 22 | Mordida +3 1d4+1 | — | minion |
| **Sapo Gigante** *(Giant Toad)* | 1 | 11 | 39 | Mordida +4 1d10+2+1d10 | **Engolir** · save FOR CD 12 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Servo de Esporos Quaggoth** *(Quaggoth Spore Servant)* | 1 | 13 | 45 | Garra +5 1d6+3 | — | minion, âncora |
| **Sombra** *(Shadow)* | 1/2 | 12 | 16 | Drenar Força +4 2d6+2 + fraqueza, exaustao (save CON CD 12) | **Toque Drenante** · 4d6 · save CON CD 12 · deixa fraqueza, exaustao · *rec. 5+, sai na rodada 1* | minion |
| **Sprite** | 1/4 | 15 | 2 | Espada Longa +2 1 + envenenado, exaustao (save CON CD 12) | **Fascinar** · 3d6 · save SAB CD 12 · em 2 · *rec. 5+, sai na rodada 1* | minion |
| **Stirge** | 1/8 | 14 | 2 | Sugar Sangue +5 1d4+3 + exaustao (save CON CD 12) | — | regenera 3/rodada · minion |
| **Sátiro** *(Satyr)* | 1/2 | 14 | 31 | Aríete +3 2d4+1 | — | minion |
| **Texugo Gigante** *(Giant Badger)* | 1/4 | 10 | 13 | Mordida +3 1d6+1 | — | minion |
| **Thri-kreen** | 1 | 15 | 33 | Mordida +3 1d6+1 + envenenado (save CON CD 12) | — | minion, âncora |
| **Tigre** *(Tiger)* | 1 | 12 | 37 | Mordida +5 1d10+3 | **Bote** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Tridrone** | 1/2 | 15 | 16 | Soco +3 1d4+1 | — | minion |
| **Tritão** *(Merfolk)* | 1/8 | 11 | 11 | Lança +2 1d6 | — | minion |
| **Troglodita** *(Troglodyte)* | 1/4 | 11 | 13 | Mordida +4 1d4+2 | **Golpe Poderoso** · 1d8+2 · rola ataque · *rec. 4+, sai na rodada 1* | minion |
| **Urso-Negro** *(Black Bear)* | 1/2 | 11 | 19 | Mordida +4 1d6+2 | **Investida Selvagem** · 2d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion |
| **Urso-Pardo** *(Brown Bear)* | 1 | 11 | 34 | Mordida +6 1d8+4 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Vespa Gigante** *(Giant Wasp)* | 1/2 | 12 | 13 | Ferrão +4 1d6+2 + envenenado (save CON CD 12) | — | minion |
| **Worg** | 1/2 | 13 | 26 | Mordida +5 2d6+3 | — | minion |
| **Yuan-ti Sangue-Puro** *(Yuan-ti Pureblood)* | 1 | 11 | 40 | Cimitarra +3 1d6+1 + envenenado (save CON CD 12) | — | minion, âncora |
| **Zumbi** *(Zombie)* | 1/4 | 8 | 22 | Pancada +3 1d6+1 + fraqueza (save CON CD 12) | **Toque da Morte** · 2d6 · save CON CD 13 · *rec. 5+, sai na rodada 1* | minion |
| **Águia Gigante** *(Giant Eagle)* | 1 | 13 | 26 | Bico +5 1d6+3 | — | minion, âncora |

## Tier 2 — CR 2 a 4

114 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Alce Gigante** *(Giant Elk)* | 2 | 14 | 42 | Aríete +6 2d6+4 | **Investida Selvagem** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Alossauro** *(Allosaurus)* | 2 | 13 | 51 | Mordida +6 2d10+4 | **Bote** · 5d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Ankheg** | 2 | 14 | 39 | Mordida +5 2d6+3+1d6 | **Jato de Ácido** · 3d6 · save DES CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Anquilossauro** *(Ankylosaurus)* | 3 | 15 | 68 | Cauda +7 4d6+4 | **Golpe Poderoso** · 6d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Aranha de Fase** *(Phase Spider)* | 3 | 13 | 32 | Mordida +4 1d10+2 + envenenado (save CON CD 13) | — | minion, âncora |
| **Azer** | 2 | 17 | 39 | Martelo de Guerra +5 1d8+3 | — | minion, âncora |
| **Banshee** | 4 | 12 | 58 | Toque Corruptor +4 3d6+2 | **Lamento Mortal** · 6d6 · save CON CD 13 · em 3 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Basilisco** *(Basilisk)* | 3 | 15 | 52 | Mordida +5 2d6+3+2d6 | **Olhar Petrificante** · save CON CD 13 · deixa letargia · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Berserker** | 2 | 13 | 67 | Machado Grande +5 1d12+3 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Boca Balbuciante** *(Gibbering Mouther)* | 2 | 9 | 67 | Mordidas +2 5d6 | **Blinding Spittle** · save DES CD 13 · em 2 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Bruxa do Mar** *(Sea Hag)* | 2 | 14 | 52 | Garras +5 2d6+3 | **Olhar Horripilante** · save SAB CD 13 · em 3 · deixa medo, exaustao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Bruxa Verde** *(Green Hag)* | 3 | 17 | 82 | Garras +6 2d8+4 + introversao (save SAB CD 13) | **Maldição** · save SAB CD 14 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Capitão Bandido** *(Bandit Captain)* | 2 | 15 | 65 | Cimitarra +5 1d6+3 | **Golpe Certeiro** · 3d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Capitão Hobgoblin** *(Hobgoblin Captain)* | 3 | 17 | 39 | Montante +4 2d6+2 + introversao (save SAB CD 13) | **Bomba de Veneno** · 4d6 · save CON CD 13 · em 3 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cavaleiro** *(Knight)* | 3 | 18 | 52 | Montante +5 2d6+3 | **Golpe Certeiro** · 4d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Centauro** *(Centaur)* | 2 | 12 | 45 | Pique +6 1d10+4 | — | minion, âncora |
| **Chefe Bugbear** *(Bugbear Chief)* | 3 | 17 | 65 | Maça Estrela +5 2d8+3 | — | âncora, boss |
| **Chefe de Guerra Orc** *(Orc War Chief)* | 4 | 16 | 93 | Machado Grande +6 1d12+4+1d8 | **Golpe Poderoso** · 5d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Chuul** | 4 | 16 | 93 | Pinça +6 2d6+4 + envenenado (save CON CD 13) | — | minion, âncora |
| **Cobra Constritora Gigante** *(Giant Constrictor Snake)* | 2 | 12 | 60 | Mordida +6 2d6+4 | **Contrair** · 5d6 · save FOR CD 14 · atordoa 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Couatl** | 4 | 19 | 97 | Mordida +8 1d6+5 + envenenado (save CON CD 13) | — | minion, âncora |
| **Crânio Flamejante** *(Flameskull)* | 4 | 13 | 40 | Raio de Fogo +5 3d6 + fraqueza (save CON CD 13) | **Bola de Fogo** · 8d6 · save DES CD 13 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cubo Gelatinoso** *(Gelatinous Cube)* | 2 | 6 | 84 | Pseudópode +4 3d6 | **Engolfar** · 4d6 · save DES CD 15 · deixa moleza · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Cão Infernal** *(Hell Hound)* | 3 | 15 | 45 | Mordida +5 1d8+3+2d6 | **Sopro de Fogo** · 6d6 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Demônio das Sombras** *(Shadow Demon)* | 4 | 13 | 66 | Garras +5 2d6+3+4d6+3 | **Escuridão Aterrorizante** · save SAB CD 13 · em 2 · deixa medo · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Devorador de Intelecto** *(Intellect Devourer)* | 2 | 12 | 21 | Garras +4 2d4+2 | **Devorar Intelecto** · save INT CD 12 · deixa tolice · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Diabo Barbado** *(Bearded Devil)* | 3 | 13 | 52 | Barba +5 1d8+2 + debilidade (save CON CD 13) | — | minion, âncora |
| **Diabo Espinhoso** *(Spined Devil)* | 2 | 13 | 22 | Mordida +2 2d4 + debilidade (save CON CD 12) | — | minion, âncora |
| **Doppelganger** | 3 | 14 | 52 | Pancada +6 1d6+4 | **Ler Mentes** · save SAB CD 14 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Azul)** *(Faerie Dragon (Blue))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Verde)** *(Faerie Dragon (Green))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Violeta)** *(Faerie Dragon (Violet))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Dragão Feérico (Índigo)** *(Faerie Dragon (Indigo))* | 2 | 15 | 14 | Mordida +7 1 | **Sopro de Euforia** · save SAB CD 11 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Druida** *(Druid)* | 2 | 11 | 27 | Cajado +2 1d6+1d8 | **Emaranhar** · save FOR CD 12 · em 2 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Elefante** *(Elephant)* | 4 | 12 | 76 | Chifrada +8 3d8+6 | **Investida Selvagem** · 7d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Escorpião Gigante** *(Giant Scorpion)* | 3 | 15 | 52 | Garra +4 1d8+2 + envenenado (save CON CD 13) | — | minion, âncora |
| **Espectador** *(Spectator)* | 3 | 14 | 39 | Mordida +1 1d6-1 + tolice (save INT CD 13) | **Raio Ocular** · save SAB CD 12 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Esqueleto de Minotauro** *(Minotaur Skeleton)* | 2 | 12 | 67 | Machado Grande +6 2d12+4 | — | minion, âncora |
| **Ettercap** | 2 | 13 | 44 | Mordida +4 1d8+2+1d8 + envenenado (save CON CD 12) | **Teia** · save FOR CD 12 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Ettin** | 4 | 12 | 85 | Machado de Batalha +7 2d8+5 + moleza (save DES CD 13) | — | minion, âncora |
| **Fantasma** *(Ghost)* | 4 | 11 | 45 | Toque Murchador +5 4d6+3 | **Possession** · save CAR CD 13 · em 3 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Fanático do Culto** *(Cult Fanatic)* | 2 | 13 | 33 | Adaga +4 1d4+2 | **Comando Sombrio** · save SAB CD 12 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Fera Deslocadora** *(Displacer Beast)* | 3 | 13 | 85 | Tentáculo +6 1d6+4+1d6 + insensatez (save SAB CD 13) | — | minion, âncora |
| **Filhote de Dragão Azul** *(Blue Dragon Wyrmling)* | 3 | 17 | 52 | Mordida +5 1d10+3+1d6 | **Sopro de Relâmpago** · 4d10 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Branco** *(White Dragon Wyrmling)* | 2 | 16 | 32 | Mordida +4 1d10+2+1d4 | **Sopro Gélido** · 5d8 · save CON CD 12 · em 2 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Bronze** *(Bronze Dragon Wyrmling)* | 2 | 17 | 32 | Mordida +5 1d10+3 | **Armas de Sopro** · 3d10 · save DES CD 12 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Ouro** *(Gold Dragon Wyrmling)* | 3 | 17 | 60 | Mordida +6 1d10+4 | **Armas de Sopro** · 4d10 · save DES CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão de Prata** *(Silver Dragon Wyrmling)* | 2 | 17 | 45 | Mordida +6 1d10+4 | **Armas de Sopro** · 4d8 · save CON CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Negro** *(Black Dragon Wyrmling)* | 2 | 17 | 33 | Mordida +4 1d10+2+1d4 | **Sopro Ácido** · 5d8 · save DES CD 11 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Verde** *(Green Dragon Wyrmling)* | 2 | 17 | 38 | Mordida +4 1d10+2+1d6 | **Sopro Venenoso** · 6d6 · save CON CD 11 · em 2 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Filhote de Dragão Vermelho** *(Red Dragon Wyrmling)* | 4 | 17 | 75 | Mordida +6 1d10+4+1d6 | **Sopro de Fogo** · 7d6 · save DES CD 13 · em 2 · metade quem resiste · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Fogo-Fátuo** *(Will-o'-Wisp)* | 2 | 19 | 22 | Choque +4 2d8 | — | minion, âncora |
| **Geleia Ocre** *(Ochre Jelly)* | 2 | 8 | 45 | Pseudópode +4 2d6+2+1d6 | — | minion, âncora |
| **Grell** | 3 | 12 | 55 | Tentáculos +4 1d10+2 + envenenado (save CON CD 13) | **Tentáculos Paralisantes** · save CON CD 12 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Grick** | 2 | 14 | 27 | Tentáculos +4 2d6+2 | — | minion, âncora |
| **Grifo** *(Griffon)* | 2 | 12 | 59 | Bico +6 1d8+4 | — | minion, âncora |
| **Guerreiro Githyanki** *(Githyanki Warrior)* | 3 | 17 | 49 | Montante +4 2d6+2+2d6 | — | minion, âncora |
| **Gárgula** *(Gargoyle)* | 2 | 15 | 52 | Mordida +4 1d6+2 | — | minion, âncora |
| **Homem-Javali** *(Wereboar)* | 4 | 10 | 78 | Presas +5 2d6+3 + perdicao (save SAB CD 13) | — | minion, âncora |
| **Homem-Rato** *(Wererat)* | 2 | 12 | 33 | Mordida +4 1d4+2 + perdicao (save SAB CD 12) | — | minion, âncora |
| **Homem-Tigre** *(Weretiger)* | 4 | 12 | 120 | Cimitarra +5 1d6+3 + perdicao (save SAB CD 13) | **Bote** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Horror Elmado** *(Helmed Horror)* | 4 | 20 | 60 | Espada Longa +6 1d8+4 | — | minion, âncora |
| **Horror Gancho** *(Hook Horror)* | 3 | 15 | 75 | Gancho +6 2d6+4 | — | minion, âncora |
| **Javali Gigante** *(Giant Boar)* | 2 | 12 | 42 | Presa +5 2d6+3 | **Investida Selvagem** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Lobisomem** *(Werewolf)* | 3 | 11 | 58 | Lança +4 1d6+2 + perdicao (save SAB CD 13) | — | minion, âncora |
| **Lobo do Inverno** *(Winter Wolf)* | 3 | 13 | 75 | Mordida +6 2d6+4 | **Sopro Gélido** · 4d8 · save DES CD 12 · em 2 · deixa letargia, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | matilha · minion, âncora |
| **Lâmia** *(Lamia)* | 4 | 13 | 97 | Garras +5 2d10+3 + perdicao (save SAB CD 13) | **Toque Encantador** · save SAB CD 13 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Lívido** *(Ghast)* | 2 | 13 | 36 | Mordida +3 2d8+3 + letargia, exaustao (save CON CD 12) | **Garras Paralisantes** · save CON CD 13 · atordoa 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Mantícora** *(Manticore)* | 3 | 14 | 68 | Mordida +5 1d8+3 | **Rajada de Espinhos** · 3d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Merrow** | 2 | 13 | 45 | Mordida +6 1d8+4 | — | minion, âncora |
| **Minotauro** *(Minotaur)* | 3 | 14 | 76 | Machado Grande +6 2d12+4 | **Investida Selvagem** · 6d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Monge Githzerai** *(Githzerai Monk)* | 2 | 14 | 38 | Ataque Desarmado +4 1d8+2+2d8 | — | minion, âncora |
| **Monitor Kuo-toa** *(Kuo-toa Monitor)* | 3 | 13 | 65 | Mordida +6 1d4+2 + tolice (save INT CD 13) | — | minion, âncora |
| **Myconid Soberano** *(Myconid Sovereign)* | 2 | 13 | 60 | Soco +3 3d4+1+3d4 | **Esporos** · save CON CD 12 · em 3 · deixa perturbacao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mímico** *(Mimic)* | 2 | 12 | 58 | Pseudópode +5 1d8+3 | **Aderência** · save FOR CD 13 · deixa moleza · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Múmia** *(Mummy)* | 3 | 11 | 58 | Punho Apodrecido +5 2d6+3+3d6 + debilidade (save CON CD 13) | **Olhar Terrível** · save SAB CD 13 · atordoa 1 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Naga Ossuária (Espiritual)** *(Bone Naga (Spirit))* | 4 | 15 | 58 | Mordida +5 2d6+3+3d6 + fraqueza (save CON CD 13) | — | minion, âncora |
| **Naga Ossuária (Guardiã)** *(Bone Naga (Guardian))* | 4 | 15 | 58 | Mordida +5 2d6+3+3d6 | — | minion, âncora |
| **Nothic** | 2 | 15 | 45 | Garra +4 1d6+3 | **Olhar Apodrecido** · 3d6 · save CON CD 13 · deixa perturbacao · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Ogro** *(Ogre)* | 2 | 11 | 59 | Clava Grande +6 2d8+4 | **Golpe Poderoso** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Olho de Gruumsh Orc** *(Orc Eye of Gruumsh)* | 2 | 16 | 45 | Lança +5 1d6+3+1d8 | **Maldição de Gruumsh** · save SAB CD 13 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Orog** | 2 | 18 | 42 | Machado Grande +6 1d12+4 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Pentadrone** | 2 | 16 | 32 | Braço +4 1d6+2 | **Paralysis Gas** · save CON CD 11 · em 2 · atordoa 1 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Peritonte** *(Peryton)* | 2 | 13 | 33 | Chifrada +5 1d8+3 | — | minion, âncora |
| **Pesadelo** *(Nightmare)* | 3 | 13 | 68 | Cascos +6 2d8+4+2d6 | — | minion, âncora |
| **Poltergeist** | 2 | 12 | 22 | Pancada Brutal +4 3d6 | — | minion, âncora |
| **Presa de Yeenoghu Gnoll** *(Gnoll Fang of Yeenoghu)* | 4 | 14 | 65 | Mordida +5 1d6+3 | — | âncora, boss |
| **Pudim Negro** *(Black Pudding)* | 4 | 7 | 85 | Pseudópode +5 1d6+3+4d8 + deterioracao, moleza (save CON CD 13) | — | minion, âncora |
| **Pégaso** *(Pegasus)* | 2 | 12 | 59 | Cascos +6 2d6+4 | — | minion, âncora |
| **Quaggoth** | 2 | 13 | 45 | Garra +5 1d6+3 | — | minion, âncora |
| **Rainha Lagarto** *(Lizard Queen)* | 4 | 15 | 78 | Mordida +5 1d6+3 | — | âncora, boss |
| **Rastejante da Carniça** *(Carrion Crawler)* | 2 | 13 | 51 | Tentáculos +8 1d4+2 + envenenado (save CON CD 12) | — | minion, âncora |
| **Rei Lagarto** *(Lizard King)* | 4 | 15 | 78 | Mordida +5 1d6+3 | — | âncora, boss |
| **Rinoceronte** *(Rhinoceros)* | 2 | 11 | 45 | Chifrada +7 2d8+5 | **Investida Selvagem** · 5d8 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Sacerdote** *(Priest)* | 2 | 13 | 27 | Maça +2 1d6 | **Guardiões Espirituais** · 3d8 · save SAB CD 13 · em 2 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Sacerdotisa Sahuagin** *(Sahuagin Priestess)* | 2 | 12 | 33 | Mordida +3 1d4+1 | — | âncora, boss |
| **Senhor da Matilha Gnoll** *(Gnoll Pack Lord)* | 2 | 15 | 49 | Glaive +5 1d10+3 | **Golpe Poderoso** · 5d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Súcubo** *(Succubus)* | 4 | 15 | 66 | Garra +5 1d6+3 | **Beijo Drenante** · 3d6 · save CON CD 15 · em 3 · deixa exaustao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Tapete Sufocante** *(Rug of Smothering)* | 2 | 12 | 33 | Sufocar +5 0 | **Sufocar** · 3d6 · save FOR CD 13 · atordoa 3 · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Thonot Quaggoth** *(Quaggoth Thonot)* | 3 | 13 | 45 | Garra +5 1d6+3 | — | âncora, boss |
| **Tigre-Dente-de-Sabre** *(Saber-Toothed Tiger)* | 2 | 12 | 52 | Mordida +6 1d10+5 | **Bote** · 5d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Urso-Coruja** *(Owlbear)* | 3 | 13 | 59 | Bico +7 1d10+5 + insensatez (save SAB CD 13) | — | minion, âncora |
| **Urso-das-Cavernas** *(Cave Bear)* | 2 | 12 | 42 | Mordida +7 1d8+5 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Urso-Polar** *(Polar Bear)* | 2 | 12 | 42 | Mordida +7 1d8+5 | **Golpe Poderoso** · 4d6 · rola ataque · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Veterano** *(Veteran)* | 3 | 17 | 58 | Espada Longa +5 1d8+3 | — | minion, âncora |
| **Wight** | 3 | 14 | 45 | Espada Longa +4 1d8+2 + deterioracao, exaustao (save CON CD 13) | — | âncora, boss |
| **Xamã Povo-Lagarto** *(Lizardfolk Shaman)* | 2 | 13 | 27 | Mordida +4 1d6+2 | — | âncora, boss |
| **Yeti** | 3 | 12 | 51 | Garra +6 1d6+4+1d6 | **Olhar Gélido** · save CON CD 14 · deixa letargia · *rec. 5+, sai na rodada 1* | minion, âncora |
| **Yuan-ti Malison (Tipo 1)** *(Yuan-ti Malison (Type 1))* | 3 | 12 | 66 | Mordida +5 1d4+3+2d6 + envenenado (save CON CD 13) | — | minion, âncora |
| **Yuan-ti Malison (Tipo 2)** *(Yuan-ti Malison (Type 2))* | 3 | 12 | 66 | Mordida +5 1d4+3+2d6 + envenenado (save CON CD 13) | — | minion, âncora |
| **Yuan-ti Malison (Tipo 3)** *(Yuan-ti Malison (Type 3))* | 3 | 12 | 66 | Constrição +5 2d6+3 + envenenado (save CON CD 13) | — | minion, âncora |
| **Zumbi de Ogro** *(Ogre Zombie)* | 2 | 8 | 85 | Maça Estrela +6 2d8+4 | — | minion, âncora |
| **Árvore Desperta** *(Awakened Tree)* | 2 | 13 | 59 | Pancada +6 3d6+4 | — | minion, âncora |
| **Íncubo** *(Incubus)* | 4 | 15 | 66 | Garra +5 1d6+3 | **Beijo Drenante** · 3d6 · save CON CD 15 · em 3 · deixa exaustao · *rec. 5+, sai na rodada 1* | âncora, boss |

## Tier 3 — CR 5 a 8

76 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Abominação Yuan-ti** *(Yuan-ti Abomination)* | 7 | 15 | 127 | Mordida +7 1d6+4+3d6 + envenenado (save CON CD 15) · Constrição +7 2d6+4 | **Contrair** · 6d8 · save FOR CD 15 · em 4 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Aparição** *(Wraith)* | 5 | 13 | 67 | Drenar Vida +6 4d8+3 + deterioracao, exaustao (save CON CD 14) ×2 | — | âncora, boss |
| **Arquissacerdote Kuo-toa** *(Kuo-toa Archpriest)* | 6 | 13 | 97 | Cetro +6 1d6+3+4d6 · Ataque Desarmado +6 1d4+3 | **Maldição** · save SAB CD 14 · em 3 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Assassino** *(Assassin)* | 8 | 15 | 78 | Espada Curta +6 1d6+3 + envenenado (save CON CD 15) · Besta Leve +6 1d8+3 | **Golpe Certeiro** · 3d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Barlgura** | 5 | 15 | 68 | Mordida +7 2d6+4 · Soco +7 1d10+4 | — | âncora, boss |
| **Barão Sahuagin** *(Sahuagin Baron)* | 5 | 16 | 76 | Mordida +7 2d4+4 · Garras +7 2d6+4 | — | âncora, boss |
| **Bruxa da Noite** *(Night Hag)* | 5 | 17 | 112 | Garras +7 2d8+4 ×2 | **Assombrar Pesadelos** · save SAB CD 15 · em 3 · deixa exaustao, perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Bulette** | 5 | 17 | 94 | Mordida +7 4d12+4 ×2 | **Salto Devastador** · 9d10 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cambion** | 5 | 19 | 82 | Raio de Fogo +7 3d6 · Lança +7 1d6+4 | **Raio de Fogo** · 4d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cavaleiro Githyanki** *(Githyanki Knight)* | 8 | 18 | 91 | Montante de Prata +9 2d6+6+3d6 + introversao (save SAB CD 15) ×2 | **Golpe Poderoso** · 7d8 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Chasme** | 6 | 15 | 84 | Probóscide +5 4d6+2+7d6 ×2 | **Zumbido Soporífero** · save CON CD 13 · em 3 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Ciclope** *(Cyclops)* | 6 | 14 | 138 | Clava Grande +9 3d8+6 · Pedra +9 4d10+6 | **Golpe Sísmico** · 7d8 · save DES CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Colosso Umbral** *(Umber Hulk)* | 5 | 18 | 93 | Garra +8 1d8+5 · Mandíbulas +8 2d8+5 | **Olhar Confuso** · save SAB CD 16 · em 3 · deixa insensatez · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Cria de Vampiro** *(Vampire Spawn)* | 5 | 15 | 82 | Mordida +6 1d6+3+2d6 + deterioracao (save CON CD 14) · Garras +6 2d4+3 | — | regenera 10/rodada · âncora, boss |
| **Crocodilo Gigante** *(Giant Crocodile)* | 5 | 14 | 85 | Mordida +8 3d10+5 + debilidade (save CON CD 14) · Cauda +8 2d8+5 | **Contrair** · 7d8 · save FOR CD 16 · em 3 · atordoa 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Devorador de Mentes** *(Mind Flayer)* | 7 | 15 | 71 | Tentáculos +7 2d10+4 · Extrair Cérebro +7 10d10 | **Rajada Mental** · 4d8+4 · save INT CD 15 · em 4 · deixa tolice · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Devorador de Mentes Arcanista** *(Mind Flayer Arcanist)* | 8 | 15 | 71 | Tentáculos +7 2d10+4 ×2 | **Rajada Mental** · 4d8+4 · save INT CD 15 · em 4 · deixa tolice · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Diabo Acorrentado** *(Chain Devil)* | 8 | 16 | 85 | Corrente +8 2d6+4 + debilidade (save CON CD 15) ×2 | **Máscara Perturbadora** · save SAB CD 15 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Diabo Farpado** *(Barbed Devil)* | 5 | 15 | 110 | Cauda +6 2d6+3 + debilidade (save CON CD 14) · Garra +6 1d6+3 | **Lançar Chama** · 5d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Branco Jovem** *(Young White Dragon)* | 6 | 17 | 133 | Mordida +7 2d10+4+1d8 · Garra +7 2d6+4 | **Sopro Gélido** · 10d8 · save CON CD 15 · em 3 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Bronze Jovem** *(Young Bronze Dragon)* | 8 | 18 | 142 | Mordida +8 2d10+5 + fraqueza (save CON CD 15) · Garra +8 2d6+5 | **Armas de Sopro** · 10d10 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Cobre Jovem** *(Young Copper Dragon)* | 7 | 17 | 119 | Mordida +7 2d10+4 · Garra +7 2d6+4 | **Armas de Sopro** · 9d8 · save DES CD 14 · em 4 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Latão Jovem** *(Young Brass Dragon)* | 6 | 17 | 110 | Mordida +7 2d10+4 · Garra +7 2d6+4 | **Armas de Sopro** · 12d6 · save DES CD 14 · em 3 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Negro Jovem** *(Young Black Dragon)* | 7 | 18 | 127 | Mordida +7 2d10+4+1d8 · Garra +7 2d6+4 | **Sopro Ácido** · 11d8 · save DES CD 14 · em 4 · deixa deterioracao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Verde Jovem** *(Young Green Dragon)* | 8 | 18 | 136 | Mordida +7 2d10+4+2d6 · Garra +7 2d6+4 | **Sopro Venenoso** · 12d6 · save CON CD 14 · em 4 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Drider** | 6 | 19 | 123 | Espada Longa +6 1d8+3 + envenenado (save CON CD 14) · Arco Longo +6 1d8+3+1d8 | **Teia** · save FOR CD 15 · em 3 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental da Terra** *(Earth Elemental)* | 5 | 17 | 126 | Pancada +8 2d8+5 ×2 | **Golpe Sísmico** · 5d8 · save DES CD 16 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental da Água** *(Water Elemental)* | 5 | 14 | 114 | Pancada +7 2d8+4 ×2 | **Whelm** · 2d8+4+2d8+4 · save FOR CD 15 · em 3 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental do Ar** *(Air Elemental)* | 5 | 15 | 90 | Pancada +8 2d8+5 ×2 | **Redemoinho** · 3d8+2+1d6 · save FOR CD 13 · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Elemental do Fogo** *(Fire Elemental)* | 5 | 13 | 102 | Toque +6 2d6+3+1d10 ×2 | **Explosão de Chamas** · 6d8 · save DES CD 14 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Espreitador Invisível** *(Invisible Stalker)* | 6 | 14 | 104 | Pancada +6 2d6+3 + insensatez (save SAB CD 14) ×2 | — | âncora, boss |
| **Espreitador Manto** *(Cloaker)* | 8 | 14 | 78 | Mordida +6 2d6+3 + insensatez (save SAB CD 15) · Cauda +6 1d8+3 | **Gemido** · save SAB CD 14 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Fomoriano** *(Fomorian)* | 8 | 14 | 149 | Clava Grande +9 3d8+6 ×2 | **Mau-Olhado** · save SAB CD 17 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Galeb Duhr** | 6 | 16 | 85 | Pancada +8 2d6+5 ×2 | — | âncora, boss |
| **Gigante da Colina** *(Hill Giant)* | 5 | 13 | 105 | Clava Grande +8 3d8+5 · Pedra +8 3d10+5 | **Golpe Sísmico** · 6d8 · save DES CD 16 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gigante da Pedra** *(Stone Giant)* | 7 | 17 | 126 | Clava Grande +9 3d8+6 + moleza (save DES CD 15) · Pedra +9 4d10+6 | **Golpe Sísmico** · 6d8 · save DES CD 17 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gigante do Gelo** *(Frost Giant)* | 8 | 15 | 138 | Machado Grande +9 3d12+6 + exaustao (save CON CD 15) · Pedra +9 4d10+6 | **Golpe Sísmico** · 9d8 · save DES CD 17 · em 5 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gladiador** *(Gladiator)* | 5 | 16 | 112 | Lança +7 2d6+4 + introversao (save SAB CD 14) · Escudada +7 2d4+4 | **Escudada** · save FOR CD 18 · em 3 · atordoa 1 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Golem de Carne** *(Flesh Golem)* | 5 | 9 | 93 | Pancada +7 2d8+4 + moleza (save DES CD 14) ×2 | **Golpe Poderoso** · 5d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Grick Alfa** *(Grick Alpha)* | 7 | 18 | 75 | Cauda +7 2d6+4 + deterioracao (save CON CD 15) · Tentáculos +7 4d8+4 | — | âncora, boss |
| **Guardião Protetor** *(Shield Guardian)* | 7 | 17 | 142 | Soco +7 2d6+4 + exaustao (save CON CD 15) ×2 | — | regenera 10/rodada · âncora, boss |
| **Guerreiro de Elite Drow** *(Drow Elite Warrior)* | 5 | 18 | 71 | Espada Curta +7 1d6+4+3d6 + envenenado (save CON CD 14) · Besta de Mão +7 1d6+4 | **Golpe Certeiro** · 6d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Górgona** *(Gorgon)* | 5 | 19 | 114 | Chifrada +8 2d12+5 · Cascos +8 2d10+5 | **Petrifying Breath** · save CON CD 13 · em 3 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Hezrou** | 8 | 16 | 136 | Mordida +7 2d10+4 · Garras +7 2d6+4 | **Fedor** · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Hidra** *(Hydra)* | 8 | 15 | 172 | Mordida +8 1d10+5 + insensatez (save SAB CD 15) ×2 | **Golpe Poderoso** · 5d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Homem-Urso** *(Werebear)* | 5 | 10 | 135 | Garra +7 2d8+4 + perdicao (save SAB CD 14) · Machado Grande +7 1d12+4 | **Golpe Poderoso** · 5d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Laçador** *(Roper)* | 5 | 20 | 93 | Tentáculo +7 0 · Mordida +7 4d8+4 | **Tentáculos** · save FOR CD 15 · em 3 · deixa fraqueza · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Macaco Gigante** *(Giant Ape)* | 7 | 12 | 157 | Soco +9 3d10+6 + fraqueza (save CON CD 15) · Pedra +9 7d6+6 | **Arremesso de Pedra** · 7d8 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mago** *(Mage)* | 6 | 12 | 40 | Adaga +5 1d4+2 + tolice (save INT CD 14) ×2 | **Bola de Fogo** · 8d6 · save DES CD 17 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mago Drow** *(Drow Mage)* | 7 | 12 | 45 | Cajado +2 1d6-1 + introversao (save SAB CD 15) ×2 | **Relâmpago** · 8d6 · save DES CD 14 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mamute** *(Mammoth)* | 6 | 13 | 126 | Chifrada +10 4d8+7 · Pisão +10 4d10+7 | **Investida Selvagem** · 9d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Medusa** | 6 | 15 | 127 | Cabelo de Serpentes +5 1d4+2+4d6 · Espada Curta +5 1d6+2 | **Olhar Petrificante** · save CON CD 14 · em 3 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Mezzoloth** | 5 | 18 | 75 | Garras +7 2d4+4 · Tridente +7 1d6+4 | — | âncora, boss |
| **Monte Cambaleante** *(Shambling Mound)* | 5 | 15 | 136 | Pancada +7 2d8+4 + moleza (save DES CD 14) ×2 | **Engolfar** · 5d8 · save FOR CD 15 · em 3 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Naga Espiritual** *(Spirit Naga)* | 8 | 15 | 75 | Mordida +7 1d6+4 + envenenado (save CON CD 15) ×2 | **Raio Elétrico** · 8d6 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Oni** | 7 | 16 | 110 | Garra +7 1d8+4 + moleza (save DES CD 15) · Glaive +7 2d10+4 | **Cone Gélido** · 8d8 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Otyugh** | 5 | 14 | 114 | Mordida +6 2d8+3 + perturbacao (save SAB CD 14) · Tentáculo +6 1d8+3+1d8 | — | âncora, boss |
| **Quimera** *(Chimera)* | 6 | 14 | 114 | Mordida +7 2d6+4 + perturbacao (save SAB CD 14) · Chifres +7 1d12+4 | **Sopro de Fogo** · 7d8 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Remorhaz Jovem** *(Young Remorhaz)* | 5 | 14 | 93 | Mordida +6 3d10+4+2d6 ×2 | — | âncora, boss |
| **Revenante** *(Revenant)* | 5 | 13 | 136 | Soco +7 2d6+4+4d6 ×2 | **Olhar Vingativo** · save SAB CD 15 · em 3 · atordoa 2 · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Sacerdotisa Drow de Lolth** *(Drow Priestess of Lolth)* | 8 | 16 | 71 | Flagelo +5 1d6+2+5d6 ×2 | **Maldição** · save SAB CD 18 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Salamandra** *(Salamander)* | 5 | 15 | 90 | Lança +7 2d6+4 · Cauda +7 2d6+4+2d6 | — | âncora, boss |
| **Senhor da Guerra Hobgoblin** *(Hobgoblin Warlord)* | 6 | 20 | 97 | Azagaia +9 1d6+3 · Espada Longa +9 1d8+3 | — | âncora, boss |
| **Serpe** *(Wyvern)* | 6 | 13 | 110 | Mordida +7 2d6+4 + envenenado (save CON CD 14) · Ferrão +7 2d6+4 | — | âncora, boss |
| **Slaad Azul** *(Blue Slaad)* | 7 | 15 | 123 | Mordida +8 2d6+5 + perturbacao (save SAB CD 15) · Garra +8 2d6+5 | — | regenera 10/rodada · âncora, boss |
| **Slaad Verde** *(Green Slaad)* | 8 | 16 | 127 | Mordida +7 2d6+4 + perturbacao (save SAB CD 15) · Garra +7 1d6+4 | **Bola de Fogo** · 8d6 · save DES CD 15 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Slaad Vermelho** *(Red Slaad)* | 5 | 14 | 93 | Mordida +6 2d4+3 + deterioracao, tolice (save CON CD 14) · Garra +6 1d8+3 | — | regenera 10/rodada · âncora, boss |
| **Tiranossauro Rex** *(Tyrannosaurus Rex)* | 8 | 13 | 136 | Mordida +10 4d12+7 + debilidade (save CON CD 15) · Cauda +10 3d8+7 | **Golpe Poderoso** · 8d10 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Tricerátopo** *(Triceratops)* | 5 | 13 | 95 | Chifrada +9 4d8+6 · Pisão +9 3d10+6 | **Investida Selvagem** · 9d8 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Troll** | 5 | 15 | 84 | Mordida +7 1d6+4 + medo (save SAB CD 14) · Garra +7 2d6+4 | **Golpe Poderoso** · 4d6 · rola ataque · em 3 · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Unicórnio** *(Unicorn)* | 5 | 12 | 67 | Cascos +7 2d6+4 · Chifre +7 1d8+4 ×2 | — | âncora, boss |
| **Veterano Meio-Dragão Vermelho** *(Half-Red Dragon Veteran)* | 5 | 18 | 65 | Espada Longa +5 1d8+3 + introversao (save SAB CD 14) · Espada Curta +5 1d6+3 | **Sopro de Fogo** · 7d6 · save DES CD 15 · em 3 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Vrock** | 6 | 15 | 104 | Bico +6 2d6+3 · Garras +6 2d10+3 | **Esporos** · 1d10 · save CON CD 14 · em 3 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Xorn** | 5 | 19 | 73 | Garra +6 1d6+3 · Mordida +6 3d6+3 | — | âncora, boss |
| **Zerth Githzerai** *(Githzerai Zerth)* | 6 | 17 | 84 | Ataque Desarmado +7 2d6+4+3d8 ×2 | — | âncora, boss |
| **Zumbi Beholder** *(Beholder Zombie)* | 5 | 15 | 93 | Mordida +3 4d6 + medo, fraqueza (save SAB CD 14) ×2 | — | âncora, boss |

## Tier 4 — CR 9 a 13

40 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Aboleth** | 10 | 17 | 135 | Tentáculo +9 2d6+5 · Cauda +9 3d6+5 ×3 | **Escravizar Mente** · save SAB CD 17 · em 4 · deixa tolice, debilidade · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Arcanaloth** | 12 | 17 | 104 | Garras +7 2d4+3 ×3 | **Maldição Arcana** · save SAB CD 17 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | boss |
| **Arquimago** *(Archmage)* | 12 | 12 | 99 | Adaga +6 1d4+2 + introversao (save SAB CD 16) ×3 | **Bola de Fogo** · 8d6 · save DES CD 21 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Behir** | 11 | 17 | 168 | Mordida +10 3d10+6 + insensatez (save SAB CD 16) · Constrição +10 2d10+6+2d10+6 ×2 | **Sopro de Relâmpago** · 12d10 · save DES CD 16 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Dao** | 11 | 18 | 187 | Soco +10 2d8+6 · Marreta +10 4d6+6 ×2 | **Golpe Sísmico** · 5d8 · save DES CD 19 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Deva** | 10 | 17 | 136 | Maça +8 1d6+4+4d8 ×3 | **Luz Radiante** · 9d8 · save CON CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Diabo Chifrudo** *(Horned Devil)* | 11 | 18 | 178 | Forcado +10 2d8+6 + debilidade (save CON CD 16) · Cauda +10 1d8+6 ×2 | — | âncora, boss |
| **Diabo Ósseo** *(Bone Devil)* | 9 | 19 | 142 | Garra +8 1d8+4 · Ferrão +8 2d8+4+5d6 | **Ferrão Venenoso** · 4d6 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Djinni** | 11 | 17 | 161 | Cimitarra +9 2d6+5+1d6 ×3 | **Redemoinho** · 6d8 · save FOR CD 18 · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Azul Jovem** *(Young Blue Dragon)* | 9 | 18 | 152 | Mordida +9 2d10+5+1d10 · Garra +9 2d6+5 | **Sopro de Relâmpago** · 10d10 · save DES CD 16 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Branco Adulto** *(Adult White Dragon)* | 13 | 18 | 200 | Mordida +11 2d10+6+1d8 · Garra +11 2d6+6 ×3 | **Sopro Gélido** · 12d8 · save CON CD 19 · em 5 · deixa medo, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Latão Adulto** *(Adult Brass Dragon)* | 13 | 18 | 172 | Mordida +11 2d10+6 · Garra +11 2d6+6 ×3 | **Armas de Sopro** · 13d6 · save DES CD 18 · em 5 · deixa medo, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Ouro Jovem** *(Young Gold Dragon)* | 10 | 18 | 178 | Mordida +10 2d10+6 · Garra +10 2d6+6 ×2 | **Armas de Sopro** · 10d10 · save DES CD 17 · em 4 · deixa fraqueza · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão de Prata Jovem** *(Young Silver Dragon)* | 9 | 18 | 168 | Mordida +10 2d10+6 · Garra +10 2d6+6 | **Armas de Sopro** · 12d8 · save CON CD 17 · em 4 · deixa letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Dragão Vermelho das Sombras Jovem** *(Young Red Shadow Dragon)* | 13 | 18 | 178 | Mordida +11 2d10+6+1d6 · Garra +11 2d6+6 ×2 | **Shadow Breath** · 16d6 · save DES CD 18 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Dragão Vermelho Jovem** *(Young Red Dragon)* | 10 | 18 | 178 | Mordida +10 2d10+6+1d6 · Garra +10 2d6+6 ×2 | **Sopro de Fogo** · 16d6 · save DES CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Efreeti** | 11 | 17 | 200 | Cimitarra +10 2d6+6+2d6 · Lançar Chama +7 5d6 ×2 | **Muralha de Fogo** · 8d8 · save DES CD 19 · em 4 · deixa exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Ente** *(Treant)* | 9 | 16 | 138 | Pancada +10 3d6+6 + moleza (save DES CD 16) · Pedra +10 4d10+6 | **Vinhas Constritoras** · save FOR CD 18 · em 4 · atordoa 3 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Erínia** *(Erinyes)* | 12 | 18 | 153 | Espada Longa +8 1d8+4 · Arco Longo +7 1d8+3+3d8 ×2 | **Flecha Envenenada** · 4d6 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | boss |
| **Gigante da Tempestade** *(Storm Giant)* | 13 | 16 | 230 | Montante +14 6d6+9 · Pedra +14 4d12+9 ×2 | **Raio** · 12d8 · save DES CD 17 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Gigante das Nuvens** *(Cloud Giant)* | 9 | 14 | 200 | Maça Estrela +12 3d8+8 · Pedra +12 4d10+8 | **Golpe Sísmico** · 8d8 · save DES CD 20 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Gigante do Fogo** *(Fire Giant)* | 9 | 18 | 162 | Montante +11 6d6+7 · Pedra +11 4d10+7 | **Golpe Sísmico** · 9d10 · save DES CD 19 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Ginoesfinge** *(Gynosphinx)* | 11 | 17 | 136 | Garra +8 2d8+4 ×4 | **Rugido** · save SAB CD 16 · em 5 · deixa medo · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Glabrezu** | 9 | 17 | 157 | Pinça +9 2d10+5 · Soco +9 2d4+2 | **Palavra de Poder** · save CON CD 17 · em 4 · atordoa 2 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Golem de Argila** *(Clay Golem)* | 9 | 14 | 133 | Pancada +8 2d10+5 + deterioracao (save CON CD 16) ×2 | — | âncora, boss, solo |
| **Golem de Pedra** *(Stone Golem)* | 10 | 17 | 178 | Pancada +10 3d8+6 + moleza (save DES CD 16) ×3 | **Slow** · save SAB CD 17 · em 4 · deixa letargia · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Marid** | 11 | 17 | 229 | Tridente +10 2d6+6 + insensatez (save SAB CD 16) ×3 | **Onda de Água** · 6d6 · save FOR CD 20 · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Naga Guardiã** *(Guardian Naga)* | 10 | 18 | 127 | Mordida +8 1d8+4 + envenenado (save CON CD 16) ×3 | **Cuspe Venenoso** · 4d6 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Nalfeshnee** | 13 | 18 | 184 | Mordida +10 5d10+5 · Garra +10 3d6+5 ×2 | **Horror Nimbus** · save SAB CD 15 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | boss |
| **Nycaloth** | 9 | 18 | 123 | Garra +9 2d6+5 · Machado Grande +9 2d12+5 | — | âncora, boss |
| **Observador** *(Beholder)* | 13 | 18 | 180 | Mordida +5 4d6 ×4 | **Raios Oculares** · 5d8 · save DES CD 17 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Rakshasa** | 13 | 16 | 110 | Garra +7 2d6+2 ×3 | **Maldição** · save SAB CD 18 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | boss |
| **Remorhaz** | 11 | 17 | 195 | Mordida +11 6d10+7+3d6 ×3 | **Calor Irradiante** · 14d10 · save CON CD 19 · em 5 · deixa exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Roca** *(Roc)* | 11 | 15 | 248 | Bico +13 4d8+9 · Garras +13 4d6+9 ×2 | **Mergulho** · 9d10 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | âncora, boss, solo |
| **Slaad Cinzento** *(Gray Slaad)* | 9 | 18 | 127 | Mordida +7 1d6+3 + tolice (save INT CD 16) · Garras +7 1d10+3 | — | regenera 10/rodada · âncora, boss |
| **Slaad da Morte** *(Death Slaad)* | 10 | 18 | 170 | Mordida +9 1d8+5+2d6 · Garras +9 1d10+5+2d6 ×2 | **Maldição Caótica** · save SAB CD 17 · em 4 · deixa perdicao · *rec. 5+, sai na rodada 1* | regenera 10/rodada · âncora, boss |
| **Ultroloth** | 13 | 19 | 153 | Espada Longa +8 1d8+3 ×3 | **Olhar Aterrorizante** · save SAB CD 17 · em 4 · deixa medo · *rec. 5+, sai na rodada 1* | boss |
| **Vampiro** *(Vampire)* | 13 | 16 | 144 | Mordida +9 1d6+4+3d6 + deterioracao, exaustao (save CON CD 16) · Ataque Desarmado +9 1d8+4 ×3 | **Encanto Vampírico** · save SAB CD 17 · em 4 · deixa perturbacao · *rec. 5+, sai na rodada 1* | regenera 20/rodada · boss |
| **Yeti Abominável** *(Abominable Yeti)* | 9 | 15 | 137 | Garra +11 2d6+7+2d6 ×2 | **Sopro Gélido** · 10d8 · save CON CD 18 · em 5 · deixa letargia, exaustao · metade quem resiste · *rec. 5+, sai na rodada 1* | âncora, boss |
| **Yochlol** | 10 | 15 | 136 | Pancada +6 1d6+2+6d6 ×3 | **Toque Venenoso** · 8d10 · save CON CD 16 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | âncora, boss |

## Tier 5 — CR 14 ou mais

24 criaturas.

| Criatura | CR | CA | HP | Golpes por rodada | Habilidade | Notas |
|---|---|---|---|---|---|---|
| **Androesfinge** *(Androsphinx)* | 17 | 17 | 199 | Garra +12 2d10+6 ×4 | **Rugido** · save SAB CD 20 · em 5 · deixa medo · *rec. 5+, sai na rodada 1* | boss, solo |
| **Balor** | 19 | 19 | 262 | Espada Longa +14 3d8+8+3d8 · Chicote +14 2d6+8+3d6 ×2 | **Explosão de Chamas** · 11d10 · save DES CD 22 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Cavaleiro da Morte** *(Death Knight)* | 17 | 20 | 180 | Espada Longa +11 1d8+5 ×3 | **Bola de Fogo Infernal** · 10d6+10d6 · save DES CD 19 · em 4 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Demilich** | 18 | 20 | 80 | Golpe +9 2d8+7 ×4 | **Howl** · save CON CD 15 · em 4 · deixa exaustao, deterioracao · *rec. 5+, sai na rodada 1* | boss, solo |
| **Diabo do Gelo** *(Ice Devil)* | 14 | 18 | 180 | Mordida +10 2d6+5+3d6 · Garras +10 2d4+5+3d6 ×2 | **Wall of Ice** · 10d6+5d6 · save DES CD 17 · em 4 · deixa exaustao, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss |
| **Dracolich Azul Adulto** *(Adult Blue Dracolich)* | 17 | 19 | 225 | Mordida +13 2d10+7+1d10 · Garra +13 2d6+7 ×3 | **Sopro de Relâmpago** · 12d10 · save DES CD 20 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Azul Adulto** *(Adult Blue Dragon)* | 16 | 19 | 225 | Mordida +12 2d10+7+1d10 · Garra +12 2d6+7 ×3 | **Sopro de Relâmpago** · 12d10 · save DES CD 19 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Bronze Adulto** *(Adult Bronze Dragon)* | 15 | 19 | 212 | Mordida +12 2d10+7 · Garra +12 2d6+7 ×3 | **Armas de Sopro** · 12d10 · save DES CD 19 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Cobre Adulto** *(Adult Copper Dragon)* | 14 | 18 | 184 | Mordida +11 2d10+6 · Garra +11 2d6+6 ×3 | **Armas de Sopro** · 12d8 · save DES CD 18 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Ouro Adulto** *(Adult Gold Dragon)* | 17 | 19 | 256 | Mordida +14 2d10+8 · Garra +14 2d6+8 ×3 | **Armas de Sopro** · 12d10 · save DES CD 21 · em 5 · deixa medo, fraqueza · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão de Prata Adulto** *(Adult Silver Dragon)* | 16 | 19 | 243 | Mordida +13 2d10+8 · Garra +13 2d6+8 ×3 | **Armas de Sopro** · 13d8 · save CON CD 20 · em 5 · deixa medo, letargia · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Negro Adulto** *(Adult Black Dragon)* | 14 | 19 | 195 | Mordida +11 2d10+6+1d8 · Garra +11 2d6+6 ×3 | **Sopro Ácido** · 12d8 · save DES CD 18 · em 5 · deixa medo, deterioracao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Verde Adulto** *(Adult Green Dragon)* | 15 | 19 | 207 | Mordida +11 2d10+6+2d6 · Garra +11 2d6+6 ×3 | **Sopro Venenoso** · 16d6 · save CON CD 18 · em 5 · deixa medo, envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Dragão Vermelho Adulto** *(Adult Red Dragon)* | 17 | 19 | 256 | Mordida +14 2d10+8+2d6 · Garra +14 2d6+8 ×3 | **Sopro de Fogo** · 18d6 · save DES CD 21 · em 5 · deixa medo · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Golem de Ferro** *(Iron Golem)* | 16 | 20 | 210 | Pancada +13 3d8+7 · Espada +13 3d10+7 ×2 | **Sopro Venenoso** · 10d8 · save CON CD 19 · em 5 · deixa envenenado · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Goristro** | 17 | 19 | 310 | Chifrada +13 7d10+7 + introversao (save SAB CD 16) · Soco +13 3d8+7 ×2 | **Investida Selvagem** · 13d10 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | boss, solo |
| **Marilith** | 16 | 18 | 189 | Espada Longa +9 2d8+4 · Cauda +9 2d10+4 ×2 | **Golpe Poderoso** · 6d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | boss |
| **Planetar** | 16 | 19 | 200 | Montante +12 4d6+7+5d8 ×3 | **Luz Radiante** · 14d10 · save CON CD 20 · em 4 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Senhor das Múmias** *(Mummy Lord)* | 15 | 17 | 97 | Punho Apodrecido +9 3d6+4+6d6 ×4 | **Olhar Terrível** · save SAB CD 17 · em 4 · deixa debilidade, medo · *rec. 5+, sai na rodada 1* | boss |
| **Tartaruga-Dragão** *(Dragon Turtle)* | 17 | 20 | 341 | Mordida +13 3d12+7 · Garra +13 2d8+7 ×2 | **Sopro de Vapor** · 15d6 · save CON CD 18 · em 5 · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Tirano da Morte** *(Death Tyrant)* | 14 | 19 | 187 | Mordida +5 4d6 ×4 | **Raio Negativo** · 5d8 · save CON CD 17 · em 4 · deixa deterioracao · metade quem resiste · *rec. 5+, sai na rodada 1* | boss, solo |
| **Vampiro Conjurador** *(Vampire Spellcaster)* | 15 | 16 | 144 | Mordida +9 1d6+4+3d6 + deterioracao (save CON CD 16) · Ataque Desarmado +9 1d8+4 ×3 | **Encanto Vampírico** · save SAB CD 17 · em 4 · deixa perturbacao · *rec. 5+, sai na rodada 1* | regenera 20/rodada · boss |
| **Vampiro Guerreiro** *(Vampire Warrior)* | 15 | 18 | 144 | Montante +9 2d6+4 + deterioracao (save CON CD 16) · Ataque Desarmado +9 1d8+4 ×3 | **Golpe Poderoso** · 5d6 · rola ataque · em 4 · *rec. 5+, sai na rodada 1* | regenera 20/rodada · boss |
| **Verme Púrpura** *(Purple Worm)* | 15 | 18 | 247 | Mordida +14 3d8+9 · Ferrão da Cauda +14 3d6+9 ×2 | **Ferrão Venenoso** · 8d8 · save CON CD 22 · em 4 · deixa envenenado · *rec. 5+, sai na rodada 1* | solo |

---

Gerado por `tools/gerar_criaturas_md.py` a partir de `data/bestiario.json`.
Não edite à mão: rode o gerador.
