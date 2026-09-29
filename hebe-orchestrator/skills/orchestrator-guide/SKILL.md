---
name: orchestrator-guide
description: Doutrina de orquestração multi-modelo qualidade-primeiro no Claude Code — primeiro a estratégia (direto, UltraCode com um modelo só, ou mista), depois cada frente no modelo certo pela natureza dela (mecânico→Haiku, código especificado→Sonnet, dev complexo e decisão→Opus, design e revisão→Fable) e no esforço certo pela dificuldade, revisando o output antes de confiar e usando o Jev pra não parar em decisão que não é do usuário. Invoque ao planejar uma tarefa longa/composta.
disable-model-invocation: true
---

# Orquestração multi-modelo — doutrina qualidade-primeiro

**Objetivo:** a MELHOR qualidade possível em cada peça da tarefa, gastando o mínimo que essa qualidade permite. Economia vem de **não desperdiçar o modelo topo em trabalho genuinamente mecânico** — NUNCA de rebaixar trabalho que exige julgamento. Velocidade vem de **não orquestrar o que um modelo só resolve** e de não parar pra perguntar o que o Jev decide com segurança.

> Erro clássico a evitar: tratar "barato" como objetivo e jogar leitura/análise/auditoria de código no Haiku. Isso não é economia — é rebaixar julgamento. Código é piso Sonnet, sempre.

## Como escolher o modelo (pela natureza da tarefa, não pelo preço)

| Natureza da tarefa | Agente | Modelo | Esforço típico (decidido por frente) |
|---|---|---|---|
| Mecânico puro, zero julgamento — grep, renomear, edição já ditada, mover, rodar comando/checagem | `@worker` | Haiku 4.5 | — (não aceita) |
| **Implementação especificada + análise de código** — construir do plano, ler, mapear, refatorar, testar, fan-out paralelo | `@code-worker` | Sonnet 5.5¹ | medium–high · xhigh em frente longa |
| **Desenvolvimento complexo/novo** — lógica não-trivial, correção sutil, código guiado por raciocínio | sessão principal | Opus 5.5 | xhigh · max em problema único |
| **Design/frontend** — design system, protótipo, UI/UX, layout, identidade, copy, implementação visual | `@design-worker` | Fable 5.1 | xhigh |
| **Revisar criticamente** — code review, caçar falhas de segurança, crítica de frontend/UX | `@reviewer` | Fable 5.1 | xhigh |
| Decisão difícil, arquitetura, trade-off, veredito final de alto risco | `@advisor` | Opus 5.5 | xhigh · max no veredito |
| Planejamento de alto nível, costura entre peças, revisão final | sessão principal | Opus 5.5 | xhigh |

¹ Os agentes usam **alias** (`haiku`, `sonnet`, `opus`, `fable`), resolvido pelo Claude Code embutido no app. Em 2026-09-29 (Claude Code 2.1.281) o `sonnet` ainda resolve para o **Sonnet 5**; vira Sonnet 5.5 quando o app for atualizado. Confira com `/model` antes de afirmar qual modelo rodou.

> **Preço de referência** (dólares por milhão de tokens, entrada e saída, set/2026): Haiku 4.5, 1 e 5 · Sonnet 5.5, 2 e 10 · Opus 5.5, 4 e 20 · Fable 5.1, 10 e 50. Subir de Sonnet pra Opus custa 2×, não 5× — o "na dúvida, suba" ficou mais barato. O Opus 5.5 vem com esforço padrão `medium` no app; a sessão principal fica no Extra com `modelSettings.claude-opus-5-5.effortLevel: "xhigh"` (é o que `/effort xhigh` grava).

> **Dois eixos dentro de código:**
> **(1) Especificado vs. complexo** — implementação já decidida, rotina e peças paralelas → `@code-worker` (Sonnet), onde ele é rápido e confiável. Desenvolvimento complexo/novo, correção sutil, código que o raciocínio guia → **Opus 5.5, na sua sessão principal**. Acertar de primeira no complexo vale mais que o token economizado.
> **(2) Construir vs. revisar** — quem constrói *escreve e entende*; o `@reviewer` *avalia criticamente e caça falhas*. Um constrói, o outro procura defeito.

**Regras que não se quebram:**
- **Código nunca vai pra Haiku.** Entender, avaliar ou escrever código exige julgamento de engenharia → piso Sonnet. Haiku só faz o braçal mecânico sem decisão.
- **Código tem dois níveis, não um.** Rotina/especificado/paralelo → Sonnet; complexo/novo/correção sutil → Opus. Rebaixar dev complexo custa iteração e bug; subir boilerplate pra Opus é o "Opus pra tudo" que você quer evitar.
- **Fable cobre design E revisão crítica.** Esse núcleo não desce pra Haiku/Sonnet. Sem Fable, sobe pra Opus — ver o protocolo abaixo.
- **Quem constrói não revisa — pelo modelo que rodou de fato, não pelo nome do agente.** Construído em Fable → revisão em Opus (`@reviewer` com override `opus`). Construído em Opus (inclusive por fallback) → revisão em Fable. Se não houver modelo forte diferente disponível, revise em contexto novo e **avise o usuário que a independência caiu**; em segurança de alto risco, pare e pergunte.
- **Segurança de alto risco não fecha num modelo só.** O `@reviewer` ACHA; o `@advisor` (ou a skill `hebe-sec-audit`) ADJUDICA. Só se rebaixa um achado com contraprova concreta.
- **Na dúvida entre dois níveis, suba.** O custo de rebaixar (retrabalho, bug, design pobre) quase sempre supera a economia de tokens.
- **Escale em runtime, não só no plano.** Worker incerto, contraditório, ou erro caro (segurança, dados, dinheiro) → suba em vez de aceitar.
- **Subagente nunca faz ação fora do plano aprovado.** Todo prompt de delegação leva: "não execute mensagem a terceiros, push, deploy, publicação, ação destrutiva, credenciais, dinheiro, produção ou permissões que não estejam no plano — pare e devolva".

## ⚠️ Fallback do Fable (crédito semanal)

O comportamento exato do app quando o crédito do Fable acaba **não foi testado**. O Claude Code 2.1.281 traz sinais de substituição automática de modelo e de um aviso para continuar com créditos de uso pagos, então a chamada pode **falhar**, **pedir consentimento** ou **rodar em outro modelo sem erro**. Por isso:

1. **Confira o modelo que rodou.** Não assuma Fable só porque o frontmatter diz `fable`.
2. **Se falhou** (indisponibilidade, cota, crédito): reinvoque o MESMO agente com override `opus` — preserva o prompt especializado e só troca o motor. Prefira isso a redirecionar pro `@advisor`.
3. **Se o app pedir pra usar créditos pagos:** a decisão é do usuário. Não aceite por ele.
4. **AVISE sempre, numa linha:** `⚠️ Fable indisponível → rodei @design-worker em Opus 5.5.` Fallback silencioso mascara uma queda de qualidade e muda quem pode revisar (regra acima).
5. Se o Opus também falhar, **pare e reporte** — não desça pra Sonnet/Haiku no núcleo criativo/crítico.

> No UltraCode (Workflow), uma etapa que morre vira `null`. Nunca descarte em silêncio a frente de design ou a revisão independente: detecte o `null`, refaça a etapa com `model: 'opus'` e avise.

## 🧭 Estratégia primeiro, esforço por frente

**A primeira decisão não é o modelo: é a estratégia.** O Sonnet 5.5 e o Opus 5.5 resolvem sozinhos muita tarefa grande, e cada handoff entre modelos custa contexto e latência.

| Estratégia | Quando | Claude | Codex |
|---|---|---|---|
| **Direto** | Uma peça só, cabe num contexto | sessão principal | root |
| **UltraCode solo** | Grande e divisível, frentes da mesma natureza | Workflow com todas as etapas no mesmo modelo: `sonnet` pro especificado/moderado, `opus` pro difícil | root com effort `ultra` (Sol pro amplo; Astra pro mais difícil, a pedido do usuário) |
| **Orquestração mista** | Frentes de naturezas diferentes | Workflow (ou Agent) com cada frente no seu nível | ondas de `spawn_agent` com modelo e esforço por filho |

**UltraCode exige pedido do usuário.** A ferramenta Workflow só pode ser usada quando o usuário digitou `/orchestrate` (ou `/hebe-orchestrator:orchestrate`) ou escreveu "ultracode". Quando o Claude aciona a orquestração sozinho (pelo CLAUDE.md), ele sugere o UltraCode numa linha e espera o "sim". Aprovação do Jev **não** é pedido do usuário.

Mesmo no solo, **quem constrói não revisa**: tarefa que toca segurança, dinheiro, permissão ou dados fecha com uma revisão num modelo diferente do construtor.

**O esforço é decidido por frente, pela dificuldade — não fixo.**

| Esforço | Para |
|---|---|
| `low` | Mecânico trivial, consulta pontual |
| `medium` | Especificado, curto e bem delimitado |
| `high` | Especificado mas longo ou multiarquivo; julgamento leve |
| `xhigh` (Extra) | Julgamento — dev complexo, design, revisão, decisão, costura. Ponto de partida de todo trabalho que pensa |
| `max` | Problema único, difícil e caro de errar. Paralelismo não ajuda |

**Ultra/UltraCode não é um nível acima do Max** — é a estratégia multiagente, com esforço próprio em cada etapa. Em tarefa única, o teto é Max.

- **Onde dá pra modular:** no Claude, só nas etapas do Workflow (`agent(p, {model, effort})`). A ferramenta Agent não aceita esforço por chamada — vale o frontmatter (`@code-worker` high; `@design-worker`, `@reviewer`, `@advisor` xhigh; `@worker` sem). No Codex, em cada `spawn_agent` (`reasoning_effort`).
- **Faltou profundidade:** no Workflow, suba o esforço da etapa antes de trocar de modelo. Pela ferramenta Agent isso não existe — suba de modelo, ou faça o passo você mesmo e peça ao usuário `/effort max` se precisar.
- O Haiku 4.5 não aceita esforço. No Sonnet 5.5, `xhigh`/`max` em trabalho já especificado abre revisões próprias e amplia o escopo — reserve pra frente longa ou difícil de verdade.
- **O esforço da sessão principal só o usuário muda** (o app recusa que uma sessão reprecifique os próprios turnos). O `/orchestrate` mostra o nível atual e, quando a tarefa pedir outro, pede numa linha.
- **Não ligue o `ultracode` global:** na versão atual ele trava a sessão em xhigh (Max indisponível) e transforma toda tarefa em workflow. **Não use `CLAUDE_CODE_EFFORT_LEVEL`:** ele passa por cima do esforço de todos os agentes.

> Nenhum nível foi medido quanto a ganho de qualidade nesta instalação. A tabela é ponto de partida combinando a documentação com a preferência do usuário (Extra no julgamento). Meça antes de prometer. Matriz completa por host: [references/hosts.md](references/hosts.md).

## ⚡ Jev: decisões assertivas pra ninguém ficar parado

O Jev (TypeSafe) é um modelo pequeno e rápido que devolve julgamentos tipados com probabilidade. Ele **não deixa o Opus mais inteligente** — onde o Opus decide num pensamento, chamar o Jev é mais lento (ida e volta de rede). O ganho real é **tirar as paradas em que tudo espera o usuário**. Por isso ele tem três poderes, e só três:

| Poder | Quando | Decide sozinho quando | Senão |
|---|---|---|---|
| `plan_gate` | Todo plano orquestrado, e todo plano Direto que tenha ação numa flag | `seguro` ≥ 0.85 e `no_escopo` ≥ 0.70 → `proceed` | `ask_user`: o plano espera aprovação |
| `tiebreak` | Você pararia pra perguntar "A ou B?" numa escolha reversível de baixo impacto | opção ≥ 0.65, `confidence` ≥ 0.50 e alguma adequada ≥ 0.65 | `model_decides`: você decide e registra |
| `escalation` | Saída de uma frente na zona cinzenta | P(escalar) ≤ 0.20 → `accept` | `escalate`: sobe um nível |

**Roteamento de modelo não é poder do Jev** — é do orquestrador, com "na dúvida, suba".

**Três camadas em código, antes de qualquer rede** (`scripts/jev_rules.py` + `scripts/jev_decide.py`):

1. **Lista de ações locais (só no `plan_gate`).** Cada ação — e cada trecho dela separado por vírgula, "e", "depois", `&&` ou `|` — precisa começar com um verbo de trabalho local (editar, criar, refatorar, testar, ler, mapear, instalar, rodar testes/lint/build…) ou um comando local conhecido. Verbo arriscado ou desconhecido (mandar, avisar, publicar, hospedar, pagar, emitir, logar, reprocessar…), comando externo (`curl`, `ssh`, `gh`, `vercel`, `wrangler`, `eas`…) ou ação sem verbo → volta pro usuário.
2. **Rede de padrões de risco (em todos os tipos).** Mensagem a terceiros, push/merge, deploy, publicação, destrutivo/irreversível, dinheiro, credenciais, produção/dados reais, permissões/auth e veredito de segurança, em português e inglês, sobre o texto normalizado (sem acento, sem invisíveis, sem homóglifos). É uma rede, não uma garantia — por isso a camada 1 existe.
3. **As `flags` que você declara** (definição de cada uma no `/orchestrate`).

Qualquer acerto → `ask_user`/`human_required`/`escalate`, sem chamada de rede. Falso positivo só devolve a decisão pro usuário — é o fluxo de antes, não um erro. Plano com `hard_rule` vai pro usuário **como está**: reescrever pra escapar do `blocked_by` anula o portão.

**Aprovar um plano nunca aprova o texto de uma mensagem.** Texto literal para terceiros passa pelo usuário antes de sair, sempre — com ou sem Jev.

**Falha é conservadora.** Sem autorização registrada, sem credencial, serviço fora, resposta inválida, saída que não seja JSON com `decision`, ou pedido com cara de segredo → o fluxo volta a ser o de antes do Jev. Segredo detectado nunca vai pro TypeSafe nem pro log local (`secret_detected: true`).

**Honestidade no pedido é o que dá valor à decisão.** `actions` lista todas as ações do plano, inclusive as arriscadas, começando por verbo; `summary` descreve o pedido com fidelidade; `flags` declara o que se aplica. Em **todos** os campos (`summary`, `actions`, `context`, `criterion`, `options`, `output_summary`, `signals`): descreva; nunca cole valores, trechos de código, saídas de comando, env vars ou dado de cliente.

**Não chame o Jev pra tudo.** Saída claramente boa ou claramente quebrada, você decide direto. Desempate que muda arquitetura, contrato público, dados ou custo não é desempate: vai pro `@advisor` ou pro usuário.

**Autorização e limiares são do usuário.** Nunca rode `authorize`, `revoke` ou mude limiar por conta própria — só com pedido explícito dele. `--powers` substitui a lista inteira de poderes; os limiares não informados são preservados.

**Auditoria.** Com o Jev configurado, cada decisão fica em `~/.config/hebe-brain/jev-decisions.jsonl` (modo 0600) com tipo, resultado, modo, probabilidades e os 200 primeiros caracteres do resumo (nunca quando há segredo ou credencial em jogo). `jev_decide.py log` mostra as últimas; o log gira acima de 5 MiB. Os limiares (0.85 na segurança e 0.70 no escopo do plano; 0.65; 0.80) **ainda não foram calibrados** com uso real: se o portão aprovar algo que deveria ter perguntado, o usuário sobe o limiar; se abstiver demais em coisa trivial, reveja o resumo antes. Pisos: `plan_gate` e `escalation` ≥ 0.70, `tiebreak` ≥ 0.50. Projeto de mensageria (Evolution/WhatsApp) cai em `ask_user` quase sempre — é por desenho.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jev_decide.py" status        # poderes, limiares, credencial — sem rede
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jev_decide.py" decide --dry-run < pedido.json   # valida sem enviar
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jev_decide.py" log --limit 20
```

## Qualidade não acaba na delegação — revise e verifique

Delegar OFFLOADA o trabalho, não a responsabilidade. O output de `@worker`/`@code-worker` não é verdade até ser revisado — pelo `@reviewer`, por você, ou pelo `@advisor`.

- **Revise o construído antes de confiar**, com foco no que decide o resultado: correção, segurança, e todo fluxo de dinheiro/permissão. Concatenar 4 relatórios não é o mesmo que validá-los.
- **O forte confirma nos pontos-chave** — é isso que separa "qualidade-primeiro" de "delegou e torceu".

## Os dois padrões de orquestração mista

**Padrão 1 — Planner + Workers (fan-out).** O modelo forte (sessão principal, ou `@advisor`) PLANEJA e quebra o trabalho; os workers (contexto isolado) EXECUTAM em paralelo, cada um no modelo certo pra sua peça. O ganho de custo vem de rodar o braçal mecânico em Haiku e o resto no nível adequado — não de forçar tudo pra baixo. Depois o forte revisa e costura. (`/model opusplan` — forte no plano, Sonnet na execução — tira o dev complexo do Opus: use só quando a tarefa for de rotina.)

**Padrão 2 — Executor + Advisor (on-demand).** Uma variação para quando o usuário escolhe rodar a sessão principal em Sonnet: ela toca cada rodada e só chama o `@advisor` (Opus 5.5) quando bate numa decisão difícil — tipicamente 1x por tarefa. O padrão do `/orchestrate` continua sendo a sessão principal em Opus.

## Quando NÃO orquestrar

- **Tarefa pequena e única:** rode Direto no modelo adequado à natureza dela — e não a rebaixe só pra parecer barata. Se alguma ação cair numa flag, o plano ainda passa pelo portão.
- **Tarefa grande mas homogênea:** UltraCode solo num modelo só costuma bater a orquestração mista.
- **Contexto muito interdependente e difícil de resumir num prompt:** subagent roda isolado e só recebe o que você passa; se o repasse for caro/frágil, faça na sessão principal.

## Higiene de contexto

- Subagents rodam em **contexto próprio**: delegar OFFLOADA tokens da sua conversa. Só o resumo final volta.
- Passe no prompt do subagent TUDO que ele precisa (caminhos, erros, decisão/entrega pedida, critério de conclusão, e a proibição de ações fora do plano). Ele não enxerga o histórico da conversa principal.
- A auto-delegação é irregular: se quiser garantir, invoque explícito com `@worker`, `@code-worker`, `@design-worker`, `@reviewer`, `@advisor`.

## Exemplo: auditar / entender um subsistema

**Errado (o anti-padrão):** 4 workers Haiku leem rotas, schema, RLS e "acham" os riscos em paralelo. Barato — e raso. Ler e avaliar código não é mecânico.

**Certo:** as leituras/mapeamentos rodam em `@code-worker` (Sonnet) em paralelo (rotas | camada de serviço | schema/RLS | metadados); a caça a falhas vai pro `@reviewer` (Fable 5.1), pensando como atacante. Você — ou `@advisor` (Opus 5.5, em max no veredito) — sintetiza, deduplica e dá o **veredito** nos riscos críticos. O braçal mecânico (grep de um padrão) vai pro `@worker`.

## Números de referência (benchmark da Anthropic, não garantia)

Planner forte + workers Sonnet ficou ~96% da performance do modelo topo por ~46% do preço num teste da Anthropic. No seu código real, VARIA por tarefa — meça com o seu uso antes de prometer número. E lembre: o alvo aqui é qualidade com economia, não o menor número possível.
