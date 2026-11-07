# Certificados intermediários públicos

Usados **só para completar a cadeia TLS** de servidores que não enviam o certificado intermediário. A verificação
continua ligada: a cadeia precisa terminar numa raiz confiável do sistema (certifi). Nada aqui é segredo.

| Arquivo | Para | Emitido por | Válido de | Válido até | SHA-256 |
|---|---|---|---|---|---|
| `rnp-icpedu-gr46-ov-tls-ca-2025.pem` | `download.inep.gov.br` (planilhas do IDEB/Saeb) | GlobalSign Root R46 | 19/11/2025 | **19/11/2030** | `E1:07:47:D4:DA:7B:AB:09:CB:A9:95:2F:01:9D:35:34:CB:9F:BA:07:0B:F1:3D:87:91:B1:69:9C:D2:FF:59:DD` |

Origem: endereço oficial "CA Issuers" (AIA) do próprio certificado do servidor,
`http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt`, convertido para PEM e conferido com
`openssl verify` contra a raiz GlobalSign R46 (07/11/2026).

O coletor do INEP avisa no painel administrativo (Painel de indicadores) **60 dias antes** do vencimento.
Para trocar: baixe o novo intermediário do endereço AIA do certificado atual de `download.inep.gov.br`,
confira com `openssl verify`, substitua o arquivo, atualize esta tabela e refaça o build.
