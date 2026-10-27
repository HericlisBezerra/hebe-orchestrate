---
name: orchestrator-guide
description: Doutrina de orquestração multi-modelo qualidade-primeiro no Claude Code — primeiro a estratégia (direto, UltraCode com um modelo só, ou mista), depois cada frente no modelo certo pela natureza dela (mecânico→Haiku, código especificado→Sonnet, dev complexo e decisão→Opus, design e revisão→Opus, com o Fable desativado até nova ordem do usuário) e no esforço certo pela dificuldade, revisando o output antes de confiar e usando o Jev pra não parar em decisão que não é do usuário. Invoque ao planejar uma tarefa longa/composta.
disable-model-invocation: true
---

# Orquestração multi-modelo — doutrina qualidade-primeiro

> 🔒 **Fable desativado — até nova ordem do usuário ou até sair um Fable novo (nesse caso, pergunte se volta).** **Nada é roteado para Fable**: `@design-worker` roda em Opus (esforço `medium`) e `@reviewer` roda em Opus (esforço `high`). Nunca use `model: 'fable'` em Agent nem em etapa de Workflow. Para reativar, só com ordem do usuário: trocar `model: opus` por `model: fable` nos dois agentes (seção "Fable desativado" abaixo).

**Objetivo:** a MELHOR qualidade possível em cada peça da tarefa, gastando o mínimo que essa qualidade permite. Economia vem de **não desperdiçar o modelo topo em trabalho genuinamente mecânico** — NUNCA de rebaixar trabalho que exige julgamento. Velocidade vem de **não orquestrar o que um modelo só resolve** e de não parar pra perguntar o que o Jev decide com segurança.

> Erro clássico a evitar: tratar "barato" como objetivo e jogar leitura/análise/auditoria de código no Haiku. Isso não é economia — é rebaixar julgamento. Código é piso Sonnet, sempre.

## Como escolher o modelo (pela natureza da tarefa, não pelo preço)

| Natureza da tarefa | Agente | Modelo | Esforço típico (decidido por frente) |
|---|---|---|---|
| Mecânico puro, zero julgamento — grep, renomear, edição já ditada, mover, rodar comando/checagem | `@worker` | Haiku | — (não aceita) |
| **Implementação especificada + análise de código** — construir do plano, ler, mapear, refatorar, testar, fan-out paralelo | `@code-worker` | Sonnet¹ | medium–high · xhigh em frente longa |
| **Desenvolvimento complexo/novo** — lógica não-trivial, correção sutil, código guiado por raciocínio | sessão principal | Opus | medium para começar · high/xhigh com ganho comprovado · max em problema único |
| **Design/frontend** — design system, protótipo, UI/UX, layout, identidade, copy, implementação visual | `@design-worker` | Opus² | medium · high/xhigh em design final com ganho comprovado |
| **Revisar criticamente** — code review, caçar falhas de segurança, crítica de frontend/UX | `@reviewer` | Opus² | high · xhigh/max em segurança de alto risco |
| Decisão difícil, arquitetura, trade-off, veredito final de alto risco | `@advisor` | Opus | high · max no veredito |
| Planejamento de alto nível, costura entre peças, revisão final | sessão principal | Opus | medium · high se a costura for densa |

² Fable desativado até nova ordem do usuário ou até sair um Fable novo — ver o aviso no topo e a seção "Fable desativado".

¹ Os agentes usam **alias** (`haiku`, `sonnet`, `opus`, `fable`), resolvido pelo Claude Code embutido no app para a versão mais recente de cada família, sem número fixo. Em 2026-09-29 (Claude Code 2.1.284) os quatro apelidos resolveram para a família esperada. No app o esforço padrão do Sonnet é `medium`. Confira com `/model` antes de afirmar qual modelo rodou.

> **Preço de referência** (dólares por milhão de tokens, entrada e saída, set/2026, versões vigentes na época): Haiku, 1 e 5 · Sonnet, 2 e 10 · Opus, 4 e 20 · Fable, 10 e 50. Subir de Sonnet pra Opus custa 2×, não 5× — o "na dúvida, suba" ficou mais barato. O Opus vem com esforço padrão `medium` no app, e o `settings.example.json` mantém a sessão principal em `medium` (chave `modelSettings.claude-opus-5-5.effortLevel`).

> **Dois eixos dentro de código:**
> **(1) Especificado vs. complexo** — implementação já decidida, rotina e peças paralelas → `@code-worker` (Sonnet), onde ele é rápido e confiável. Desenvolvimento complexo/novo, correção sutil, código que o raciocínio guia → **Opus, na sua sessão principal**. Acertar de primeira no complexo vale mais que o token economizado.
> **(2) Construir vs. revisar** — quem constrói *escreve e entende*; o `@reviewer` *avalia criticamente e caça falhas*. Um constrói, o outro procura defeito.

**Regras que não se quebram:**
- **Código nunca vai pra Haiku.** Entender, avaliar ou escrever código exige julgamento de engenharia → piso Sonnet. Haiku só faz o braçal mecânico sem decisão.
- **Código tem dois níveis, não um.** Rotina/especificado/paralelo → Sonnet; complexo/novo/correção sutil → Opus. Rebaixar dev complexo custa iteração e bug; subir boilerplate pra Opus é o "Opus pra tudo" que você quer evitar.
- **Design e revisão crítica não descem pra Haiku/Sonnet.** Esse núcleo roda em Opus enquanto o Fable estiver desativado (até nova ordem do usuário ou até sair um Fable novo).
- **Quem constrói não revisa — pelo modelo que rodou de fato, dentro do que está ativo.** Com o Fable desativado: construído em Sonnet → revisão em Opus é independente de modelo. Construído em Opus → revisão em contexto novo, mas mesmo modelo: o Codex GPT-6 Astra entra como segunda lente automática (seção "Segunda lente de revisão"). Se ele não estiver disponível ou falhar, **avise o usuário em uma linha que a independência de modelo caiu**.
- **Segurança de alto risco não fecha num modelo só.** O `@reviewer` ACHA; o Astra é a segunda lente; o plugin `claude-security` é a terceira lente opcional; o `@advisor` ADJUDICA. Só se rebaixa um achado com contraprova concreta. Se a cadeia ficar só em Opus (Astra indisponível), diga isso e pergunte ao usuário antes de tratar como definitivo.
- **Na dúvida entre dois níveis, suba.** O custo de rebaixar (retrabalho, bug, design pobre) quase sempre supera a economia de tokens.
- **Escale em runtime, não só no plano.** Worker incerto, contraditório, ou erro caro (segurança, dados, dinheiro) → suba em vez de aceitar.
- **Subagente nunca faz ação fora do plano aprovado.** Todo prompt de delegação leva: "não execute mensagem a terceiros, push, deploy, publicação, ação destrutiva, credenciais, dinheiro, produção ou permissões que não estejam no plano — pare e devolva".

## 🔒 Fable desativado (estado oficial desta versão)

**Decisão do usuário (2026-09-29):** o Opus se mostrou mais eficiente que o Fable para este uso, então a orquestração para Fable fica desativada até nova ordem dele ou até sair um Fable novo (nesse caso, pergunte a ele se volta).

- `@design-worker` e `@reviewer` rodam em **Opus** (`@design-worker` `medium`, `@reviewer` `high`).
- **Nunca** use `model: 'fable'` em Agent nem em etapa de Workflow, e não escolha Fable em estratégia nenhuma.
- **Custo da decisão:** a revisão passa a ser da mesma família de modelo do construtor quando o construtor foi Opus. Compense com contexto novo, com o Codex GPT-6 Astra como segunda lente automática (seção "Segunda lente de revisão") e **avisando o usuário** quando a independência de modelo cair (Astra indisponível ou com falha).
- **Reativar o Fable:** só com ordem do usuário. Troque `model: opus` por `model: fable` em `agents/design-worker.md` e em `agents/reviewer.md`.

> No UltraCode (Workflow), uma etapa que morre vira `null`. Nunca descarte em silêncio a frente de design ou a revisão: detecte o `null`, refaça a etapa e avise.

## 🧭 Estratégia primeiro, esforço por frente

**A primeira decisão não é o modelo: é a estratégia.** O Sonnet e o Opus resolvem sozinhos muita tarefa grande, e cada handoff entre modelos custa contexto e latência.

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
| `medium` | **Ponto de partida** (padrão oficial do Opus): especificado e delimitado, e a maior parte do trabalho que pensa |
| `high` | Especificado mas longo ou multiarquivo; julgamento que já pesa (revisão crítica, decisão de arquitetura) |
| `xhigh` (Extra) | Só onde você mediu ganho sobre `high` — dev complexo, design final, costura de peças interdependentes. No Opus pensa mais por turno que antes |
| `max` | Problema único, difícil e caro de errar. Paralelismo não ajuda. Nunca por garantia |

**Ultra/UltraCode não é um nível acima do Max** — é a estratégia multiagente, com esforço próprio em cada etapa. Em tarefa única, o teto é Max.

- **Onde dá pra modular:** no Claude, só nas etapas do Workflow (`agent(p, {model, effort})`). A ferramenta Agent não aceita esforço por chamada — vale o frontmatter (`@code-worker` high; `@advisor` high; `@design-worker` medium e `@reviewer` high, em Opus com o Fable desativado; `@worker` sem). No Codex, em cada `spawn_agent` (`reasoning_effort`).
- **Faltou profundidade:** no Workflow, suba o esforço da etapa antes de trocar de modelo. Pela ferramenta Agent isso não existe — suba de modelo, ou faça o passo você mesmo e peça ao usuário `/effort max` se precisar.
- O Haiku não aceita esforço. No Sonnet, `xhigh`/`max` em trabalho já especificado abre revisões próprias e amplia o escopo — reserve pra frente longa ou difícil de verdade.
- **O esforço da sessão principal só o usuário muda** (o app recusa que uma sessão reprecifique os próprios turnos). O `/orchestrate` mostra o nível atual e, quando a tarefa pedir outro, pede numa linha.
- **Não ligue o `ultracode` global:** na versão atual ele trava a sessão em xhigh (Max indisponível) e transforma toda tarefa em workflow. **Não use `CLAUDE_CODE_EFFORT_LEVEL`:** ele passa por cima do esforço de todos os agentes.

> Base: guia oficial *Prompting Claude Opus 5.5* ("Calibrate effort") — começar em `medium`, testar vários níveis nos seus próprios casos e reservar `xhigh`/`max` para ganho medido; pensar menos = baixar o esforço, não pedir por texto; nada de "pense com calma" nos prompts. Sonnet: padrão oficial `high`; `medium` em código bem especificado. Nenhum nível foi medido ainda nesta instalação: meça antes de prometer. Matriz completa por host: [references/hosts.md](references/hosts.md).

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

### Segunda lente de revisão: Codex GPT-6 Astra

O Astra **complementa** o `@reviewer`; nunca o substitui.

- **Quando o orquestrador aciona sozinho:** sempre que o trabalho foi construído em Opus (a independência de modelo cairia) e sempre em segurança, arquitetura ou refactor grande. Fora desses casos, só quando o usuário pedir.
- **Como acionar:** pelo plugin oficial do Codex (`openai-codex`), em modo somente leitura. O usuário digita `/codex:adversarial-review --model gpt-6-astra` (com `--base <ref>` para revisar commits). O orquestrador roda pelo Bash:

  ```bash
  node "$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/ | sort -V | tail -1)scripts/codex-companion.mjs" adversarial-review --model gpt-6-astra --scope working-tree --json
  ```

  Isso vale para mudanças ainda não commitadas; para commits, `--base <ref>` no lugar de `--scope working-tree`. Rode em segundo plano (`run_in_background`) quando for longo. O retorno é um veredito curto em JSON.

  **Auditoria de código que já existe (sem diff):** os dois modos acima só revisam diferenças do git. Com a árvore limpa o diff vem vazio, e a revisão não cobre nada. Nesse caso, use uma tarefa somente leitura (sem `--write`) e escreva no pedido os caminhos, o objetivo e o escopo:

  ```bash
  node "$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/ | sort -V | tail -1)scripts/codex-companion.mjs" task --model gpt-6-astra --effort high --json "Auditoria somente leitura de <caminhos>. Objetivo: <o que procurar>. Liste os arquivos que leu e os achados com arquivo e linha."
  ```

  **Cobertura antes de contar a lente:** só conte a segunda lente como feita se o retorno mostrar que o Codex leu o que devia. Na revisão de mudanças, o diff não pode estar vazio. Na auditoria, a lista de arquivos lidos precisa cobrir o escopo.
- **O que fazer com o resultado:** confira cada achado no código antes de agir. Achado do Codex é hipótese, não ordem. Segundo o piloto de 2026-10-26, ele achou cerca de 16% do que o Opus achou, sem nenhum alarme falso, e pegou defeitos que o Opus deixou passar (fluxo de dados, ordem das gravações, garantias de apagamento). Por isso ele complementa e não substitui.
- **Se o Codex não estiver disponível ou falhar:** diga ao usuário, numa linha, que a independência de modelo caiu.
- **Não usar** em repositório de terceiros ou de origem não confiável: o Codex do plugin oficial roda com a configuração completa do usuário, incluindo os conectores.
- **Segurança de alto risco:** o `@reviewer` acha, o Astra é a segunda lente, o plugin `claude-security` é a terceira lente opcional e o `@advisor` adjudica.
- O código é enviado à OpenAI. O usuário já aprovou isso para os próprios projetos, e a regra de não usar em repositório de terceiros cobre o resto.

## Os dois padrões de orquestração mista

**Padrão 1 — Planner + Workers (fan-out).** O modelo forte (sessão principal, ou `@advisor`) PLANEJA e quebra o trabalho; os workers (contexto isolado) EXECUTAM em paralelo, cada um no modelo certo pra sua peça. O ganho de custo vem de rodar o braçal mecânico em Haiku e o resto no nível adequado — não de forçar tudo pra baixo. Depois o forte revisa e costura. (`/model opusplan` — forte no plano, Sonnet na execução — tira o dev complexo do Opus: use só quando a tarefa for de rotina.)

**Padrão 2 — Executor + Advisor (on-demand).** Uma variação para quando o usuário escolhe rodar a sessão principal em Sonnet: ela toca cada rodada e só chama o `@advisor` (Opus) quando bate numa decisão difícil — tipicamente 1x por tarefa. O padrão do `/orchestrate` continua sendo a sessão principal em Opus.

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

**Certo:** as leituras/mapeamentos rodam em `@code-worker` (Sonnet) em paralelo (rotas | camada de serviço | schema/RLS | metadados); a caça a falhas vai pro `@reviewer` (Opus, com o Fable desativado), pensando como atacante. Você — ou `@advisor` (Opus, em max no veredito) — sintetiza, deduplica e dá o **veredito** nos riscos críticos. O braçal mecânico (grep de um padrão) vai pro `@worker`.

## Números de referência (benchmark da Anthropic, não garantia)

Planner forte + workers Sonnet ficou ~96% da performance do modelo topo por ~46% do preço num teste da Anthropic. No seu código real, VARIA por tarefa — meça com o seu uso antes de prometer número. E lembre: o alvo aqui é qualidade com economia, não o menor número possível.
