# 🎛️ hebe-orchestrate

**A Claude Code _plugin_ that routes every task to the right model — by the nature of the task, not by its price.**

> ⚠️ **This is a plugin, not a skill.** It installs through the plugin marketplace (`/plugin`), not by copying a folder into `~/.claude/skills/`. See [Install](#install).

Most "cost optimization" setups make everything cheaper and quietly make everything worse. This one does the opposite: it puts each piece of work on the model that actually fits it, and saves money only where saving costs nothing.

The rule it enforces: **economy comes from not wasting the top model on genuinely mechanical work — never from downgrading work that requires judgement.**

---

## The routing table

| Nature of the task | Agent | Model |
|---|---|---|
| Mechanical, zero judgement — grep, rename, dictated edit, run a command | `@worker` | `haiku` |
| **Anything touching code** — implement from a plan, read, map, refactor, test | `@code-worker` | `sonnet` |
| Complex/novel development, subtle bug fixing, reasoning-led code | *main session* | `opus` |
| Design & frontend — design system, prototype, UI/UX, layout, copy | `@design-worker` | `fable` |
| Critical review — code review, hunting security flaws, frontend critique | `@reviewer` | `fable` · high effort |
| Hard decisions, architecture, trade-offs, final verdict on high risk | `@advisor` | `opus` |

Models are set by **alias**, never by pinned ID — each agent always runs the newest model of its family, with no manual bump when a new version ships.

## Rules that don't bend

- **Code never goes to the cheapest model.** Reading, evaluating or writing code takes engineering judgement. The floor is Sonnet; the mechanical tier only does work with no decision in it.
- **Code has two tiers, not one.** Specified/routine/parallel work goes to Sonnet; complex, novel, or subtle work stays on Opus in your main session. Downgrading hard development costs iterations and bugs — and promoting boilerplate to the top model is the waste you were trying to avoid. Both mistakes cost.
- **High-risk security never closes on a single model.** The reviewer *finds*; the advisor *adjudicates*. Different models catch different bugs.
- **When in doubt between two tiers, go up.** The cost of downgrading — rework, a shipped bug, poor design — almost always exceeds the tokens saved.
- **Delegation offloads the work, not the responsibility.** Cheap output isn't truth until the strong model reviews what matters: correctness, security, and every money or permission flow.

## Install

This is a **plugin**, distributed as a marketplace. From inside Claude Code:

```
/plugin marketplace add HericlisBezerra/hebe-orchestrate
/plugin install hebe-orchestrator@hebe-orchestrator
/reload-plugins
```

Then confirm:

```
/help      → should list /orchestrate
/agents    → should list worker, code-worker, design-worker, reviewer, advisor
```

> The repository is `hebe-orchestrate`; the plugin inside it is `hebe-orchestrator` — hence `hebe-orchestrator@hebe-orchestrator` (plugin name @ marketplace name).

## Use

**Automatic** — it plans, shows you the delegation plan for approval, then executes:

```
/orchestrate implement the users CRUD with tests
```

**Manual** — call an agent directly when you want to force the routing:

```
@code-worker  @design-worker  @reviewer  @advisor  @worker
```

**Doctrine on demand** — `/orchestrator-guide` loads the full reasoning. It's marked `disable-model-invocation`, so it costs zero context until you ask for it.

## What's inside

```
hebe-orchestrate/
├── .claude-plugin/marketplace.json     # makes the repo installable as a marketplace
└── hebe-orchestrator/
    ├── .claude-plugin/plugin.json
    ├── agents/                         # 5 subagents, isolated context
    │   ├── worker.md                   # haiku · low
    │   ├── code-worker.md              # sonnet · medium
    │   ├── design-worker.md            # fable · medium
    │   ├── reviewer.md                 # fable · high
    │   └── advisor.md                  # opus · high
    ├── commands/orchestrate.md         # /orchestrate <task>
    ├── skills/orchestrator-guide/      # the doctrine (loads on demand)
    └── settings.example.json
```

Subagents run in their **own context window** — delegating moves tokens out of your main conversation, and only the summary comes back.

## When *not* to orchestrate

Honesty matters more than adoption:

- **Small, single task** — orchestration costs context and latency on every handoff. Run it directly on the model that fits, and don't downgrade it just to look cheap.
- **Highly interdependent context** — a subagent runs isolated and only receives what you put in its prompt. If handing over the context is expensive or fragile, keep it in the main session.

The plugin is instructed to tell you when orchestration isn't worth it, instead of forcing the pipeline.

## A note on the numbers

A published Anthropic benchmark put a strong planner with Sonnet workers at ~96% of top-model performance for ~46% of the price. That's their measurement, not a promise about your codebase — measure your own. And the target here is **quality with economy**, not the smallest possible number.

## Licence

MIT — see [LICENSE](LICENSE). Built by **HeBeDigital** ([@hericlisbezerra](https://github.com/HericlisBezerra)).
