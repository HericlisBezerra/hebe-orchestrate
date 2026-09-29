# hebe-orchestrator — orquestração multi-modelo pro Claude Code (e variante Codex)

Empacota a estratégia **qualidade-primeiro** "cada tarefa no modelo certo pela natureza dela" num plugin reutilizável em qualquer projeto. O objetivo é a melhor qualidade por peça gastando o mínimo que essa qualidade permite — economia vem de não desperdiçar o modelo topo em trabalho mecânico, nunca de rebaixar o que exige julgamento.

## O que vem dentro

```
hebe-orchestrator/
├── .claude-plugin/plugin.json   # manifesto Claude Code
├── .codex-plugin/plugin.json    # manifesto Codex (aponta só pra codex-skills/)
├── agents/                      # subagents = contexto ISOLADO (offloada tokens da conversa)
│   ├── worker.md                # haiku (Haiku 4.5) · sem esforço → SÓ mecânico sem julgamento
│   ├── code-worker.md           # sonnet (Sonnet 5.5) · high    → implementação especificada + análise
│   ├── design-worker.md         # fable (Fable 5.1) · xhigh     → design system, protótipo, UI/UX, frontend
│   ├── reviewer.md              # fable (Fable 5.1) · xhigh     → code review, falhas de segurança, crítica de frontend
│   └── advisor.md               # opus (Opus 5.5) · xhigh       → decisão difícil, veredito de segurança (max)
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
├── settings.example.json        # sessão principal (Opus 5.5) em Extra
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
- **UltraCode solo** — tarefa grande e divisível, frentes da mesma natureza: todas as etapas no mesmo modelo, Sonnet 5.5 pro especificado/moderado ou Opus 5.5 pro difícil. Não divide entre modelos o que um modelo só faz bem.
- **Orquestração mista** — frentes de naturezas diferentes: cada uma no seu nível (Haiku, Sonnet, Opus, Fable).

Depois, o **esforço de cada frente** pela dificuldade: `low`/`medium` pro mecânico e especificado curto, `high` pro especificado longo, `xhigh` (Extra) como ponto de partida de todo julgamento, `max` pro problema único e caro de errar. UltraCode não é um nível acima do Max — é a estratégia multiagente, com esforço próprio em cada etapa.

Onde isso é modulável: nas etapas do UltraCode (Workflow), cada uma com modelo e esforço escolhidos na hora — e o UltraCode só roda quando você digita `/orchestrate` ou escreve "ultracode"; quando o Claude aciona a orquestração sozinho, ele sugere numa linha. Pela ferramenta Agent vale o frontmatter (`@code-worker` high; `@design-worker`, `@reviewer`, `@advisor` xhigh; `@worker` sem, porque o Haiku não aceita). A sessão principal só você muda — o app não deixa uma sessão reprecificar os próprios turnos; o orquestrador lê o nível atual e pede o ajuste numa linha quando precisar. O Opus 5.5 vem em `medium` por padrão no app: o `settings.example.json` o coloca em Extra. **Não ligue o `ultracode` global** — na versão atual ele trava a sessão em xhigh (Max indisponível) e transforma toda tarefa em workflow.

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

O `settings.example.json` põe a sessão principal (Opus 5.5) em Extra. Copie o `modelSettings` pro `~/.claude/settings.json`. Os `model:` dos subagents usam **alias** (`opus`, `sonnet`, `fable`, `haiku`) — assim cada agente roda sempre no modelo **mais atual** da sua família, sem precisar bumpar quando sair versão nova. Quem resolve o alias é o Claude Code embutido no app: o `sonnet` passa a ser o Sonnet 5.5 quando o app se atualizar. `design-worker` e `reviewer` rodam em Fable. **Não há fallback automático de modelo no Claude Code** — quando o crédito semanal do Fable acaba, a doutrina manda o orquestrador reinvocar o mesmo agente com override para Opus e **avisar você**.

## Ressalvas honestas

- **Overhead:** orquestrar tem custo de contexto e latência por handoff. Em tarefa pequena, rodar Sonnet direto pode sair mais barato. O plugin já é instruído a avisar quando não vale a pena.
- **Auto-delegação é irregular:** se o Claude não chamar o subagent sozinho, invoque com `@nome`.
- **Números variam:** o "~96% da performance por ~46% do custo" é benchmark da Anthropic, não promessa pro seu código. Meça o seu uso. E o alvo aqui é qualidade com economia, não o menor número possível.
- **Código nunca vai pra Haiku:** ler/entender/auditar código exige julgamento → piso Sonnet. Haiku só faz o braçal mecânico. Design e revisão (Fable) não descem pra Sonnet/Haiku — sem Fable, sobem pra Opus; segurança de alto risco não fecha num modelo só (`@reviewer` acha, `@advisor` adjudica).
- **Código tem dois níveis:** especificado/rotina/fan-out → `@code-worker` (Sonnet); desenvolvimento complexo/novo/correção sutil → Opus (sua sessão principal). Rebaixar dev complexo pra Sonnet custa iteração; subir boilerplate pra Opus é "Opus pra tudo". Acerte pela natureza.
