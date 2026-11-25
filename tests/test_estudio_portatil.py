"""Conteúdo e instalação do pacote privado, sem baixar durante os testes."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from tools import empacotar_estudio as P


class Pacote(unittest.TestCase):
    def test_copia_codigo_e_conteudo_sem_segredos_ou_banco_do_bot(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta) / "projeto"
            arquivos = [
                "src/__init__.py", "src/combate/mesa.py", "tools/estudio.py",
                "tools/simular_combate.py", "tools/sugestor.py", "tools/validar_conteudo.py",
                "tools/estudio/index.html",
                "tools/simulacao/execucao.py", "tools/simulacao/medidas.json",
                "data/bestiario.json", "data/bancos/banco.json", "data/incursoes/a.json",
            ]
            privados = [".env", "data/incursoes.db", "data/incursoes.db-wal",
                        "data/backups/segredo.json", "src/__pycache__/x.pyc", "tests/segredo.py"]
            for nome in arquivos + privados:
                p = raiz / nome
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(nome)
            destino = Path(pasta) / "app"
            P.copiar_app(raiz, destino)
            obtidos = sorted(p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file())
            self.assertEqual(obtidos, sorted(arquivos))

    def test_o_estudio_copiado_abre_e_confere_sozinho(self):
        """A cópia de verdade, e não uma lista de nomes, sobe e confere.

        O caso acima confere a LISTA; ele passava enquanto o pacote saía sem o
        `validar_conteudo.py` que o estúdio importa, e o "conferir" de todo
        colaborador dava ModuleNotFoundError. Aqui o estúdio roda de dentro da
        pasta copiada, sem o repositório no caminho de importação.
        """
        import subprocess

        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "app"
            P.copiar_app(RAIZ, destino)
            roteiro = (
                "import json, sys\n"
                "import estudio as E\n"
                "c = E.conteudo()\n"
                "assert c['incursoes'] and c['bancos'], 'leu nada'\n"
                "inc = next(iter(c['incursoes'].values()))\n"
                "r = E.conferir({'dados': {'formato': c['formato']['nome'],\n"
                "    'versao': c['formato']['versao'], 'organizacao': inc['organizacao'],\n"
                "    'incursao': inc, 'salas': []}})\n"
                "assert r['tipo'] == 'pacote', r\n"
                "print('ok')\n"
            )
            # -I: sem o diretório atual nem o site-packages do usuário no
            # caminho, como o atalho do pacote roda o estúdio.
            saida = subprocess.run(
                [sys.executable, "-I", "-c",
                 f"import sys; sys.path[:0] = [{str(destino / 'tools')!r}, {str(destino)!r}]\n"
                 + roteiro],
                capture_output=True, text=True, encoding="utf-8", cwd=pasta,
            )
            self.assertEqual(saida.returncode, 0, saida.stderr[-2000:])
            self.assertIn("ok", saida.stdout)

    def test_wheel_instala_purelib_no_caminho_de_importacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            wheel = pasta / "teste.whl"
            with zipfile.ZipFile(wheel, "w") as z:
                z.writestr("teste.data/purelib/modulo/__init__.py", "valor = 7")
                z.writestr("teste.dist-info/licenses/LICENSE", "licença")
            P.extrair(wheel, pasta / "libs", wheel=True)
            self.assertEqual((pasta / "libs/modulo/__init__.py").read_text(), "valor = 7")
            self.assertTrue((pasta / "libs/teste.dist-info/licenses/LICENSE").exists())

    def test_caminhos_de_arquivo_nao_escapam_da_pasta(self):
        for nome in ("../fora.py", "/fora.py", "C:/fora.py", "..\\fora.py"):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                P.caminho_seguro(nome)

    def test_runtime_diferente_e_recusado_antes_de_montar(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            errado = pasta / "python.zip"
            errado.write_bytes(b"incompleto")
            with self.assertRaisesRegex(ValueError, "distribuição oficial"):
                P.montar(RAIZ, pasta / "pacote", errado, pasta / "wheels")
            self.assertFalse((pasta / "pacote").exists())

    def test_wheel_de_outro_sistema_e_recusada(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            (pasta / "teste-1.0-cp312-cp312-manylinux_2_17_x86_64.whl").touch()
            (pasta / "constraints.txt").write_text("teste==1.0\n")
            with self.assertRaisesRegex(ValueError, "incompatível"):
                P.instalar_wheels(pasta, pasta / "libs", pasta / "constraints.txt")


if __name__ == "__main__":
    unittest.main()
