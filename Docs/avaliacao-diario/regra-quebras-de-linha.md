# Diário — regra das quebras de linha do texto dos atos (para validação do gestor)

Pedido: `Docs/PEDIDO-DIARIO-CAPA.md`, item A.7. **O conteúdo não muda**: são as mesmas palavras, na mesma ordem. Isso foi conferido automaticamente na Edição nº 1 (`validacao-e-texto.json`: texto anterior = texto novo = texto cadastrado, ignorando quebras e hifenização). Só muda onde ficam as quebras de linha.

## A regra

1. As linhas de um mesmo parágrafo são juntadas.
2. A quebra é mantida quando:
   - a linha termina em **ponto** ou **dois-pontos**;
   - a linha seguinte começa com **"Art."**, **"§"**, **"Parágrafo"**, inciso (**"I -"**, **"II –"**) ou alínea (**"a)"**);
   - a linha seguinte é uma chamada em maiúsculas terminada em dois-pontos (**RESOLVE:**, **DECRETA:**, **TORNA PÚBLICO:**).
3. "Publique-se / e / Cumpra-se." vira **"Publique-se e Cumpra-se."**, porque só a última linha termina em ponto.
4. Depois da linha de **local e data** ("Borá, 13 de novembro de 2026."):
   - as linhas em maiúsculas são a **assinatura**: nome em negrito e cargo abaixo, centralizados;
   - o texto seguinte ("Registrada nesta Secretaria…") é o **registro**, em 8,5 pt depois de um fio pontilhado, com o nome de quem registrou.
5. Atos digitados no editor com formatação (negrito, listas, alinhamento) não passam por esta regra: já chegam com os parágrafos certos.

O pedido era mostrar 3 atos reais. Até hoje há **um único ato real** cadastrado (o da Edição nº 1, abaixo). Os outros dois exemplos são **fictícios** e mostram os casos que o ato real não tem: incisos, parágrafo único e chamada "DECRETA:".

## 1. Ato real — Lei 419/2026 (Edição nº 1)

**Antes** (como foi cadastrado; cada linha é uma quebra manual):

```
LUIZ CARLOS RODRIGUES, Prefeito Municipal de Borá,
Estado de São Paulo, no uso de suas atribuições legais,
RESOLVE:
Art. 1º. Ficam nomeadas as Sras. Deyse Aparecida de
Almeida Trevisan e Francielli Garcia Menezes, como
Presidente e Vice-Presidente respectivamente do Conselho
Municipal de Acompanhamento e Controle Social do Fundo
de Manutenção e Desenvolvimento da Educação Básica e
de Valorização dos Profissionais da Educação-Conselho do
FUNDEB, instituído pela Lei nº 800 de 17/03/2021, por força
de eleição entre seus pares em assembleia realizada em
11/11/2026.
Art. 2º. Esta Portaria entra em vigor na data de sua
publicação.
Publique-se
e
Cumpra-se.
Borá, 13 de novembro de 2026.
LUIZ CARLOS RODRIGUES
PREFEITO MUNICIPAL
Registrada nesta Secretaria em livro próprio, na data
supra e publicada por edital afixado em lugar público de
costume.
EDNA MARIA PAVANELI
```

**Depois** (parágrafos do miolo):

> LUIZ CARLOS RODRIGUES, Prefeito Municipal de Borá, Estado de São Paulo, no uso de suas atribuições legais,
>
> RESOLVE:
>
> Art. 1º. Ficam nomeadas as Sras. Deyse Aparecida de Almeida Trevisan e Francielli Garcia Menezes, como Presidente e Vice-Presidente respectivamente do Conselho Municipal de Acompanhamento e Controle Social do Fundo de Manutenção e Desenvolvimento da Educação Básica e de Valorização dos Profissionais da Educação-Conselho do FUNDEB, instituído pela Lei nº 800 de 17/03/2021, por força de eleição entre seus pares em assembleia realizada em 11/11/2026.
>
> Art. 2º. Esta Portaria entra em vigor na data de sua publicação.
>
> Publique-se e Cumpra-se.
>
> Borá, 13 de novembro de 2026.
>
> *(assinatura, centralizada)* **LUIZ CARLOS RODRIGUES** / PREFEITO MUNICIPAL
>
> *(registro, 8,5 pt)* Registrada nesta Secretaria em livro próprio, na data supra e publicada por edital afixado em lugar público de costume. / **EDNA MARIA PAVANELI**

Observação (item E do pedido, **não alterado**): o título diz "Lei 419/2026", mas o texto diz "RESOLVE:" e "Esta Portaria entra em vigor". Parece ser uma Portaria cadastrada com o tipo errado. Isso é dado do ato, não do layout: confira o cadastro antes da edição real.

## 2. Exemplo fictício — incisos e parágrafo único

**Antes:**

```
Art. 1º. Fica nomeada a Sra. Beltrana de Tal (EXEMPLO) para
o conselho municipal de exemplo, por força de eleição
entre seus pares.
Parágrafo único. O mandato é de dois anos.
I - primeiro inciso de exemplo;
II - segundo inciso de exemplo.
```

**Depois:**

> Art. 1º. Fica nomeada a Sra. Beltrana de Tal (EXEMPLO) para o conselho municipal de exemplo, por força de eleição entre seus pares.
>
> Parágrafo único. O mandato é de dois anos.
>
> I - primeiro inciso de exemplo;
>
> II - segundo inciso de exemplo.

## 3. Exemplo fictício — chamada "DECRETA:" no meio do texto

**Antes:**

```
FULANO DE TAL (EXEMPLO), Prefeito Municipal (EXEMPLO), no uso de
suas atribuições legais,
DECRETA:
Art. 1º O poder executivo regulamentará, no que couber, o disposto neste
artigo no prazo de noventa dias contados da publicação.
```

**Depois:**

> FULANO DE TAL (EXEMPLO), Prefeito Municipal (EXEMPLO), no uso de suas atribuições legais,
>
> DECRETA:
>
> Art. 1º O poder executivo regulamentará, no que couber, o disposto neste artigo no prazo de noventa dias contados da publicação.

## Limites da regra (para o gestor saber)

- Uma linha que termina com abreviação ("Sr.", "nº.") no fim da linha também quebra o parágrafo nesse ponto.
- Se a assinatura não estiver em maiúsculas, ela fica como texto comum, alinhado à esquerda (nada se perde, só não fica centralizada).
