"""Monta um ZIP privado do Estúdio para Windows 10/11 x64.

    python tools/empacotar_estudio.py

O Python embutido oficial e as wheels Windows vão dentro da pasta. Quem
recebe só extrai e abre Abrir Estudio.cmd; não precisa de Python, pip ou venv.
O empacotador pode rodar no Linux. A execução final precisa ser conferida
no Windows. Só os arquivos de código e conteúdo listados abaixo entram.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import zipfile

RAIZ = Path(__file__).resolve().parents[1]
PYTHON_VERSAO = "3.12.10"
PYTHON_ARQUIVO = f"python-{PYTHON_VERSAO}-embed-amd64.zip"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSAO}/{PYTHON_ARQUIVO}"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"

ABRIR = r'''@echo off
setlocal
title Estudio de Incursoes
cd /d "%~dp0"
"%~dp0runtime\python.exe" -I "%~dp0app\tools\estudio.py" %*
if errorlevel 1 (
  echo.
  echo Nao foi possivel abrir o Estudio. Confira se o ZIP foi extraido inteiro.
  echo Se outra janela do Estudio estiver aberta, use essa janela ou feche-a.
  pause
)
'''

LEIA = """ESTÚDIO DE INCURSÕES — WINDOWS 10/11, 64 BITS

1. Extraia a pasta inteira do ZIP.
2. Abra "Abrir Estudio.cmd" com dois cliques.
3. O navegador abre o Estúdio. Siga Escolher → Editar → Testar.
4. Use "Baixar JSON" para guardar e enviar o banco de salas.

Não precisa instalar Python nem dependências. Funciona sem internet.
Mantenha a janela de abertura aberta durante o uso; feche-a ao terminar.
Os rascunhos ficam neste navegador. Para levar o trabalho, baixe o JSON.
"""


def sha256(arquivo: Path) -> str:
    digest = hashlib.sha256()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def copiar_app(raiz: Path, destino: Path) -> None:
    """Lista positiva: não copia .env, banco de jogadores, venv ou backups."""
    arquivos = [raiz / "data/bestiario.json"]
    for pasta, padrao in (
        ("src", "**/*.py"), ("tools/simulacao", "*.py"),
        ("tools/simulacao", "*.json"), ("tools/estudio", "*.html"),
        ("tools/estudio", "*.css"), ("tools/estudio", "*.js"),
        ("data/bancos", "*.json"), ("data/incursoes", "*.json"),
    ):
        arquivos.extend((raiz / pasta).glob(padrao))
    # `validar_conteudo` entra porque o estúdio confere com ele: sem ele no
    # pacote, todo "conferir" do colaborador dava ModuleNotFoundError.
    arquivos.extend(raiz / "tools" / n for n in (
        "estudio.py", "simular_combate.py", "sugestor.py", "validar_conteudo.py",
    ))
    for arquivo in sorted(set(arquivos)):
        alvo = destino / arquivo.relative_to(raiz)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(arquivo, alvo)


def caminho_seguro(nome: str) -> PurePosixPath:
    p = PurePosixPath(nome)
    if p.is_absolute() or ".." in p.parts or "\\" in nome or ":" in nome:
        raise ValueError(f"Caminho inválido no arquivo: {nome}")
    return p


def extrair(arquivo: Path, destino: Path, *, wheel=False) -> None:
    """Wheels usam purelib/platlib para arquivos que pertencem ao sys.path."""
    with zipfile.ZipFile(arquivo) as z:
        for info in z.infolist():
            p = caminho_seguro(info.filename)
            if info.is_dir():
                continue
            if wheel and p.parts[0].endswith(".data"):
                if len(p.parts) < 3 or p.parts[1] not in ("purelib", "platlib"):
                    continue
                p = PurePosixPath(*p.parts[2:])
            alvo = destino.joinpath(*p.parts)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as origem, alvo.open("wb") as f:
                shutil.copyfileobj(origem, f)


def instalar_wheels(pasta: Path, destino: Path, constraints: Path) -> list[dict]:
    pins = dict(re.findall(r"^([\w.-]+)==([^\s]+)$", constraints.read_text(), re.M))
    normalizar = lambda n: re.sub(r"[-_.]+", "-", n).lower()
    pins = {normalizar(n): v for n, v in pins.items()}
    pacotes = []
    for wheel in sorted(pasta.glob("*.whl")):
        partes = wheel.stem.rsplit("-", 3)
        python, abi, plataforma = partes[-3:]
        if plataforma not in ("any", "win_amd64") or (abi != "none" and (python, abi) != ("cp312", "cp312")):
            raise ValueError(f"Wheel incompatível com Python 3.12 Windows x64: {wheel.name}")
        with zipfile.ZipFile(wheel) as z:
            metadata = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
            dados = BytesParser().parsebytes(z.read(metadata))
        nome, versao = dados["Name"], dados["Version"]
        if pins.get(normalizar(nome)) != versao:
            raise ValueError(f"Dependência fora de constraints.txt: {nome}=={versao}")
        extrair(wheel, destino, wheel=True)
        pacotes.append({"nome": nome, "versao": versao, "arquivo": wheel.name, "sha256": sha256(wheel)})
    for modulo in ("aiosqlite", "dotenv", "discord", "aiohttp", "PIL"):
        if not (destino / modulo / "__init__.py").exists():
            raise ValueError(f"Dependência ausente no pacote: {modulo}")
    return pacotes


def montar(raiz: Path, destino: Path, python_zip: Path, wheels: Path) -> None:
    if sha256(python_zip) != PYTHON_SHA256:
        raise ValueError("O ZIP do Python difere da distribuição oficial esperada.")
    runtime = destino / "runtime"
    extrair(python_zip, runtime)
    pacotes = instalar_wheels(wheels, runtime / "Lib/site-packages", raiz / "constraints.txt")
    # _pth mantém o interpretador independente do Python instalado na máquina.
    # App e tools entram porque o servidor e os simuladores compartilham regras.
    (runtime / "python312._pth").write_text(
        "python312.zip\n.\nLib/site-packages\n../app\n../app/tools\nimport site\n", encoding="utf-8"
    )
    copiar_app(raiz, destino / "app")
    (destino / "Abrir Estudio.cmd").write_bytes(ABRIR.replace("\n", "\r\n").encode("ascii"))
    (destino / "LEIA-ME.txt").write_text(LEIA, encoding="utf-8-sig")
    manifesto = {
        "python": {"versao": PYTHON_VERSAO, "url": PYTHON_URL, "sha256": PYTHON_SHA256},
        "plataforma": "Windows x64", "dependencias": pacotes,
        "app": {p.relative_to(destino).as_posix(): sha256(p) for p in sorted((destino / "app").rglob("*")) if p.is_file()},
    }
    (destino / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--saida", type=Path, default=RAIZ / "dist")
    p.add_argument("--cache", type=Path, default=RAIZ / ".cache-estudio")
    p.add_argument("--python-zip", type=Path, help="ZIP embutido oficial, para montar sem download")
    p.add_argument("--wheels", type=Path, help="Pasta com wheels Windows já baixadas")
    args = p.parse_args(argv)
    args.cache.mkdir(parents=True, exist_ok=True)
    python_zip = args.python_zip or args.cache / PYTHON_ARQUIVO
    if not python_zip.exists():
        if args.python_zip:
            p.error(f"Arquivo não encontrado: {python_zip}")
        print("Baixando o Python portátil oficial…", flush=True)
        with urlopen(PYTHON_URL, timeout=30) as r, python_zip.open("wb") as f:
            shutil.copyfileobj(r, f)
    wheels = args.wheels
    if wheels is None:
        wheels = args.cache / "wheels"
        wheels.mkdir(exist_ok=True)
        subprocess.run([
            sys.executable, "-m", "pip", "download", "--dest", str(wheels),
            "--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp",
            "--abi", "cp312", "--only-binary=:all:", "-r", str(RAIZ / "requirements.txt"),
        ], check=True)
    args.saida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="estudio-") as temporario:
        destino = Path(temporario) / "Estudio"
        montar(RAIZ, destino, python_zip, wheels)
        zip_final = args.saida / "Estudio-Windows-x64.zip"
        with zipfile.ZipFile(zip_final, "w", zipfile.ZIP_DEFLATED) as z:
            for arquivo in sorted(destino.rglob("*")):
                if arquivo.is_file():
                    z.write(arquivo, arquivo.relative_to(destino.parent))
    print(f"Pronto: {zip_final.resolve()}")
    print("Envie este ZIP. Quem recebe extrai e abre Abrir Estudio.cmd.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
