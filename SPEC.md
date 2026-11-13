# SPEC — Data Quality Monitor v0.1

**Status:** draft para implementação por agente de IA
**Versão do produto:** `0.1.0`
**Testes:** caixa-preta, escritos por outro agente de IA, independente do implementador, contra o executável `./app`
**Idioma:** explicações em português; identificadores, flags, campos e nomes técnicos em inglês.

---

## 1. Visão geral

`data-quality-monitor` é uma CLI que lê arquivos CSV com schema explícito, calcula métricas de qualidade (null rate, outliers por IQR, estatísticas de distribuição), compara com baseline local e produz: relatórios JSON, Markdown com análise de desvios, e validação de conformidade.

O programa é *stream-friendly*: lê de arquivo ou `stdin`, tolera linhas malformadas (reporta-as), nunca aborta e sempre relata quantas linhas foram descartadas/validadas.

### 1.1 Modelo interno (data record)

Um record é uma linha do CSV com valores parseados segundo o schema. Campos ausentes ou nulos são `null` após parsing.

| campo | tipo | origem |
|---|---|---|
| `row_number` | integer ≥ 1 | sequência da linha no CSV (header = 1) |
| `column_name` | string | nome de coluna do header |
| `value` | string/int/float/bool/null | valor bruto ou parseado conforme schema |
| `is_valid` | boolean | conforma com o tipo esperado |
| `is_outlier` | boolean | (apenas para tipo numérico) detectado por IQR |
| `is_null` | boolean | se o valor é null/NA/vazio |

### 1.2 Schema (JSON)

Define as colunas esperadas, tipos e políticas de validação:

```json
{
  "columns": [
    {
      "name": "user_id",
      "type": "integer",
      "required": true,
      "nullable": false
    },
    {
      "name": "email",
      "type": "string",
      "required": true,
      "nullable": false,
      "pattern": "^[^@]+@[^@]+$"
    },
    {
      "name": "age",
      "type": "integer",
      "required": false,
      "nullable": true,
      "min": 0,
      "max": 150
    },
    {
      "name": "score",
      "type": "float",
      "required": false,
      "nullable": true
    }
  ]
}
```

Tipos suportados: `string`, `integer`, `float`, `boolean`, `date` (ISO-8601).
Campos de schema: `name`, `type`, `required`, `nullable`, `pattern` (regex para string), `min`, `max` (numérico).

---

## 2. Não-objetivos (fora do escopo da v0.1)

1. Conectores para banco de dados, S3, GCS ou APIs externas.
2. Alertas por e-mail, webhook ou integração com serviços em nuvem.
3. TUI interativa, paginação ou painel web.
4. Profiling de performance ou otimização de memória sob gigabytes.
5. Suporte a formatos além de CSV (Parquet, Avro, protobuf).
6. Clustering, PCA ou modelos de ML para detecção de anomalias.
7. Audit log persistente ou cache entre execuções.
8. Suporte a Windows nativo (alvo: Linux/macOS; `./app` é executável POSIX).

---

## 3. Contrato de execução (CLI)

### 3.1 Invocação

Executável `./app` na raiz do repositório, com permissão de execução (`chmod +x`). Pode ser binário, script ou wrapper shell que delega para o runtime real.

```
./app <subcommand> [options] [FILE]
```

- `FILE` é opcional. Ausente ou `-` ⇒ lê de `stdin`.
- Flags podem vir antes ou depois do `FILE`.
- Flags aceitam `--flag valor` e `--flag=valor`.

### 3.2 Subcomandos e flags

**Globais (aceitas por todos os subcomandos, exceto onde indicado):**

| flag | valores | default | efeito |
|---|---|---|---|
| `--schema` | caminho | obrigatório | arquivo JSON com schema |
| `--format` | `csv` | `csv` | formato de entrada (v0.1 suporta apenas CSV) |
| `--json` | — | off | saída JSON em `stdout` |
| `--quiet` | — | off | suprime avisos em `stderr` |
| `--help` | — | — | ajuda (em `stdout` ou `stderr`, à escolha da implementação) e exit `0` |
| `--version` | — | — | imprime `data-quality-monitor 0.1.0` e exit `0` |

**`validate`**
```
./app validate --schema SCHEMA [--json] [FILE]
```
Valida o CSV contra o schema. Reporta erros de conformidade.

**`analyze`**
```
./app analyze --schema SCHEMA [--baseline BASELINE.json] [--outlier-threshold K] [--json] [FILE]
```
`--baseline` (opcional): arquivo JSON com métricas esperadas.
`--outlier-threshold K` (default `1.5`, float ≥ 0): multiplicador para IQR ao detectar outliers.

**`report`**
```
./app report --schema SCHEMA [--baseline BASELINE.json] [--outlier-threshold K] --out <path.md> [--now ISO8601] [FILE]
```
`--out` obrigatório; `-` escreve o Markdown **completo** em `stdout` (exit `0`, nenhum arquivo é criado).
`--now` sobrescreve o instante de geração (para testes determinísticos); default = relógio do sistema em UTC.
`--json` **não é permitido** com `report` ⇒ exit `1`.

### 3.3 Códigos de saída

| código | condição |
|---|---|
| `0` | sucesso (inclui arquivo vazio e inclui linhas inválidas quando entrada não falha completamente) |
| `1` | erro de uso: subcomando desconhecido, flag desconhecida, valor inválido, flag obrigatória ausente, `--json` com `report` |
| `2` | erro de I/O: `FILE` inexistente/ilegível, `--out` não gravável, schema não encontrado |
| `3` | validação falhou: ≥ 1 linha inválida com schema **e** entrada contém ≥ 1 linha não vazia |
| `4` | erro interno inesperado (nunca deve ocorrer em uso normal; mensagem em `stderr`) |

Regras:
- Entrada com **0 bytes** ou só whitespace ⇒ `lines_total = 0`, exit `0` (não é caso de exit `3`).
- Mistura de linhas válidas e inválidas ⇒ exit `0` (sem `--strict`).
- Em qualquer execução: mensagens de erro vão para `stderr`; dados vão para `stdout`.

### 3.4 Formatação de saída

- `stdout` de dados: UTF-8, terminado por `\n`.
- Cor ANSI apenas se `stdout` for TTY **e** `NO_COLOR` não estiver definida **e** `--json` ausente. Em pipe/redirect: sem cor. Testes caixa-preta sempre capturam via pipe ⇒ sem cor.
- Modo `--json`: **uma única linha compacta** (sem indentação), sem espaços supérfluos, terminada por `\n`.
- Números de ponto flutuante: arredondamento *half-up* para 6 casas decimais no JSON; contagens como inteiros.
- Chaves de objeto JSON podem vir em qualquer ordem; testes devem comparar estrutura, não strings.

---

## 4. Formato CSV

### 4.1 Estrutura

- Primeira linha: header com nomes de coluna.
- Linhas subsequentes: dados.
- Delimitador: vírgula (`,`); valores com vírgula/aspas/newline são quoted com `"`.
- Encoding: UTF-8.
- Linhas vazias (contendo só whitespace após strip) são ignoradas e **não** contam como inválidas nem válidas.

### 4.2 Parsing

Regras:
1. Header deve ter ≥ 1 coluna.
2. Linhas com número de campos ≠ número de colunas no header: campos extras são ignorados; campos faltantes são preenchidos com `null`.
3. Valores entre aspas duplas são unquoted; `""` dentro de string quoted = `"` (escape padrão CSV).
4. Valores não-quoted: espaços à esquerda/direita são trimmed.
5. Valores literalmente vazios, ou iguais a `NA`, `N/A`, `null`, `NULL` (case-insensitive) após parsing ⇒ `null` interno.

### 4.3 Validade de linha

- Linha é válida se, após parsing, todos os campos requeridos (`required: true` no schema) são não-null e todos os campos presentes respeitam o tipo, pattern, min/max esperado no schema.
- Se campo no schema tem `nullable: false` e o valor é null ⇒ linha inválida.
- Se coluna no CSV não está no schema ⇒ ignorada (não invalidava linha).
- Se coluna no schema não está no CSV ⇒ campo é treated como null.

### 4.4 Linhas inválidas

- Nunca lançam exceção, nunca interrompem o processo.
- Contadas em `lines_invalid`.
- Em modo texto e se `lines_invalid > 0` e `--quiet` ausente, imprime em `stderr`:
  `warning: N invalid line(s) skipped`

---

## 5. Funcionalidades

### 5.1 `validate`

Testa conformidade do CSV contra o schema.

Calcula:
- `lines_total`: número de linhas de dados (excl. header, excl. linhas em branco).
- `lines_valid`: linhas que passaram na validação.
- `lines_invalid`: linhas que falharam.
- `errors`: lista detalhada de erros, uma entrada por erro encontrado (pode haver múltiplos por linha).

Cada erro contém:
- `row`: número da linha (1-indexed, header = 1, primeira linha de dados = 2).
- `column`: nome da coluna.
- `value`: valor bruto da célula.
- `expected_type`: tipo esperado (ex. `integer`).
- `error`: mensagem descritiva (ex. `invalid integer format`, `required field is null`, `value 999 exceeds max 150`).

Saída JSON:
```json
{
  "version": "0.1",
  "command": "validate",
  "input": {
    "source": "file",
    "path": "data.csv",
    "format": "csv",
    "lines_total": 10,
    "lines_valid": 9,
    "lines_invalid": 1
  },
  "errors": [
    {
      "row": 5,
      "column": "age",
      "value": "xyz",
      "expected_type": "integer",
      "error": "invalid integer format"
    }
  ]
}
```

### 5.2 `analyze`

Calcula métricas de qualidade por coluna.

**Métricas por coluna:**

Para todas as colunas:
- `count`: número de valores não-null.
- `null_rate`: percentagem de valores null, `0.0` a `100.0`.
- `distinct_count`: número de valores únicos (entre não-null).

Para colunas numéricas (`integer`, `float`):
- `min`, `max`: extremos.
- `mean`: média aritmética.
- `stddev`: desvio-padrão populacional (dividir por `n`).
- `q1`, `q2`, `q3`: quartis pelo método nearest-rank.
- `iqr`: `q3 - q1`.
- `outlier_count`: número de valores detectados como outliers.

**Cálculo de quartis (nearest-rank, 1-indexed):**

Ordenar valores numéricos não-null ascendentemente. Seja `n = count`.
```
q1_index = min(n, max(1, ceil(0.25 * (n + 1))))
q3_index = min(n, max(1, ceil(0.75 * (n + 1))))
q1 = sorted[q1_index - 1]  (converte para 0-indexed)
q3 = sorted[q3_index - 1]
q2 = median (média dos dois valores centrais quando n é par)
iqr = q3 - q1
```

**Detecção de outliers:**

Com `k = --outlier-threshold` (default `1.5`):
```
é_outlier = valor < (q1 - k * iqr) OU valor > (q3 + k * iqr)
```

Se `iqr == 0`, nenhum valor é outlier (mesmo com `k = 0`).

**Comparação com baseline:**

Se `--baseline` fornecido (arquivo JSON com métricas esperadas por coluna):
- `expected_null_rate`, `actual_null_rate`, `diff_null_rate` (actual - expected).
- `expected_outlier_count`, `actual_outlier_count`, `diff_outlier_count`.
- Se campo esperado não existe no baseline ou na análise real, comparação é `null`.

Saída JSON:
```json
{
  "version": "0.1",
  "command": "analyze",
  "input": {
    "source": "file",
    "path": "data.csv",
    "format": "csv",
    "lines_total": 10,
    "lines_valid": 10,
    "lines_invalid": 0
  },
  "outlier_threshold": 1.5,
  "columns": [
    {
      "name": "user_id",
      "type": "integer",
      "count": 10,
      "null_rate": 0.0,
      "distinct_count": 10,
      "min": 1.0,
      "max": 1000.0,
      "mean": 500.5,
      "stddev": 289.165126,
      "q1": 250.75,
      "q2": 500.5,
      "q3": 750.25,
      "iqr": 499.5,
      "outlier_count": 1,
      "baseline_comparison": null
    },
    {
      "name": "email",
      "type": "string",
      "count": 10,
      "null_rate": 0.0,
      "distinct_count": 10,
      "baseline_comparison": null
    }
  ],
  "baseline_path": null
}
```

### 5.3 `report`

Gera Markdown com análise de qualidade:

```markdown
# Data Quality Report

- Input: `data.csv`
- Schema: `schema.json`
- Generated at: `2026-10-06T12:00:00Z`
- Lines: `10 valid, 0 invalid`

## Validation Summary
- **Total rows:** 10
- **Valid rows:** 10
- **Invalid rows:** 0

## Column Analysis

### user_id (integer)
- **Count:** 10
- **Null rate:** 0.00%
- **Distinct values:** 10
- **Min:** 1.00, **Max:** 1000.00, **Mean:** 500.50
- **Q1:** 250.75, **Median:** 500.50, **Q3:** 750.25
- **IQR:** 499.50
- **Outliers detected:** 1

### email (string)
- **Count:** 10
- **Null rate:** 0.00%
- **Distinct values:** 10

## Baseline Comparison

(only if --baseline provided)

| Column | Expected Null Rate | Actual Null Rate | Difference |
|---|---|---|---|
| user_id | 0.00% | 0.00% | 0.00% |

```

Regras:
- Tabelas Markdown com cabeçalho e separador `|---|`.
- `--now` fixa o `Generated at` (testes determinísticos). Sem `--now`, usa o relógio do sistema em UTC.
- Se `--out` não for gravável ⇒ exit `2`, nada é escrito.
- Se `--baseline` fornecido, seção "Baseline Comparison" é incluída com tabela.
- Escrita atômica recomendada (arquivo temporário + rename); não é requisito testável. Único efeito observável exigido: após a execução, o diretório de destino contém apenas o arquivo `--out` (nenhum temporário remanescente).

---

## 6. Esquema JSON exato

Todo objeto JSON emitido tem `"version": "0.1"` e `"command"` iguais ao subcomando.

**`validate`:**
```json
{
  "version": "0.1",
  "command": "validate",
  "input": {
    "source": "file",
    "path": "tests/fixtures/ac1.csv",
    "format": "csv",
    "lines_total": 3,
    "lines_valid": 3,
    "lines_invalid": 0
  },
  "errors": []
}
```
- `input.source`: `"file"` ou `"stdin"`. `input.path`: o argumento `FILE` **literalmente como passado** (caminho absoluto permanece absoluto, relativo permanece relativo); `null` quando `source == "stdin"`.
- `errors`: lista vazia se nenhum erro.

**`analyze`:**
```json
{
  "version": "0.1",
  "command": "analyze",
  "input": {
    "source": "file",
    "path": "tests/fixtures/ac1.csv",
    "format": "csv",
    "lines_total": 3,
    "lines_valid": 3,
    "lines_invalid": 0
  },
  "outlier_threshold": 1.5,
  "columns": [
    {
      "name": "user_id",
      "type": "integer",
      "count": 3,
      "null_rate": 0.0,
      "distinct_count": 3,
      "min": 1.0,
      "max": 3.0,
      "mean": 2.0,
      "stddev": 0.816497,
      "q1": 1.0,
      "q2": 2.0,
      "q3": 3.0,
      "iqr": 2.0,
      "outlier_count": 0,
      "baseline_comparison": null
    },
    {
      "name": "email",
      "type": "string",
      "count": 3,
      "null_rate": 0.0,
      "distinct_count": 3,
      "baseline_comparison": null
    },
    {
      "name": "age",
      "type": "integer",
      "count": 2,
      "null_rate": 33.333333,
      "distinct_count": 2,
      "min": 25.0,
      "max": 30.0,
      "mean": 27.5,
      "stddev": 2.5,
      "q1": 25.0,
      "q2": 27.5,
      "q3": 30.0,
      "iqr": 5.0,
      "outlier_count": 0,
      "baseline_comparison": null
    }
  ],
  "baseline_path": null
}
```

**`input` (objeto comum):** `source`, `path`, `format`, `lines_total`, `lines_valid`, `lines_invalid`.

---

## 7. Saída em modo texto (sem `--json`)

Blocos separados por `\n`, indentação de 2 espaços em seções aninhadas.

**`validate`:**
```
total_lines: 3
valid_lines: 3
invalid_lines: 0

errors: none
```

Se houver erros:
```
errors:
  row 5, column age: invalid integer format (value: "xyz")
```

**`analyze`:**
```
format: csv
lines_total: 3
lines_valid: 3
lines_invalid: 0

column: user_id
  type: integer
  count: 3
  null_rate: 0.00%
  distinct_count: 3
  min: 1.00
  max: 3.00
  mean: 2.00
  stddev: 0.81
  q1: 1.50
  q2: 2.00
  q3: 2.50
  iqr: 1.00
  outlier_count: 0

column: email
  type: string
  count: 3
  null_rate: 0.00%
  distinct_count: 3
```

Casas decimais no modo texto:
- `null_rate`, `min`, `max`, `mean`, `q1`, `q2`, `q3`, `iqr` com **2 casas**.
- `stddev` com **2 casas**.
- Contagens como inteiros.

---

## 8. Casos de borda (numerados)

1. **Arquivo vazio (0 bytes) ou apenas header.** `lines_total = 0`, `lines_valid = 0`, `lines_invalid = 0`, `columns = []`, exit `0`.
2. **Apenas linhas em branco.** Igual ao caso 1; linhas em branco não contam.
3. **Todas as linhas inválidas.** `lines_valid = 0`, `lines_invalid > 0`, exit `3`.
4. **Mistura válidas + inválidas.** Exit `0`; contadores exatos.
5. **Coluna no CSV não no schema.** Ignorada silenciosamente; não invalida linha.
6. **Coluna no schema não no CSV.** Treated como null em todas as linhas; `null_rate = 100.0`.
7. **All nulls em coluna.** `null_rate = 100.0`, `count = 0`, métrica numérica (min/max/mean/q1/q2/q3/stddev/iqr) = `null`.
8. **Sem valor numérico em coluna (all nulls ou tipo string).** `min`, `max`, `mean`, `stddev`, `q1`, `q2`, `q3`, `iqr`, `outlier_count` = `null`.
9. **IQR = 0.** Nenhum valor é outlier, mesmo com `--outlier-threshold 0`.
10. **Schema não encontrado.** Exit `2`, erro em stderr, nada em stdout.
11. **CSV com valores quoted contendo `<script>` ou `&`.** Parseado normalmente; em Markdown, escapado (`&lt;`, `&amp;`).
12. **Baseline com estrutura diferente.** Campo de comparação = `null`; não invalida análise.
13. **Pattern regex no schema não faz match.** Linha inválida.
14. **Valor numérico fora de `min`/`max` no schema.** Linha inválida.
15. **Campo `required: true` com valor null.** Linha inválida.
16. **Campo `nullable: false` com valor null.** Linha inválida.
17. **Valores duplicados em coluna.** `distinct_count < count`; não é erro.
18. **CSV com CRLF (`\r\n`).** Parseado normalmente (biblioteca padrão cuida).

---

## 9. Critérios de aceite (AC)

Fixtures referenciadas ficam em `tests/fixtures/`. Comparações de float em JSON usam tolerância `1e-6`. Comparações de texto são exatas (após normalizar espaçamento).

---

### AC-1 — `validate --json` com CSV simples

**Entrada** `tests/fixtures/ac1.csv`:
```csv
user_id,email,age
1,alice@example.com,30
2,bob@example.com,25
3,charlie@example.com,
```

**Schema** `tests/fixtures/ac1_schema.json`:
```json
{
  "columns": [
    {"name": "user_id", "type": "integer", "required": true, "nullable": false},
    {"name": "email", "type": "string", "required": true, "nullable": false},
    {"name": "age", "type": "integer", "required": false, "nullable": true}
  ]
}
```

**Comando:** `./app validate --schema tests/fixtures/ac1_schema.json --json tests/fixtures/ac1.csv`

**Esperado:** exit `0`; JSON com `lines_valid = 3`, `lines_invalid = 0`, `errors = []`.

---

### AC-2 — Detecção de outliers por IQR

**Entrada** `tests/fixtures/ac2.csv`:
```csv
value
1
2
3
4
5
6
7
8
9
100
```

**Schema:** coluna `value` tipo `integer`, não-requerida.

**Comando:** `./app analyze --schema schema.json --outlier-threshold 1.5 --json tests/fixtures/ac2.csv`

**Esperado:** `count = 10`, `q1 = 3`, `q3 = 9`, `iqr = 6`.
Outlier: `100 > 9 + 1.5*6 = 18` ⇒ `outlier_count = 1`.

---

### AC-3 — Null rate em coluna

**Entrada:** 5 linhas, coluna `age` com 3 valores e 2 nulls.

**Esperado:** `count = 3`, `null_rate = 40.0`.

---

### AC-4 — Baseline comparison

**Entrada:** dados e baseline JSON com `expected_null_rate`, `expected_outlier_count`.

**Comando:** `./app analyze --schema schema.json --baseline baseline.json --json data.csv`

**Esperado:** cada coluna em `analyze` contém `baseline_comparison` com `expected_*`, `actual_*`, `diff_*`.

---

### AC-5 — Linhas inválidas não derrubam programa

**Entrada:** 3 linhas válidas, 2 inválidas (status fora de range, tipo errado).

**Comando:** `./app validate --schema schema.json --json data.csv`

**Esperado:** exit `0`, `lines_valid = 3`, `lines_invalid = 2`, `errors` lista os 2 erros, aviso em stderr.

---

### AC-6 — Validação falha com `--strict`

**Comando:** `./app validate --strict --schema schema.json data.csv` (com dados inválidos)

**Esperado:** exit `3`, `lines_invalid > 0`.

---

### AC-7 — Arquivo vazio

**Comando:** `printf '' | ./app validate --schema schema.json --json`

**Esperado:** exit `0`, `lines_total = 0`, `lines_valid = 0`, `columns = []`.

---

### AC-8 — CSV com aspas e delimitadores

**Entrada:**
```csv
text
"hello, world"
"quote ""inside"""
```

**Esperado:** valores parseados como `hello, world` e `quote "inside"` (sem aspas externas).

---

### AC-9 — HTML escape em report

**Entrada:** coluna com valores `<script>`, `&`, `"`.

**Comando:** `./app report --schema schema.json --out out.md data.csv`

**Esperado:** no Markdown, valores listados com escape: `&lt;script&gt;`, `&amp;`, `&quot;`.

---

### AC-10 — `--now` determinístico em report

**Comando:** `./app report --schema schema.json --out out.md --now 2026-10-06T12:00:00Z data.csv`

**Esperado:** exit `0`, `out.md` contém `Generated at: 2026-10-06T12:00:00Z`.

---

### AC-11 — Schema obrigatório

**Comando:** `./app validate data.csv` (sem `--schema`)

**Esperado:** exit `1`, erro em stderr.

---

### AC-12 — Schema não encontrado

**Comando:** `./app validate --schema /not/found.json data.csv`

**Esperado:** exit `2`, erro em stderr.

---

### AC-13 — Coluna no schema não no CSV

**Entrada:** schema com coluna `email`, CSV só tem `user_id`.

**Comando:** `./app analyze --schema schema.json --json data.csv`

**Esperado:** análise inclui `email` com `count = 0`, `null_rate = 100.0`.

---

### AC-14 — `--report` com `--json` é erro

**Comando:** `./app report --schema schema.json --out x.md --json data.csv`

**Esperado:** exit `1`, erro em stderr.

---

### AC-15 — Distintos valores e distribuição

**Entrada:** 5 valores, 3 distintos (ex. `[1, 1, 2, 3, 3]`).

**Esperado:** `count = 5`, `distinct_count = 3`.

---

## 10. Requisitos de portfólio

### 10.1 README (em inglês)

`README.md` deve conter, nesta ordem:

1. Título `# Data Quality Monitor` + one-line pitch.
2. Diagrama Mermaid (fluxo de processamento ou arquitetura).
3. `## Install` (clone + `./app --version`, sem dependências obrigatórias de build quando possível).
4. `## Usage` com todos os subcomandos e **saída real colada** (não inventada), incluindo pelo menos um exemplo `--json`.
5. `## Schema format` com documentação completa (tipos, campos, validação).
6. `## Quality metrics` com explicações:
   - **Null rate:** percentagem de valores null.
   - **IQR (Interquartile Range):** Q3 - Q1, método nearest-rank explícito.
   - **Outliers:** fórmula e detecção por `--outlier-threshold`.
7. `## CSV input` com exemplo e regras de parsing.
8. `## Baseline format** com estrutura JSON esperada.
9. `## Exit codes` (tabela da seção 3.3).
10. `## How this was built` — narrativa honesta: o agente de IA implementou; os testes caixa-preta foram escritos por outro agente de IA, independente do implementador; como a spec foi usada como contrato; o que o agente errou na primeira rodada e como os testes pegaram.
11. `## Testing` (como rodar os testes caixa-preta).
12. `## License`.

### 10.2 Testes públicos

- Diretório `tests/blackbox/`, executados com `make test`.
- Os testes **não importam** módulos internos: invocam `./app` via subprocesso (`subprocess.run`/equivalente), com `stdin`/`stdout`/`stderr` capturados.
- Table-driven, um arquivo por subcomando, fixtures em `tests/fixtures/`.
- Cada AC da seção 9 mapeia para, no mínimo, um teste nomeado `test_ac_<n>_...`.
- Determinismo: nenhum teste depende de relógio do sistema (usa `--now`) nem de cor (pipe ⇒ sem cor).

### 10.3 CI

GitHub Actions, workflow `.github/workflows/ci.yml`, disparado em `push` e `pull_request`, matriz Linux + macOS, passos:
1. checkout; 2. instalar runtime; 3. `make lint`; 4. `make test`; 5. `make smoke` (roda `./app validate --schema tests/fixtures/ac1_schema.json --json tests/fixtures/ac1.csv` e valida o JSON).

### 10.4 Lint

- `make lint` executa o linter do runtime escolhido (ex. `ruff`, `shellcheck`), com configuração versionada.
- `make fmt` aplica formatação automática.
- Lint deve passar sem warnings no código entregue.

### 10.5 Licença e release

- `LICENSE` com texto MIT completo, ano `2026`.
- `CHANGELOG.md` no formato Keep a Changelog, com entrada `## [0.1.0] - 2026-10-06`.
- Tag git `v0.1.0` e GitHub Release `v0.1.0` com notas derivadas do changelog.
- `./app --version` imprime exatamente `data-quality-monitor 0.1.0`.

---

## 11. Estrutura de repositório

```
.
├── app                     # executável (binário ou wrapper)
├── src/                    # código-fonte do runtime escolhido
├── tests/
│   ├── blackbox/           # testes caixa-preta (subprocess)
│   └── fixtures/           # CSVs, schemas, baselines
├── demo/
│   └── demo.tape           # script vhs (opcional)
├── docs/
│   └── demo.gif            # (opcional)
├── .github/workflows/ci.yml
├── Makefile                # targets: run, lint, fmt, test, smoke, release
├── README.md
├── CHANGELOG.md
├── LICENSE
└── SPEC.md                 # este documento
```

---

## 12. Definições e convenções

- **linha vazia:** após `strip()`, string de comprimento zero. Ignorada, não contada em nenhum contador.
- **linha inválida:** linha não vazia que não passou na validação contra o schema.
- **null_rate:** `(null_count / lines_total) * 100`, em percentagem, 0–100.
- **IQR (Interquartile Range):** `q3 - q1`.
- **outlier (por IQR):** valor `< q1 - k·iqr` ou `> q3 + k·iqr`, onde `k = --outlier-threshold`.
- **quartis:** método nearest-rank, 1-indexed: `q_index = ceil(percentil/100 * (n + 1))`, depois converte para 0-indexed.
- **baseline:** JSON com métricas esperadas (null_rate, outlier_count, etc) por coluna. Opcional; se ausente, `baseline_path = null` e `baseline_comparison = null`.
- **HTML escape:** `&`, `<`, `>`, `"`, `'` escapados em Markdown quando apresentados em inline code ou texto.
- **arredondamento:** half-up, 2 casas decimais em modo texto, 6 em JSON; aplicado somente na serialização.
- **tolerância de comparação numérica nos testes:** `1e-6`.

---

## 13. Esclarecimentos v0.1.1

Revisão que elimina ambiguidades apontadas pelos testes caixa-preta independentes.

1. `--help` pode imprimir a ajuda em `stdout` **ou** `stderr` (implementação escolhe); exit `0` inalterado.
2. `--out -` no `report` grava o Markdown completo em `stdout`, exit `0`, sem criar arquivo.
3. Schema é **obrigatório** em todos os subcomandos.
4. `--format` em v0.1 suporta apenas `csv`; outro valor ⇒ exit `1`.
5. Baseline é opcional; se ausente, campos de comparação = `null`.
6. `--quiet` suprime aviso de linhas inválidas em `stderr`.
7. `--outlier-threshold` é float ≥ 0; default `1.5`.
8. Linhas em branco não contam em `lines_total` nem invalidam dado.
9. Pattern regex no schema: validação literal (ex. `^[^@]+@[^@]+$` para email); falha ⇒ linha inválida.
10. `input.path` ecoa o argumento `FILE` **literalmente** (absoluto permanece absoluto; relativo permanece relativo); `null` só em `stdin`.

---

## Apêndice — Contrato de entrega v0.1.2

Vale para todos os casos do lote e prevalece sobre qualquer trecho acima em caso de conflito.

1. **Divulgação honesta (README › How this was built).** A spec foi escrita primeiro. A implementação foi feita por um agente de IA autônomo de um harness interno (sem edição humana do código). Os testes caixa-preta de aceite foram escritos por **outro agente de IA, independente do implementador**, a partir só da spec; ficam fora deste repositório e são rodados pelo harness. Não afirmar que foram escritos por uma pessoa.

2. **Diagrama.** O README tem pelo menos um bloco ```mermaid com a arquitetura ou o fluxo principal.

3. **Dependências.** Se o projeto precisar de pacotes de terceiros, a raiz tem um executável `./setup` (shebang, idempotente) que os instala localmente (ex.: `.venv` ou `node_modules`). O avaliador o roda **uma vez** antes dos testes, sem segredos no ambiente e com rede só para pypi.org/files.pythonhosted.org/registry.npmjs.org. `./app` usa o que o `./setup` instalou. **Biblioteca padrão é preferível; sem dependências externas, não crie `./setup`.**

4. **Tag e Release.** A tag `v0.1.0` e o GitHub Release são criados pelo mantenedor **depois do merge**. O PR não cria tag.

5. **GIF de terminal.** O GIF (vhs) é opcional nesta versão: se a ferramenta não estiver disponível no ambiente, deixe o `.tape` versionado e não bloqueie a entrega.
