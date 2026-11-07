# Modelos de importação (Fase 5)
Arquivos CSV em UTF-8, separador ponto e vírgula, datas dd/mm/aaaa. O Claude Code cria os modelos completos na Fase 5; a lista mínima:
- legislaturas.csv: numero;anos;prefeito;vice
- vereadores.csv: legislatura;nome;apelido;partido;votos
- mesas.csv: legislatura;bienio;cargo;nome
- proposicoes.csv: tipo;numero;ano;autores;relator;ementa;situacao
- tramitacao.csv: tipo;numero;ano;data;fase;descricao
- sessoes.csv: nome;data;hora;tipo
- presencas.csv: sessao_data;sessao_nome;vereador;situacao(presente|ausente|justificada)
- votos.csv: sessao_data;tipo;numero;ano;vereador;voto(sim|nao|abstencao|ausente)
- diarias.csv: beneficiario;cargo;destino;motivo;inicio;fim;valor
