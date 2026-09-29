# Contributing

Contributions are welcome — especially routing rules learned from real use.

## The principle to preserve

Every change should serve one idea: **each task on the model that fits its nature.**
Economy comes from not wasting the top model on mechanical work — never from
downgrading work that requires judgement.

A PR that makes something cheaper *and* worse is not an optimization.

## Changing an agent

Agents live in `hebe-orchestrator/agents/`. Keep the `model:` field as an **alias**
(`opus`, `sonnet`, `fable`, `haiku`) rather than a pinned model ID, so each agent
follows the newest model of its family without a manual bump.

If you add an agent, say plainly in its description what it is **not** for. Half the
value of this plugin is agents refusing work that belongs to another tier.

## Changing the doctrine

`hebe-orchestrator/skills/orchestrator-guide/SKILL.md` is the reasoning behind the
routing table. If you change a rule there, change it in `commands/orchestrate.md`,
`skills/orchestrator-guide/references/hosts.md` and `codex-skills/orchestrate/SKILL.md` too —
they must not disagree.

## Versioning

Bump `version` in `.claude-plugin/marketplace.json`, `hebe-orchestrator/.claude-plugin/plugin.json`
and `hebe-orchestrator/.codex-plugin/plugin.json`, and add the entry to `CHANGELOG.md`. The version
bump is what triggers an update for existing users; without it, nobody gets your change.
`python3 -m unittest discover -s hebe-orchestrator/tests` checks that they agree.

## Licence

By contributing, you agree your contribution is licensed under the MIT License.
