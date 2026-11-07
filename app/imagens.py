"""Imagens: versões .webp otimizadas das fotos do tema e validação de uploads.

Uso (roda no build da imagem Docker):
  python -m app.imagens otimizar   # gera app/static/img/*.webp (≤ 250 KB), mantendo os originais
"""
import io, sys
from pathlib import Path
from PIL import Image

PASTA = Path(__file__).parent / 'static' / 'img'
LIMITE_WEBP = 250 * 1024
LIMITE_UPLOAD = 3 * 1024 * 1024
FORMATOS = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}

def para_webp(origem: Path, destino: Path, largura_max=1920):
    im = Image.open(origem)
    im.load()
    if im.mode not in ('RGB', 'RGBA'):
        im = im.convert('RGBA' if 'A' in im.getbands() else 'RGB')
    if im.width > largura_max:
        im = im.resize((largura_max, round(im.height * largura_max / im.width)), Image.LANCZOS)
    for q in (82, 74, 66, 58, 50, 42):
        buf = io.BytesIO()
        im.save(buf, 'WEBP', quality=q, method=6)
        if buf.tell() <= LIMITE_WEBP:
            break
    destino.write_bytes(buf.getvalue())
    return destino.stat().st_size

def otimizar(pasta: Path = PASTA):
    for f in sorted(pasta.iterdir()):
        if f.suffix.lower() in ('.jpg', '.jpeg', '.png'):
            n = para_webp(f, f.with_suffix('.webp'))
            print(f'{f.name} → {f.stem}.webp ({n // 1024} KB)')

def validar_upload(dados: bytes) -> str:
    """Confere tamanho e formato real do arquivo (não confia na extensão). Devolve a extensão."""
    if len(dados) > LIMITE_UPLOAD:
        raise ValueError('Arquivo maior que 3 MB.')
    try:
        im = Image.open(io.BytesIO(dados))
        im.verify()
    except Exception:
        raise ValueError('Arquivo não é uma imagem PNG, JPG ou WEBP válida.')
    ext = FORMATOS.get(im.format)
    if not ext:
        raise ValueError('Use PNG, JPG ou WEBP.')
    return ext

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'otimizar':
        otimizar()
