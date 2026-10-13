import ast
import glob
import json
import os
import re
import sys

PT = re.compile(r"[áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]|\b(você|não|sem|com|para|controle|bateria|luz|modo|botão|botões|gatilho|"
                r"gatilhos|carregar|carregando|desligar|ligar|abrir|sair|teste|analógico|conectado|ajustes|"
                r"informações|versão|perfil|perfis|cor|cabo|aviso|atualizar|baixar|fechar|depois)\b", re.I)
CAMPO = re.compile(r"\{(\w*)[^}]*\}")
IDENTIFICADOR = re.compile(r"[a-z0-9_.\-]+|com\.ayrames\.\w+|https?://\S+")


def traducoes(*pastas):
    dados = {}
    for pasta in pastas:
        for arquivo in sorted(glob.glob(os.path.join(pasta, "*.json"))):
            with open(arquivo, encoding="utf-8") as f:
                dados.update(json.load(f))
    return dados


def _chamada_traducao(no):
    return isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in ("_", "N_")


def problemas(arquivos, dados, ignorar=("Português",)):
    erros = []
    for arquivo in arquivos:
        arvore = ast.parse(open(arquivo, encoding="utf-8").read())
        dentro = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in ("registrar", "print"):
                for sub in ast.walk(no):
                    dentro.add(id(sub))
        for no in ast.walk(arvore):
            if _chamada_traducao(no) and no.args:
                arg = no.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    dentro.add(id(arg))
                    texto = arg.value
                    if (len(no.args) > 1 and isinstance(no.args[1], ast.Constant)
                            and isinstance(no.args[1].value, str)):
                        texto_chave = f"{no.args[1].value}|{texto}"
                        if texto_chave in dados:
                            texto = texto_chave
                    if texto not in dados:
                        erros.append(f"{arquivo}:{arg.lineno}: sem tradução: {texto!r}")
                    elif sorted(CAMPO.findall(arg.value)) != sorted(CAMPO.findall(dados[texto])):
                        erros.append(f"{arquivo}:{arg.lineno}: campos diferentes: {texto!r}")
        for no in ast.walk(arvore):
            if isinstance(no, ast.JoinedStr) and id(no) not in dentro:
                partes = "".join(v.value for v in no.values if isinstance(v, ast.Constant))
                if PT.search(partes) and "://" not in partes:
                    erros.append(f"{arquivo}:{no.lineno}: f-string em português fora de _(): {partes[:50]!r}")
                for v in no.values:
                    if isinstance(v, ast.Constant):
                        dentro.add(id(v))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in dentro:
                texto = no.value
                if " " in texto.strip() or len(texto) > 3:
                    if (PT.search(texto) and texto not in ignorar and not texto.startswith(("/", "-"))
                            and not IDENTIFICADOR.fullmatch(texto)):
                        erros.append(f"{arquivo}:{no.lineno}: texto em português fora de _(): {texto[:60]!r}")
    return erros


if __name__ == "__main__":
    pastas = [p for p in sys.argv[1:] if os.path.isdir(p) and p.endswith("traducoes")]
    arquivos = [p for p in sys.argv[1:] if p.endswith(".py")]
    for linha in problemas(arquivos, traducoes(*pastas)):
        print(linha)
