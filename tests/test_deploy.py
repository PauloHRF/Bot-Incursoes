"""O que sobe o bot no servidor: as unidades, o script e as versões, coerentes.

Nada aqui roda o deploy — não há servidor na suíte. O que se confere é o que
um descuido quebraria em silêncio, e só apareceria no leeroy:

- a unidade do bot e a do backup apontando para usuários, pastas ou Pythons
  diferentes (o backup leria outro banco, ou nenhum);
- o `atualizar.sh` reiniciando uma unidade com outro nome, ou instalando com
  outro pip, ou com o corpo fora da função que o protege do próprio `git pull`;
- uma dependência nova do bot sem versão travada no `constraints.txt`;
- fim de linha CRLF, que o systemd recusa sem dizer que é isso.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DEPLOY = RAIZ / "deploy"


def _diretivas(unidade: Path) -> dict[str, str]:
    """As diretivas de uma unidade do systemd: {chave: valor}, sem comentário."""
    saida = {}
    for linha in unidade.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith(("#", ";", "[")):
            continue
        chave, _, valor = linha.partition("=")
        saida[chave.strip()] = valor.strip()
    return saida


def caso_o_bot_e_o_backup_moram_no_mesmo_lugar():
    """Mesmo usuário, mesma pasta, mesmo Python do venv nas duas unidades."""
    bot = _diretivas(DEPLOY / "incursoes.service")
    backup = _diretivas(DEPLOY / "incursoes-backup.service")
    for chave in ("User", "WorkingDirectory"):
        assert bot[chave] == backup[chave], (chave, bot[chave], backup[chave])
    python = f"{bot['WorkingDirectory']}/.venv/bin/python"
    for nome, unidade in (("bot", bot), ("backup", backup)):
        assert unidade["ExecStart"].split()[0] == python, (nome, unidade["ExecStart"])
    assert bot["ExecStart"].endswith("-m src.main"), bot["ExecStart"]
    print("  o bot e o backup: mesmo usuario, mesma pasta, mesmo python: ok")


def caso_o_atualizar_mexe_no_bot_certo():
    """A pasta, o pip e a unidade que o script usa são os da unidade do bot."""
    bot = _diretivas(DEPLOY / "incursoes.service")
    script = (DEPLOY / "atualizar.sh").read_text(encoding="utf-8")
    casa = f"/home/{bot['User']}"

    pasta = re.search(r"^\s*cd\s+(\S+)\s*$", script, re.M).group(1)
    assert pasta.replace("~", casa, 1) == bot["WorkingDirectory"], (pasta, bot["WorkingDirectory"])
    assert re.search(r"^\s*\.venv/bin/pip install .*-r requirements\.txt", script, re.M), (
        "o atualizar.sh tem de instalar pelo pip do venv, e pelo requirements.txt"
    )
    nome = (DEPLOY / "incursoes.service").stem
    assert re.search(rf"systemctl restart {nome}\b", script), (
        f"o atualizar.sh nao reinicia a unidade `{nome}`"
    )
    print("  o atualizar.sh usa a pasta, o pip e a unidade do bot: ok")


def caso_o_atualizar_sobrevive_ao_proprio_git_pull():
    """O corpo numa função, e a chamada com `exit` na mesma linha.

    O `git pull` pode reescrever o próprio script enquanto ele roda, e o bash
    lê o arquivo aos pedaços. Fora da função, ele seguiria lendo o arquivo
    novo a partir da posição do velho.
    """
    script = (DEPLOY / "atualizar.sh").read_text(encoding="utf-8")
    # Só código: o comentário do cabeçalho fala do `git pull` antes da função.
    codigo = [
        linha.strip() for linha in script.splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    ]
    abre = codigo.index("atualizar() {")
    puxa = next(i for i, linha in enumerate(codigo) if linha.startswith("git pull"))
    fecha = codigo.index("}", abre)
    assert abre < puxa < fecha, "o git pull esta fora da funcao"
    assert codigo[-1] == 'atualizar "$@"; exit $?', (
        f"a ultima linha tem de chamar e sair na mesma linha, veio {codigo[-1]!r}"
    )
    bash = shutil.which("bash")
    if bash:
        feito = subprocess.run(
            [bash, "-n", str(DEPLOY / "atualizar.sh")], capture_output=True, text=True
        )
        assert feito.returncode == 0, feito.stderr
    print("  o atualizar.sh le o corpo inteiro antes de o git pull mexer nele: ok")


def caso_o_atualizar_copia_o_banco_antes_de_tudo():
    """A cópia do banco sai antes do `git pull` e antes do restart.

    Antes do restart porque é ao subir que a versão nova migra o banco: a
    cópia tem de ser a do banco que a versão antiga sabia ler. E antes do
    `git pull` porque roda com o `backup.py` que já está na máquina — um pull
    que trouxesse um backup quebrado não pode impedir a cópia que protege dele.

    `--local`, e o caso confere que a opção existe de verdade: um nome errado
    aqui faria o `set -e` parar todo deploy, e só no servidor se saberia.
    """
    script = (DEPLOY / "atualizar.sh").read_text(encoding="utf-8")
    codigo = [
        linha.strip() for linha in script.splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    ]

    def onde(comeco: str) -> int:
        return next(i for i, linha in enumerate(codigo) if linha.startswith(comeco))

    copia = onde(".venv/bin/python tools/backup.py")
    assert copia < onde("git pull"), "a copia do banco tem de vir antes do git pull"
    assert copia < onde("sudo systemctl restart"), "a copia tem de vir antes do restart"
    assert "--local" in codigo[copia].split(), codigo[copia]

    ajuda = subprocess.run(
        [sys.executable, str(RAIZ / "tools" / "backup.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert ajuda.returncode == 0 and "--local" in ajuda.stdout, ajuda.stdout or ajuda.stderr
    print("  o atualizar.sh copia o banco antes do pull e do restart: ok")


def caso_nada_do_deploy_vai_com_crlf():
    """Unidade com CRLF o systemd recusa a carregar; script com CRLF não roda.

    Quem garante é o `.gitattributes`, com `eol=lf`: o git grava LF no
    repositório e entrega LF no checkout do servidor, venha o arquivo de onde
    vier. Por isso o caso confere a REGRA, e não a cópia de trabalho — numa
    máquina Windows a cópia local pode estar em CRLF, e não é ela que sobe.
    """
    arquivos = [
        *DEPLOY.glob("*.service"), *DEPLOY.glob("*.timer"), *DEPLOY.glob("*.sh"),
    ]
    assert len(arquivos) >= 4, arquivos
    git = shutil.which("git")
    if git is None:
        print("  sem git nesta maquina: a regra de fim de linha nao foi conferida")
        return
    feito = subprocess.run(
        [git, "check-attr", "eol", "--", *[a.relative_to(RAIZ).as_posix() for a in arquivos]],
        cwd=RAIZ, capture_output=True, text=True,
    )
    sem_regra = [l for l in feito.stdout.splitlines() if not l.endswith(": lf")]
    assert not sem_regra, f"sem eol=lf no .gitattributes: {sem_regra}"
    print(f"  os {len(arquivos)} arquivos do deploy sobem em LF: ok")


def _nome(requisito: str) -> str:
    return re.split(r"[\s<>=!~;\[]", requisito.strip(), maxsplit=1)[0].lower().replace("_", "-")


def caso_toda_dependencia_do_bot_tem_versao_travada():
    """O `requirements.txt` puxa o `constraints.txt`, e nada do bot fica sem pino.

    A dependência nova que entrar sem pino volta a ser "a mais nova do dia"
    no servidor — o problema que o arquivo de travas existe para fechar.
    """
    requisitos = (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "-c constraints.txt" in [l.strip() for l in requisitos], (
        "o requirements.txt nao puxa o constraints.txt"
    )
    travas = {}
    for linha in (RAIZ / "constraints.txt").read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        assert re.fullmatch(r"[A-Za-z0-9._-]+==[0-9][A-Za-z0-9.]*", linha), (
            f"trava que nao e nome==versao: {linha!r}"
        )
        travas[_nome(linha)] = linha
    diretos = [
        _nome(l) for l in requisitos if l.strip() and not l.strip().startswith(("#", "-"))
    ]
    soltos = [n for n in diretos if n not in travas]
    assert not soltos, f"dependencias do bot sem versao no constraints.txt: {soltos}"
    print(f"  as {len(diretos)} dependencias do bot tem versao travada: ok")


def main():
    caso_o_bot_e_o_backup_moram_no_mesmo_lugar()
    caso_o_atualizar_mexe_no_bot_certo()
    caso_o_atualizar_sobrevive_ao_proprio_git_pull()
    caso_o_atualizar_copia_o_banco_antes_de_tudo()
    caso_nada_do_deploy_vai_com_crlf()
    caso_toda_dependencia_do_bot_tem_versao_travada()


main()
print("TESTES DO DEPLOY PASSARAM")
