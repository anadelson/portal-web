"""Arquivos anexos dos comunicados (editais, avisos, convites…), 10/11/2026.

Aceita PDF, imagens (PNG, JPG, WEBP), documentos e planilhas abertos ou do Office sem macro (DOCX, XLSX, ODT, ODS) e CSV.
O tipo é conferido pelo CONTEÚDO do arquivo (não pela extensão). Office com macro, .doc/.xls antigos, compactados e
executáveis são recusados. Cada anexo exige uma descrição curta (vira o texto do link e o texto alternativo da imagem).
Arquivos ficam em DADOS_DIR/<órgão>/anexos/<32 hex>.<ext>; o portal só entrega anexo de comunicado publicado e visível."""
import io, re, secrets, zipfile
from pathlib import Path
from . import config, db

LIMITE = 20 * 1024 * 1024
MAX_POR_COMUNICADO = 15
# ext -> (tipo MIME, rótulo, abrir no navegador?)
TIPOS = {'pdf': ('application/pdf', 'PDF', True), 'png': ('image/png', 'imagem PNG', True), 'jpg': ('image/jpeg', 'imagem JPG', True),
         'webp': ('image/webp', 'imagem WEBP', True),
         'docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'documento Word (DOCX)', False),
         'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'planilha Excel (XLSX)', False),
         'odt': ('application/vnd.oasis.opendocument.text', 'documento ODT', False),
         'ods': ('application/vnd.oasis.opendocument.spreadsheet', 'planilha ODS', False),
         'csv': ('text/csv; charset=utf-8', 'planilha CSV', False)}
IMAGENS = {'png', 'jpg', 'webp'}
ACEITOS = 'PDF, PNG, JPG, WEBP, DOCX, XLSX, ODT, ODS ou CSV'
ARQ_OK = re.compile(r'^[0-9a-f]{32}\.(' + '|'.join(TIPOS) + r')$')

def detectar(dados: bytes, nome: str = '') -> str:
    """Devolve a extensão real do arquivo ou levanta ValueError com a explicação para o usuário."""
    if not dados:
        raise ValueError('O arquivo está vazio.')
    if len(dados) > LIMITE:
        raise ValueError('Arquivo maior que 20 MB.')
    if dados.startswith(b'%PDF-'):
        return 'pdf'
    if dados.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if dados[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if dados[:4] == b'RIFF' and dados[8:12] == b'WEBP':
        return 'webp'
    if dados[:4] == b'PK\x03\x04':
        try:
            z = zipfile.ZipFile(io.BytesIO(dados))
            nomes = z.namelist()
        except zipfile.BadZipFile:
            raise ValueError('Arquivo compactado inválido.')
        if any(n.lower().endswith('vbaproject.bin') or n.lower().startswith('basic/') or '/basic/' in n.lower() for n in nomes):
            raise ValueError('Documento com macro não é aceito. Salve sem macro (DOCX, XLSX, ODT ou ODS) ou envie em PDF.')
        if 'word/document.xml' in nomes:
            return 'docx'
        if 'xl/workbook.xml' in nomes:
            return 'xlsx'
        if 'mimetype' in nomes:
            mt = z.read('mimetype').decode('ascii', 'ignore').strip()
            if mt == 'application/vnd.oasis.opendocument.text':
                return 'odt'
            if mt == 'application/vnd.oasis.opendocument.spreadsheet':
                return 'ods'
        raise ValueError(f'Arquivo compactado (ZIP) não é aceito. Envie {ACEITOS}.')
    if nome.lower().endswith('.csv') and b'\x00' not in dados[:4096]:
        try:
            dados[:65536].decode('utf-8')
        except UnicodeDecodeError:
            try:
                dados[:65536].decode('latin-1')
            except UnicodeDecodeError:
                raise ValueError('O CSV não é um texto válido.')
        inicio = dados[:200].lstrip().lower()
        if inicio.startswith((b'<', b'#!', b'mz')):
            raise ValueError('O arquivo não é um CSV.')
        return 'csv'
    if dados[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        raise ValueError('Formato antigo do Office (.doc/.xls) não é aceito: pode conter macro. Salve como DOCX, XLSX ou PDF.')
    raise ValueError(f'Formato não aceito. Envie {ACEITOS}.')

def pasta(o):
    p = Path(config.DADOS_DIR) / o['slug'] / 'anexos'
    p.mkdir(parents=True, exist_ok=True)
    return p

async def salvar(o, comunicado_id, arquivo, titulo, quem):
    """Valida e guarda o arquivo enviado. Devolve o id do anexo."""
    titulo = re.sub(r'\s+', ' ', titulo or '').strip()
    if len(titulo) < 3:
        raise ValueError('Escreva o que é o arquivo (ex.: “Edital completo”, “Anexo I — Planilha de preços”). O texto aparece no link e é lido pelo leitor de tela.')
    if not arquivo or not getattr(arquivo, 'filename', ''):
        raise ValueError('Escolha o arquivo.')
    n = db.um(o['banco'], 'SELECT count(*) n FROM comunicado_anexos WHERE comunicado_id=%s', (comunicado_id,))['n']
    if n >= MAX_POR_COMUNICADO:
        raise ValueError(f'No máximo {MAX_POR_COMUNICADO} anexos por comunicado.')
    dados = await arquivo.read(LIMITE + 1)
    ext = detectar(dados, arquivo.filename)
    nome = f'{secrets.token_hex(16)}.{ext}'
    (pasta(o) / nome).write_bytes(dados)
    original = re.sub(r'[^\w.\- ]+', '', Path(arquivo.filename).name)[:120] or nome
    return db.exe(o['banco'], 'INSERT INTO comunicado_anexos (comunicado_id, arquivo, nome_original, titulo, ext, bytes, enviado_por) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                  (comunicado_id, nome, original, titulo[:200], ext, len(dados), quem))['id']

def remover(o, anexo_id, comunicado_id):
    a = db.um(o['banco'], 'SELECT * FROM comunicado_anexos WHERE id=%s AND comunicado_id=%s', (anexo_id, comunicado_id))
    if not a:
        return None
    db.exe(o['banco'], 'DELETE FROM comunicado_anexos WHERE id=%s', (anexo_id,))
    try:
        (pasta(o) / a['arquivo']).unlink()
    except FileNotFoundError:
        pass
    return a

def listar(banco, comunicado_id):
    return [dict(a, rotulo=TIPOS[a['ext']][1], imagem=a['ext'] in IMAGENS, tamanho=tamanho(a['bytes']))
            for a in db.todos(banco, 'SELECT * FROM comunicado_anexos WHERE comunicado_id=%s ORDER BY ordem, id', (comunicado_id,))]

def contagem(banco, ids):
    if not ids:
        return {}
    return {x['comunicado_id']: x['n'] for x in db.todos(banco, 'SELECT comunicado_id, count(*) n FROM comunicado_anexos WHERE comunicado_id = ANY(%s) GROUP BY 1', (list(ids),))}

def tamanho(b):
    if b < 1024 * 1024:
        return f'{max(1, round(b / 1024))} KB'
    return f'{b / 1024 / 1024:.1f} MB'.replace('.', ',')
