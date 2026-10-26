# Ameaça: quem a criatura escolhe bater

Sem isto o alvo é sorteado uniformemente, e então não existe tanque: o mago leva tanta pancada quanto o guerreiro de armadura pesada. A Ameaça dá a cada personagem um peso nesse sorteio.

## As três partes

- **A inicial da classe** — a posição dela na sala virando número. Quem bate de perto aparece primeiro. Não escala por tier: ameaça é o papel na sala, não o poder do personagem.
- **O que as habilidades ligadas somam**, enquanto duram.
- **O que o personagem gerou agindo**, que acumula do primeiro golpe ao fim do combate e morre com a sala.

## A inicial de cada classe

| Classe | Ameaça | Fatia da atenção |
|---|---|---|
| Guerreiro | 6 | 30,2% |
| Paladino | 6 | 30,2% |
| Bárbaro | 5 | 28,3% |
| Monge | 4 | 26,1% |
| Patrulheiro | 3 | 23,4% |
| Clérigo | 3 | 23,4% |
| Artífice | 3 | 23,4% |
| Ladino | 2 | 20,0% |
| Xamã | 2 | 20,0% |
| Mago | 2 | 20,0% |
| Bruxo | 2 | 20,0% |
| Druida | 2 | 20,0% |
| Feiticeiro | 2 | 20,0% |
| Bardo | 2 | 20,0% |

A fatia é num grupo de cinco onde os outros quatro estão no piso (2). O sorteio uniforme seria 20%. Classe sem tabela cai no padrão, 3.

## Quanto cada ação gera

**Cada ação gera a ameaça da própria classe, dobrada se for área ou cura.** Cabe numa frase de propósito: o jogador precisa saber de antemão o que chama atenção.

Dobram: `cura`, `grupo`, `area`.

| Classe | Por golpe | Por área ou cura |
|---|---|---|
| Guerreiro | 6 | 12 |
| Paladino | 6 | 12 |
| Bárbaro | 5 | 10 |
| Monge | 4 | 8 |
| Patrulheiro | 3 | 6 |
| Clérigo | 3 | 6 |
| Artífice | 3 | 6 |
| Ladino | 2 | 4 |
| Xamã | 2 | 4 |
| Mago | 2 | 4 |
| Bruxo | 2 | 4 |
| Druida | 2 | 4 |
| Feiticeiro | 2 | 4 |
| Bardo | 2 | 4 |

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
| 0 | 25,9% | 25,9% | 18,3% | 15,0% | 15,0% |
| 1 | 24,1% | 24,1% | 20,9% | 13,9% | 17,0% |
| 2 | 23,6% | 23,6% | 21,6% | 13,6% | 17,6% |
| 3 | 23,4% | 23,4% | 21,9% | 13,5% | 17,9% |
| 4 | 23,3% | 23,3% | 22,1% | 13,4% | 18,0% |
| 5 | 23,2% | 23,2% | 22,2% | 13,4% | 18,1% |

O tanque segue o tanque, o curandeiro sobe (é o motivo clássico de ele precisar de alguém na frente) e quem bate um alvo só perde espaço. A ordem da abertura nunca se desmancha: a geração é proporcional à inicial.

## Onde a conta mora

Em `run_efeitos`, sem coluna nova: a chave de lá é `(run, passo, alvo, efeito)`, que é exatamente o escopo — a acumulação vale pelo combate e morre quando o grupo troca de sala, porque o `passo` muda. A soma é um UPSERT dentro do banco, não em Python, porque dois jogadores clicando junto leriam o mesmo valor antes de qualquer um escrever.

O campo é **separado** do que as habilidades somam. No mesmo campo, a marca 🩸 do painel — que quer dizer "tem algo ligado chamando atenção" — apareceria em todo mundo que já agiu, e deixaria de dizer nada.

## Imunidade e alcance

Um fator multiplica o **peso** já curvado, e não a ameaça crua. A curva é quase reta embaixo, então mexer na ameaça só daria "modesto" ou "imune", sem meio-termo. No peso o fator é um botão de verdade: 0,2 tira de alcance sem tornar invulnerável, e 0 é imunidade de verdade (o Antilife Shell do druida).

Quem caiu e quem está atordoado saem do bolo antes da ameaça — atordoar duas vezes não faz nada.

---

Gerado por `tools/gerar_mecanicas_md.py` a partir de `src/ameaca.py`, `src/motor.py`. Não edite à mão: rode o gerador.
