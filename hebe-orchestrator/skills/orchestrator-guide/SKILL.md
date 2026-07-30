---
name: orchestrator-guide
description: Doutrina de orquestração multi-modelo qualidade-primeiro no Claude Code — colocar cada tarefa no modelo CERTO pela natureza dela (mecânico→Haiku 4.5, código→Sonnet 5, design e revisão→Fable 5, decisão difícil→Opus 5), economizando só onde isso não custa qualidade, e revisando o output barato antes de confiar. Invoque ao planejar uma tarefa longa/composta.
disable-model-invocation: true
---

# Orquestração multi-modelo — doutrina qualidade-primeiro

**Objetivo:** a MELHOR qualidade possível em cada peça da tarefa, gastando o mínimo que essa qualidade permite. Economia vem de **não desperdiçar o modelo topo em trabalho genuinamente mecânico** — NUNCA de rebaixar trabalho que exige julgamento. Cada tarefa no modelo certo; cada token no contexto certo.

> Erro clássico a evitar: tratar "barato" como objetivo e jogar leitura/análise/auditoria de código no Haiku. Isso não é economia — é rebaixar julgamento. Código é piso Sonnet, sempre.

## Como escolher o modelo (pela natureza da tarefa, não pelo preço)

| Natureza da tarefa | Agente | Modelo |
|---|---|---|
| Mecânico puro, zero julgamento — grep, renomear, edição já ditada, mover, rodar comando/checagem | `@worker` | Haiku 4.5 |
| **Implementação especificada + análise de código** — construir do plano, ler, mapear, refatorar, testar, fan-out paralelo | `@code-worker` | Sonnet 5 |
| **Desenvolvimento complexo/novo** — lógica não-trivial, correção sutil, código guiado por raciocínio | sessão principal | Opus 5 |
| **Design/frontend** — design system, protótipo, UI/UX, layout, identidade, copy, implementação visual | `@design-worker` | Fable 5 |
| **Revisar criticamente** — code review, caçar falhas de segurança, crítica de frontend/UX | `@reviewer` | Fable 5 |
| Decisão difícil, arquitetura, trade-off, veredito final de alto risco | `@advisor` | Opus 5 |
| Planejamento de alto nível, costura entre peças, revisão final | sessão principal | Opus 5 |

> **Dois eixos dentro de código:**
> **(1) Especificado vs. complexo** — implementação já decidida, rotina e peças paralelas → `@code-worker` (Sonnet 5), onde ele é rápido e confiável. Desenvolvimento complexo/novo, correção sutil, código que o raciocínio guia → **Opus 5, na sua sessão principal** (é lá que você desenvolve; o orquestrador offloada o resto pra baixo). Acertar de primeira no complexo vale mais que o token economizado.
> **(2) Construir vs. revisar** — `@code-worker` (Sonnet 5) *escreve e entende*; `@reviewer` (Fable 5) *avalia criticamente e caça falhas*. Um constrói, o outro procura defeito.

**Regras que não se quebram:**
- **Código nunca vai pra Haiku.** Entender, avaliar ou escrever código exige julgamento de engenharia → piso Sonnet. Haiku só faz o braçal mecânico sem decisão.
- **Código tem dois níveis, não um.** Rotina/especificado/paralelo → Sonnet; complexo/novo/correção sutil → Opus (sua sessão). Rebaixar dev complexo pra Sonnet custa iteração e bug; subir boilerplate pra Opus é o "Opus pra tudo" que você quer evitar. Os dois erros custam — acerte pela natureza, não pelo preço.
- **Fable cobre design E revisão crítica.** Esse núcleo (criativo + caça a falhas) não desce pra Haiku/Sonnet. Sem Fable, sobe pra Opus — ver o protocolo abaixo.

## ⚠️ Fallback do Fable (crédito semanal esgotado)

**Não existe fallback automático** — o campo `model` aceita um valor só, e o Claude Code não tem "modelo reserva". Quando o crédito do Fable acaba, a invocação de `@design-worker`/`@reviewer` **falha**. Cabe a você, orquestrador, tratar:

1. **Detecte** o erro de invocação (indisponibilidade / cota / crédito).
2. **Reinvoque o MESMO agente com override de modelo `opus`** — o parâmetro `model` da invocação tem precedência sobre o frontmatter. Isso preserva o prompt especializado (o olhar de design/revisão) e só troca o motor.
   *Prefira isso a redirecionar pro `@advisor`*: o advisor é consultor de arquitetura, não designer nem revisor — trocar de agente troca a personalidade junto.
3. **AVISE o usuário, sempre, numa linha:** `⚠️ Fable indisponível (crédito) → rodei @design-worker em Opus 5.` Fallback silencioso é pior que o problema: ele mascara uma queda de qualidade/custo que o usuário precisa saber.
4. Se o Opus também falhar, **pare e reporte** — não desça pra Sonnet/Haiku no núcleo criativo/crítico.

> O crédito do Fable é **semanal**. Se você bater no limite cedo na semana, vale avisar o usuário pra ele decidir se segura o trabalho de design até o reset ou toca em Opus.
- **Segurança de alto risco não fecha num modelo só.** O `@reviewer` (Fable 5) ACHA as falhas; o veredito final é adjudicado pelo `@advisor` (Opus 5) ou pela skill `hebe-sec-audit`. Modelos diferentes pegam bugs diferentes — uma lente só perde coisa.
- **Na dúvida entre dois níveis, suba.** Entre Haiku e Sonnet → Sonnet. O custo de rebaixar (retrabalho, bug, design pobre) quase sempre supera a economia de tokens.
- **Escale em runtime, não só no plano.** Se o worker voltar incerto, se contradisser, ou se o erro for caro (segurança, dados, dinheiro), suba de tier em vez de aceitar o output. Classificar no início não te obriga a confiar no fim.

> **Effort é o segundo dial.** Antes de pular de modelo, considere subir o `effort` do agente (low→medium→high). Uma análise espinhosa às vezes se resolve com `@code-worker` em effort alto — mais barato que ir pra Opus, sem rebaixar qualidade. (O `@reviewer` já roda em effort alto por padrão: revisão rasa não vale nada.)

## Qualidade não acaba na delegação — revise e verifique

Delegar OFFLOADA o trabalho, não a responsabilidade. O output de `@worker`/`@code-worker` não é verdade até ser revisado — pelo `@reviewer`, por você, ou pelo `@advisor`.

- **Revise o construído antes de confiar**, com foco no que decide o resultado: correção, segurança, e todo fluxo de dinheiro/permissão. Concatenar 4 relatórios não é o mesmo que validá-los.
- **Segurança e lógica de negócio nunca fecham num modelo só.** O `@reviewer` (Fable 5) caça as falhas; o veredito de alto risco é adjudicado pelo `@advisor` (Opus 5). Auditoria de verdade: combine com a skill `hebe-sec-audit`.
- **O forte confirma nos pontos-chave** — é isso que separa "qualidade-primeiro" de "delegou e torceu".

## Os dois padrões de orquestração

**Padrão 1 — Planner + Workers (fan-out).** O modelo forte (sessão principal, ou `@advisor`) PLANEJA e quebra o trabalho; os workers (contexto isolado) EXECUTAM em paralelo, cada um no modelo certo pra sua peça — `@worker` pro mecânico, `@code-worker` pro código, `@design-worker` pro visual, `@reviewer` pra revisão/segurança. O ganho de custo vem de rodar o braçal mecânico em Haiku e o resto no nível adequado — não de forçar tudo pra baixo. Depois o forte revisa e costura (ver seção acima). Atalho do Claude Code: `/model opusplan` (forte no plano, Sonnet na execução).

**Padrão 2 — Executor + Advisor (on-demand).** A sessão principal roda num modelo intermediário (ex.: Sonnet) e toca cada rodada. Só chama `@advisor` (Opus 5) quando bate numa decisão difícil — tipicamente 1x por tarefa. O cache de cada agente evita pagar o mesmo contexto duas vezes em chamadas repetidas.

## Quando NÃO orquestrar

- **Tarefa pequena e única:** orquestrar tem overhead de contexto e latência (cada handoff custa). Rode direto no modelo adequado à natureza dela — e não a rebaixe só pra parecer barata.
- **Contexto muito interdependente e difícil de resumir num prompt:** subagent roda isolado e só recebe o que você passa; se o repasse for caro/frágil, faça na sessão principal.

## Higiene de contexto

- Subagents rodam em **contexto próprio**: delegar OFFLOADA tokens da sua conversa. Só o resumo final volta — logs e saída verborrágica ficam lá.
- Passe no prompt do subagent TUDO que ele precisa (caminhos, erros, decisão/entrega pedida). Ele não enxerga o histórico da conversa principal.
- A auto-delegação é irregular: se quiser garantir, invoque explícito com `@worker`, `@code-worker`, `@design-worker`, `@reviewer`, `@advisor`.

## Exemplo: auditar / entender um subsistema

**Errado (o anti-padrão):** 4 workers Haiku leem rotas, schema, RLS e "acham" os riscos em paralelo. Barato — e raso. Ler e avaliar código não é mecânico; Haiku entrega a superfície e perde o que mora nas bordas (autorização entre recursos, concorrência, lógica de negócio).

**Certo:** as leituras/mapeamentos rodam em `@code-worker` (Sonnet 5) em paralelo (rotas | camada de serviço | schema/RLS | metadados); a caça a falhas de segurança vai pro `@reviewer` (Fable 5), pensando como atacante. Você — ou `@advisor` (Opus 5) — sintetiza, deduplica e dá o **veredito** nos riscos críticos. Código nunca no Haiku; nenhuma falha de segurança fecha num modelo só. O braçal mecânico (grep de um padrão, extrair uma env var) esse sim vai pro `@worker`.

## Números de referência (benchmark da Anthropic, não garantia)

Planner forte + workers Sonnet ficou ~96% da performance do modelo topo por ~46% do preço num teste da Anthropic. No seu código real, VARIA por tarefa — meça com o seu uso antes de prometer número. E lembre: o alvo aqui é qualidade com economia, não o menor número possível.
