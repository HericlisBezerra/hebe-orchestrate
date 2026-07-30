# hebe-orchestrator — plugin de orquestração multi-modelo pro Claude Code

Empacota a estratégia **qualidade-primeiro** "cada tarefa no modelo certo pela natureza dela" num plugin reutilizável em qualquer projeto. O objetivo é a melhor qualidade por peça gastando o mínimo que essa qualidade permite — economia vem de não desperdiçar o modelo topo em trabalho mecânico, nunca de rebaixar o que exige julgamento.

## O que vem dentro

```
hebe-orchestrator/
├── .claude-plugin/
│   └── plugin.json              # manifesto do plugin
├── agents/                      # subagents = contexto ISOLADO (offloada tokens da conversa)
│   ├── worker.md                # haiku (Haiku 4.5) · low     → SÓ mecânico sem julgamento
│   ├── code-worker.md           # sonnet (Sonnet 5) · medium → implementação especificada + análise (dev complexo escala pra Opus)
│   ├── design-worker.md         # fable (Fable 5) · medium  → design system, protótipo, UI/UX, frontend
│   ├── reviewer.md              # fable (Fable 5) · high    → code review, caça a falhas de segurança, crítica de frontend
│   └── advisor.md               # opus (Opus 5) · high  → decisão difícil, veredito de segurança
├── skills/
│   └── orchestrator-guide/
│       └── SKILL.md             # doutrina "modelo certo por tarefa" · disable-model-invocation (custo ZERO até chamar)
├── commands/
│   └── orchestrate.md           # /orchestrate <tarefa> → planeja e delega automaticamente
├── settings.example.json        # exemplo de default de modelo (opusplan)
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

## Como usar

**Modo automático:**
```
/orchestrate implementar o CRUD de usuários com testes
```
Ele planeja, mostra o plano de delegação, e executa distribuindo entre os workers.

**Modo manual (controle total):**
- `/model opusplan` → forte no plano, Sonnet na execução (o Padrão 1 num comando).
- Invoque explícito quando quiser garantir o roteamento: `@worker`, `@code-worker`, `@design-worker`, `@reviewer`, `@advisor`.
- `/orchestrator-guide` → carrega a doutrina de quando delegar (só quando você quiser).

## Ajuste de modelo (opcional)

O `settings.example.json` mostra como definir um default de modelo. Copie o conteúdo pro `.claude/settings.json` do projeto (ou `~/.claude/settings.json` pra global) se quiser que o projeto já abra em `opusplan`. Os `model:` dos subagents usam **alias** (`opus`, `sonnet`, `fable`, `haiku`) — assim cada agente roda sempre no modelo **mais atual** da sua família, sem precisar bumpar quando sair versão nova. `design-worker` e `reviewer` rodam em Fable. **Não há fallback automático de modelo no Claude Code** — quando o crédito semanal do Fable acaba, a doutrina manda o orquestrador reinvocar o mesmo agente com override para Opus e **avisar você**.

## Ressalvas honestas

- **Overhead:** orquestrar tem custo de contexto e latência por handoff. Em tarefa pequena, rodar Sonnet direto pode sair mais barato. O plugin já é instruído a avisar quando não vale a pena.
- **Auto-delegação é irregular:** se o Claude não chamar o subagent sozinho, invoque com `@nome`.
- **Números variam:** o "~96% da performance por ~46% do custo" é benchmark da Anthropic, não promessa pro seu código. Meça o seu uso. E o alvo aqui é qualidade com economia, não o menor número possível.
- **Código nunca vai pra Haiku:** ler/entender/auditar código exige julgamento → piso Sonnet. Haiku só faz o braçal mecânico. Design e revisão (Fable) não descem de Fable→Opus; segurança de alto risco não fecha num modelo só (`@reviewer` acha, `@advisor` adjudica).
- **Código tem dois níveis:** especificado/rotina/fan-out → `@code-worker` (Sonnet); desenvolvimento complexo/novo/correção sutil → Opus (sua sessão principal). Rebaixar dev complexo pra Sonnet custa iteração; subir boilerplate pra Opus é "Opus pra tudo". Acerte pela natureza.
