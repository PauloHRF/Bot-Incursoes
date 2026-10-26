# Mecânicas

Um arquivo por mecânica. Tudo aqui é **gerado**:

```bash
.venv/Scripts/python.exe tools/gerar_mecanicas_md.py
```

Os números saem dos módulos que os usam de verdade, então mexer numa constante e rodar o gerador atualiza a documentação na hora. Não edite estes arquivos à mão — a edição se perde, e pior, ela passa a discordar do código sem ninguém notar.

| Arquivo | O que cobre |
|---|---|
| [tier-e-progressao.md](tier-e-progressao.md) | Níveis, tiers, e tudo que escala com eles: CD de sala e tamanho de criatura. |
| [combate.md](combate.md) | Iniciativa, ataque, crítico, THP, cair, descanso e a regra da cura. |
| [ameaca.md](ameaca.md) | Quem a criatura escolhe bater: a inicial da classe, o que cada ação gera e a curva. |
| [incursoes-e-salas.md](incursoes-e-salas.md) | A forma de uma incursão, os tipos de sala, as faixas de CD e a votação. |
| [consequencias.md](consequencias.md) | O que cada tipo de sala faz com o grupo quando ele passa ou falha. |
| [condicoes.md](condicoes.md) | O catálogo de buffs e debuffs, o que um stack faz e quanto tempo dura. |
| [habilidades.md](habilidades.md) | A gramática do catálogo: tipos, usos, escopos e como dois bônus se juntam. |
| [mercado.md](mercado.md) | Ouro, vitrine semanal derivada, raridade, preço e o domínio de cada slot. |
| [bestiario.md](bestiario.md) | As criaturas prontas que uma sala chama pelo nome. |

## Os outros dois documentos

- **[../FICHAS.md](../FICHAS.md)** — o conteúdo: os números e as habilidades de cada uma das 14 classes, tier por tier.
- **[../BALANCO.md](../BALANCO.md)** — a medição: dano por rodada, durabilidade, cura e valor de cada habilidade, para achar o que está forte ou fraco demais.

A divisão: aqui estão as **regras**, no `FICHAS.md` o **conteúdo** e no `BALANCO.md` a **medição**.
