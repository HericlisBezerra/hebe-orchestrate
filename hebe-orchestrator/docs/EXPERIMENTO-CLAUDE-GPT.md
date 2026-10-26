# Experimento `for-claude+gpt` — Claude coordena, Codex soma

**Branch:** `for-claude+gpt` (não é a `main`). **Início:** 2026-10-26. **Duração prevista:** 15 a 30 dias de uso real.

## A pergunta

Dá para tirar mais qualidade e mais eficiência das duas assinaturas (Claude e Codex), usando só a interface do Claude, **sem trocar quem faz cada coisa por palpite**?

O Claude continua coordenando: plano, costura, decisões, testes e commit. O Codex entra por `scripts/codex_bridge.py` em dois papéis:

| Papel | Quando | Modelo |
|---|---|---|
| Segunda lente de revisão (outro fornecedor) | Toda revisão que o `@reviewer` faria | GPT-6.1 Sol |
| Construtor | Frente grande, especificada, com testes, sem decisão de produto aberta, enquanto o Claude faz outra frente | GPT-6 Astra em `high` (Sol em `high` como comparação) |

Também nesta branch: o Fable fica desativado (decisão do usuário), e `@design-worker` e `@reviewer` rodam em Opus 5.5.

## O que o piloto mostrou

Código real de um serviço de um cliente. Detalhes do cliente e do serviço ficam fora deste repositório público.

### Revisão (3 rodadas, mesmo estado do código para todos)

| | Opus 5.5 (revisão original) | GPT-6.1 Sol | GPT-6 Astra |
|---|---|---|---|
| Itens achados (gabarito = achados do Opus corrigidos depois) | 34 | ~5,5 (~16%) | ~5,5 (~16%) |
| Alarmes falsos | — | 0 | 0 |
| Problemas reais que o Opus daquela rodada não achou | — | 6 (2 antecipados, 3 ainda abertos) | 5 |
| Tokens do Claude por revisão | 6,6–17,6 M de cache + 131–203 mil de saída | ~1 mil (leitura do JSON) | ~1 mil |

Leitura: o Codex não substitui a revisão do Opus. Ela cobre operação, configuração, observabilidade e protocolo, e rodou sondas e testes. O Codex é um complemento barato para o Claude, com acerto alto, e vê outra classe de defeito: fluxo de dados, ordem de gravação, garantias de apagamento.

### Construção (mesmo pedido: corrigir os 7 achados de uma revisão)

| | Opus 5.5 | Astra `high` | Sol `high` | Astra `medium` | Sol `medium` |
|---|---|---|---|---|---|
| Tempo | 14 min | 10 min | 16,5 min | 7 min | 9 min |
| Tokens do Claude | 15,3 M de cache + 148 mil de saída | ~1 mil | ~1 mil | ~1 mil | ~1 mil |
| Suíte original e carga | passa | passa | passa | passa | passa |
| Defeitos reais (avaliação cega) | — | 0 | 0 | 0 | 0 |
| Nota de qualidade (avaliação cega, 1–10) | **7** | **6,5** | 6 | 5 | 5 |
| Problemas de escopo | afirmação não verificável sobre staging | funcionalidade desligada por variável, contrato alterado, ADR e notas | funcionalidade desligada por variável, contrato alterado, dependência nova, notas | funcionalidade desligada fixa no código, contrato alterado, logs de teste versionados, notas | funcionalidade desligada fixa no código, contrato alterado, notas |
| Commits | 6 | 0 (o `.git` ficou bloqueado no sandbox) | 0 | 0 | 0 |

Leitura: o Codex constrói com correção comparável e mais rápido (o Astra `high` ficou meio ponto abaixo do Opus em 10 min), por uma fração da cota do Claude. Mas as quatro versões do Codex tomaram as mesmas decisões de produto e de escopo que ninguém pediu. Daí as regras: pedido fechado, proibições explícitas no pedido, checagem automática de escopo, `high` como piso, Astra como padrão de construção e revisão do Opus antes do commit.

### Limites do piloto

- Um só projeto e uma só tarefa de construção.
- O gabarito da revisão e os testes de aceitação foram escritos pelo próprio Claude, o que favorece a interface dele.
- O Codex só leu o código: sem dependências instaladas, não rodou testes na revisão.
- O consumo de cota do Codex não foi medido, porque o plugin não informa.
- Não verificado: o que `approvalPolicy: never` faz com chamadas MCP no Codex 0.164. O isolamento contorna a questão, porque o Codex da ponte não tem MCP.

## Hipóteses deste experimento

| # | Hipótese | Métrica (`codex_bridge.py report`) | Mantém se… |
|---|---|---|---|
| H1 | A revisão do Codex acha problema real que o Opus não achou | `outcome` de revisão com `--real` > 0 em achados fora da lista do `@reviewer` | ≥ 1 em cada 3 revisões relevantes |
| H2 | A revisão do Codex quase não gera ruído | `precision` das revisões | ≥ 0,8 |
| H3 | A construção do Codex é aproveitada | `outcomes` de construção: `accepted` + `reworked` leve | ≥ 60% sem refazer do zero |
| H4 | A construção do Codex poupa a cota do Claude | `avg_claude_tokens_est` da construção contra uma frente parecida feita no Claude | < 10% do equivalente no Claude |
| H5 | As regras de escopo seguram o Codex | `avg_scope_flags` | ≤ 1 por construção |
| H6 | O ganho não custa tempo de parede | `avg_minutes` com o Claude fazendo outra frente em paralelo | a entrega total não fica mais lenta |
| H7 | Astra `high` constrói melhor que Sol `high` | desfechos de `build` por modelo (rode o Sol de vez em quando) | Astra com mais `accepted` e menos `scope_flags` |

## Antes do primeiro uso

1. `python3 scripts/codex_bridge.py doctor` — confere o plugin `openai-codex` (validado na 1.0.6), o Codex isolado e a política.
2. Faça o login **isolado** uma vez (é separado do seu Codex principal; nenhum token é compartilhado):

```bash
CODEX_HOME=~/.cache/hebe-orchestrator/codex-home codex login
```

3. Rode `doctor` de novo: `isolated_login: true` e nenhum servidor MCP listado.

O Codex da ponte roda sem conectores MCP, sem plugins, sem memória, sem AGENTS.md global e com a sandbox sem rede. A ponte sobe um app-server próprio por chamada, com ambiente mínimo, e em timeout ou interrupção encerra só o grupo de processos daquela chamada.

## Como registrar no dia a dia

Cada `review` e cada `build` grava uma linha em `~/.config/hebe-brain/codex-experiment.jsonl` (privado, modo 0600). Ela tem modelo, esforço, duração, tamanho do que voltou para o Claude e `scope_flags`, e nunca o texto do pedido nem a resposta. Depois de adjudicar ou integrar, o orquestrador registra o desfecho:

```bash
python3 scripts/codex_bridge.py outcome --id <ledger_id> --result confirmed --real 2 --false 0 --missed 1 --reviewer opus
python3 scripts/codex_bridge.py outcome --id <ledger_id> --result accepted --reviewer opus --note "1 scope_flag revertida"
```

Em `review`, o `--result` aceita `confirmed`, `mixed` ou `noise`. Em `build`, aceita `accepted`, `reworked` ou `rejected`.

## Pontos de controle

- **Dia 7:** `python3 scripts/codex_bridge.py report --days 7`. Verifique se os desfechos estão sendo registrados. Sem `outcome`, não há dado de qualidade.
- **Dia 15:** primeira decisão. Se H2 ou H5 falharem com folga, ajuste as regras: o foco da revisão, as proibições do pedido ou o critério de quando delegar.
- **Dia 30:** decisão final, uma de três:
  - levar à `main`;
  - manter só a revisão cruzada;
  - encerrar o experimento.

## Como sair do experimento

Volte o repositório local do marketplace para a `main` e atualize o plugin:

```bash
git -C <pasta local do marketplace hebe-orchestrator> switch main
```

```bash
claude plugin update hebe-orchestrator@hebe-orchestrator
```

O diário fica em `~/.config/hebe-brain/` para consulta.
