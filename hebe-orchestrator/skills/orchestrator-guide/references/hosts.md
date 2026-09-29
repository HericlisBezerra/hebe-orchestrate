# Hosts: Claude e Codex no mesmo modelo de orquestração

A doutrina é uma só — estratégia primeiro (direto, UltraCode solo ou mista), papel pela natureza da tarefa, esforço pela dificuldade de cada frente, Jev nos portões, quem constrói não revisa. O que muda por host é o modelo que ocupa cada papel e a forma de delegar. Observado em **2026-09-29**: catálogo do app Claude (Claude Code 2.1.281) e `models_cache.json` do app Codex (cliente 0.158.0). Catálogos mudam; confira antes de fixar.

## Estratégia por host

| Estratégia | Claude (app) | Codex (app) |
|---|---|---|
| Direto | sessão principal (Opus 5.5) | root (`gpt-6-sol`) |
| UltraCode solo — amplo, especificado ou moderado | Workflow com todas as etapas em `sonnet` (alias: Sonnet 5 até o app atualizar, depois Sonnet 5.5) | root `gpt-6-sol` com effort `ultra` (max com delegação) |
| UltraCode solo — amplo e difícil | Workflow com todas as etapas em `opus` (Opus 5.5) | root `gpt-6-astra` com effort `ultra` (xhigh com delegação) — única exceção ao "Astra nunca como root", a pedido do usuário |
| Orquestração mista | Workflow com `agentType` por papel e esforço por etapa (Agent sem pedido do usuário, com o esforço do frontmatter) | ondas de até 3 `spawn_agent` com `model` e `reasoning_effort` por filho |

## Matriz papel × host (esforço típico — decidido por frente)

| Papel | Claude (app) | Codex (app) |
|---|---|---|
| Mecânico | `@worker` · Haiku 4.5 · sem esforço | `gpt-6-luna` · high |
| Código especificado / análise | `@code-worker` · Sonnet 5.5 · high (xhigh em frente longa) | `gpt-6-sol` · high (xhigh em frente longa) |
| Dev complexo | sessão principal · Opus 5.5 · xhigh (max em problema único) | root `gpt-6-sol` · xhigh (max em problema único); `gpt-6-astra` no mais difícil de ponta a ponta |
| Design / frontend | `@design-worker` · Fable 5.1 · xhigh | `gpt-6-astra` · xhigh (fallback `gpt-6-sol`) |
| Revisão crítica | `@reviewer` · Fable 5.1 · xhigh (`opus` se o construtor foi Fable) | o modelo forte que **não** construiu · xhigh · `fork_turns: "none"` |
| Decisão difícil / veredito | `@advisor` · Opus 5.5 · xhigh (max no veredito) | `gpt-6-astra` · xhigh; veredito de alto risco em max com o forte que não achou |
| Planejamento / costura | sessão principal · Opus 5.5 · xhigh | root `gpt-6-sol` · xhigh |
| Portões (Jev) | `scripts/jev_decide.py` | o mesmo script — não depende de host |

No Claude, o UltraCode (ferramenta Workflow) só roda quando o usuário digitou o comando ou escreveu "ultracode"; quando o Claude aciona a orquestração sozinho, ele sugere numa linha.

## Esforço por frente

| Esforço | Para | Claude | Codex |
|---|---|---|---|
| `low` / `medium` | Mecânico trivial; especificado curto | etapa de Workflow | `reasoning_effort` no `spawn_agent` |
| `high` | Especificado longo ou multiarquivo | idem (padrão do `@code-worker`) | idem |
| `xhigh` (Extra) | Todo julgamento | idem; sessão via `modelSettings.claude-opus-5-5.effortLevel` | idem (o root já está em xhigh no `config.toml`) |
| `max` | Problema único, difícil e caro de errar | etapa com `effort: 'max'`, ou `/effort max` pelo usuário | `reasoning_effort: "max"` — teto do Luna |

Onde o esforço **não** é modulável: no Claude, a ferramenta Agent (vale o frontmatter) e a própria sessão principal (só o usuário muda; o app recusa que uma sessão reprecifique os próprios turnos). No Codex, os modelos GPT-6 aceitam troca de esforço no meio da thread; o `gpt-5.6-terra` não.

## Particularidades dos modelos do Codex

| Modelo | O que é | Use quando | Evite quando |
|---|---|---|---|
| `gpt-6-astra` | "Frontier intelligence for the most demanding work". Computer use, browsing, julgamento mais forte. Custa 5× o Sol na API ($10/$50). Fast = 2× velocidade. Para cedo para pedir revisão ("mais tentativo") | Revisor independente de um build do Sol; decisão difícil, ambígua ou sensível; design que precisa conferir a tela; o trabalho mais difícil de ponta a ponta | Root (exceto o Ultra solo pedido pelo usuário), construtor padrão, tarefa simples ou de volume; pedido sem critério de conclusão; max/ultra por hábito |
| `gpt-6-sol` | "Workhorse model for coding and everyday work". Código complexo e fluxos agênticos a 1/5 do Astra ($2/$10). Mais persistente que o Astra. Já é o modelo padrão do `config.toml` | Root do orquestrador, dev complexo, código especificado (high), revisor de um build do Astra, adjudicador quando o Astra achou | Volume repetitivo (Luna custa 20× menos); revisar o próprio build |
| `gpt-6-luna` | "Fast and affordable model for easier tasks". O mais barato ($0.10/$0.50). Vai até max, **sem ultra** | Mecânico: busca, extração, classificação, transformação, triagem | Escrever código (piso Sol); trabalho aberto; revisão de alto risco |
| `gpt-5.6-terra` | "Older balanced model for straightforward work". **Não existe GPT-6 Terra** (a API responde 404). Custa o mesmo ou mais que o `gpt-6-sol`, sendo mais antigo. Não troca esforço no meio da thread | Reserva do Sol (indisponível ou no limite), fluxo já calibrado nele, A/B contra o Sol | Qualquer rota nova; assunto posterior a fev/2026; adjudicar achado de modelo mais forte |
| Legados | `gpt-5.6-sol`, `gpt-5.6-luna` (multi-agent v1: um pai v2 o recusa como filho), `gpt-5.5` (aposenta em 14/10/2026) | Só compatibilidade | Qualquer rota do HeBe |

## Delegar no Codex

```text
spawn_agent{task_name: "review-auth", model: "gpt-6-astra", reasoning_effort: "xhigh",
            fork_turns: "none", message: "<tarefa autocontida + critério de conclusão>"}
```

- O parâmetro é `reasoning_effort` (não `model_reasoning_effort`). Mande sempre, porque os padrões divergem entre modelos.
- `fork_turns: "none"` é obrigatório para revisor e adjudicador (independência) e evita que o filho herde o esforço `ultra` do pai. Use `"N"` quando o filho precisa do contexto recente. Sem fork, o `message` leva tudo.
- **Limite observado: 3 filhos abertos por sessão**, contando a árvore inteira e as threads concluídas que continuam abertas. Planeje ondas de até 3 e confira com `list_agents` antes de cada uma.
- O `ultra` nativo disputa esses slots. Numa sessão, ou o HeBe faz ondas explícitas, ou o root roda em `ultra` e delega sozinho — nunca os dois.
- Retomar: `followup_task{target, message}`. Esperar: `wait_agent{timeout_ms}`.
- Não use `persistent` como esforço (pelo que se observou, é um modo de sessão — não confirmado oficialmente).
- Astra: dê critério de conclusão explícito e liberdade segura ("rode testes, corrija e rerode sem perguntar").

**Pipeline de segurança de alto risco no Codex.** O construtor é `gpt-6-sol` em xhigh. O achador é `gpt-6-astra` em xhigh, com `fork_turns: "none"`. O adjudicador é o forte que **não achou** (`gpt-6-sol`, em max), em thread nova. O adjudicador só rebaixa um achado com contraprova concreta; na dúvida, o achado fica e sobe para o usuário. Se o construtor for o Astra, os papéis se invertem. O Jev não adjudica.

## O que não foi verificado

- Como o `ultra` resolve em cada modelo (Astra em xhigh, Sol e Terra em max) vem da leitura do PR openai/codex#41206 e do cache local, sem teste de ponta a ponta.
- O limite de 3 filhos é observação local mais issues, sem número oficial.
- Nenhum filho `gpt-6-luna` foi observado ainda.
- Não se sabe se o schema do `spawn_agent` na 0.158 ainda expõe `model` e `reasoning_effort`.
- O Astra como especialista em design visual não tem fonte oficial; a escolha vem de "na dúvida, suba" e do computer use. Faça A/B contra o Sol antes de fixar.
- O descarte silencioso do esforço no Haiku 4.5 e a precedência de esforço no Workflow vêm do código do Claude Code, não da documentação.
- `persistent` como modo de sessão é inferência da pesquisa, sem fonte oficial.
- O alias `sonnet` do app (Claude Code 2.1.281) ainda resolve para o Sonnet 5; o Sonnet 5.5 chega com a atualização do app.
- O comportamento do app sem crédito de Fable (falha, consentimento para créditos pagos ou troca automática de modelo) não foi testado.
- Nenhum nível de esforço foi medido quanto a ganho de qualidade, em nenhum dos hosts.

Fontes: `~/.codex/models_cache.json` (2026-09-29), [modelos da API](https://developers.openai.com/api/docs/models/gpt-6-astra), [preços](https://developers.openai.com/api/docs/pricing), [prompts para o GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), [modelos no Codex](https://learn.chatgpt.com/docs/models), [openai/codex#41206](https://github.com/openai/codex/pull/41206), [migração para Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide).
