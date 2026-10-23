## CRIAÇÃO DE FICHA — as fichas padrão das classes

O cadastro é **Nome → Classe → Skills**: cada classe tem um número
pré-definido de skills, habilidades, acerto, CA e dano, que sobem
de tier em tier. Um tier são dois níveis, e o teto é o nível 10.

**Este arquivo é gerado.** Ele sai de `src/classes.py`,
`src/habilidades.py` e `src/ameaca.py`, que são o que o bot executa de
verdade — então o que está aqui é o que acontece na mesa, não o que foi
combinado e esquecido. Para mudar uma ficha, mude a classe e rode:

```
.venv/Scripts/python.exe tools/gerar_fichas_md.py
```

Nos tiers 1, 3 e 5 das classes novas o jogador decide entre três
opções, e a escolhida é uma ativa que ele aciona; nos tiers 2 e 4 a
habilidade entra sozinha na conta. As seis primeiras classes vêm de
antes dessa regra e não a seguem.

### As classes

* [Ladino](#ladino)
* [Bárbaro](#bárbaro)
* [Guerreiro](#guerreiro)
* [Monge](#monge)
* [Patrulheiro](#patrulheiro)
* [Paladino](#paladino)
* [Xamã](#xamã)
* [Clérigo](#clérigo)
* [Artífice](#artífice)
* [Mago](#mago)
* [Bruxo](#bruxo)
* [Druida](#druida)
* [Feiticeiro](#feiticeiro)
* [Bardo](#bardo)

---

# **LADINO**

*Muitas perícias e o maior dado de dano por acerto.*

**Vida:** 17 a 73, +14 por tier  
**Saves fortes:** Destreza e Inteligência  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 17  
**AC:** 15  
**Skills:** 6  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 2d6+3

### **Passiva — Reliable Talent**

Soma +5 em todo teste de perícia.

---

## **Tier 2**

**HP:** 31  
**AC:** 16  
**Skills:** 6  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +6  
**Dano:** 3d6+4

### **Escolha — Expertise**

Escolhe 2 perícias com proficiência; o bônus delas dobra.

Escolhe 2 perícias com proficiência; dobra o bônus.

---

## **Tier 3**

**HP:** 45  
**AC:** 16  
**Skills:** 6  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +7  
**Dano:** 4d6+4

### **Ativa — Uncanny Dodge**

**1x por combate.**

Corta pela metade o primeiro golpe pesado que sofrer.

---

## **Tier 4**

**HP:** 59  
**AC:** 17  
**Skills:** 6  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +8  
**Dano:** 5d6+5

### **Escolha — Expertise**

Escolhe mais 2 perícias com proficiência; o bônus delas dobra.

Escolhe 2 perícias com proficiência; dobra o bônus.

---

## **Tier 5**

**HP:** 73  
**AC:** 18  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +10  
**Dano:** 6d6+5

### **Passiva — Reliable Talent +**

Soma +10 em todo teste de perícia.

---

# **BÁRBARO**

*O mais duro de derrubar, com o dado de dano mais alto.*

**Vida:** 23 a 103, +20 por tier  
**Saves fortes:** Força e Constituição  
**Ameaça inicial:** 5 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 23  
**AC:** 15  
**Skills:** 3  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d12+3

### **Ativa — Rage**

**1x por combate.**

50% menos dano e +2 de dano por 3 turnos.

---

## **Tier 2**

**HP:** 43  
**AC:** 16  
**Skills:** 3  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d12+6

### **Escolha — Primal Knowledge**

Ganha proficiência em mais 2 perícias.

Escolhe 2 perícias quaisquer; dá proficiência.

---

## **Tier 3**

**HP:** 63  
**AC:** 17  
**Skills:** 3  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 1d12+7

### **Passiva — Multiattack**

Ataca 2x por rodada.

### **Ativa — Reckless Attack**

**1x por combate.**

Os ataques do próximo turno tem vantagem, e você ganha ameaça 3 — atacar descuidado chama atenção.

---

## **Tier 4**

**HP:** 83  
**AC:** 18  
**Skills:** 3  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 1d12+7

### **Ativa — Relentless**

**1x por combate.**

Ao cair a 0 HP fica com 1 HP e ganha 1d12+7 de THP.

---

## **Tier 5**

**HP:** 103  
**AC:** 19  
**Skills:** 3  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 1d12+9

### **Ativa — Brutal Strike**

**1x por incursão.**

Com Reckless Attack ligado, o ataque sai com +1d10 de dano, e ele ganha o mesmo em THP.

---

# **GUERREIRO**

*A melhor CA e o acerto mais constante.*

**Vida:** 21 a 93, +18 por tier  
**Saves fortes:** Força e Constituição  
**Ameaça inicial:** 6 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 21  
**AC:** 17  
**Skills:** 3  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +6  
**Dano:** 1d10+3

### **Ativa — Second Wind**

**1x por combate.**

Recupera 30% do HP máximo.

---

## **Tier 2**

**HP:** 39  
**AC:** 18  
**Skills:** 3  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d10+6

### **Escolha — Fighting Style**

Escolhe um: +1 acerto, +1 CA ou +2 de dano.

* **Ofensivo** — +1 de acerto
* **Defensivo** — +1 de CA
* **Heavy** — +2 de dano

---

## **Tier 3**

**HP:** 57  
**AC:** 19  
**Skills:** 3  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 1d10+6

### **Passiva — Multiattack**

Ataca 2x por rodada.

### **Ativa — Action Surge**

**1x por combate.**

Age duas vezes no mesmo turno.

---

## **Tier 4**

**HP:** 75  
**AC:** 20  
**Skills:** 3  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 1d10+8

### **Passiva — Improved Critical**

Crítico com 19 ou 20 no dado.

---

## **Tier 5**

**HP:** 93  
**AC:** 21  
**Skills:** 3  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 1d10+10

### **Ativa — Action Mastery**

**1x por combate.**

Age duas vezes no mesmo turno.

---

# **MONGE**

*Muitas perícias e ataques rápidos.*

**Vida:** 17 a 73, +14 por tier  
**Saves fortes:** Força e Destreza  
**Ameaça inicial:** 4 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 17  
**AC:** 16  
**Skills:** 5  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d6+3

### **Ativa — Flurry of Blows**

**1x por descanso.**

Golpeia duas vezes no mesmo turno.

---

## **Tier 2**

**HP:** 31  
**AC:** 17  
**Skills:** 5  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d6+4

### **Passiva — Martial Arts**

Ao acertar, o próximo ataque ganha +1 acerto, até +2; errar zera.

---

## **Tier 3**

**HP:** 45  
**AC:** 18  
**Skills:** 6  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 1d8+4

### **Passiva — Multiattack**

Ataca 2x por rodada.

### **Ativa — Stunning Strike**

**1x por descanso.**

Um ataque que, se acertar, atordoa por 1 rodada. Só gasta o uso quando acerta.

---

## **Tier 4**

**HP:** 59  
**AC:** 19  
**Skills:** 6  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 1d8+5

### **Passiva — Mente e Corpo**

+2 em Acrobacia, Atletismo, Percepção, Furtividade e Sobrevivência.

---

## **Tier 5**

**HP:** 73  
**AC:** 20  
**Skills:** 7  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 1d10+5

### **Ativa — Perfect Strike**

**1x por combate.**

Um ataque que acerta e já sai crítico.

---

# **PATRULHEIRO**

*O melhor acerto e perícias de exploração.*

**Vida:** 19 a 83, +16 por tier  
**Saves fortes:** Destreza e Constituição  
**Ameaça inicial:** 3 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 19  
**AC:** 16  
**Skills:** 6  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +6  
**Dano:** 1d8+3

### **Ativa — Marca do Caçador**

**1x por combate.**

Marca um inimigo por 3 turnos, com +1d6 de dano nele.

---

## **Tier 2**

**HP:** 35  
**AC:** 17  
**Skills:** 6  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +9  
**Dano:** 1d8+4

### **Passiva — Predador**

+2 de dano contra inimigos com metade ou menos do HP.

---

## **Tier 3**

**HP:** 51  
**AC:** 18  
**Skills:** 7  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +10  
**Dano:** 1d8+4

### **Passiva — Multiattack**

Ataca 2x por rodada.

### **Ativa — Rajada do Caçador**

**1x por descanso.**

Um ataque em até 3 inimigos diferentes.

---

## **Tier 4**

**HP:** 67  
**AC:** 19  
**Skills:** 7  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +11  
**Dano:** 1d8+5

### **Passiva — Sobrevivente**

+2 em Percepção, Sobrevivência e Natureza.

### **Ativa — Sobrevivente — socorro**

**1x por incursão.**

Quando alguém falha o teste da sala, soma +5 — e só dispara se o +5 fizer passar.

---

## **Tier 5**

**HP:** 83  
**AC:** 20  
**Skills:** 8  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 1d8+5

### **Ativa — Caçador Supremo**

**1x por descanso.**

Uma presa por 3 turnos, com +2d8 e vantagem.

---

# **PALADINO**

*Linha de frente que cura e protege o grupo.*

**Vida:** 21 a 93, +18 por tier  
**Saves fortes:** Força e Sabedoria  
**Ameaça inicial:** 6 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 21  
**AC:** 17  
**Skills:** 3  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +6  
**Dano:** 1d8+4

### **Ativa — Cura pelas Mãos**

**1x por descanso.**

Cura um aliado em 30% do HP máximo dele.

---

## **Tier 2**

**HP:** 39  
**AC:** 18  
**Skills:** 3  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d8+6

### **Passiva — Golpe Consagrado**

Os ataques causam +2 de dano radiante.

---

## **Tier 3**

**HP:** 57  
**AC:** 19  
**Skills:** 4  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 1d8+6

### **Ativa — Golpe Divino**

**1x por combate.**

Um ataque com +3d8 de dano radiante.

---

## **Tier 4**

**HP:** 75  
**AC:** 20  
**Skills:** 4  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 1d8+6

### **Passiva — Líder Sagrado**

+2 em Persuasão, Intuição, Religião e Intimidação.

### **Ativa — Líder Sagrado — socorro**

**1x por incursão.**

Quando um aliado falha o teste da sala, soma +5 — e só dispara se o +5 fizer passar.

---

## **Tier 5**

**HP:** 93  
**AC:** 21  
**Skills:** 5  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 1d8+7

### **Ativa — Avatar da Luz**

**1x por incursão.**

3 turnos com +2 CA, +5 de dano e cura por turno.

---

# **XAMÃ**

*Apoio: fortalece o grupo enquanto luta.*

**Vida:** 17 a 73, +14 por tier  
**Saves fortes:** Sabedoria e Carisma  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 17  
**AC:** 16  
**Skills:** 5  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d6+3

### **Ativa — Tradição xamânica — marcial**

**1x por descanso.** O uso é o mesmo das outras opções deste tier: escolhe uma.

Um ataque com +1d6 de dano; você ganha 1d6 de THP.

### **Ativa — Tradição xamânica — espiritual**

**1x por descanso.** O uso é o mesmo das outras opções deste tier: escolhe uma.

Cura um aliado em 30% do HP máximo dele; você ganha 1d6+3 de THP.

---

## **Tier 2**

**HP:** 31  
**AC:** 17  
**Skills:** 5  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d6+3

### **Passiva — Espírito Guardião**

Com 19+ no d20 ganha 5 THP; com THP, o grupo ganha +1 em tudo.

---

## **Tier 3**

**HP:** 45  
**AC:** 18  
**Skills:** 6  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 1d6+4

### **Escolha — Multiattack ou Cântico Benevolente**

Escolhe entre atacar 2x por rodada ou dar 4 THP extra ao curar.

* **Multiattack** — Ataca 2x por rodada
* **Cântico Benevolente** — Curar dá +4 de THP ao alvo

### **Ativa — Dança totêmica**

**1x por descanso.**

O grupo cura 1% da vida, ganha 4d6 de THP e +1d6+4 no próximo ataque.

---

## **Tier 4**

**HP:** 59  
**AC:** 19  
**Skills:** 6  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 1d8+5

### **Passiva — Sintonização Ancestral**

Com 15+ no d20 ganha 5 THP. E +2 em História, Natureza, Medicina, Adestrar Animais e Intuição.

---

## **Tier 5**

**HP:** 73  
**AC:** 20  
**Skills:** 7  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 1d10+5

### **Passiva — Expansão totêmica**

Com THP, o grupo ganha +2 em acertos, testes, cura e dano.

### **Ativa — Guerreiros anciões**

**1x por incursão.**

Os próximos dois ataques dos aliados levam +1d6+5 de dano e critam com 15+, e o grupo cura 10% do HP. Com 20+ de THP, gasta 20 e vira 1d10+5, crítico automático, 20% de cura e 8d6 em todos os inimigos.

---

# **CLÉRIGO**

*Cura o grupo e dobra o inimigo com testes de resistência.*

**Vida:** 19 a 73, +13,5 por tier  
**Saves fortes:** Constituição e Sabedoria  
**Ameaça inicial:** 3 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 19  
**AC:** 15  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d8

### **Escolha — Magia de 1º círculo**

Escolhe uma: Cure Wounds, Command ou Guiding Bolt.

* **Cure Wounds** (1x por descanso) — cura um aliado em 30% do HP máximo dele.
* **Command** (1x por descanso) — um inimigo faz save de SAB; falhando, perde a próxima vez.
* **Guiding Bolt** (1x por descanso) — 4d6 de dano num inimigo; o grupo ataca ele com vantagem na próxima rodada.

---

## **Tier 2**

**HP:** 31  
**AC:** 16  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d8

### **Escolha — Domínio divino**

Escolhe um: Protetor, Taumaturgo ou Curandeiro.

* **Protetor** — +2 de CA
* **Taumaturgo** — Proficiência em 2 perícias, à escolha; abre uma segunda escolha
* **Curandeiro** — As curas dele curam 10% a mais

---

## **Tier 3**

**HP:** 45  
**AC:** 17  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 2d8

### **Escolha — Magia de 2º círculo**

Escolhe uma: Spirit Guardians, Mass Healing Word ou Hypnotic Pattern.

* **Spirit Guardians** (1x por incursão) — todos os inimigos fazem save de SAB; quem falha leva 3d8.
* **Mass Healing Word** (1x por descanso) — o grupo inteiro cura 15% do HP máximo.
* **Hypnotic Pattern** (1x por incursão) — todos os inimigos fazem save de SAB; quem falha perde a próxima vez.

---

## **Tier 4**

**HP:** 59  
**AC:** 18  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 2d8

### **Escolha — Domínio maior**

Escolhe um: Ataques abençoados, Especialista em cura ou Restauração.

* **Ataques abençoados** — +1d8 de dano nos ataques
* **Especialista em cura** — As curas dele curam 10% a mais
* **Restauração** — As curas dele tiram o atordoamento

---

## **Tier 5**

**HP:** 73  
**AC:** 19  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 2d8

### **Escolha — Magia de 3º círculo**

Escolhe uma: Flame Strike, Mass Cure Wounds ou Dominate Person.

* **Flame Strike** (1x por incursão) — todos os inimigos fazem save de DES; quem falha leva 10d6, quem passa leva metade.
* **Mass Cure Wounds** (1x por descanso) — o grupo inteiro cura 35% do HP máximo.
* **Dominate Person** (1x por descanso) — um inimigo faz save de SAB; falhando, ataca outra criatura dele.

---

# **ARTÍFICE**

*Empresta número ao grupo: infunde o equipamento e salva o teste alheio.*

**Vida:** 19 a 73, +13,5 por tier  
**Saves fortes:** Constituição e Inteligência  
**Ameaça inicial:** 3 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 19  
**AC:** 16  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d10

### **Escolha — Magia de ferramenta**

Escolhe uma: Cure Wounds, Thunderwave ou Faerie Fire.

* **Cure Wounds** (1x por descanso) — cura um aliado em 30% do HP máximo dele.
* **Thunderwave** (1x por descanso) — todos os inimigos fazem save de CON; quem falha leva 2d8, quem passa leva metade.
* **Faerie Fire** (1x por descanso) — um inimigo fica delineado; o grupo ataca ele com vantagem na próxima rodada.

---

## **Tier 2**

**HP:** 31  
**AC:** 17  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d10

### **Escolha — Infusão**

O equipamento que ele infunde dá +1 ao grupo inteiro. Escolhe onde: acerto, CA ou dano.

* **Armas infundidas** — +1 de acerto para o grupo inteiro
* **Armaduras infundidas** — +1 de CA para o grupo inteiro
* **Munição infundida** — +1 de dano para o grupo inteiro

---

## **Tier 3**

**HP:** 45  
**AC:** 18  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 2d10

### **Escolha — Engenho**

Escolhe um: Arma Arcana, Sabedoria Alquímica ou Precisão Guiada.

* **Arma Arcana** — +1d8 de dano em todo golpe dele
* **Sabedoria Alquímica** — As curas dele curam 10% a mais
* **Precisão Guiada** — +3 de dano em todo golpe dele

---

## **Tier 4**

**HP:** 59  
**AC:** 19  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 2d10

### **Ativa — Flash of Genius**

**1x por descanso.**

Quando alguém do grupo falha o teste da sala, soma +5 — e só dispara se o +5 fizer passar.

---

## **Tier 5**

**HP:** 73  
**AC:** 20  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 3d10

### **Ativa — Arcane Jolt — destrutivo**

**1x por combate.** O uso é o mesmo das outras opções deste tier: escolhe uma.

Um golpe com +2d6 de dano.

### **Ativa — Arcane Jolt — restaurador**

**1x por combate.** O uso é o mesmo das outras opções deste tier: escolhe uma.

Cura um aliado em 15% do HP máximo dele.

### **Passiva — Gênio refinado**

O Flash of Genius dele soma +10 em vez de +5.

---

# **MAGO**

*Apaga a sala com uma magia e cai em dois golpes.*

**Vida:** 15 a 63, +12 por tier  
**Saves fortes:** Constituição e Inteligência  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 15  
**AC:** 13  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d10

### **Escolha — Magia de 1º círculo**

Escolhe uma: Magic Missile, Sleep ou Thunderwave.

* **Magic Missile** (1x por descanso) — 3d4+3 num inimigo. Não tem save — os dardos sempre acertam.
* **Sleep** (1x por descanso) — todos os inimigos fazem save de SAB; quem falha perde a próxima vez.
* **Thunderwave** (1x por descanso) — todos os inimigos fazem save de CON; quem falha leva 2d8, quem passa leva metade.

---

## **Tier 2**

**HP:** 27  
**AC:** 14  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 2d10

### **Passiva — Scholar**

+3 em Arcanismo, História, Investigação, Medicina, Natureza e Religião: ele estudou todas.

---

## **Tier 3**

**HP:** 39  
**AC:** 15  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 2d10

### **Escolha — Magia de 3º círculo**

Escolhe uma: Fireball, Hypnotic Pattern ou Fly.

* **Fireball** (1x por descanso) — todos os inimigos fazem save de DES; quem falha leva 8d6, quem passa leva metade.
* **Hypnotic Pattern** (1x por descanso) — todos os inimigos fazem save de SAB; quem falha perde a próxima vez.
* **Fly** (1x por descanso) — três aliados sobem fora de alcance por 3 rodadas — os inimigos quase deixam de mirá-los.

---

## **Tier 4**

**HP:** 51  
**AC:** 16  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 3d10

### **Escolha — Tradição arcana**

Escolhe uma: Evocação Potente, Escudo Arcano ou Sabedoria Arcana.

* **Evocação Potente** — +1d8 de dano em tudo que ele lança
* **Escudo Arcano** — THP igual a 2x o tier, e recarrega a cada magia
* **Sabedoria Arcana** — +2 nos saves do grupo inteiro

---

## **Tier 5**

**HP:** 63  
**AC:** 17  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 4d10

### **Escolha — Magia de 5º círculo**

Escolhe uma: Cone of Cold, Hold Monster ou Circle of Power.

* **Cone of Cold** (1x por descanso) — todos os inimigos fazem save de CON; quem falha leva 12d8, quem passa leva metade.
* **Hold Monster** (1x por descanso) — um inimigo faz save de SAB; falhando, perde três vezes seguidas.
* **Circle of Power** (1x por descanso) — por 3 rodadas o grupo rola os saves com vantagem e, passando, não leva nem metade.

---

# **BRUXO**

*Trocou algo por poder: poucos favores do pacto, e cada um grande.*

**Vida:** 19 a 73, +13,5 por tier  
**Saves fortes:** Sabedoria e Carisma  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 19  
**AC:** 14  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d10

### **Escolha — Dádiva do pacto**

Escolhe uma: Hex, Arms of Hadar ou Charm Person.

* **Hex** (1x por incursão) — marca um inimigo por 3 rodadas; todo golpe nele causa +1d6 de dano.
* **Arms of Hadar** (1x por incursão) — todos os inimigos fazem save de FOR; quem falha leva 2d6, quem passa leva metade.
* **Charm Person** (1x por incursão) — um inimigo faz save de SAB; falhando, perde a próxima vez.

---

## **Tier 2**

**HP:** 31  
**AC:** 15  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d10

### **Escolha — Eldritch Invocation**

Conhecimento proibido que fica ligado. Escolhe uma: Agonizing Blast, Fiendish Vigor ou Devil's Sight.

* **Agonizing Blast** — +3 de dano em todo Eldritch Blast
* **Fiendish Vigor** — Abre o combate com vida temporária
* **Devil's Sight** — +3 em Percepção e Investigação

---

## **Tier 3**

**HP:** 45  
**AC:** 16  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 2d10

### **Escolha — Favor do patrono**

Escolhe uma: Hunger of Hadar, Healing Light ou Hypnotic Pattern.

* **Hunger of Hadar** (1x por incursão) — todos os inimigos fazem save de DES; quem falha leva 6d6 e perde a próxima vez.
* **Healing Light** (1x por incursão) — cura um aliado em 40% do HP máximo dele.
* **Hypnotic Pattern** (1x por incursão) — todos os inimigos fazem save de SAB; quem falha perde as duas próximas vezes.

---

## **Tier 4**

**HP:** 59  
**AC:** 17  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 2d10

### **Escolha — Benesse do patrono**

Escolhe uma: Dark One's Own Luck, Dark One's Blessing ou Radiant Soul.

* **Dark One's Own Luck** (1x por incursão) — quando VOCÊ falha o teste da sala, o patrono soma +10 — e só dispara se o +10 fizer passar.
* **Dark One's Blessing** — Vida temporária ao derrubar um inimigo
* **Radiant Soul** — +1d8 de dano em tudo que ele lança

---

## **Tier 5**

**HP:** 73  
**AC:** 18  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 3d10

### **Escolha — Grande favor**

Escolhe uma: Hold Monster, Synaptic Static ou Summon Greater Demon.

* **Hold Monster** (1x por incursão) — um inimigo faz save de SAB; falhando, perde três vezes seguidas.
* **Synaptic Static** (1x por incursão) — todos os inimigos fazem save de INT; quem falha leva 8d6 e perde 3 de ataque por 3 rodadas.
* **Summon Greater Demon** (1x por incursão) — um demônio entra na sala com HP próprio, age na vez dele e bate no inimigo mais ferido. Sai quando o grupo troca de sala.

---

# **DRUIDA**

*Vira bicho para bater: o dano dele está na forma, não nele.*

**Vida:** 19 a 73, +13,5 por tier  
**Saves fortes:** Constituição e Sabedoria  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 19  
**AC:** 15  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d8

### **Escolha — Wild Shape**

A forma que ele veste. Escolhe uma: Urso, Lobo ou Aranha.

* **Wild Shape — Urso** (1x por descanso) — vira urso por 3 rodadas. +3 de CA, vida temporária igual a 3x o tier, e o dado da forma.
* **Wild Shape — Lobo** (1x por descanso) — vira lobo por 3 rodadas. Dois golpes por rodada e vida temporária igual a 2x o tier.
* **Wild Shape — Aranha** (1x por descanso) — vira aranha por 3 rodadas. Cada golpe que acerta tira 2 do ataque do alvo por 2 rodadas.

---

## **Tier 2**

**HP:** 31  
**AC:** 16  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d8

### **Escolha — Companheiro selvagem**

Um espírito animal o acompanha. Escolhe o que ele faz: cura, morde junto, ou avisa do perigo.

* **Lambe as feridas** — Cura 3 por tier ao abrir o combate
* **Morde junto** — +2 de dano em todo golpe dele
* **Avisa do perigo** — +3 em todo teste de perícia

---

## **Tier 3**

**HP:** 45  
**AC:** 17  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 2d8

### **Escolha — Magia de círculo**

Escolhe uma: Aura of Vitality, Call Lightning ou Conjure Animals.

* **Aura of Vitality** (1x por descanso) — por 3 rodadas o grupo inteiro recupera 10% do HP máximo a cada rodada.
* **Call Lightning** (1x por descanso) — todos os inimigos fazem save de DES; quem falha leva 6d10, quem passa leva metade.
* **Conjure Animals** (1x por descanso) — um bando de bichos entra na sala, age na vez dele e bate no inimigo mais ferido.

---

## **Tier 4**

**HP:** 59  
**AC:** 18  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 2d8

### **Escolha — Dádiva da natureza**

Escolhe uma: Forma Lunar, Presságio ou Golpe Primal.

* **Forma Lunar** — A forma da o dobro de vida temporária
* **Presságio** (1x por descanso) — quando alguém do grupo falha o teste da sala, soma +5 — e só dispara se o +5 fizer passar.
* **Golpe Primal** — +1d8 de dano em todo golpe dele

---

## **Tier 5**

**HP:** 73  
**AC:** 19  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 2d8

### **Escolha — Magia maior**

Escolhe uma: Antilife Shell, Conjure Elemental ou Mass Cure Wounds.

* **Antilife Shell** (1x por descanso) — dois aliados ficam 2 rodadas fora do alcance — as criaturas batem em quem sobrou, e só neles se não houver mais ninguém.
* **Conjure Elemental** (1x por descanso) — um elemental entra na sala com 70 HP, age na vez dele e bate no inimigo mais ferido.
* **Mass Cure Wounds** (1x por descanso) — o grupo inteiro cura 35% do HP máximo.

---

# **FEITICEIRO**

*A magia vem de dentro, e ele a torce: cada feitiço sai melhorado.*

**Vida:** 15 a 63, +12 por tier  
**Saves fortes:** Destreza e Constituição  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 15  
**AC:** 13  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d10

### **Escolha — Fagulha inata**

Escolhe uma: Chromatic Orb, Burning Hands ou Dissonant Whispers.

* **Chromatic Orb** (1x por descanso) — 4d8 num inimigo. Não tem save — a esfera acerta.
* **Burning Hands** (1x por descanso) — todos os inimigos fazem save de DES; quem falha leva 3d6, quem passa leva metade.
* **Dissonant Whispers** (1x por descanso) — um inimigo faz save de SAB; falhando, leva 3d6 e perde a próxima vez.

---

## **Tier 2**

**HP:** 27  
**AC:** 14  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 2d10

### **Escolha — Metamagia**

Ele torce as próprias magias, para sempre. Escolhe uma: Empowered, Twinned ou Heightened.

* **Empowered Spell** — +1d8 de dano em toda magia dele
* **Twinned Spell** — As magias de um alvo pegam dois
* **Heightened Spell** — A criatura resiste com desvantagem

---

## **Tier 3**

**HP:** 39  
**AC:** 15  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 2d10

### **Escolha — Magia da origem**

Escolhe uma: Lightning Bolt, Haste ou Grilhões Planares.

* **Lightning Bolt** (1x por descanso) — todos os inimigos fazem save de DES; quem falha leva 8d6, quem passa leva metade.
* **Haste** (1x por descanso) — um aliado ataca duas vezes por rodada e ganha +2 de CA, por 3 rodadas.
* **Grilhões Planares** (1x por descanso) — um inimigo faz save de DES e leva 4d8 (metade no sucesso). Falhando, fica acorrentado: sangra 2d8 no fim de cada rodada e refaz o save para escapar.

---

## **Tier 4**

**HP:** 51  
**AC:** 16  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 3d10

### **Escolha — Segunda metamagia**

Mais um jeito de torcer as magias. Escolhe uma: Quickened, Empowered, Twinned ou Heightened.

* **Quickened Spell** — Lança a magia E ataca no mesmo turno
* **Empowered Spell** — +1d8 de dano em toda magia dele
* **Twinned Spell** — As magias de um alvo pegam dois
* **Heightened Spell** — A criatura resiste com desvantagem

---

## **Tier 5**

**HP:** 63  
**AC:** 17  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 4d10

### **Escolha — Magia maior**

Escolhe uma: Polymorph, Cone of Cold ou Dimension Door.

* **Polymorph** (1x por descanso) — um aliado vira uma fera por 3 rodadas — bate com o dado dela, +2 de CA e vida temporária.
* **Cone of Cold** (1x por descanso) — todos os inimigos fazem save de CON; quem falha leva 12d8, quem passa leva metade.
* **Dimension Door** (1x por descanso) — ele e um aliado desaparecem por 2 rodadas — nenhuma criatura consegue mirá-los.

---

# **BARDO**

*Sopra o dado em quem falhou: a classe que faz o grupo acertar.*

**Vida:** 19 a 71, +13 por tier  
**Saves fortes:** Destreza e Carisma  
**Ameaça inicial:** 2 — o peso dele no sorteio de alvo das criaturas

---

## **Tier 1**

**HP:** 19  
**AC:** 14  
**Skills:** 4  
**Bônus de Skills:** +3 / +5 com Prof.  
**Acerto:** +5  
**Dano:** 1d6

### **Escolha — Canção de abertura**

Escolhe uma: Healing Word, Dissonant Whispers ou Charm Person.

* **Healing Word** (1x por descanso) — cura um aliado em 20% do HP máximo dele.
* **Dissonant Whispers** (1x por descanso) — um inimigo faz save de SAB; falhando, leva 3d6 e perde a próxima vez.
* **Charm Person** (1x por descanso) — um inimigo faz save de SAB; falhando, perde as duas próximas vezes.

---

## **Tier 2**

**HP:** 32  
**AC:** 15  
**Skills:** 4  
**Bônus de Skills:** +4 / +7 com Prof.  
**Acerto:** +7  
**Dano:** 1d8

### **Escolha — Inspiração Bárdica**

O dado que ele sopra em quem falha. Escolhe em que rolagem ele entra: ataque, resistência ou perícia.

* **Inspiração — no ataque** (3x por descanso) — quando um aliado erra o golpe por pouco, o dado dele sobe no acerto.
* **Inspiração — na resistência** (3x por descanso) — quando um aliado falha o save de uma criatura por pouco, o dado o faz resistir.
* **Inspiração — na perícia** (3x por descanso) — quando alguém falha o teste da sala por pouco, o dado o faz passar.

---

## **Tier 3**

**HP:** 45  
**AC:** 16  
**Skills:** 5  
**Bônus de Skills:** +4 / +8 com Prof.  
**Acerto:** +8  
**Dano:** 1d8

### **Escolha — Canção da faculdade**

Escolhe uma: Hypnotic Pattern, Aid ou Invisibility.

* **Hypnotic Pattern** (1x por descanso) — todos os inimigos fazem save de SAB; quem falha perde as duas próximas vezes.
* **Aid** (1x por descanso) — o grupo inteiro ganha 3d8 de vida temporária e cura 20% do HP máximo.
* **Invisibility** (1x por descanso) — um aliado desaparece por 3 rodadas — os inimigos quase deixam de mirá-lo.

---

## **Tier 4**

**HP:** 58  
**AC:** 17  
**Skills:** 5  
**Bônus de Skills:** +5 / +10 com Prof.  
**Acerto:** +9  
**Dano:** 2d8

### **Passiva — Inspiração maior**

O dado da Inspiração dele passa de d6 para d10.

### **Escolha — Repertório**

Escolhe uma: Expertise, Jack of All Trades ou Versatilidade.

* **Expertise** — Dobra o bônus de Atuação e Persuasão
* **Jack of All Trades** — +3 nos testes que ele NÃO treinou
* **Versatilidade** — +2 em todo teste de perícia

---

## **Tier 5**

**HP:** 71  
**AC:** 18  
**Skills:** 6  
**Bônus de Skills:** +5 / +11 com Prof.  
**Acerto:** +11  
**Dano:** 2d8

### **Escolha — Canção maior**

Escolhe uma: Mass Cure Wounds, Animate Objects ou Otto's Irresistible Dance.

* **Mass Cure Wounds** (1x por descanso) — o grupo inteiro cura 35% do HP máximo.
* **Animate Objects** (1x por descanso) — objetos animados entram na sala, agem na vez deles e batem no inimigo mais ferido.
* **Otto's Irresistible Dance** (1x por descanso) — um inimigo faz save de SAB; falhando, dança por 3 rodadas e perde a vez.

---
