# Modelos de importação (Fase 5)

Arquivos CSV em **UTF-8**, separador **ponto e vírgula**, datas **dd/mm/aaaa**, valores com vírgula decimal (`1.234,56`).
Cada arquivo traz só o cabeçalho: preencha com os dados **exportados do sistema legislativo do fornecedor** (Pronim/Cidade360) ou digitados a partir das atas e documentos oficiais. **Não raspar o portal antigo** (tem reCAPTCHA).

| Arquivo | Colunas | Regras |
|---|---|---|
| legislaturas.csv | numero;anos;prefeito;vice | anos no formato 2021–2024 |
| vereadores.csv | legislatura;nome;apelido;partido;votos | legislatura já cadastrada |
| mesas.csv | legislatura;bienio;cargo;nome | cargo: Presidente, Vice-presidente, 1º secretário, 2º secretário |
| proposicoes.csv | tipo;numero;ano;autores;relator;ementa;situacao | tipo: Projeto de Lei, Projeto de Lei Complementar, Projeto de Resolução, Projeto de Decreto Legislativo, Indicação, Requerimento, Moção, Emenda, Veto; autores separados por `|` |
| tramitacao.csv | tipo;numero;ano;data;fase;descricao | proposição já cadastrada |
| sessoes.csv | nome;data;hora;tipo | tipo: Ordinária, Extraordinária, Solene, Especial |
| presencas.csv | sessao_data;sessao_nome;vereador;situacao | situacao: presente, ausente, justificada |
| votos.csv | sessao_data;tipo;numero;ano;vereador;voto | voto: sim, nao, abstencao, ausente (cria o item de pauta e apura) |
| diarias.csv | beneficiario;cargo;destino;motivo;inicio;fim;valor | |

Ordem: legislaturas → vereadores → mesas → proposições → tramitação → sessões → presenças → votos → diárias.

Como importar:
- Painel da Câmara → **Controle → Importar dados antigos**: primeiro **Simular** (não grava; mostra o relatório de erros linha a linha), depois **Importar e gravar**. A gravação é tudo ou nada.
- Linha de comando na VPS: `docker compose exec app python -m app.importar MODELO /caminho/arquivo.csv --orgao cm-bora` (simulação) e o mesmo com `--gravar`.

LGPD: linhas com número no formato de CPF são recusadas. Votos, presenças e atas só entram quando vêm de registro oficial.
