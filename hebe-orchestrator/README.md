# hebe-orchestrator — orquestração multi-modelo pro Claude Code (e variante Codex)

> 🔒 **Fable desativado (estado oficial desta versão):** `@design-worker` e `@reviewer` rodam em Opus até nova ordem do usuário ou até sair um Fable novo. Para reativar, só com ordem do usuário: trocar `model: opus` por `model: fable` nos dois agentes. O Codex GPT-6 Astra entra como segunda lente automática de revisão (seção "Segunda lente de revisão").

Empacota a estratégia **qualidade-primeiro** "cada tarefa no modelo certo pela natureza dela" num plugin reutilizável em qualquer projeto. O objetivo é a melhor qualidade por peça gastando o mínimo que essa qualidade permite — economia vem de não desperdiçar o modelo topo em trabalho mecânico, nunca de rebaixar o que exige julgamento.

## O que vem dentro

```
hebe-orchestrator/
├── .claude-plugin/plugin.json   # manifesto Claude Code
├── .codex-plugin/plugin.json    # manifesto Codex (aponta só pra codex-skills/)
├── agents/                      # subagents = contexto ISOLADO (offloada tokens da conversa)
│   ├── worker.md               # haiku · sem esforço        → SÓ mecânico sem julgamento
│   ├── code-worker.md          # sonnet · high              → implementação especificada + análise
│   ├── design-worker.md        # opus · medium (Fable off)  → design system, protótipo, UI/UX, frontend
│   ├── reviewer.md             # opus · high (Fable off)    → code review, falhas de segurança, crítica de frontend
│   └── advisor.md              # opus · high                → decisão difícil, veredito de segurança (max)
├── skills/
│   └── orchestrator-guide/
│       ├── SKILL.md             # doutrina · disable-model-invocation (custo ZERO até chamar)
│       └── references/hosts.md  # matriz papel × host (Claude e Codex), escala de esforço, particularidades
├── codex-skills/
│   └── orchestrate/             # a mesma doutrina para o app Codex (Luna, Sol, Astra, Terra)
├── commands/
│   └── orchestrate.md           # /orchestrate <tarefa> → planeja, passa pelo portão do Jev e delega
├── scripts/
│   ├── jev.py                   # cliente TypeSafe/Jev (credencial protegida, só biblioteca padrão)
│   └── jev_decide.py            # decisões assertivas: plan_gate, tiebreak, escalation + regras duras
├── tests/                       # python3 -m unittest discover -s tests (sem rede)
├── settings.example.json        # sessão principal (Opus) em medium
└── README.md
```

### Por que essa divisão (higiene de contexto)
- **Subagents** rodam em contexto próprio → delegar tira tokens da sua conversa principal; só o resumo volta.
- **Skill** usa disclosure progressiva → a doutrina só entra no contexto quando você chama `/orchestrator-guide`. Não infla toda conversa.
- **Nada pesado no CLAUDE.md** (que é sempre carregado). O CLAUDE.md do seu projeto fica só com regras curtas, se quiser.

## Como instalar

O jeito recomendado no Claude Code é via marketplace local. Coloque a pasta `hebe-orchestrator/` dentro de um repositório de marketplace (ou use como marketplace de diretório único) e rode:

```
/plugin marketplace add /caminho/para/o/diretorio-do-marketplace
/plugin install hebe-orchestrator
```

> Confira o passo exato em https://code.claude.com/docs/en/plugins — o comando `/plugin` mostra o fluxo interativo de instalação. Para uso pessoal, instale em escopo de usuário pra ter o plugin em todos os projetos.

Depois de instalar, valide com:
```
/help          # deve listar o comando /orchestrate
/agents        # deve listar worker, code-worker, design-worker, reviewer, advisor
```

## Jev: decisões assertivas (opcional)

Sem o Jev o plugin funciona como antes: todo plano orquestrado espera sua aprovação. Com ele, o orquestrador para de esperar em três situações — e só nelas:

- **`plan_gate`** — plano local e reversível, dentro do escopo, executa direto (segurança ≥ 0.85; escopo ≥ 0.70).
- **`tiebreak`** — "A ou B?" reversível e de baixo impacto é decidido sem te perguntar (limiar 0.65).
- **`escalation`** — saída de worker na zona cinzenta sobe de nível ou é aceita (aceita só com P(escalar) ≤ 0.20).

Três camadas em código, antes de qualquer rede: (1) no `plan_gate`, cada ação precisa começar com um verbo de trabalho local conhecido — verbo arriscado ou desconhecido, comando externo ou ação sem verbo volta pra você; (2) uma rede de padrões pega mensagem a terceiros, push, deploy, publicação, destrutivo, credenciais, dinheiro, produção, permissões e veredito de segurança; (3) as flags que o orquestrador declara. A rede de padrões não é uma garantia — por isso a lista de ações locais existe. **Os limiares (0.85 na segurança e 0.70 no escopo do plano, 0.65, 0.80) ainda não foram calibrados com uso real**; autorizar o Jev e mudar limiar é só seu.

**Configurar (uma vez por máquina):**

```bash
python3 scripts/jev.py configure --web      # chave TypeSafe em ~/.config/hebe-brain/typesafe.json (0600), fora do Git
python3 scripts/jev_decide.py authorize --powers plan_gate,tiebreak,escalation
python3 scripts/jev_decide.py status        # confere poderes, limiares e credencial, sem rede
```

A chave é a mesma do `hebe-orchestrator-codex`; se ela já existe, pule o primeiro comando. `authorize` registra a autorização permanente de enviar **resumos curtos** das decisões ao TypeSafe — nunca código, conversa ou dado de cliente; um filtro recusa o envio se o texto parecer conter segredo. `revoke` desliga tudo. Cada decisão fica em `~/.config/hebe-brain/jev-decisions.jsonl` pra auditoria (`jev_decide.py log`).

## Estratégia e esforço — decididos pela tarefa

A primeira decisão do `/orchestrate` é a **estratégia**:

- **Direto** — uma peça só: a sessão principal resolve.
- **UltraCode solo** — tarefa grande e divisível, frentes da mesma natureza: todas as etapas no mesmo modelo, Sonnet pro especificado/moderado ou Opus pro difícil. Não divide entre modelos o que um modelo só faz bem.
- **Orquestração mista** — frentes de naturezas diferentes: cada uma no seu nível (Haiku, Sonnet, Opus; Fable desativado).

Depois, o **esforço de cada frente** pela dificuldade: comece em `medium` (padrão do Opus, que segundo o guia da Anthropic iguala ou supera o `high` da versão anterior), `high` pro especificado longo e o julgamento que já pesa, e reserve `xhigh` (Extra) e `max` para onde você mediu ganho — `max` pro problema único e caro de errar, nunca por garantia. UltraCode não é um nível acima do Max — é a estratégia multiagente, com esforço próprio em cada etapa.

Onde isso é modulável: nas etapas do UltraCode (Workflow), cada uma com modelo e esforço escolhidos na hora — e o UltraCode só roda quando você digita `/orchestrate` ou escreve "ultracode"; quando o Claude aciona a orquestração sozinho, ele sugere numa linha. Pela ferramenta Agent vale o frontmatter (`@code-worker` high; `@design-worker` medium; `@reviewer` e `@advisor` high; `@worker` sem, porque o Haiku não aceita). A sessão principal só você muda — o app não deixa uma sessão reprecificar os próprios turnos; o orquestrador lê o nível atual e pede o ajuste numa linha quando precisar. O Opus vem em `medium` por padrão no app, e o `settings.example.json` mantém a sessão principal em `medium`. **Não ligue o `ultracode` global** — na versão atual ele trava a sessão em xhigh (Max indisponível) e transforma toda tarefa em workflow.

## Segunda lente de revisão (Codex GPT-6 Astra)

O Astra **complementa** o `@reviewer`; nunca o substitui. A regra é a mesma no `/orchestrate`, na skill `orchestrator-guide` e no `@reviewer`.

- **Quando o orquestrador aciona sozinho:** sempre que o trabalho foi construído em Opus (a independência de modelo cairia) e sempre em segurança, arquitetura ou refactor grande. Fora desses casos, só quando o usuário pedir.
- **Como acionar:** pelo plugin oficial do Codex (`openai-codex`), em modo somente leitura. Você digita `/codex:adversarial-review --model gpt-6-astra` (com `--base <ref>` para revisar commits). O orquestrador roda pelo Bash:

  ```bash
  node "$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/ | sort -V | tail -1)scripts/codex-companion.mjs" adversarial-review --model gpt-6-astra --scope working-tree --json
  ```

  Isso vale para mudanças ainda não commitadas; para commits, `--base <ref>` no lugar de `--scope working-tree`. Em segundo plano quando for longo. O retorno é um veredito curto em JSON.
- **O que fazer com o resultado:** conferir cada achado no código antes de agir. Achado do Codex é hipótese, não ordem. Segundo o piloto de 2026-10-26, ele achou cerca de 16% do que o Opus achou, sem nenhum alarme falso, e pegou defeitos que o Opus deixou passar (fluxo de dados, ordem das gravações, garantias de apagamento). Por isso complementa e não substitui.
- **Se o Codex não estiver disponível ou falhar:** o orquestrador diz numa linha que a independência de modelo caiu.
- **Não usar** em repositório de terceiros ou de origem não confiável: o Codex do plugin oficial roda com a sua configuração completa, incluindo os conectores.
- **Segurança de alto risco:** o `@reviewer` acha, o Astra é a segunda lente, o plugin `claude-security` é a terceira lente opcional e o `@advisor` adjudica.
- O código é enviado à OpenAI. Aprove isso só para os seus projetos; a regra de não usar em repositório de terceiros cobre o resto.

## Variante Codex

A mesma doutrina (estratégia, esforço por frente, Jev) roda no app Codex com a variável de host trocando os modelos: mecânico no `gpt-6-luna`, código no `gpt-6-sol`, julgamento difícil e revisão independente no `gpt-6-astra`, e `gpt-5.6-terra` como reserva (não existe GPT-6 Terra). A matriz completa, com as particularidades de cada modelo e o que ainda não foi verificado, está em `skills/orchestrator-guide/references/hosts.md`. A skill do Codex fica em `codex-skills/orchestrate/`, com invocação implícita desligada para não disputar com o `hebe-orchestrator-codex`. **Ela ainda não foi instalada nem testada no app Codex.**

## Como usar

**Modo automático:**
```
/orchestrate implementar o CRUD de usuários com testes
```
Ele planeja, passa o plano pelo portão do Jev (ou pela sua aprovação, se o Jev não liberar), e executa distribuindo entre os workers.

**Modo manual (controle total):**
- `/model opusplan` → forte no plano, Sonnet na execução (atalho do Padrão 1; tira o dev complexo do Opus, então use só quando a tarefa for de rotina).
- Invoque explícito quando quiser garantir o roteamento: `@worker`, `@code-worker`, `@design-worker`, `@reviewer`, `@advisor`.
- `/orchestrator-guide` → carrega a doutrina de quando delegar (só quando você quiser).

## Ajuste de modelo

O `settings.example.json` põe a sessão principal (Opus) em `medium`. Copie o `modelSettings` pro `~/.claude/settings.json`. Os `model:` dos subagents usam **alias** (`opus`, `sonnet`, `fable`, `haiku`) — assim cada agente roda sempre no modelo **mais atual** da sua família, sem número fixo e sem precisar bumpar quando sair versão nova. Quem resolve o alias é o Claude Code embutido no app. `design-worker` e `reviewer` rodam em Opus, porque o **Fable está desativado** até nova ordem do usuário ou até sair um Fable novo; para reativar, troque `model: opus` por `model: fable` nos dois agentes, só com ordem do usuário.

## Ressalvas honestas

- **Overhead:** orquestrar tem custo de contexto e latência por handoff. Em tarefa pequena, rodar Sonnet direto pode sair mais barato. O plugin já é instruído a avisar quando não vale a pena.
- **Auto-delegação é irregular:** se o Claude não chamar o subagent sozinho, invoque com `@nome`.
- **Números variam:** o "~96% da performance por ~46% do custo" é benchmark da Anthropic, não promessa pro seu código. Meça o seu uso. E o alvo aqui é qualidade com economia, não o menor número possível.
- **Código nunca vai pra Haiku:** ler/entender/auditar código exige julgamento → piso Sonnet. Haiku só faz o braçal mecânico. Design e revisão não descem pra Sonnet/Haiku (rodam em Opus, com o Fable desativado); segurança de alto risco não fecha num modelo só (`@reviewer` acha, o Astra é a segunda lente, `@advisor` adjudica).
- **Código tem dois níveis:** especificado/rotina/fan-out → `@code-worker` (Sonnet); desenvolvimento complexo/novo/correção sutil → Opus (sua sessão principal). Rebaixar dev complexo pra Sonnet custa iteração; subir boilerplate pra Opus é "Opus pra tudo". Acerte pela natureza.
