---
description: Escolhe a estratégia (direto, UltraCode com um modelo só, ou orquestração mista) e, para cada frente, o modelo e o esforço certos — decididos pela tarefa, não fixos. O Jev aprova planos de baixo risco, desempata escolhas reversíveis e decide escalar ou aceitar.
---

Aja como orquestrador **qualidade-primeiro** para a seguinte tarefa:

$ARGUMENTS

Princípio: cada frente no **modelo** certo pela natureza dela e no **esforço** certo pela dificuldade dela — decididos agora, para esta tarefa, nunca por hábito. Economia vem de não desperdiçar o topo em trabalho mecânico — NUNCA de rebaixar o que exige julgamento. Velocidade vem de não orquestrar o que um modelo resolve sozinho e de não parar pra perguntar o que o Jev pode decidir — NUNCA de pular as decisões que são minhas.

Seu esforço atual nesta sessão: `${CLAUDE_EFFORT}` (se aparecer literalmente assim, sem valor, e a ferramenta `get_session` estiver disponível, leia com `get_session("self")`).

> 🔒 **Fable desativado — até nova ordem do usuário ou até sair um Fable novo (nesse caso, me pergunte se volta).** **Nada é roteado para Fable**: `@design-worker` roda em Opus (esforço `medium`) e `@reviewer` roda em Opus (esforço `high`). Nunca use `model: 'fable'` em Agent nem em etapa de Workflow. Para reativar, só com ordem minha: trocar `model: opus` por `model: fable` nos dois agentes.

## 1. Estratégia — a primeira decisão

Olhe o tamanho, se a tarefa se divide em frentes independentes e se as frentes têm a mesma natureza. Escolha uma:

| Estratégia | Quando | Como |
|---|---|---|
| **Direto** | Uma peça só, cabe num contexto | Você mesmo, na sessão principal. Sem subagentes |
| **UltraCode solo — Sonnet** | Grande e divisível, frentes da mesma natureza, trabalho especificado ou moderado: migração por módulo, refactor em massa, suíte de testes, CRUD em vários módulos, mapeamento amplo | Workflow com todas as etapas em `model: 'sonnet'`, esforço por etapa |
| **UltraCode solo — Opus** | Grande e divisível, frentes da mesma natureza, trabalho difícil: refactor complexo entre subsistemas, auditoria profunda, bug que atravessa módulos | Workflow com todas as etapas em `model: 'opus'`, esforço por etapa |
| **Orquestração mista** | Frentes de naturezas diferentes (mecânico + código + design + revisão + decisão) | Cada frente no seu nível (seção 3), esforço por frente |

- O Sonnet e o Opus resolvem sozinhos muita tarefa grande. **Não divida entre modelos o que um modelo só faz bem** — cada handoff custa contexto e latência.
- Os modelos vão pelo apelido (`haiku`, `sonnet`, `opus`), que o app resolve para a versão mais recente de cada família. Reporte o modelo que rodou de fato.
- Mesmo no solo, **quem constrói não revisa**: se a tarefa toca risco (segurança, dinheiro, permissão, dados), feche com uma etapa de revisão num modelo diferente do construtor.
- Diga a estratégia escolhida e o porquê numa linha no plano.

## 2. Esforço — decidido por frente, não fixo

| Esforço | Para |
|---|---|
| `low` | Mecânico trivial, consulta pontual |
| `medium` | **Ponto de partida** (padrão oficial do Opus): especificado e delimitado, e também a maior parte do trabalho que pensa |
| `high` | Especificado mas longo ou multiarquivo; julgamento que já pesa (revisão crítica, decisão de arquitetura) |
| `xhigh` (Extra) | Só onde você **mediu ganho** sobre `high`: dev complexo, design final, costura de peças interdependentes. No Opus pensa mais por turno que antes: custa mais tempo e tokens |
| `max` | Problema único, difícil e caro de errar: bug sutil de estado/concorrência, decisão irreversível, veredito de segurança. **Nunca por garantia** |
| **UltraCode** | Não é um nível acima do Max — é a estratégia multiagente da seção 1, com esforço próprio em cada etapa |

- **Só dá pra modular o esforço de uma frente no UltraCode** (etapas do Workflow). Pela ferramenta Agent vale o frontmatter do agente, e a sua própria sessão só eu mudo — o app não deixa uma sessão reprecificar os próprios turnos.
- **Faltou profundidade:** no UltraCode, suba o esforço da etapa antes de trocar de modelo. Pela ferramenta Agent, suba de modelo ou faça o passo você mesmo; se a tarefa pedir `max` na sessão principal, me diga numa linha: `Isso pede max; ajusta no menu de esforço?`.
- **Comece em `medium` e suba só com ganho comprovado na tarefa** (guia oficial do Opus, "Calibrate effort": `medium` iguala ou supera o `high` da versão anterior; teste vários níveis nos seus casos e reserve `xhigh`/`max` para ganho medido). Para o modelo pensar menos, **baixe o esforço antes de mexer no texto**.
- **Não escreva "pense com calma", "pense passo a passo" ou parecido** nos prompts de delegação: o modelo já raciocina e o esforço é o controle.
- O Haiku não aceita esforço. No Sonnet o padrão oficial é `high`: use `medium` em código bem especificado e curto, `high` em frente difícil ou longa, e `xhigh`/`max` só com ganho medido (em trabalho já especificado abrem revisões próprias e ampliam o escopo).

## 3. Quem faz cada natureza

`subagent_type` entre parênteses. O esforço entre colchetes é o **padrão do frontmatter**, que vale quando você delega pela ferramenta Agent. No UltraCode, você escolhe o esforço de cada etapa pela seção 2.

| Natureza | Quem | Modelo [padrão] |
|---|---|---|
| Mecânico puro, zero julgamento | `@worker` (`hebe-orchestrator:worker`) | Haiku [sem esforço] |
| Código especificado + análise | `@code-worker` (`hebe-orchestrator:code-worker`) | Sonnet [high] |
| Dev complexo/novo, correção sutil | você, na sessão principal (ou etapa `model: 'opus'`) | Opus [o da sessão] |
| Design/frontend | `@design-worker` (`hebe-orchestrator:design-worker`) | Opus [medium] — Fable desativado |
| Revisão crítica | `@reviewer` (`hebe-orchestrator:reviewer`) | Opus [high] — Fable desativado |
| Decisão difícil, veredito de alto risco | `@advisor` (`hebe-orchestrator:advisor`) | Opus [high] |

- **Código nunca vai pro Haiku.** Na dúvida entre dois níveis, suba. O roteamento é seu, não do Jev.
- **Quem constrói não revisa — pelo modelo que rodou de fato, dentro do que está ativo.** Com o Fable desativado: construído em Sonnet (`@code-worker`) → `@reviewer` em Opus é independente de modelo. Construído em Opus (sessão principal, `@advisor`, `@design-worker`) → o `@reviewer` revisa em contexto novo, mas o modelo é o mesmo: **o Codex GPT-6 Astra entra como segunda lente automática** (seção 6). Se o Astra não estiver disponível ou falhar, **me diga numa linha que a independência de modelo caiu**. Segurança de alto risco: a cadeia de lentes está na seção 6.
- **Fable desativado (estado oficial desta versão):** vale até ordem minha ou até sair um Fable novo (nesse caso, me pergunte se volta). Não há fallback a fazer, porque nada é roteado para Fable: não invoque agente com override `fable` e não use `model: 'fable'` em etapa de Workflow. Se eu mandar reativar, siga a seção "Fable desativado" da skill `orchestrator-guide`.

## 4. Portão do plano (Jev)

Passa pelo portão todo plano orquestrado (UltraCode ou mista) e todo plano Direto que tenha alguma ação numa flag. Plano Direto sem nenhuma flag executa sem portão.

Monte o plano em 3-6 linhas — estratégia, e modelo e esforço de cada frente com o porquê — e submeta. **Cada ação começa com um verbo de trabalho local** (editar, criar, refatorar, testar, ler, mapear, instalar, rodar testes/lint/build…) ou um comando local; o script devolve pra mim qualquer ação com verbo arriscado ou desconhecido, comando externo ou sem verbo. Comando na coluna zero:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jev_decide.py" decide <<'JSON'
{"kind": "plan_gate",
 "summary": "<o pedido, descrito com fidelidade>",
 "actions": ["<verbo + ação concreta 1>", "<verbo + ação 2>"],
 "flags": []}
JSON
```

**`flags` — declare cada uma que se aplica** (qualquer uma devolve a aprovação pra mim, sem rede):

| Flag | Quando |
|---|---|
| `third_party_message` | qualquer coisa que alcance outra pessoa: WhatsApp/Evolution, e-mail, Slack, SMS, PR, issue, comentário, release notes, webhook de cliente, post em rede social |
| `push` | git push, merge, `db push` |
| `deploy` | colocar no ar: Vercel, Cloudflare, servidor, DNS/domínio, loja de apps, "subir o site" |
| `publish` | tornar algo público ou lançar versão: npm publish, release, bucket/repositório público |
| `destructive` | apagar/zerar/recriar dados, tabelas, colunas, bucket, migrations, reset de banco, `--force`, `rm -rf` |
| `irreversible` | qualquer efeito que git ou apagar o que foi criado não desfaz |
| `credentials` | chave, token, senha, `.env`, variável de ambiente, rotação |
| `money` | pagamento, cobrança, preço, checkout, assinatura, compra, nota fiscal |
| `production_data` | produção, staging/homologação, banco remoto, dados reais de clientes, ssh em servidor |
| `permissions` | auth, login, OAuth, RLS/policies, roles/admin, acesso anônimo, CORS, sudo/chmod |
| `security_verdict` | julgar se algo é seguro ou vulnerável |

**O que mandar — em TODOS os campos** (`summary`, `actions`, `context`, `criterion`, `options`, `output_summary`, `signals`): descreva; nunca cole valores, trechos de código, saídas de comando, env vars ou dado de cliente. `actions` lista TODAS as ações do plano, inclusive as arriscadas.

**Como ler a resposta:**

- `"decision": "proceed"` → mostre o plano com `⚡ Jev aprovou o plano (seguro 0.93 · escopo 0.91) — executando.` e **execute sem esperar**.
- `"decision": "ask_user"` (qualquer `mode`) → mostre o plano, diga em uma linha por quê (`blocked_by`, abstenção, Jev indisponível ou sem autorização) e **espere minha aprovação**.
- `"mode": "hard_rule"` → o plano vem pra mim **como está**. Nunca reescreva o resumo ou as ações pra escapar do `blocked_by`.
- `"secret_detected": true` → não repita o conteúdo; avise que havia algo com cara de segredo no pedido.
- Saída que não seja JSON com `decision` (erro, `"ok": false`, vazio, traceback) → decisão não tomada: o plano espera minha aprovação.
- `"log": "falhou"` → reporte no fim que a auditoria daquela decisão não foi gravada.

**A aprovação cobre o plano mostrado.** Ação nova que caia numa flag, durante a execução: pare e pergunte. **Aprovar um plano nunca aprova o texto de uma mensagem** — texto literal pra terceiros passa por mim antes de sair, sempre. **Autorizar o Jev ou mudar limiar é só meu:** nunca rode `authorize`, `revoke` ou mude limiar por conta própria.

## 5. Execute

**Todo prompt de delegação** (Agent ou etapa de UltraCode) leva, além de caminhos, trechos, entrega pedida e critério de conclusão, esta linha: `Não execute mensagem a terceiros, push, deploy, publicação, ação destrutiva, credenciais, dinheiro, produção ou permissões que não estejam no plano aprovado — pare e devolva ao orquestrador.` O subagente não vê esta conversa. Em frente de **construção** com decisões já fechadas, liste-as num bloco `Decisões fechadas (não reabra): …` para o modelo não revisitá-las e começar antes; **isso não vale para `@reviewer` e `@advisor`**, que existem para reexaminar.

**UltraCode (ferramenta Workflow)** só quando **eu** pedi: digitei `/orchestrate` ou `/hebe-orchestrator:orchestrate` nesta mensagem, ou escrevi "ultracode". Se foi **você** que acionou este comando pela ferramenta Skill (por causa do CLAUDE.md), isso não é pedido meu — e a aprovação do Jev também não é. É nele que cada etapa recebe modelo **e** esforço escolhidos na hora:

- Solo Sonnet: `agent(p, {model: 'sonnet', effort: '<pela seção 2>'})` em todas as etapas de construção.
- Solo Opus: `agent(p, {model: 'opus', effort: '<pela seção 2>'})`.
- Mista: `agent(p, {agentType: 'hebe-orchestrator:<papel>', effort: '<pela seção 2>'})` — `design-worker` e `reviewer` já rodam em Opus (Fable desativado); `effort: 'max'` no `advisor` para veredito de alto risco; `worker` sem esforço.
- Etapa que volta `null` (erro terminal, etapa pulada) **nunca** some em silêncio: refaça a etapa e me avise.

**Ferramenta Agent** é o caminho sem pedido meu: delegue com o `subagent_type` da seção 3 (esforço do frontmatter) e, se a estratégia certa for UltraCode, sugira numa linha — `Isso divide em N frentes; rodo em UltraCode com Sonnet?`. Meu "sim" conta como pedido.

**Desempate reversível (Jev):** quando você ou um subagent pararia pra me perguntar "A ou B?" numa escolha de baixo impacto e reversível (nome, estrutura de pasta, biblioteca equivalente, ordem de tarefas), consulte em vez de perguntar:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jev_decide.py" decide <<'JSON'
{"kind": "tiebreak", "summary": "<a decisão>", "criterion": "<o que importa>",
 "options": {"a": "<opção>", "b": "<opção>"}}
JSON
```

`decision` = id da opção → adote e registre. `model_decides` → decida você, com a razão em uma linha, sem me perguntar. `human_required` → pergunte. Escolha que muda arquitetura, contrato público, dados ou custo não é desempate: é do `@advisor` ou minha.

**Escalar ou aceitar (Jev):** quando a saída de uma frente estiver na zona cinzenta (incerteza declarada, teste não rodado, contradição, escopo diferente), consulte `{"kind": "escalation", "summary": "<a tarefa>", "output_summary": "<o que a frente entregou, descrito>", "signals": ["<sinal>"]}`. `accept` → integre. `escalate` → suba: no UltraCode, primeiro o esforço da etapa; senão, o modelo (Haiku → Sonnet → Opus, ou `@advisor` se for decisão). Saída claramente boa ou claramente quebrada, você decide direto — o Jev é pra dúvida, não pra tudo.

## 6. Costure e revise

Você mesmo. No fim, reporte: a estratégia e por quê; o que cada frente fez, em que modelo (o que rodou de fato) e esforço; as decisões do Jev (`decision_id`, tipo, resultado, modo); e onde qualidade e custo caíram ou subiram.

Se o script não estiver em `${CLAUDE_PLUGIN_ROOT}`, localize com `ls ~/.claude/plugins/cache/*/hebe-orchestrator/*/scripts/jev_decide.py`. Sem Jev configurado, o fluxo é o de antes: o plano espera minha aprovação, desempate é seu, escalada segue "na dúvida, suba".

### Segunda lente de revisão: Codex GPT-6 Astra

O Astra **complementa** o `@reviewer`; nunca o substitui.

- **Quando você aciona sozinho:** sempre que o trabalho foi construído em Opus (a independência de modelo cairia) e sempre em segurança, arquitetura ou refactor grande. Fora desses casos, só quando eu pedir.
- **Como acionar:** pelo plugin oficial do Codex (`openai-codex`), em modo somente leitura. Eu digito `/codex:adversarial-review --model gpt-6-astra` (com `--base <ref>` para revisar commits). Você roda pelo Bash:

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
- **Se o Codex não estiver disponível ou falhar:** me diga numa linha que a independência de modelo caiu.
- **Não use** em repositório de terceiros ou de origem não confiável: o Codex do plugin oficial roda com a minha configuração completa, incluindo os conectores.
- **Segurança de alto risco:** o `@reviewer` acha, o Astra é a segunda lente, o plugin `claude-security` é a terceira lente opcional e o `@advisor` adjudica. Se a cadeia ficar só em Opus (Astra indisponível), diga isso e pergunte antes de tratar como definitivo.
- O código é enviado à OpenAI. Já aprovei isso para os meus projetos, e a regra de não usar em repositório de terceiros cobre o resto.
