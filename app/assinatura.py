"""Assinatura digital do Diário Oficial: PAdES (pyHanko) com carimbo do tempo RFC 3161 e dados de validação (LTV).

Provedores (Lei 910/2026, art. 7º; MP 2.200-2/2001; Lei 14.063/2020):
  a1     certificado ICP-Brasil A1 (PKCS#12) em SEGREDOS_DIR/a1/<arquivo>.p12, senha na variável do .env indicada na designação
  nuvem  certificado em nuvem: interface pronta; falta o provedor fornecer API e credenciais (ver ProvedorNuvem)
  a3     token/cartão: o signatário assina o PDF no próprio computador e envia; o sistema valida antes de aceitar
  teste  MODO TESTE: certificados gerados só para teste (SEGREDOS_DIR/teste), ACT de teste local e marca d'água

Uso (linha de comando, gera a cadeia de TESTE):  python -m app.assinatura gerar-teste [pasta]
Nenhum certificado, chave ou senha vai para o git ou para o log.
"""
import io, os, re, secrets, sys, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from . import config

ETAPAS = {'executivo': 'Caderno do Poder Executivo', 'legislativo': 'Caderno do Poder Legislativo', 'final': 'Assinatura final da edição (setor responsável)'}

class NaoConfigurado(Exception):
    """Falta segredo/configuração para assinar (certificado, senha, ACT, credenciais do provedor)."""

def modo_teste() -> bool:
    return config.DIARIO_MODO != 'oficial'

def _pasta(*p):
    return Path(config.SEGREDOS_DIR, *p)

# ---------- cadeia de TESTE (só para modo teste e testes automatizados) ----------
def gerar_cadeia_teste(destino: str | None = None):
    """Gera AC raiz de teste, certificados de signatário (um por etapa) e da ACT de teste. Senhas aleatórias em arquivos .senha (600)."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    d = Path(destino or _pasta('teste'))
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    agora = datetime.now(timezone.utc) - timedelta(days=1)
    nome = lambda cn: x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, 'BR'), x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'TESTE - SEM VALOR OFICIAL'), x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    def chave():
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rk = chave()
    raiz = (x509.CertificateBuilder().subject_name(nome('AC Raiz de TESTE do Portal')).issuer_name(nome('AC Raiz de TESTE do Portal'))
            .public_key(rk.public_key()).serial_number(x509.random_serial_number()).not_valid_before(agora).not_valid_after(agora + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(rk.public_key()), critical=False)
            .sign(rk, hashes.SHA256()))
    escrever = lambda nome_arq, dados: (d / nome_arq).write_bytes(dados) or os.chmod(d / nome_arq, 0o600)
    escrever('raiz.crt', raiz.public_bytes(serialization.Encoding.PEM))
    def emitir(cn, tsa=False):
        k = chave()
        b = (x509.CertificateBuilder().subject_name(nome(cn)).issuer_name(raiz.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(agora).not_valid_after(agora + timedelta(days=730))
             .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
             .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(rk.public_key()), critical=False)
             .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=not tsa, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True))
        if tsa:
            b = b.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
        return k, b.sign(rk, hashes.SHA256())
    for etapa, cn in (('executivo', 'Prefeito(a) - TESTE'), ('legislativo', 'Presidente da Camara - TESTE'), ('final', 'Responsavel pelo Diario - TESTE')):
        k, c = emitir(cn)
        senha = secrets.token_urlsafe(18)
        escrever(f'{etapa}.p12', pkcs12.serialize_key_and_certificates(etapa.encode(), k, c, [raiz], serialization.BestAvailableEncryption(senha.encode())))
        escrever(f'{etapa}.senha', senha.encode())
    k, c = emitir('ACT de TESTE do Portal', tsa=True)
    escrever('tsa.crt', c.public_bytes(serialization.Encoding.PEM))
    escrever('tsa.key', k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return str(d)

# ---------- peças do pyHanko ----------
def _carregar_cert(caminho):
    try:
        from pyhanko.keys import load_cert_from_pemder
    except ImportError:  # versões antigas
        from pyhanko.sign.general import load_cert_from_pemder
    return load_cert_from_pemder(str(caminho))

def _carregar_chave(caminho):
    try:
        from pyhanko.keys import load_private_key_from_pemder
    except ImportError:
        from pyhanko.sign.general import load_private_key_from_pemder
    return load_private_key_from_pemder(str(caminho), passphrase=None)

def raizes_confiaveis():
    """Modo teste: AC Raiz de TESTE. Oficial: AC Raiz ICP-Brasil em SEGREDOS_DIR/icp (baixadas do ITI)."""
    if modo_teste():
        return [_carregar_cert(_pasta('teste', 'raiz.crt'))]
    pasta = _pasta(config.ICP_RAIZES)
    certs = [_carregar_cert(p) for p in sorted(pasta.glob('*')) if p.suffix.lower() in ('.crt', '.cer', '.pem')] if pasta.is_dir() else []
    if not certs:
        raise NaoConfigurado(f'Coloque as AC Raiz ICP-Brasil (.crt) em segredos/{config.ICP_RAIZES}/ (download no site do ITI).')
    return certs

def contexto_validacao():
    from pyhanko_certvalidator import ValidationContext
    if modo_teste():
        return ValidationContext(trust_roots=raizes_confiaveis(), allow_fetching=False, revocation_mode='soft-fail')
    return ValidationContext(trust_roots=raizes_confiaveis(), allow_fetching=True)

def carimbador():
    """ACT: em modo teste, ACT local de teste; em modo oficial, a ACT contratada (RFC 3161) configurada no .env."""
    if modo_teste():
        from pyhanko.sign.timestamps import DummyTimeStamper
        tsa = _carregar_cert(_pasta('teste', 'tsa.crt'))
        return DummyTimeStamper(tsa_cert=tsa, tsa_key=_carregar_chave(_pasta('teste', 'tsa.key')), certs_to_embed=[_carregar_cert(_pasta('teste', 'raiz.crt'))])
    if not config.ACT_URL:
        raise NaoConfigurado('Configure ACT_URL (e, se a ACT exigir, ACT_USUARIO/ACT_SENHA) no .env com os dados do contrato da Autoridade de Carimbo do Tempo.')
    from pyhanko.sign.timestamps.requests_client import HTTPTimeStamper
    auth = None
    if config.ACT_USUARIO:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth(config.ACT_USUARIO, config.ACT_SENHA)
    if config.ACT_CERT:
        raise NaoConfigurado('ACT com certificado de cliente: integração a validar com a documentação da ACT contratada (ver README, Fase 6).')
    return HTTPTimeStamper(config.ACT_URL, auth=auth, timeout=30)

# ---------- provedores ----------
class ProvedorPKCS12:
    def __init__(self, arquivo: Path, senha: bytes, rotulo: str):
        self.arquivo, self.senha, self.rotulo = arquivo, senha, rotulo

    def signer(self):
        from pyhanko.sign import signers
        if not self.arquivo.is_file():
            raise NaoConfigurado(f'Certificado não encontrado: segredos/{self.arquivo.relative_to(config.SEGREDOS_DIR) if str(self.arquivo).startswith(config.SEGREDOS_DIR) else self.arquivo.name}')
        s = signers.SimpleSigner.load_pkcs12(pfx_file=str(self.arquivo), passphrase=self.senha)
        if s is None:
            raise NaoConfigurado(f'Não foi possível abrir o certificado de {self.rotulo} (senha incorreta ou arquivo inválido).')
        return s

def provedor_teste(etapa):
    senha = _pasta('teste', f'{etapa}.senha')
    if not senha.is_file():
        raise NaoConfigurado('Cadeia de teste não gerada: rode "python -m app.assinatura gerar-teste" (ver README).')
    return ProvedorPKCS12(_pasta('teste', f'{etapa}.p12'), senha.read_bytes().strip(), f'teste/{etapa}')

def provedor_a1(designacao):
    if not designacao.get('certificado') or not re.fullmatch(r'[\w.-]+\.(p12|pfx)', designacao['certificado']):
        raise NaoConfigurado('Designação sem arquivo de certificado A1 (.p12/.pfx) válido.')
    senha = os.environ.get(designacao.get('senha_env') or '', '')
    if not senha:
        raise NaoConfigurado(f"Defina a senha do certificado na variável {designacao.get('senha_env') or '(não informada)'} do .env.")
    return ProvedorPKCS12(_pasta('a1', designacao['certificado']), senha.encode(), designacao['nome'])

class ProvedorNuvem:
    """Certificado em nuvem (ex.: serviços de assinatura remota credenciados no ICP-Brasil).
    O provedor precisa fornecer: (1) API de assinatura remota de hash (CSC/Cloud Signature Consortium ou API própria documentada),
    (2) credenciais da aplicação (client_id/secret ou certificado de cliente), (3) fluxo de autorização do titular (OTP/push),
    (4) cadeia do certificado do titular. Com isso, implementa-se um pyhanko.sign.signers.ExternalSigner que envia o hash e recebe a assinatura.
    Sem esses dados, NÃO há endpoint inventado: a etapa usa o fluxo A3 (upload do PDF assinado) ou A1."""
    def signer(self):
        raise NaoConfigurado('Certificado em nuvem: aguardando o provedor contratado fornecer a API e as credenciais (ver README, Fase 6). Use A1 ou envie o PDF assinado (A3).')

def provedor_para(designacao, etapa):
    if modo_teste():
        return provedor_teste(etapa)
    if not designacao:
        raise NaoConfigurado(f'Não há signatário designado para: {ETAPAS[etapa]}.')
    if designacao['provedor'] == 'a1':
        return provedor_a1(designacao)
    if designacao['provedor'] == 'nuvem':
        return ProvedorNuvem()
    raise NaoConfigurado('Signatário com token/cartão (A3): baixe o PDF, assine no seu computador e envie o arquivo assinado.')

# ---------- assinar e validar ----------
def assinar(pdf: bytes, etapa: str, designacao, motivo: str, local: str) -> bytes:
    """Acrescenta uma assinatura PAdES (atualização incremental) com carimbo do tempo e, quando possível, LTV."""
    from pyhanko.sign import signers, fields
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    signer = provedor_para(designacao, etapa).signer()
    ts = carimbador()
    vc = contexto_validacao()
    campo = f'Assinatura_{etapa}_{secrets.token_hex(3)}'
    def tentar(ltv):
        meta = signers.PdfSignatureMetadata(field_name=campo, md_algorithm='sha256', subfilter=fields.SigSeedSubFilter.PADES, reason=motivo[:120], location=local[:80],
                                            embed_validation_info=ltv, validation_context=vc if ltv else None, use_pades_lta=False)
        w = IncrementalPdfFileWriter(io.BytesIO(pdf))
        out = io.BytesIO()
        signers.sign_pdf(w, meta, signer=signer, timestamper=ts, output=out)
        return out.getvalue()
    try:
        return tentar(True)
    except Exception:
        if not modo_teste():
            raise
        return tentar(False)  # cadeia de teste sem revogação publicada: assina sem embutir LTV

def _nome(st):
    try:
        return st.signing_cert.subject.native.get('common_name') or st.signing_cert.subject.human_friendly
    except Exception:
        return '?'

def validar(pdf: bytes):
    """Valida todas as assinaturas. Devolve lista de dicts: campo, signatário, íntegra, válida, confiável, data do carimbo, cobre o documento."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    r = PdfFileReader(io.BytesIO(pdf))
    vc = contexto_validacao()
    res = []
    for sig in r.embedded_signatures:
        try:
            st = validate_pdf_signature(sig, vc)
            ts = getattr(st, 'timestamp_validity', None)
            res.append({'campo': sig.field_name, 'signatario': _nome(st), 'integra': bool(st.intact), 'valida': bool(st.valid), 'confiavel': bool(st.trusted),
                        'carimbo': ts.timestamp.isoformat() if ts is not None and getattr(ts, 'timestamp', None) else None,
                        'carimbo_valido': bool(ts and ts.valid and ts.intact) if ts is not None else False,
                        'data_assinante': st.signer_reported_dt.isoformat() if getattr(st, 'signer_reported_dt', None) else None,
                        'resumo': st.summary() if hasattr(st, 'summary') else ''})
        except Exception as e:
            res.append({'campo': sig.field_name, 'signatario': '?', 'integra': False, 'valida': False, 'confiavel': False, 'carimbo': None, 'carimbo_valido': False, 'erro': type(e).__name__})
    return res

def _norm(s):
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()

def aceitar_upload_a3(pdf_anterior: bytes, pdf_novo: bytes, designacao) -> list:
    """A3: aceita o PDF assinado fora do servidor só se (1) preserva o documento anterior byte a byte (atualização incremental),
    (2) traz exatamente uma assinatura nova, (3) todas as assinaturas estão íntegras e válidas e (4) a nova é do signatário designado."""
    if not pdf_novo.startswith(b'%PDF-') or len(pdf_novo) <= len(pdf_anterior) or not pdf_novo.startswith(pdf_anterior):
        raise ValueError('O arquivo enviado não é o PDF desta edição assinado sobre a versão atual (a assinatura deve ser acrescentada, sem alterar o documento).')
    antes, depois = validar(pdf_anterior), validar(pdf_novo)
    if len(depois) != len(antes) + 1:
        raise ValueError('O PDF deve trazer exatamente uma assinatura nova.')
    ruins = [a['campo'] for a in depois if not (a['integra'] and a['valida'])]
    if ruins:
        raise ValueError('Assinatura inválida ou documento alterado: ' + ', '.join(ruins))
    if not modo_teste() and not depois[-1]['confiavel']:
        raise ValueError('A assinatura não é de um certificado ICP-Brasil confiável.')
    if designacao and not modo_teste() and _norm(designacao['nome']).split()[0] not in _norm(depois[-1]['signatario']):
        raise ValueError(f"A assinatura é de {depois[-1]['signatario']}, mas o signatário designado é {designacao['nome']}.")
    return depois

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'gerar-teste':
        print('Cadeia de TESTE gerada em', gerar_cadeia_teste(sys.argv[2] if len(sys.argv) > 2 else None), '(sem valor oficial)')
    else:
        print(__doc__)
