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

# ---- Identidade: remover sem apagar e restaurar a anterior (16/11/2026) ----
# Remover só desvincula a imagem da configuração; o arquivo e a linha da biblioteca de mídia ficam.
# `identidade.anteriores[uso]` guarda as últimas imagens desvinculadas ou trocadas (a mais recente no fim).
MAX_ANTERIORES = 5

def guardar_anterior(ident, uso, item):
    if item:
        h = ident.setdefault('anteriores', {}).setdefault(uso, [])
        if not h or h[-1] != item:
            h.append(item)
        del h[:-MAX_ANTERIORES]

def tem_anterior(ident, uso):
    return bool(((ident or {}).get('anteriores') or {}).get(uso))

def restaurar_anterior(ident, uso, atual):
    """Tira a última anterior do histórico e devolve; a atual (se houver) vai para o histórico no lugar."""
    h = ((ident.get('anteriores') or {}).get(uso)) or []
    if not h:
        return None
    volta = h.pop()
    if atual:
        h.append(atual)
    return volta

def existe_midia(pasta, url):
    """Imagem enviada pelo painel cujo arquivo sumiu (cópia de banco sem a pasta de mídia, por exemplo) não vira <img> quebrada."""
    if not isinstance(url, str) or not url.startswith('/midia/'):
        return bool(url)
    return (Path(pasta) / url[7:]).is_file()
