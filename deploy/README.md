# Deploy, backup e a conta da Oracle

O bot roda numa instância **Always Free** da Oracle Cloud, sob `systemd`. Este
diretório tem o que dá para versionar disso: as unidades do backup e o passo a
passo. O que **não** está aqui, de propósito: o `.env` (que tem o token e o
webhook) e qualquer chave.

## O backup

`tools/backup.py` tira uma cópia do banco, comprime e manda para um canal do
Discord por **webhook**.

**Ele não para o bot.** A cópia sai pela API de backup online do SQLite
(`sqlite3.Connection.backup`), que tira um retrato consistente de um banco
aberto e sendo escrito. Um `cp` do arquivo vivo pode pegar uma escrita no meio
e devolver um banco corrompido — justamente no dia em que ele for preciso.

**Por que webhook e não o próprio bot:** o backup funciona com o bot parado,
que é exatamente quando se quer um (antes de uma atualização); dá para rodar
na mão e ver o resultado na hora; e o webhook só sabe escrever num canal — não
lê nada, não administra nada, e vazar ele não dá acesso ao bot.

### O tamanho, medido

Medido no banco de verdade, com 31 incursões jogadas:

| Runs | `.db` cru | `.db.gz` |
|---|---|---|
| 31 | 256 KB | **35 KB** |
| 1.000 | ~5 MB | ~1 MB |
| 10.000 | ~50 MB | ~9 MB |

Dá **cerca de 1 KB comprimido por incursão**. Um grupo que joga toda semana faz
~50 runs por ano, então 10.000 runs são dois séculos de jogo — e só aí o
arquivo encostaria no limite de upload do Discord. Não há nada a podar.

### Instalar, uma vez

1. **Criar o canal e o webhook.** Num canal privado (só você), *Editar canal →
   Integrações → Webhooks → Novo webhook*, e copiar a URL.

2. **Pôr a URL no `.env`**, na instância, pelo `nano` — como o token:

   ```bash
   nano ~/Bot-Incursoes/.env
   ```

   Acrescentar a linha:

   ```
   BACKUP_WEBHOOK=https://discord.com/api/webhooks/...
   ```

   **Se o bot estiver em mais de um servidor**, acrescente também a guilda cujos
   dados devem ir no arquivo:

   ```
   BACKUP_GUILDA=<id do servidor>
   ```

   O banco é um arquivo só, com todos os servidores dentro. Sem esta linha o
   anexo é o banco **inteiro** — o canal de um servidor receberia as fichas do
   outro. Com ela, o arquivo enviado leva só aquela guilda, e a mensagem no
   canal avisa que ele não é o banco completo. A cópia **local** continua
   inteira de propósito: ela é o cinto de restaurar, e perder o canal custa um
   download, perder a máquina custa tudo.

   Um valor que não seja um id **para** o backup em vez de mandar tudo: falhar
   custa um backup, seguir custa os dados do outro servidor.

3. **Provar que funciona, antes de automatizar:**

   ```bash
   cd ~/Bot-Incursoes && .venv/bin/python tools/backup.py
   ```

   Ele imprime o nome do arquivo, o tamanho e as contagens, e o arquivo
   aparece no canal. Com `BACKUP_GUILDA`, imprime uma linha a mais com as
   contagens da fatia — se ela disser `0 personagens`, o id está errado. Para
   testar sem mexer no `.env`: `tools/backup.py --guilda <id>`. Se o envio
   falhar, o código HTTP diz o quê: **401/404** é
   a URL do webhook, **403** é o Cloudflare recusando a requisição (e não o
   Discord), **413** é arquivo grande demais para o canal. Sem a linha no `.env` ele guarda só a cópia local, avisa e
   sai bem — um servidor que ainda não configurou o envio não é um erro.

4. **Instalar o timer** (confira o usuário e a pasta no `.service` antes, se os
   seus não forem `ubuntu` e `/home/ubuntu/Bot-Incursoes` — é o que
   `systemctl cat incursoes` mostra no `User=` e no `WorkingDirectory=`):

   ```bash
   sudo cp ~/Bot-Incursoes/deploy/incursoes-backup.* /etc/systemd/system/
   ```

   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now incursoes-backup.timer
   ```

5. **Conferir quando ele vai rodar:**

   ```bash
   systemctl list-timers incursoes-backup.timer
   ```

   O `NEXT` sai em **UTC**. O timer está escrito em `07:00:00 UTC`, que é
   **4h da manhã em São Paulo** — e não `04:00:00 America/Sao_Paulo`, que
   seria o óbvio, porque o sufixo de fuso no `OnCalendar` só existe do
   **systemd 252** em diante e o leeroy roda o 249 (Ubuntu 22.04). Nele a
   linha com o nome do fuso faz a unidade falhar a carregar. Se um dia a
   máquina subir de versão (`systemctl --version`), dá para trocar — a linha
   está comentada dentro do próprio `.timer`.

### Restaurar

```bash
cd ~/Bot-Incursoes && sudo systemctl stop incursoes
```

```bash
gunzip -c data/backups/incursoes-AAAA-MM-DD_HHMM.db.gz > /tmp/restaurado.db
```

Confira **antes** de trocar o banco bom pelo backup:

```bash
sqlite3 /tmp/restaurado.db "PRAGMA integrity_check; SELECT COUNT(*) FROM personagens;"
```

```bash
mv data/incursoes.db data/incursoes.db.ruim && mv /tmp/restaurado.db data/incursoes.db
```

O banco antigo vira `.ruim` em vez de desaparecer: se o backup estiver mais
velho do que você pensava, ele ainda está ali.

### O que fica no disco

As **14 cópias** mais novas, em `data/backups/` (ignorado pelo git). São o
segundo cinto: dão para restaurar sem baixar nada e cobrem o caso de o envio
ter falhado sem ninguém ver. Falha de envio sai com código 2 e **não** apaga a
cópia local.

## Pay As You Go

**Isto é da sua conta, no console da Oracle — não há nada no código a mudar, e
eu não tenho como clicar por você.** Vale o passo a passo porque o motivo é
concreto:

**Por que fazer.** Numa conta Always Free pura, a Oracle **recicla** instâncias
consideradas ociosas: ela avisa por e-mail e, se nada mudar, desliga e remove a
VM. Um bot de Discord fica quase todo o tempo parado esperando evento, que é o
perfil exato que o critério dela pega. Fazer o upgrade para Pay As You Go
**tira a instância da fila de reciclagem** e *mantém os recursos Always Free
gratuitos* — você passa a pagar só o que exceder a cota, e o bot não excede
(desde que o formato da instância esteja na cota; ver abaixo).

**Antes de clicar, confira o formato da instância.** Em 2026 a Oracle cortou
a cota grátis de **ARM** pela metade — de 4 OCPU / 24 GB para 2 OCPU / 12 GB,
com prazo até 18/08/2026 — e as fontes se contradizem sobre se o corte vale
para contas Pay As You Go. Isso **inverte o risco**: numa conta Always Free,
estar acima do limite faz a instância ser reciclada; depois do upgrade, faz
ela ser *cobrada*.

```bash
uname -m && nproc && free -g | head -2 && df -h / | tail -1
```

- `x86_64`, 2 vCPU, menos de 1 GB → é a `VM.Standard.E2.1.Micro`, a AMD. São
  duas grátis e o corte de ARM não a alcança. **É o caso do leeroy** (medido
  em 16/11/2026: boot volume de 47 GB dos 200 GB grátis).
- `aarch64` com até 2 OCPU / 12 GB → Ampere dentro do limite novo.
- `aarch64` com 4 OCPU / 24 GB → **pare**. Encolha para 2/12 antes do upgrade,
  senão a parte excedente passa a virar fatura mensal.

E um volume ÓRFÃO não aparece de dentro da VM: boot volume de instância
apagada fica desanexado, continua contando nos 200 GB e, depois do PAYG,
continua sendo cobrado com nada rodando nele. Confira em *Storage → Block
Volumes* e *Boot Volumes* que só existe o da instância que você usa.

**O passo a passo:**

1. Console da Oracle Cloud → o menu do perfil (canto superior direito) →
   **Billing & Cost Management**.
2. **Upgrade and Manage Payment** → **Upgrade to Pay As You Go**.
3. Cartão de crédito (ela faz uma autorização pequena para validar e devolve).
4. Esperar a conta virar — costuma ser minutos, e chega um e-mail.

**Depois, os dois cuidados que valem o tempo:**

- **Um alerta de orçamento ANTES do upgrade**, não depois: *Billing & Cost
  Management → Budgets → Create Budget*, com alvo na raiz do tenancy, valor
  baixo (US$ 1 já serve) e alerta em 100% do previsto. Se algo sair da cota
  gratuita, você sabe por e-mail no mesmo dia em vez de no fim do mês.
- **Não criar recurso fora da cota sem querer.** O que é grátis é o que está
  marcado **Always Free** no console; depois do upgrade, o console passa a
  deixar você criar o que não é, e sem o alerta acima isso vira fatura.

Nada disso muda o bot: a instância, o `systemd` e o backup seguem iguais.
