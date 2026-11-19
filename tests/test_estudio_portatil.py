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
                "tools/simular_combate.py", "tools/sugestor.py", "tools/estudio/index.html",
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
