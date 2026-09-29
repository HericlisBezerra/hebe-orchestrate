---
name: orchestrate
description: Orquestração multi-modelo qualidade-primeiro no app Codex — primeiro a estratégia (direto, ultra com um modelo só, ou mista), depois cada frente no modelo certo (Luna, Sol, Astra; Terra como reserva) e no esforço decidido pela dificuldade, com o Jev aprovando planos de baixo risco, desempatando escolhas reversíveis e decidindo escalar ou aceitar. Use para tarefas compostas; tarefas simples seguem direto.
---

# Orquestrador HeBe — host Codex

Mesma doutrina do plugin do Claude: papel pela **natureza** da tarefa, esforço pela **dificuldade**, Jev nos portões, **quem constrói não revisa**. Economia vem de não desperdiçar o topo em trabalho mecânico — nunca de rebaixar o que exige julgamento. Velocidade vem de não parar pra perguntar o que o Jev pode decidir com segurança — nunca de pular as decisões que são do usuário.

`<plugin-root>` é a pasta que contém `codex-skills/` e `scripts/` (este arquivo fica em `<plugin-root>/codex-skills/orchestrate/SKILL.md`). Rode os scripts por caminho absoluto: `python3 <plugin-root>/scripts/jev_decide.py`. Se não achar, procure com `ls ~/.codex/plugins/cache/*/hebe-orchestrator/*/scripts/jev_decide.py`.

## 1. Estratégia — a primeira decisão

| Estratégia | Quando | Como |
|---|---|---|
| **Direto** | Uma peça só, cabe num contexto | Você mesmo (root) |
| **Ultra solo — Sol** | Grande e divisível, frentes da mesma natureza, especificado ou moderado | Peça ao usuário o effort `ultra` no root `gpt-6-sol` (max com delegação automática), ou faça uma onda de filhos todos `gpt-6-sol` |
| **Ultra solo — Astra** | Grande e divisível, frentes da mesma natureza, difícil | Root `gpt-6-astra` em `ultra` (xhigh com delegação) — a única exceção à regra "Astra nunca como root", e só a pedido do usuário, porque troca o modelo da sessão |
| **Mista** | Frentes de naturezas diferentes | Ondas de até 3 `spawn_agent`, cada filho com o seu modelo e esforço |

Não divida entre modelos o que um modelo só faz bem. Mesmo no solo, tarefa que toca segurança, dinheiro, permissão ou dados fecha com revisão num modelo diferente do construtor. Diga a estratégia e o porquê numa linha no plano.

## 2. Esforço — decidido por frente, não fixo

`low` (mecânico trivial) · `medium` (especificado curto) · `high` (especificado longo) · `xhigh` (todo julgamento — ponto de partida de trabalho que pensa) · `max` (problema único, difícil e caro de errar; teto do Luna). `ultra` é a estratégia de delegação, não um nível acima do max. Suba o esforço antes de trocar de modelo quando faltar profundidade; troque de modelo quando faltar capacidade.

## 3. Quem faz cada natureza (esforço típico)

| Natureza | Modelo | Esforço |
|---|---|---|
| Mecânico puro (busca, extração, classificação, edição já ditada, rodar comando) | `gpt-6-luna` | low–high |
| Código especificado + análise (construir do plano, ler, mapear, refatorar, testar) | `gpt-6-sol` | medium–high · xhigh em frente longa |
| Dev complexo/novo, correção sutil | você (root `gpt-6-sol`) | xhigh · max em problema único |
| O mais difícil de ponta a ponta, com computer use ou browsing | `gpt-6-astra` | xhigh |
| Design/frontend | `gpt-6-astra` (reserva `gpt-6-sol`) | xhigh |
| Revisão crítica | o forte que **não** construiu: build do Sol/Luna → `gpt-6-astra`; build do Astra → `gpt-6-sol` | xhigh |
| Decisão difícil | `gpt-6-astra` | xhigh |
| Veredito de segurança de alto risco | o forte que **não** achou: achador Astra → `gpt-6-sol`; achador Sol → `gpt-6-astra` | max, thread nova |
| Reserva do Sol (indisponível ou no limite) | `gpt-5.6-terra` | igual ao papel que substitui |

- **Código nunca vai pro Luna.** Na dúvida entre dois níveis, suba. O roteamento é seu, não do Jev.
- **Terra** é a melhor Terra disponível, mas é de geração anterior e custa o mesmo ou mais que o `gpt-6-sol`: fica como reserva ou A/B, nunca como rota principal.
- **Legados** (`gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.5`) não entram em rota nenhuma.
- **Astra:** dê critério de conclusão explícito e liberdade segura ("rode testes, corrija e rerode sem perguntar"). Ele para cedo pra pedir revisão e custa 5× o Sol — nunca como root (exceto no Ultra solo pedido pelo usuário) nem como construtor padrão.

**Ultra** nunca na mesma sessão em que você faz `spawn_agent` explícito — os dois disputam os mesmos 3 slots. "Most tasks do not need Max or Ultra."

## 4. Portão do plano (Jev)

Passa pelo portão todo plano orquestrado e todo plano Direto com ação numa flag. Monte o plano em 3-6 linhas (estratégia, e modelo e esforço de cada frente com o porquê) e submeta. **Cada ação começa com um verbo de trabalho local** (editar, criar, refatorar, testar, ler, mapear, instalar, rodar testes/lint/build…) ou comando local; o script devolve pro usuário ação com verbo arriscado ou desconhecido, comando externo ou sem verbo.

```bash
python3 <plugin-root>/scripts/jev_decide.py decide <<'JSON'
{"kind": "plan_gate",
 "summary": "<o pedido, descrito com fidelidade>",
 "actions": ["<ação concreta 1>", "<ação 2>"],
 "flags": []}
JSON
```

`flags` — declare cada uma que se aplica: `third_party_message` (WhatsApp/Evolution, e-mail, Slack, PR, issue, comentário, webhook de cliente), `push`, `deploy`, `publish`, `destructive`, `irreversible`, `credentials`, `money`, `production_data`, `permissions`, `security_verdict`. Qualquer flag devolve a aprovação pro usuário sem rede.

Em **todos** os campos (`summary`, `actions`, `context`, `criterion`, `options`, `output_summary`, `signals`): descreva; nunca cole valores, código, saídas de comando, env vars ou dado de cliente. `actions` lista todas as ações, inclusive as arriscadas. Autorizar o Jev ou mudar limiar é só do usuário.

- `proceed` → mostre o plano com `⚡ Jev aprovou o plano — executando.` e execute.
- `ask_user` (qualquer `mode`) → mostre o plano, diga por quê numa linha e espere aprovação.
- `hard_rule` → o plano vai pro usuário **como está**; nunca reescreva pra escapar do `blocked_by`.
- `secret_detected: true` → não repita o conteúdo; avise.
- Qualquer saída que não seja JSON com `decision` → decisão não tomada: o plano espera aprovação.

**Aprovar um plano nunca aprova o texto de uma mensagem** — texto literal para terceiros passa pelo usuário antes de sair, sempre.

## 5. Execute

Delegue com modelo e esforço na própria chamada:

```text
spawn_agent{task_name: "<frente>", model: "gpt-6-sol", reasoning_effort: "high",
            fork_turns: "none", message: "<tarefa autocontida + critério de conclusão>"}
```

- `reasoning_effort` sempre explícito — os padrões divergem entre modelos.
- `fork_turns: "none"` para revisor e adjudicador (independência) e para não herdar `ultra` do pai; `"N"` quando o filho precisa do contexto recente.
- **Ondas de até 3 filhos** (limite observado por sessão, contando a árvore e as threads concluídas ainda abertas). Confira com `list_agents` antes de cada onda. `wait_agent` pra esperar; `followup_task` pra retomar.

**Desempate reversível (Jev):** quando você pararia pra perguntar "A ou B?" numa escolha de baixo impacto e reversível, rode `jev_decide.py decide` com `{"kind": "tiebreak", "summary": ..., "criterion": ..., "options": {"a": ..., "b": ...}}`. Id da opção → adote. `model_decides` → decida você com a razão numa linha. `human_required` → pergunte.

**Escalar ou aceitar (Jev):** saída de filho na zona cinzenta → `{"kind": "escalation", "summary": ..., "output_summary": "<descrito>", "signals": [...]}`. `accept` → integre. `escalate` → suba (Luna → Sol; Sol → você em xhigh/max, ou Astra se for decisão).

**Segurança de alto risco:** o construtor é o Sol em xhigh. O achador é o Astra em xhigh, com `fork_turns: "none"`. O adjudicador é o forte que não achou (Sol em max), em thread nova. Se o construtor for o Astra, os papéis se invertem (Sol acha, Astra adjudica). O adjudicador só rebaixa um achado com contraprova concreta; na dúvida, o achado sobe para o usuário. O Jev não adjudica.

**Todo `message` de delegação** leva: `Não execute mensagem a terceiros, push, deploy, publicação, ação destrutiva, credenciais, dinheiro, produção ou permissões que não estejam no plano aprovado — pare e devolva.`

## 6. Costure e reporte

Integre, verifique por artefato e reporte: a estratégia e por quê, frentes e ondas, modelo e esforço efetivos de cada uma, decisões do Jev (`decision_id`, tipo, resultado, modo) e onde qualidade e custo subiram ou caíram. O tier Fast (`service_tier = priority`) multiplica o consumo; vale só quando a tarefa pede velocidade.

**Não verificado em 2026-09-29:** se o `spawn_agent` da versão 0.158 ainda expõe `model` e `reasoning_effort`; o esforço efetivo dos filhos do `ultra`; o limite exato de filhos; qualquer filho `gpt-6-luna` observado. Se uma chamada recusar um parâmetro, informe e siga com o que o host aceitar — nunca finja o modelo ou o esforço usados.
