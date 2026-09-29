# 🎛️ hebe-orchestrate

**A Claude Code _plugin_ that picks the right strategy, model and reasoning effort for every task — by its nature and difficulty, not by its price. Ships a Codex variant of the same doctrine.**

> ⚠️ **This is a plugin, not a skill.** It installs through the plugin marketplace (`/plugin`), not by copying a folder into `~/.claude/skills/`. See [Install](#install).

Most "cost optimization" setups make everything cheaper and quietly make everything worse. This one does the opposite: it puts each piece of work on the model that actually fits it, and saves money only where saving costs nothing.

The rule it enforces: **economy comes from not wasting the top model on genuinely mechanical work — never from downgrading work that requires judgement.**

---

## Strategy first

The first decision is not the model, it's the strategy. Sonnet 5.5 and Opus 5.5 each solve a lot of large tasks alone, and every hand-off between models costs context and latency.

| Strategy | When | How |
|---|---|---|
| **Direct** | One piece, fits one context | The main session does it |
| **Solo UltraCode** | Large and divisible, fronts of the same nature | Multi-agent workflow with every stage on one model — Sonnet 5.5 for specified/moderate work, Opus 5.5 for hard work |
| **Mixed orchestration** | Fronts of different natures | Each front on its own tier (table below) |

Solo UltraCode and mixed orchestration run as a multi-agent workflow only when you typed the command or wrote "ultracode"; when Claude starts orchestrating on its own, it suggests it in one line.

Then the **effort of each front**, by difficulty: `low`/`medium` for mechanical and short specified work, `high` for long specified work, `xhigh` as the starting point for anything that takes judgement, `max` for a single hard problem that is expensive to get wrong. UltraCode is not a level above Max — it's the multi-agent strategy, with its own effort per stage.

## The routing table

| Nature of the task | Agent | Claude model | Codex model |
|---|---|---|---|
| Mechanical, zero judgement — grep, rename, dictated edit, run a command | `@worker` | `haiku` | `gpt-6-luna` |
| **Specified code + analysis** — implement from a plan, read, map, refactor, test | `@code-worker` | `sonnet` | `gpt-6-sol` |
| Complex/novel development, subtle bug fixing, reasoning-led code | *main session* | `opus` | root `gpt-6-sol` |
| Design & frontend — design system, prototype, UI/UX, layout, copy | `@design-worker` | `fable` | `gpt-6-astra` |
| Critical review — code review, hunting security flaws, frontend critique | `@reviewer` | `fable` (`opus` if Fable built it) | the strong model that didn't build it |
| Hard decisions, architecture, trade-offs, final verdict on high risk | `@advisor` | `opus` | `gpt-6-astra` |

`gpt-5.6-terra` is the Codex fallback for Sol (there is no GPT-6 Terra). Full matrix, model particularities and what is still unverified: [`references/hosts.md`](hebe-orchestrator/skills/orchestrator-guide/references/hosts.md).

Models are set by **alias**, never by pinned ID — each agent always runs the newest model of its family that your Claude Code version knows, with no manual bump when a new version ships. As of September 2026 that is Haiku 4.5, Sonnet 5.5, Opus 5.5 and Fable 5.1.

## Rules that don't bend

- **Code never goes to the cheapest model.** Reading, evaluating or writing code takes engineering judgement. The floor is Sonnet; the mechanical tier only does work with no decision in it.
- **Code has two tiers, not one.** Specified/routine/parallel work goes to Sonnet; complex, novel, or subtle work stays on Opus in your main session. Downgrading hard development costs iterations and bugs — and promoting boilerplate to the top model is the waste you were trying to avoid. Both mistakes cost.
- **High-risk security never closes on a single model.** The reviewer *finds*; the advisor *adjudicates*. Different models catch different bugs.
- **Whoever builds doesn't review.** Fable-built design is reviewed by the reviewer running on Opus.
- **Don't split across models what one model does well.** Solo UltraCode on Sonnet 5.5 or Opus 5.5 beats a mixed pipeline when the fronts are all the same kind of work.
- **When in doubt between two tiers, go up.** The cost of downgrading — rework, a shipped bug, poor design — almost always exceeds the tokens saved.
- **Delegation offloads the work, not the responsibility.** Cheap output isn't truth until the strong model reviews what matters: correctness, security, and every money or permission flow.

## Jev: assertive decisions (optional)

The slowest part of an orchestrated run is usually a human: every plan waits for approval, every "A or B?" waits for an answer. With a [TypeSafe](https://typesafe.ai) key, the orchestrator hands three kinds of decision to **Jev**, a small fast model that returns typed judgements with probabilities:

| Power | Decides on its own when | Otherwise |
|---|---|---|
| `plan_gate` | the plan is local and reversible (≥ 0.85) and in scope (≥ 0.70) | the plan waits for you |
| `tiebreak` | a low-impact, reversible "A or B?" has a clear winner (≥ 0.65) | the main model decides and says why |
| `escalation` | a worker's shaky output is still consistent (P(escalate) ≤ 0.20) | it goes one tier up |

Jev never routes models, and it never decides anything that is yours. Three code layers run before any network call: in `plan_gate`, every action must start with a known local-work verb (a risky or unknown verb, an external command or a verb-less action goes back to you); a pattern net catches messages to other people, push, deploy, publishing, destructive actions, credentials, money, production data, permissions and security verdicts; and the orchestrator declares flags. The pattern net is a net, not a guarantee — that's why the allow-list exists. Thresholds (0.85 safety / 0.70 scope, 0.65, 0.80) are not calibrated against real use yet. Missing key, service down, low confidence or secret-looking text all fall back to the pre-Jev flow — it stops accelerating, nothing breaks. Every decision is logged locally for audit.

```bash
python3 hebe-orchestrator/scripts/jev.py configure --web
python3 hebe-orchestrator/scripts/jev_decide.py authorize --powers plan_gate,tiebreak,escalation
```

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

**Automatic** — it picks the strategy, plans each front's model and effort, passes the plan through the Jev gate (or your approval, when Jev doesn't clear it), then executes:

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
    ├── .codex-plugin/plugin.json       # Codex manifest (points only at codex-skills/)
    ├── agents/                         # 5 subagents, isolated context · default effort
    │   ├── worker.md                   # haiku · none (Haiku takes no effort)
    │   ├── code-worker.md              # sonnet · high
    │   ├── design-worker.md            # fable · xhigh
    │   ├── reviewer.md                 # fable · xhigh
    │   └── advisor.md                  # opus · xhigh
    ├── codex-skills/orchestrate/       # the same doctrine for the Codex app
    ├── commands/orchestrate.md         # /orchestrate <task>
    ├── skills/orchestrator-guide/      # the doctrine (loads on demand)
    ├── scripts/                        # jev.py (TypeSafe client) · jev_decide.py (gates + hard rules)
    ├── tests/                          # python3 -m unittest discover -s tests — no network
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
