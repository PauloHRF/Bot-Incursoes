# Ameaça: quem a criatura escolhe bater

Sem isto o alvo é sorteado uniformemente, e então não existe tanque: o mago leva tanta pancada quanto o guerreiro de armadura pesada. A Ameaça dá a cada personagem um peso nesse sorteio.

## As quatro partes

- **A inicial da classe** — a posição dela na sala virando número. Quem bate de perto aparece primeiro. Não escala por tier: ameaça é o papel na sala, não o poder do personagem.
- **O que as habilidades ligadas somam**, enquanto duram.
- **O que o personagem gerou agindo**, que acumula do primeiro golpe ao fim do combate e morre com a sala.
- **O bônus de quem está ferido** — `+3` abaixo de 30% do HP, que é a criatura indo terminar o serviço.

## Os seis grupos

A inicial sai de seis grupos, e não de um número por classe. Eram três degraus para catorze classes, com sete empatadas no piso: para a criatura, ladino, mago, bardo, bruxo, druida, feiticeiro e xamã eram a mesma pessoa. Os seis degraus abrem a janela de 20–30% para 20–38%.

| Grupo | Ameaça | Classes | Fatia da atenção |
|---|---|---|---|
| G1 | 12 | Guerreiro, Bárbaro | 38,0% |
| G2 | 10 | Paladino | 35,9% |
| G3 | 8 | Druida, Xamã, Patrulheiro | 33,3% |
| G4 | 6 | Monge, Clérigo, Bruxo | 30,2% |
| G5 | 4 | Artífice, Mago, Feiticeiro, Bardo | 26,1% |
| G6 | 2 | Ladino | 20,0% |

A fatia é num grupo de cinco onde os outros quatro estão no piso (2); o sorteio uniforme seria 20%. Classe sem grupo cai no padrão, 6.

**Os valores só importam como razão.** A potência normalizada cancela qualquer fator comum, então `12/10/8/6/4/2` e `6/5/4/3/2/1` dão a mesma distribuição. O tamanho absoluto da escala existe para dar resolução ao que é **somado** por cima — o bônus de ferido, o Reckless Attack, os pontos de ação. Dobrar a escala sem dobrar esses números os enfraquece em silêncio.

## Quem está por cair

Abaixo de **30% do HP** o personagem leva `+3` de ameaça: a criatura vai terminar o serviço.

São **pontos fixos**, e não uma fração da inicial. Por ser plano, o bônus empurra muito mais quem tem ameaça baixa — o Ladino sai de 20,0% para 28,3% da atenção, o Guerreiro de 38,0% para 40,6% —, e é exatamente isso que se quer: a criatura abandona o tanque inteiro para ir no mago sangrando. Proporcional faria o contrário, somando mais em quem já era o alvo.

Quem está no chão não entra: ele já saiu do sorteio por outro caminho.

## Quanto cada ação gera: o HP que ela moveu

Uma régua só para as três coisas que um personagem faz numa luta, cada uma medida contra a própria poça:

- o **dano** que ele causou, em fração do HP máximo somado dos inimigos da sala;
- a **cura** que ele deu (HP e vida temporária), em fração do HP máximo do grupo;
- o **dano que ele evitou** incapacitando uma criatura — o que ela daria nas rodadas que perdeu —, também em fração do HP do grupo.

A fração vira pontos pela escala, que é **55** pontos por 100% da poça. Medido na bateria dos cinco tiers com os resolvedores reais (`tools/medir_ameaca.py`, 8135 ações, 2026-11-14):

| Ação | Fração da poça | Pontos |
|---|---|---|
| média | 8,2% | 5 |
| boa (p90) | 17,2% | 9 |
| excepcional (p99) | 35,1% | 19 |

**O que conta como controle** é o que tira a vez: atordoamento e prisão. É a leitura literal de "não foi dado" — atrapalhar o ataque da criatura ou virá-la contra os seus seriam palpites sobre dano que ainda pode acontecer. E o que ela daria é o dado **dela** vezes a chance de passar da armadura de quem está na frente, porque o dano real também erra. Prender um Troll por três rodadas numa mesa de tier 5 rende uns 13 pontos: mais que a rodada de p90 de quem bate, e é de propósito — é uma ativa de tier 5, uma vez por descanso.

Conta o **ganho**, não o prazo: estender uma prisão de uma rodada para três vale duas, e renovar uma que já ia até lá vale zero.

**Por que fração, e não o dano cru.** Em números absolutos o tier alto dominaria: a mesma Fireball tira 90 de uma sala de T1 e 450 de uma de T5, e o mago de tier 5 teria dez vezes a ameaça do de tier 1 por fazer exatamente a mesma coisa. Em fração as duas valem igual, e é isso que permite uma escala só para o jogo todo — o p90 varia 1.98x entre tiers, que é ruído de cenário e não tendência.

**Por que vale uma rodada só.** A regra anterior era valor *declarado* — a ameaça da própria classe, dobrada em área e cura —, e ela acumulava o combate inteiro. Acumulando, a conta convergia: depois de três rodadas as fatias andavam meio ponto e a mira ficava parada no que a classe decidiu na abertura. A janela de uma rodada devolve a variação, e com ela o dano pode entrar sem travar ninguém no teto. O preço, dito de frente: a mira passou a responder ao dado, e não só à escolha.

**O overkill fica de fora**, por consequência de medir HP movido: bater 40 num inimigo de 5 move 5, porque matar o que já ia morrer não é notável.

Uma habilidade pode declarar `ameaca_gerada` na ação e pular a conta inteira. É o gancho para uma provocação de verdade — uma habilidade cujo ponto é chamar atenção não deveria depender de ter machucado alguém.

## A curva

A ameaça crua não vale direto no sorteio: ela passa por `peso = x ** 0.5`. Cada ponto novo rende menos que o anterior, então ninguém trava o combate stackando ameaça.

**Não é a fórmula de armadura `x / (x + Y)`**, e a diferença importa porque os pontos do HP movido são grandes perto da inicial — uma rodada de p99 soma 20 numa escala que vai de 2 a 12. Aquela fórmula tem teto em 1, então com a conta crescendo todo mundo encosta no teto e o sorteio volta a ser quase uniforme:

| Ameaça crua | Com a curva de armadura (teto em 1) | Com a potência |
|---|---|---|
| 100 / 60 / 40 | 35,4% / 33,4% / 31,2% | 41,5% / 32,2% / 26,3% |

A potência comprime igual embaixo e não satura — ainda é um tanque depois de uma luta longa.

`K` é o botão de calibragem, e anda ao contrário do que parece: **K pequeno achata** (tudo encosta em 1) e **K = 1 é o stack simples**, somar e dividir.

## A janela: o que valeu na rodada passada

A ameaça do HP movido numa rodada vale na rodada **seguinte**, e só nela. Na rodada R a criatura olha o que foi feito em R-1, fechada.

É o que tira a iniciativa da conta: todo mundo é visto exatamente uma vez por cada criatura, não importa a posição na fila. Com uma janela que incluísse a rodada corrente, quem joga antes da criatura chamaria atenção na própria rodada e quem joga depois não — e a posição na iniciativa viraria metade da mecânica.

A rodada 1 fica só com a posição da classe, o que é justo: ninguém fez nada ainda. Uma mesa de um personagem por grupo abrindo o combate:

| Rodada | Guerreiro | Paladino | Clérigo | Ladino | Mago |
|---|---|---|---|---|---|
| 1 (só a classe) | 27,7% | 25,3% | 19,6% | 11,3% | 16,0% |
| 2 (o mago estourou área em 1) | 23,1% | 21,6% | 18,2% | 14,1% | 23,1% |
| 3 (e em 2 ele não fez nada) | 26,1% | 24,4% | 20,6% | 16,0% | 13,0% |

O calor esfria sozinho, e é isso que a janela compra: sem ela a Fireball da rodada 1 travaria o mago no teto pelo resto da luta, porque nada do que viesse depois conseguiria mais mexer na razão.

## Onde a conta mora

Em `run_efeitos`, sem coluna nova: a chave de lá é `(run, passo, alvo, efeito)`, e a rodada entra no NOME do efeito (`ameaca_rodada:N`), porque a chave não tem coluna para ela. É o nome que faz a janela: quem lê pede o da rodada anterior, e só esse entra. A conta morre com a sala de graça, porque o `passo` faz parte da chave. A soma é um UPSERT dentro do banco, não em Python, porque dois jogadores clicando junto leriam o mesmo valor antes de qualquer um escrever.

O campo é **separado** do que as habilidades somam. No mesmo campo, a marca ❗ do painel — que quer dizer "tem algo ligado chamando atenção" — apareceria em todo mundo que já agiu, e deixaria de dizer nada.

## Imunidade e alcance

Um fator multiplica o **peso** já curvado, e não a ameaça crua. A curva é quase reta embaixo, então mexer na ameaça só daria "modesto" ou "imune", sem meio-termo. No peso o fator é um botão de verdade, e 0 é imunidade de verdade (o Antilife Shell do druida).

Quem tem fator hoje, e quanto do peso sobra:

- **Fly** — fator 0.1
- **Invisibility** — fator 0.1
- **Antilife Shell** — fator 0
- **Dimension Door** — fator 0

## Uma escolha por vez da criatura

A criatura sorteia o alvo **uma vez** e descarrega a vez inteira nele: três garras no mesmo peito. Sorteando por golpe, o multiataque virava uma máquina de espalhar dano — o tanque com 38% da atenção levava, em três garras, um golpe e meio, e a Ameaça prometia que a criatura ia **nele**. A promessa valia para o primeiro golpe só, e o resto diluía de volta para o uniforme.

Se o alvo cai no meio da sequência, o resto vai para outro: não se bate em quem já está no chão, e o golpe não se perde por isso. Habilidade de área é outra coisa — ali os alvos são vários por definição, e saem de um sorteio sem reposição.

Quem caiu e quem está atordoado saem do bolo antes da ameaça — atordoar duas vezes não faz nada.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/ameaca.py`, `src/motor.py`. Não edite à mão: rode o gerador.
