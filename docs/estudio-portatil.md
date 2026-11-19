# Estúdio portátil

Para quem vai usar: extraia o ZIP e abra **Abrir Estudio.cmd** com dois
cliques. O pacote é para **Windows 10/11 de 64 bits** e já inclui Python e
as dependências, incluindo `aiosqlite`. Funciona sem internet e não precisa
de conta no GitHub.

A página abre em **Escolher → Editar → Testar**. Em **Ferramentas avançadas**
continuam disponíveis filtros de dungeon, inspeção, sugestão de criaturas e
opções de simulação. Os combates usam quatro formações fixas, conferíveis
em **Ver grupos usados**. **Baixar JSON** guarda o banco completo para enviar.
Mantenha a janela de abertura aberta durante o uso e feche-a ao terminar.

## Gerar uma nova distribuição

Na máquina de quem desenvolve, com Python 3.10 ou superior e pip:

```bash
python tools/empacotar_estudio.py
```

O resultado é `dist/Estudio-Windows-x64.zip`, para enviar diretamente ao
colaborador. Pode ser montado no Linux: usa o Python embutido oficial para
Windows e baixa wheels Windows nas versões de `constraints.txt`. Quem recebe
não precisa fazer esses passos. O interpretador é isolado do Python da
máquina; HTML, CSS, JS, regras e JSONs ficam dentro da pasta do pacote.

Para repetir a montagem sem download:

```bash
python tools/empacotar_estudio.py --python-zip caminho/python-3.12.10-embed-amd64.zip --wheels caminho/wheels
```

O pacote preserva as licenças do Python e das dependências. `manifesto.json`
registra versões e hashes. O empacotador confere o hash do Python, as versões
das dependências e a compatibilidade das wheels. Copia apenas código, assets
da página e JSONs de conteúdo; `.env`, banco de jogadores, backups e a `.venv`
ficam fora da distribuição. O ZIP e o cache são ignorados pelo Git.

Antes de entregar uma nova versão, abra-a no Windows e confira leitura de
banco, edição, simulação e download de JSON. Os testes de interface rodam
também no Linux, mas não substituem essa conferência no sistema de destino.
