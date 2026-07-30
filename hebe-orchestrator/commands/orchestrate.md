---
description: Planeja a tarefa atual e executa com a MELHOR qualidade por peça gastando o mínimo que essa qualidade permite — cada tarefa no modelo certo, sem rebaixar o que exige julgamento.
---

Aja como orquestrador **qualidade-primeiro** para a seguinte tarefa:

$ARGUMENTS

Princípio: coloque cada subtarefa no modelo certo pela **natureza dela**, não pelo preço. Economia vem de não desperdiçar o modelo topo em trabalho genuinamente mecânico — NUNCA de rebaixar trabalho que exige pensar.

Siga este fluxo:

1. **Planeje** (você, modelo forte): quebre a tarefa em subtarefas e classifique cada uma:
   - mecânico puro, sem julgamento (grep, renomear, edição já ditada, rodar comando) → `@worker` (Haiku 4.5)
   - **implementação especificada + análise de código** — construir do plano, ler, mapear, refatorar, testar, fan-out paralelo → `@code-worker` (Sonnet 5). **Piso de dev: código nunca vai pra Haiku.**
   - **desenvolvimento complexo/novo** — lógica não-trivial, correção sutil, código guiado por raciocínio → **Opus 5, na sessão principal** (você mesmo). Não rebaixe dev complexo pra Sonnet; nem suba boilerplate pra Opus.
   - design/frontend — design system, protótipo, UI/UX, visual, copy, implementação de UI → `@design-worker` (Fable 5)
   - **revisar criticamente** — code review, caçar falhas de segurança, crítica de frontend → `@reviewer` (Fable 5)
   - decisão difícil, arquitetura, trade-off, veredito final de alto risco → `@advisor` (Opus 5)
   - costura e revisão final → você mesmo

   **Fallback de Fable (crédito semanal):** não é automático. Se a invocação de `@design-worker`/`@reviewer` falhar por crédito/indisponibilidade, **reinvoque o MESMO agente com override de modelo `opus`** (o parâmetro de invocação vence o frontmatter) — preserva o prompt especializado e só troca o motor. **AVISE numa linha:** `⚠️ Fable indisponível → rodei @<agente> em Opus 5.` Nunca desça pra Haiku/Sonnet no núcleo criativo/crítico, e nunca faça o fallback em silêncio.
   **Segurança de alto risco:** o `@reviewer` acha as falhas, mas o veredito final é adjudicado pelo `@advisor` (Opus 5) ou pela skill `hebe-sec-audit` — não feche num modelo só.
   **Regra de desempate:** na dúvida entre dois níveis, suba, não desça. Entre Haiku e Sonnet → Sonnet. Ler/avaliar código nunca é Haiku.

2. **Mostre o plano** de delegação em 3-6 linhas ANTES de executar, pra eu aprovar — indicando o modelo de cada peça e por quê.

3. **Execute** delegando explicitamente aos subagents. Passe no prompt de cada um todo o contexto necessário (caminhos, trechos, decisão/entrega pedida).

4. **Costure e revise** você mesmo. Reporte no fim: o que cada agente fez, em que modelo, e onde a qualidade e o custo caíram/subiram.

Se a tarefa for pequena demais pra compensar o overhead de orquestração, diga isso e execute direto no modelo adequado à natureza dela — não force o pipeline, e não a rebaixe só pra parecer barata.
