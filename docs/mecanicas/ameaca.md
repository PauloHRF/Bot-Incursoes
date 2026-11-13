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

## Quanto cada ação gera

**Cada ação gera a ameaça da própria classe, dobrada se for área ou cura.** Cabe numa frase de propósito: o jogador precisa saber de antemão o que chama atenção.

Dobram: `cura`, `grupo`, `area`.

| Classe | Por golpe | Por área ou cura |
|---|---|---|
| Bárbaro | 12 | 24 |
| Guerreiro | 12 | 24 |
| Paladino | 10 | 20 |
| Patrulheiro | 8 | 16 |
| Xamã | 8 | 16 |
| Druida | 8 | 16 |
| Monge | 6 | 12 |
| Clérigo | 6 | 12 |
| Bruxo | 6 | 12 |
| Artífice | 4 | 8 |
| Mago | 4 | 8 |
| Feiticeiro | 4 | 8 |
| Bardo | 4 | 8 |
| Ladino | 2 | 4 |

Duas decisões que valem explicação:

**É valor declarado, e não o dano feito.** Ameaça-por-dano faria o mesmo golpe valer o dobro só por ter critado, e o jogador não conseguiria prever nada.

**É proporcional à classe, e não um valor fixo igual para todos.** Fixo diluía a inicial: em três rodadas o mago que estoura área passaria o guerreiro, e o combate voltaria a focar justamente quem não aguenta. Proporcional, as razões do grupo quase não mudam, e a deriva vem só de quem faz o quê.

Uma habilidade pode declarar `ameaca_gerada` na ação e pular a regra inteira, classe e tudo. É o gancho para uma provocação de verdade.

## A curva

A ameaça crua não vale direto no sorteio: ela passa por `peso = x ** 0.5`. Cada ponto novo rende menos que o anterior, então ninguém trava o combate stackando ameaça.

**Não é a fórmula de armadura `x / (x + Y)`**, e a diferença importa porque a ameaça acumula. Aquela tem teto em 1, então com a conta crescendo todo mundo encosta no teto e o sorteio volta a ser quase uniforme:

| Ameaça crua | Com a curva de armadura (teto em 1) | Com a potência |
|---|---|---|
| 100 / 60 / 40 | 35,4% / 33,4% / 31,2% | 41,5% / 32,2% / 26,3% |

A potência comprime igual embaixo e não satura — ainda é um tanque depois de uma luta longa.

`K` é o botão de calibragem, e anda ao contrário do que parece: **K pequeno achata** (tudo encosta em 1) e **K = 1 é o stack simples**, somar e dividir.

## A deriva durante o combate

Um grupo de cinco em que o guerreiro e o paladino batem, o clérigo cura, o ladino bate e o mago estoura área:

| Rodada | Guerreiro | Paladino | Clérigo | Ladino | Mago |
|---|---|---|---|---|---|
| 0 | 27,7% | 25,3% | 19,6% | 11,3% | 16,0% |
| 1 | 25,7% | 23,4% | 22,2% | 10,5% | 18,2% |
| 2 | 25,1% | 22,9% | 22,9% | 10,3% | 18,7% |
| 3 | 24,9% | 22,7% | 23,3% | 10,2% | 19,0% |
| 4 | 24,7% | 22,6% | 23,5% | 10,1% | 19,2% |
| 5 | 24,6% | 22,5% | 23,6% | 10,1% | 19,3% |

O tanque segue o tanque, o curandeiro sobe (é o motivo clássico de ele precisar de alguém na frente) e quem bate um alvo só perde espaço. A ordem da abertura nunca se desmancha: a geração é proporcional à inicial.

## Onde a conta mora

Em `run_efeitos`, sem coluna nova: a chave de lá é `(run, passo, alvo, efeito)`, que é exatamente o escopo — a acumulação vale pelo combate e morre quando o grupo troca de sala, porque o `passo` muda. A soma é um UPSERT dentro do banco, não em Python, porque dois jogadores clicando junto leriam o mesmo valor antes de qualquer um escrever.

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
