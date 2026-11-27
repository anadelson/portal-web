"""Diário Oficial em plataforma de terceiros (27/11/2026): contrato dos adaptadores e registro por tipo.

Cada plataforma (DOSP, outra no futuro) é um adaptador nesta pasta. Só o adaptador conhece endereços e formatos da
plataforma; o resto do sistema (sincronização, portal, painel) fala apenas com este contrato. Para integrar uma nova
plataforma: criar um módulo com uma classe filha de FonteDiario, registrá-la com @registrar e cadastrar a fonte no painel.
O portal nunca consulta a plataforma em tempo real: lê o que a sincronização gravou no banco do órgão."""
import time
from dataclasses import dataclass
from datetime import date

import httpx

from .. import config


@dataclass
class Edicao:
    """Edição na plataforma: o portal guarda só isto e o link leva à edição na própria plataforma."""
    id_externo: str
    numero: str
    data: date
    extra: bool
    url: str
    paginas: int | None = None


class ErroFonte(Exception):
    """Falha ao consultar a plataforma. A mensagem vai para o painel: curta, sem endereço com parâmetros nem segredo."""


class Bloqueio(ErroFonte):
    """A plataforma respondeu com verificação de navegador (ex.: Cloudflare). Nunca contornamos: a sincronização para."""


class FonteDiario:
    tipo = ''
    plataforma = ''          # nome da plataforma para o painel
    campos = ()              # (chave, rótulo, ajuda) da configuração que o painel pede

    def __init__(self, cfg: dict | None = None, http=None):
        self.config = dict(cfg or {})
        self.http = http or Http()

    @classmethod
    def validar_config(cls, cfg: dict) -> dict:
        """Confere e normaliza a configuração digitada no painel (levanta ValueError com a mensagem para a pessoa)."""
        return {}

    def listar_edicoes(self, desde: date | None = None, ate: date | None = None) -> list[Edicao]:
        raise NotImplementedError

    def healthcheck(self) -> bool:
        try:
            self.listar_edicoes(desde=date.today(), ate=date.today())
            return True
        except ErroFonte:
            return False


class Http:
    """GET respeitoso: identificação do sistema, 30 s de limite, no máximo 1 requisição por segundo e novas tentativas
    com espera crescente. Verificação de navegador (Cloudflare) não é repetida: levanta Bloqueio na hora."""
    INTERVALO = 1.0
    TENTATIVAS = 3

    def __init__(self, timeout=30):
        self.timeout = timeout
        self._ultimo = 0.0

    def get(self, url: str, bloqueio=None) -> str:
        erro = None
        for i in range(self.TENTATIVAS):
            espera = self.INTERVALO - (time.monotonic() - self._ultimo)
            if espera > 0:
                time.sleep(espera)
            self._ultimo = time.monotonic()
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers={'User-Agent': config.USER_AGENT}) as c:
                    r = c.get(url)
            except httpx.HTTPError as e:
                erro = ErroFonte(f'sem resposta da plataforma ({type(e).__name__})')
            else:
                if bloqueio and bloqueio(r.status_code, r.text):
                    raise Bloqueio('a plataforma pediu verificação de navegador (Cloudflare); a sincronização parou sem contornar o bloqueio')
                if r.status_code == 200:
                    return r.text
                erro = ErroFonte(f'a plataforma respondeu HTTP {r.status_code}')
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    break
            if i < self.TENTATIVAS - 1:
                time.sleep(3 * (i + 1))
        raise erro


ADAPTADORES: dict[str, type[FonteDiario]] = {}


def registrar(cls):
    ADAPTADORES[cls.tipo] = cls
    return cls


def criar(tipo: str, cfg: dict | None = None, http=None) -> FonteDiario:
    if tipo not in ADAPTADORES:
        raise ErroFonte(f'tipo de fonte desconhecido: {tipo}')
    return ADAPTADORES[tipo](cfg, http)


from . import dosp  # noqa: E402,F401  (registra os adaptadores)
