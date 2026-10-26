# Changelog

## 0.6.0-exp.1 — 2026-10-26 (branch experimental `for-claude+gpt`, fora da `main`)

**Experimento de 15 a 30 dias: o Claude coordena, o Codex soma.** Detalhes, números do piloto e hipóteses: `hebe-orchestrator/docs/EXPERIMENTO-CLAUDE-GPT.md`.

- **Fable desativado na branch** (decisão do usuário): `@design-worker` e `@reviewer` em Opus 5.5 (`medium` e `high`). Antes era um ajuste local, fora do repositório.
- **`scripts/codex_bridge.py`** — ponte com o plugin oficial `openai-codex`:
  - `review`: revisão adversarial do Codex como segunda lente de outro fornecedor, somente leitura, devolvendo um JSON compacto. Sem `--base` revisa a árvore de trabalho; com `--base` revisa commits e recusa árvore suja. Recusa revisar o que o próprio Codex construiu.
  - `build`: o Codex constrói numa worktree própria, sem commit. O pedido vai com proibições de escopo, e o resultado volta com `scope_flags` sobre o diff (dependência, lockfile, notas/vault/ADR, logs de teste, arquivo apagado, fora da pasta).
  - `outcome` e `report`: diário privado do experimento (`~/.config/hebe-brain/codex-experiment.jsonl`, 0600) para medir qualidade e eficiência.
  - `policy`: pastas bloqueadas para o Codex.
  - `cleanup`: remove worktrees criadas pela ponte.
  - Codex isolado (decisão do `@advisor`): `CODEX_HOME` próprio com login separado, sem MCP, sem plugins, sem memória, sem AGENTS.md global, sandbox sem rede; app-server direto por chamada, com ambiente mínimo; em timeout ou interrupção (SIGINT/SIGTERM) encerra só o grupo de processos da chamada.
  - Proteções: recusa texto com segredo antes de qualquer chamada, e também segredo no diff e nos arquivos novos que a revisão enviaria; a política bloqueia a pasta e o repositório que a contém; `--copy` só aceita pasta ignorada pelo Git, sem symlink nem nome de segredo; o Codex recebe ambiente mínimo; timeout cancela só os jobs da própria chamada; falha do Codex nunca vira revisão válida; worktree e branch são removidas se algo falha antes do Codex; depois que o Codex começou, a worktree é preservada; `cleanup` nunca apaga branch com commits fora da base; comandos git sem hooks nem fsmonitor; `doctor` trava a versão 1.0.6 do plugin.
- **Regras** (`/orchestrate` seção 3b; skill, seção "Codex como executor"):
  - Revisão relevante = `@reviewer` (Opus) **mais** Codex Sol: complemento, nunca substituto.
  - Construção pelo Codex só com pedido fechado, testes, uma pasta e sem decisão de produto aberta, com o Claude fazendo outra frente. Padrão: GPT-6 Astra em `high`; o Claude testa, revisa e commita.
  - O Codex nunca revisa o que construiu.
  - A segunda lente de segurança de alto risco passa a ser o plugin `claude-security`.
- **Piloto em código real de cliente** (anonimizado):
  - Revisão do Codex: ~16% do que o Opus achou, 100% de acerto, problemas reais que o Opus não pegou, ~1 mil tokens do Claude por revisão.
  - Construção (nota cega): Opus 7, Astra `high` 6,5, Sol `high` 6, `medium` 5.
  - Nenhum defeito real do Codex, mas desvios de escopo repetidos.
- Testes: `test_codex_bridge.py` (companion falso, sem rede). O teste de versões aceita sufixo de pré-lançamento.

## Não lançado (próxima versão) — esforço no Opus 5.5 conforme o guia oficial

Base: *Prompting Claude Opus 5.5* (platform.claude.com, seção "Calibrate effort") e a newsletter Gruponomics "Opus 5.5: como pedir".

- **`medium` é o ponto de partida** no Opus 5.5 (padrão oficial; iguala ou supera o Opus 5 em `high`). `high` para julgamento que já pesa. `xhigh` e `max` só com ganho **medido** na tarefa, e `max` nunca por garantia. Antes, `xhigh` era o ponto de partida de todo trabalho que pensa.
- No mesmo nível o Opus 5.5 pensa mais por turno que o Opus 5, principalmente em `xhigh` e `max`: o `xhigh` de antes custa mais agora.
- **Para pensar menos, baixe o esforço** antes de mexer no texto. Proibido "pense com calma / passo a passo" nos prompts de delegação.
- Prompts de delegação de **construção** ganham o bloco `Decisões fechadas (não reabra)`. Fora de `@reviewer` e `@advisor`, que existem para reexaminar.
- `@advisor`: `xhigh` → `high` (`max` continua na etapa do veredito de segurança). `@design-worker` e `@reviewer` seguem em `xhigh` no Fable, sem dado oficial para esse modelo.
- `settings.example.json`: a sessão principal (Opus 5.5) passa de `xhigh` para `medium`.
- Sonnet 5.5: `@code-worker` continua em `high`. Orientação registrada: `medium` em código bem especificado e curto, `xhigh`/`max` só com ganho medido.
- Nenhuma mudança no Jev, no Codex nem nas regras de segurança. **Nenhum nível foi medido nesta instalação ainda.**

## 0.5.1 — 2026-09-29

- **Sonnet 5.5 confirmado no app.** No Claude Code 2.1.284 o alias `sonnet` resolve para `claude-sonnet-5-5`. Conferido no catálogo do app e por três subagentes do plugin, que se identificaram como Sonnet 5.5 (`@code-worker`), Haiku 4.5 (`@worker`) e Opus 5.5 (`@advisor`). Os avisos de "o Sonnet ainda é o 5" saíram da documentação, do comando e do agente.
- No app, o esforço padrão do Sonnet 5.5 é `medium`. O `@code-worker` continua em `high`, e o esforço de cada frente segue decidido pela tarefa.
- Nenhuma mudança no Jev nem nas regras.


## 0.5.0 — 2026-09-29

**Estratégia primeiro, esforço por frente.**
- A primeira decisão do `/orchestrate` passou a ser a estratégia, com três opções:
  - **direto**: a sessão principal resolve a tarefa sozinha;
  - **UltraCode solo**: todas as etapas num modelo só, Sonnet 5.5 no trabalho especificado ou moderado e Opus 5.5 no difícil;
  - **orquestração mista**: cada frente no nível que a natureza dela pede.
- O esforço é escolhido por frente, pela dificuldade, entre `low` e `max`, e deixou de ser fixo. O Extra (`xhigh`) é o ponto de partida de todo trabalho que exige julgamento. UltraCode é uma estratégia multiagente, não um nível acima do Max.
- Esforço padrão dos agentes, que vale quando a delegação é pela ferramenta Agent:
  - `@code-worker`: high;
  - `@design-worker`, `@reviewer` e `@advisor`: xhigh;
  - `@worker`: nenhum, porque o Haiku 4.5 não aceita esforço.
- `settings.example.json` coloca a sessão principal (Opus 5.5) em Extra. O padrão do app é `medium`.

**Modelos.**
- Os agentes passam a mirar Opus 5.5, Sonnet 5.5, Fable 5.1 e Haiku 4.5, sempre por alias.
- Em 2026-09-29 o app (Claude Code 2.1.281) ainda resolve `sonnet` para o Sonnet 5. O Sonnet 5.5 entra sozinho quando o app for atualizado.
- **Quem constrói não revisa:** design feito pelo Fable é revisado pelo `@reviewer` rodando com override `opus`.

**Jev (TypeSafe): decisões assertivas.**
- Novo `scripts/jev_decide.py` com três poderes, cada um autorizado explicitamente:
  - `plan_gate`: aprova plano local e reversível sem esperar o usuário;
  - `tiebreak`: desempata escolha reversível de baixo impacto;
  - `escalation`: decide se a saída de uma frente é aceita ou sobe de nível.
- **Três camadas em código, antes de qualquer chamada de rede:**
  - no `plan_gate`, uma lista de ações locais permitidas: cada ação, e cada trecho dela, precisa começar com um verbo de trabalho local ou um comando local conhecido. Verbo arriscado ou desconhecido, comando externo ou ação sem verbo volta para o usuário;
  - uma rede de padrões em português e inglês sobre o texto normalizado (sem acento, sem invisíveis, sem homóglifos), com exclusões que só valem quando cobrem o próprio termo encontrado. Ela cobre mensagem a terceiros (inclusive por Resend, Twilio, webhooks, redes sociais), push, deploy, publicação, destrutivo, credenciais, dinheiro, produção, permissões e veredito de segurança. É uma rede, não uma garantia;
  - as flags declaradas pelo orquestrador.
- **Segredos.** São detectados antes de tudo e nunca vão para o TypeSafe nem para o log local.
- **Log.** Cada decisão é auditável em `~/.config/hebe-brain/jev-decisions.jsonl` (modo 0600), com rotação em 5 MiB.
- **Falha conservadora.** Sem autorização, sem credencial, serviço fora do ar, resposta inválida ou abstenção: o fluxo volta a ser o de antes do Jev.
- **Autorização e limiares são do usuário.** O orquestrador não roda `authorize` nem muda limiar sozinho. Sem o Jev configurado, nada é gravado em disco.
- **Duas rodadas de revisão.**
  - A primeira foi uma revisão crítica em Fable 5.1.
  - A segunda foi adversarial, com três lentes: segurança em Fable, doutrina em Opus e fatos em Sonnet. Cada achado passou por um verificador e, no fim, por um crítico de completude.
  - A adjudicação foi feita em Opus 5.5. Nenhum caminho abre o portão sozinho: `proceed`, `accept` e a escolha de uma opção só saem com resposta validada do Jev acima do limiar.
- **Ainda não validado:**
  - os limiares (`plan_gate` 0.85 na segurança e 0.70 no escopo; 0.65; 0.80) só passaram por um teste real com 4 decisões, sem calibração com uso real;
  - o comportamento do app quando o crédito do Fable acaba (falha, consentimento para créditos pagos ou troca automática de modelo) não foi testado.

**Doutrina.**
- Quem constrói não revisa, pelo modelo que rodou de fato, não pelo nome do agente.
- Subagentes nunca executam ação arriscada fora do plano aprovado.
- Etapas do UltraCode que falham não somem em silêncio.
- O UltraCode só roda quando o usuário pede, digitando o comando ou "ultracode".

**Testes.**
- Suíte sem rede com tabelas de frases reais, tanto as que devem bloquear quanto as que devem passar, e formatos de segredo.
- Também verifica o contrato de empacotamento: versões iguais nos manifestos, frontmatter dos agentes e ausência de `$<dígito>` nas skills.

**Variante Codex.**
- `.codex-plugin/plugin.json` e `codex-skills/orchestrate/` trazem a mesma doutrina para o app Codex:
  - `gpt-6-luna` no mecânico;
  - `gpt-6-sol` no código e como root;
  - `gpt-6-astra` no julgamento difícil e na revisão independente;
  - `gpt-5.6-terra` como reserva, já que não existe GPT-6 Terra.
- Ainda não foi instalada nem testada no app Codex. A invocação implícita está desligada para não disputar com o `hebe-orchestrator-codex`.
- A matriz papel × host, as particularidades de cada modelo e o que ainda não foi verificado estão em `skills/orchestrator-guide/references/hosts.md`.

## 0.4.0

- Orquestração multi-modelo qualidade-primeiro: `@worker` (Haiku), `@code-worker` (Sonnet), `@design-worker` e `@reviewer` (Fable) e `@advisor` (Opus), com o comando `/orchestrate` e a skill `orchestrator-guide`.
