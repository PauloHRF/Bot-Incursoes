#!/bin/bash
# Atualiza o bot no servidor: puxa o código, instala as dependências, reinicia.
#
# Nasceu do ~/atualizar.sh do leeroy, versionado para não existir só lá. Os
# comandos dele estão aqui na mesma ordem; o que este acrescenta é a cópia do
# banco antes de tudo, e a forma (ver abaixo).
#
#   ~/Bot-Incursoes/deploy/atualizar.sh
#
# TUDO DENTRO DE UMA FUNÇÃO, de propósito. O bash lê o script aos pedaços,
# enquanto roda — e rodado de dentro do repositório, o `git pull` abaixo pode
# reescrever este mesmo arquivo no meio da execução. O bash seguiria lendo o
# arquivo NOVO a partir da posição em que estava no velho, e executaria um
# pedaço de linha qualquer. Numa função, o corpo é lido inteiro antes da
# primeira linha rodar, e o `exit` na mesma linha da chamada impede que ele
# volte ao arquivo depois.
#
# O ~/atualizar.sh antigo continua funcionando — ele mora fora do repositório
# e o `git pull` não o alcança —, mas sem a cópia do banco. Para ter a cópia,
# rode este (ou copie-o por cima do antigo): ver deploy/README.md.
set -e

atualizar() {
    cd ~/Bot-Incursoes
    # Uma cópia do banco ANTES de qualquer coisa mudar. A versão nova pode
    # migrar o banco quando subir (acrescentar coluna, recriar tabela), e esta
    # é a cópia de antes disso: restaurar dela é voltar para o banco que a
    # versão antiga sabia ler. Ver "Restaurar" no deploy/README.md.
    #
    # Primeiro, e com o código que JÁ está aqui: um `git pull` que trouxesse
    # um backup.py quebrado não pode impedir a cópia que protege dele.
    #
    # `--local`, sem mandar ao Discord: o envio depende de rede, e o `set -e`
    # pararia o deploy se o canal estivesse fora do ar. A cópia local não
    # depende de nada — se ELA falhar, há algo errado de verdade com o banco,
    # e então é melhor mesmo não atualizar. O bot não para: a cópia sai pela
    # API de backup online do SQLite.
    .venv/bin/python tools/backup.py --local
    git pull
    # O requirements.txt puxa o constraints.txt: o pip instala as versões
    # EXATAS em que a suíte passou, e não a mais nova que o PyPI tiver hoje.
    .venv/bin/pip install -q -r requirements.txt
    sudo systemctl restart incursoes
    sleep 5
    sudo systemctl status incursoes --no-pager | head -4
}

atualizar "$@"; exit $?
