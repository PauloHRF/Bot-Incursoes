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
   nano ~/BotIncursao/.env
   ```

   Acrescentar a linha:

   ```
   BACKUP_WEBHOOK=https://discord.com/api/webhooks/...
   ```

3. **Provar que funciona, antes de automatizar:**

   ```bash
   cd ~/BotIncursao && .venv/bin/python tools/backup.py
   ```

   Ele imprime o nome do arquivo, o tamanho e as contagens, e o arquivo
   aparece no canal. Sem a linha no `.env` ele guarda só a cópia local, avisa e
   sai bem — um servidor que ainda não configurou o envio não é um erro.

4. **Instalar o timer** (confira o usuário e a pasta no `.service` antes, se os
   seus não forem `ubuntu` e `/home/ubuntu/BotIncursao`):

   ```bash
   sudo cp ~/BotIncursao/deploy/incursoes-backup.* /etc/systemd/system/
   ```

   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now incursoes-backup.timer
   ```

5. **Conferir quando ele vai rodar:**

   ```bash
   systemctl list-timers incursoes-backup.timer
   ```

### Restaurar

```bash
cd ~/BotIncursao && sudo systemctl stop <servico-do-bot>
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
gratuitos* — você passa a pagar só o que exceder a cota, e o bot não excede.

**O passo a passo:**

1. Console da Oracle Cloud → o menu do perfil (canto superior direito) →
   **Billing & Cost Management**.
2. **Upgrade and Manage Payment** → **Upgrade to Pay As You Go**.
3. Cartão de crédito (ela faz uma autorização pequena para validar e devolve).
4. Esperar a conta virar — costuma ser minutos, e chega um e-mail.

**Depois, os dois cuidados que valem o tempo:**

- **Um alerta de orçamento**, para dormir tranquilo: *Billing & Cost
  Management → Budgets → Create Budget*, com alvo na raiz do tenancy, valor
  baixo (US$ 1 já serve) e alerta em 100% do previsto. Se algo sair da cota
  gratuita, você sabe por e-mail no mesmo dia em vez de no fim do mês.
- **Não criar recurso fora da cota sem querer.** O que é grátis é o que está
  marcado **Always Free** no console; depois do upgrade, o console passa a
  deixar você criar o que não é, e sem o alerta acima isso vira fatura.

Nada disso muda o bot: a instância, o `systemd` e o backup seguem iguais.
