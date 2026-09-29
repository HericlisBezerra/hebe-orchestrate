"""Regras locais do portão Jev: normalização, lista de ações locais, rede de
padrões de risco e detecção de segredo. Nada aqui usa rede.

Três camadas, nesta ordem de força:

1. ``plan_gate`` só libera ações que começam com um verbo de trabalho local
   conhecido (lista de permissão). Verbo desconhecido ou arriscado, comando fora
   da lista ou ação sem verbo → volta para o usuário.
2. Uma rede de padrões de risco (lista de proibição) roda em todos os tipos de
   decisão, sobre o texto normalizado, com exclusões que só valem quando cobrem
   o próprio termo encontrado.
3. As flags que o orquestrador declara (tratadas em ``jev_decide``).

A lista de proibição é uma rede, não uma garantia; por isso o ``plan_gate``, o
único poder que executa algo sem o usuário, depende da lista de permissão.
"""

import re
import unicodedata


# ---------------------------------------------------------------- normalização

CONFUSABLES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c", "т": "t",
    "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "ӏ": "l", "ο": "o", "α": "a",
    "ε": "e", "ρ": "p", "τ": "t", "υ": "u", "ν": "v", "κ": "k", "ι": "i", "ϲ": "c", "ԛ": "q", "ԝ": "w",
    "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m", "Н": "h", "О": "o", "Р": "p", "С": "c", "Т": "t",
    "Х": "x", "І": "i", "Ј": "j", "Ѕ": "s", "Ο": "o", "Α": "a", "Ε": "e", "Ρ": "p", "Τ": "t", "Κ": "k",
    "Ι": "i", "Ν": "n", "Β": "b", "Μ": "m", "Ζ": "z", "Υ": "y", "Χ": "x",
})


def strip_format(value):
    """Remove caracteres de formatação invisíveis (categoria Cf)."""
    return "".join(c for c in value if unicodedata.category(c) != "Cf")


def fold(value):
    """Minúsculas, sem acentos, sem invisíveis e sem homóglifos comuns."""
    decomposed = unicodedata.normalize("NFD", strip_format(value))
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return plain.translate(CONFUSABLES).casefold()


def clean_case(value):
    """Como ``fold``, mas preserva maiúsculas — para detectar segredos."""
    decomposed = unicodedata.normalize("NFD", strip_format(value))
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", plain.translate(CONFUSABLES))


def _rx(pattern):
    return re.compile(pattern, re.I | re.X)


# ------------------------------------------------ camada 1: ações locais (plan_gate)

LOCAL_VERBS = frozenset("""
editar edite edita alterar altere altera ajustar ajuste ajusta criar crie cria adicionar adicione adiciona
incluir inclua inclui implementar implemente implementa refatorar refatore refatora renomear renomeie renomeia
mover mova move extrair extraia extrai corrigir corrija corrige consertar conserte conserta escrever escreva escreve
reescrever reescreva reescreve documentar documente documenta ler leia mapear mapeie mapeia analisar analise analisa
investigar investigue investiga revisar revise revisa comparar compare compara inspecionar inspecione inspeciona
verificar verifique verifica conferir confira confere testar teste testa validar valide valida atualizar atualize atualiza
remover remova remove apagar apague apaga deletar deleta excluir exclua exclui substituir substitua substitui
trocar troque troca mudar mude muda formatar formate formata tipar tipe tipa estilizar estilize estiliza
organizar organize organiza reorganizar reorganize reorganiza simplificar simplifique simplifica otimizar otimize otimiza
melhorar melhore melhora converter converta converte instalar instale instala configurar configure configura
gerar gere gera colocar coloque coloca usar use usa aplicar aplique aplica exportar exporte exporta importar importe importa
dividir divida divide separar separe separa juntar junte junta unificar unifique unifica padronizar padronize padroniza
limpar limpe limpa reverter reverta reverte desfazer desfaca desfaz fazer faca faz montar monte monta desenhar desenhe desenha
prototipar prototipe planejar planeje planeja listar liste buscar busque busca procurar procure procura encontrar encontre encontra
contar conte medir meca mede calcular calcule calcula resumir resuma resume explicar explique explica descrever descreva descreve
traduzir traduza traduz salvar salve salva copiar copie copia duplicar duplique duplica mockar mocke tornar torne torna
deixar deixe deixa manter mantenha mantem preservar preserve preserva garantir garanta garante evitar evite evita tratar trate trata
cobrir cubra escolher escolha escolhe decidir decida decide definir defina define declarar declare declara abrir abra abre
fechar feche fecha integrar integre integra chamar chame chama consultar consulte consulta commitar commite mexer mexa mexe
ligar ligue desligar desligue centralizar centralize alinhar alinhe animar anime renderizar renderize
reduzir reduza reduz aumentar aumente aumenta diminuir diminua diminui cortar corte acrescentar acrescente
mostrar mostre mostra exibir exiba exibe ocultar oculte oculta esconder esconda
edit update change adjust tweak create add include implement refactor rename move extract fix repair write rewrite document
read map analyze analyse investigate review compare inspect check verify test validate remove delete replace swap format type
style organize reorganize simplify optimize improve convert install configure generate put use apply export import split clean
revert undo make build draft design prototype plan list find search count measure calculate summarize explain describe translate
save copy duplicate mock stub keep preserve ensure avoid handle cover choose decide define declare open close integrate call
consult commit wire extend reuse center align animate render reduce increase decrease trim show display hide
""".split())

# Verbos de execução: só liberam com objeto claramente local.
RUN_VERBS = frozenset("rodar rode roda executar execute executa iniciar inicie inicia subir suba sobe run start".split())
SAFE_RUN = _rx(r"""\b(?:testes?|tests?|specs?|suite|lint\w*|eslint|prettier|format\w*|typecheck|type-check|tsc|build\w*|vitest|jest|
    pytest|unittest|playwright|cypress|storybook|dev|servidor\s+(?:de\s+)?(?:dev|local|desenvolvimento)|server\s+(?:local|dev)|local\w*|
    localhost|simulador|emulador|expo\s+go|supabase\s+start|docker\s+compose\s+up|migrate\s+dev|codegen|gen\s+types|bench\w*|check|
    coverage|cobertura|start|serve)\b""")
PACKAGE_OPS = _rx(r"\b(?:install|i|add|ci|remove|uninstall|init|create)\b")

SAFE_COMMANDS = frozenset("tsc eslint prettier vitest jest pytest mkdir touch mv cp sed cat ls grep rg find echo head tail diff wc jq".split())
RUNNER_COMMANDS = frozenset("npm pnpm yarn bun npx node python python3 pip pip3 cargo deno expo docker uv poetry".split())
COMMAND_RULES = {
    "git": _rx(r"^git\s+(?:status|diff|log|add|commit|switch|branch|stash|show|blame|grep|init|rev-parse|mv)\b|^git\s+checkout\s+-b\s+[a-z][\w./-]*\s*$"),
    "supabase": _rx(r"^supabase\s+(?:start|stop|status|gen\s+types|db\s+diff|migration\s+new|db\s+lint|init)\b"),
    "rm": _rx(r"^rm\s+-[a-z]+\s+(?:\./)?(?:node_modules|\.next|dist|build|\.cache|\.turbo|out|coverage|tmp)/?(?:\s|$)"),
    "chmod": _rx(r"^chmod\s+\+x\b"),
}
# Argumento que sai do projeto ou tem efeito amplo: caminho absoluto, home, "..",
# redirecionamento, e as flags de apagar/executar do find.
UNSAFE_ARGS = _rx(r"(?:^|\s)(?:/|~|\$home)|\.\./|(?<![<>])>{1,2}|\s-delete\b|\s-exec\b|\s-execdir\b|\s-ok\b")
GLOBAL_INSTALL = _rx(r"\s(?:-g|--global|--location[= ]global)\b|\bsudo\b")
KNOWN_COMMANDS = (SAFE_COMMANDS | RUNNER_COMMANDS | frozenset(COMMAND_RULES) | frozenset(
    "curl wget ssh scp rsync gh vercel wrangler netlify fly flyctl heroku firebase eas fastlane terraform pulumi aws gcloud az "
    "psql mysql mongosh redis-cli kubectl helm twine sudo crontab launchctl".split()))

RISKY_VERBS = frozenset("""
mandar mande manda enviar envie envia avisar avise avisa responder responda responde notificar notifique notifica
compartilhar compartilhe compartilha repassar repasse repassa entregar entregue entrega encaminhar encaminhe encaminha
postar poste posta publicar publique publica disparar dispare dispara pagar pague paga comprar compre compra
assinar assine assina transferir transfira transfere cobrar cobre cobra emitir emita emite hospedar hospede hospeda
liberar libere libera conectar conecte conecta logar logue loga cadastrar cadastre cadastra aceitar aceite aceita
permitir permita permite ativar ative ativa habilitar habilite habilita desativar desative desativa marcar marque marca
setar sete seta convidar convide convida agendar agende agenda reenviar reenvie reenvia reprocessar reprocesse reprocessa
dropar drope dropa resetar resete reseta recriar recrie recria esvaziar esvazie esvazia sobrescrever sobrescreva sobrescreve
promover promova promove conceder conceda concede estornar estorne estorna renovar renove renova contratar contrate contrata
send email message text ping notify reply respond forward share invite post publish tweet upload deploy redeploy release
ship launch push merge promote host expose hardcode pay buy purchase charge bill transfer refund subscribe renew drop wipe
nuke flush erase destroy truncate reset grant revoke login log sign accept trigger retry reprocess resend sync dm set enable
disable activate allow unlock
""".split())
ER_VERBS = frozenset("vender receber correr rever trazer".split())
NON_VERBS = frozenset("""o a os as um uma uns umas the an this that these those isso isto este esta esse essa seu sua seus suas
meu minha de do da dos das no na nos nas em com para pra pro to for in on with at by of todos todas all cada each tambem also
mais more depois then so apenas only""".split())
CLAUSE_SPLIT = re.compile(r"\s*(?:\n|;|,|\s\+\s|\s/\s|\s[\u2013\u2014-]\s|&&|\|\||\||\s+(?:e|and|depois|then|em\s+seguida|e\s+depois|and\s+then|entao|apos|after|ai)\s+)\s*")
LEAD = re.compile(r"^[\s\-*•\d.):>`'\"(\[]*")
TOKEN = re.compile(r"[a-z][a-z0-9_-]*")


CLITIC = re.compile(r"-(?:la|lo|las|los|se|lhe|lhes|me|te|nos)$")


def _first_token(clause):
    stripped = LEAD.sub("", clause)
    match = TOKEN.match(stripped)
    # "aplicá-la" → "aplica": a ênclise não pode esconder o verbo.
    return (CLITIC.sub("", match.group(0)) if match else ""), stripped


def _verb_like(token):
    if token in RISKY_VERBS or token in ER_VERBS:
        return True
    return len(token) >= 5 and token.endswith(("ar", "ir"))


def _clause_status(clause):
    """'ok', 'noverb' (herda) ou o motivo do bloqueio."""
    token, stripped = _first_token(clause)
    if not token or token in NON_VERBS:
        return "noverb"
    if token in COMMAND_RULES:
        return "ok" if COMMAND_RULES[token].search(stripped) else "comando_nao_local:" + token
    if token in SAFE_COMMANDS:
        return "comando_nao_local:" + token if UNSAFE_ARGS.search(stripped) else "ok"
    if token in RUNNER_COMMANDS:
        if UNSAFE_ARGS.search(stripped) or GLOBAL_INSTALL.search(stripped):
            return "comando_nao_local:" + token
        return "ok" if (SAFE_RUN.search(stripped) or PACKAGE_OPS.search(stripped)) else "comando_nao_local:" + token
    if token in KNOWN_COMMANDS:
        return "comando_nao_local:" + token
    if token in RUN_VERBS:
        return "ok" if SAFE_RUN.search(stripped) else "execucao_nao_local"
    if token in LOCAL_VERBS:
        return "ok"
    if _verb_like(token):
        return "acao_nao_local:" + token
    return "noverb"


def action_reasons(actions):
    """Lista de permissão do plan_gate: cada cláusula começa com verbo local."""
    reasons = []
    for action in actions:
        clauses = [c for c in CLAUSE_SPLIT.split(fold(action)) if c.strip()]
        for index, clause in enumerate(clauses):
            status = _clause_status(clause)
            if status == "noverb":
                if index == 0:
                    status = "acao_sem_verbo"
                else:
                    continue
            if status != "ok" and status not in reasons:
                reasons.append(status)
    return reasons


def option_reasons(options):
    """Opções de desempate que são ações arriscadas voltam para o usuário."""
    reasons = []
    for text in options:
        for clause in CLAUSE_SPLIT.split(fold(text)):
            token, _ = _first_token(clause)
            if token and token not in LOCAL_VERBS and token not in NON_VERBS and (
                    _verb_like(token) or token in KNOWN_COMMANDS - SAFE_COMMANDS):
                reason = "opcao_nao_local:" + token
                if reason not in reasons:
                    reasons.append(reason)
    return reasons


# ------------------------------------------------- camada 2: rede de padrões de risco

CHANNELS = (r"whatsapp|zap(?:zap)?|slack|sms|telegram|discord|evolution(?:\s*api)?|instagram|linkedin|youtube|tiktok|"
            r"resend|sendgrid|twilio|mailgun|brevo|mailchimp|postmark|mailtrap|nodemailer|postfix|amazon\s+ses|aws\s+ses|ses|z-?api|chatwoot|manychat|webhook|sendtext")
SEND_VERBS = (r"enviar|envie|envia|enviando|enviamos|mandar|mande|manda|mandando|disparar|dispare|dispara|avisar|avise|avisa|"
              r"notificar|notifique|notifica|comunicar|comunique|comunica|informar|informe|alertar|cobrar|cobre|cobra|"
              r"responder|responda|responde|encaminh\w+|repass\w+|entreg\w+|compartilh\w+|convid\w+|reenvi\w+|"
              r"send|message|notify|ping|reply|respond\w*|forward|share|invite|dm")
RECIPIENTS = (r"cliente|clientes|socio|socios|parceiro|parceira|equipe|time|grupo|lead|leads|fornecedor|pessoal|galera|"
              r"usuarios|contatos?|numero|lista|base|assinantes|todos|todo\s+mundo|ele|ela|eles|elas|"
              r"client|clients|customer|customers|team|group|partner|vendor|stakeholders?|users|contacts?|number|"
              r"subscribers|everyone|everybody|him|her|them")
UI_CHANNEL = (r"(?:botao|button|link|links|icone|icones|icon|icons|widget|cta|logo|numero|number|contato|redes\s+sociais|"
              r"social(?:\s+(?:links|icons|media))?|rodape|footer|header)\b[^\n]{0,40}\b(?:" + CHANNELS + r")\b"
              r"|\b(?:" + CHANNELS + r")\s+(?:button|flutuante|float\w*|link|links|icon|icone|widget|no\s+(?:footer|rodape|header))"
              r"|\b(?:integrar|abrir|redirecionar|link\s+para)\b[^\n]{0,15}\bwhatsapp\b(?!\s*(?:api|business\s+api|evolution))"
              r"|\b(?:embed|player|iframe|video|videos)\s+(?:do|da|de|of|from)?\s*(?:youtube|tiktok|instagram)\b|\b(?:youtube|vimeo)\s+(?:embed|player|iframe)")

# (flag, padrão, exclusão, janela). A exclusão só vale se SOBREPUSER o termo
# encontrado, para que uma palavra inocente por perto nunca apague um risco real.
RULES = (
    # --- mensagem a terceiros ---
    ("third_party_message", _rx(r"\b(?:" + CHANNELS + r")\b"), _rx(UI_CHANNEL), 45),
    ("third_party_message", _rx(r"\b(?:" + SEND_VERBS + r")\b[^\n]{0,60}?\b(?:" + RECIPIENTS + r"|e-?mails?)\b"),
     _rx(r"\b(?:enviar|envie|envia|send)\s+(?:o|a|the)?\s*(?:form\w*|request|requisicao|payload|dados|arquivo)\b[^\n]{0,30}\b(?:endpoint|api|servidor|server|rota|route)"
         r"|\b(?:responder|responda|responde|respond\w*|reply)\s+(?:ao|to\s+the|o)?\s*(?:cliente|client)\s+(?:com|with)\b"
         r"|\b(?:response|resposta|cookie|json|payload|dados|erro|error)\b[^\n]{0,20}\b(?:pro|para\s+o|to\s+the)\s+(?:cliente|client)\b"
         r"|\b(?:error|success|toast|validation|warning)\s+message\b[^\n]{0,40}"), 30),
    ("third_party_message", _rx(r"\b(?:" + RECIPIENTS + r")\b[^\n]{0,40}?\b(?:por|via|no|na|pelo|pela|by|on)\s+(?:e-?mail|" + CHANNELS + r")\b"),
     _rx(r"\b(?:buscar|busque|filtrar|filtre|ordenar|find|search|filter|sort|login|entrar|autenticar)\b[^\n]{0,30}\b(?:por|by)\s+e-?mail"), 40),
    ("third_party_message", _rx(r"\b(?:" + SEND_VERBS + r")\b[^\n]{0,40}?\b(?:mensage\w+|messages?|notificac\w+|notifications?|newsletter|convites?|invites?|e-?mails?|sms)\b"),
     _rx(r"\b(?:mostrar|mostre|exibir|exiba|show|display)\b[^\n]{0,30}\b(?:mensage\w+|messages?)"
         r"|\b(?:" + SEND_VERBS + r")\b[^\n]{0,40}?\bmensage\w+\s+de\s+(?:erro|sucesso|validacao|aviso)\b"
         r"|\b(?:" + SEND_VERBS + r")\b[^\n]{0,40}?\b(?:error|success|validation)\s+messages?\b"), 50),
    ("third_party_message", _rx(r"\b(?:envio|disparo|disparador\w*|reenvio|reprocess\w*|fila|queue|worker|cron|job|script|gatilho)\b[^\n]{0,30}?\b(?:de\s+|para\s+|pros?\s+|pras?\s+|aos?\s+)?"
                                r"(?:e-?mails?|mensage\w+|sms|notificac\w+|whatsapp|newsletter|clientes?|leads?|contatos?|lista|massa|assinantes|confirmac\w+|transacion\w+)\b"), None, 0),
    ("third_party_message", _rx(r"\bdispar(?:o|os|ador\w*)\b|\bem\s+massa\b|\bmass\s+(?:e-?mails?|mail\w*|messag\w+|send\w*)\b|\bgatilho\s+de\s+(?:envio|e-?mail|mensage\w+)"),
     _rx(r"\bdispar\w*\s+(?:de\s+|do\s+|o\s+|um\s+)?(?:eventos?|events?|animac\w+|timer|trigger|gatilho\s+de\s+animac\w+)"), 25),
    ("third_party_message", _rx(r"\bemail\s+(?:the|a|an|our|my|all|every|him|her|them|[a-z]+\s+the)\b"), None, 0),
    ("third_party_message", _rx(r"\b(?:postar|poste|posta|agendar|agende|publicar|schedule|post)\b[^\n]{0,30}?\b(?:post|carrossel|carousel|reels?|story|stories|video|tweet|thread)\b"), None, 0),
    ("third_party_message", _rx(r"\b(?:coment\w+|comment\w*)\b[^\n]{0,25}?\b(?:figma|google\s+docs?|doc|docs|notion|linear|jira|trello|pr|issue|pull\s*request)\b"), None, 0),
    ("third_party_message", _rx(r"\b(?:convidar|convide|invite|adicionar|adicione|add)\b[^\n]{0,30}?\b(?:colaborador\w*|collaborators?|membros?|members?)\b"), None, 0),
    ("third_party_message", _rx(r"\bgh\s+(?:pr|issue|release|api|repo|gist)\b"), None, 0),
    ("third_party_message", _rx(r"\b(?:abrir|abra|criar|crie|comentar|comente|comentario|responder|responda|fechar|feche|aprovar|aprove|"
                                r"open|create|comment|close|approve|review)\w*\b[^\n]{0,30}?\b(?:pr|prs|pull\s*requests?|issues?)\b"),
     _rx(r"\bgit\s+checkout\b|\bgh\s+pr\s+checkout\b"), 20),
    ("third_party_message", _rx(r"\b(?:agendar|agende|marcar|marque|schedule)\b[^\n]{0,30}?\b(?:reuniao|meeting|call|chamada|evento)\b"), None, 0),
    # --- push / merge ---
    ("push", _rx(r"\bpush\b(?!\s+notific)"),
     _rx(r"\.push\b|\bpush\s*\(|\b(?:array|arrays|lista|list|stack|pilha|router|history)\s*\.?\s*push\b"
         r"|notificac\w+\s+push|\b(?:expo|web)\s+push|\bpush\s+(?:token|notification\w*|api)"), 25),
    ("push", _rx(r"\bmerge\w*\b|\bmergear\b|\bmergeie\b"), _rx(r"\bmerge\w*\s+(?:dos|das|de|of|the)?\s*(?:objetos?|objects?|props|arrays?|estilos?|styles?|config\w*|deep)"), 30),
    ("push", _rx(r"\bsubir\b[^\n]{0,30}?\b(?:github|gitlab|repositorio|repo|remoto|remote|origin|commits?|branch|alteracoes)\b"), None, 0),
    ("push", _rx(r"\b(?:sincronizar|sync)\b[^\n]{0,20}?\b(?:remoto|remote|origin|github)\b|--public\b"), None, 0),
    # --- deploy / publicação ---
    ("deploy", _rx(r"(?<![a-z])re-?deploy\w*|\bdeploy\w*"),
     _rx(r"\b(?:instruc\w*|documenta\w*|docs?|guia|guide|tutorial|secao|section)\s+(?:de\s+|do\s+|of\s+|on\s+|sobre\s+)?(?:re-?)?deploy\w*"
         r"|\bdeploy\w*\s+(?:docs?|guide|instructions)|\bdocument\w*\b[^\n]{0,30}?\bdeploy\w*|\bprocesso\s+de\s+deploy\b[^\n]{0,20}"), 40),
    ("deploy", _rx(r"\b(?:npx\s+)?vercel\b(?!\s+(?:dev|link|login|env\s+pull|logs?|ls|list|inspect))"
                   r"|\b(?:wrangler|netlify|railway)\s+(?:deploy|publish|--prod|up)\b|\bfly(?:ctl)?\s+(?:launch|deploy)\b"
                   r"|\beas\s+(?:update|submit)\b|\beas\s+build[^\n]*--auto-submit|\bfastlane\s+(?:deliver|pilot|supply|beta|release)\b"
                   r"|\bterraform\s+apply\b|\bpulumi\s+up\b|\btwine\s+upload\b|\baws\s+s3\s+(?:sync|cp)\b"
                   r"|\bno\s+ar\b|\bgo\s+live\b|\bhosped\w+|\bonline\b|\btestflight\b|\b(?:app|play)\s+store\b|\bgoogle\s+play\b"),
     _rx(r"\b(?:loja|pagamento|formulario|status|usuarios?|modo|jogo|game|indicador|badge|bolinha)\s+online\b|\bonline\s+(?:status|indicator|badge|payment|store)\b"), 25),
    ("deploy", _rx(r"\b(?:apontar|aponte|trocar|troque|configurar|configure|mudar|mude)\b[^\n]{0,20}?\b(?:dominio|domain|dns)\b"), None, 0),
    ("deploy", _rx(r"\bsubir\b[^\n]{0,30}?\b(?:site|producao|prod|servidor|server|app|vercel|cloudflare|netlify|ar|build|versao)\b"),
     _rx(r"\bsubir\b[^\n]{0,30}?\b(?:dev|local\w*|simulador|emulador|expo\s+go|docker|supabase\s+start)\b"), 45),
    ("publish", _rx(r"\bpublic(?:ar|ou|amos|ando|ado|ada|acao)\b|\bpubliqu\w+|\bpublish\w*|\bnpm\s+publish\b|\bpublicamente\b|\bpublicly\b"), None, 0),
    ("publish", _rx(r"\b(?:tornar|torne|deixar|deixe|make|set|marcar|marque|setar|mudar|mude|colocar|coloque|configurar|configure)\b[^\n]{0,30}?\b(?:publico|publica|public)\b"
                    r"|\b(?:bucket|acesso|repo\w*|storage|link|visibilidade|visibility|rota|endpoint|tabela)\b[^\n]{0,30}?\b(?:publico|publica|public)\b"
                    r"|\bpublic\s+(?:bucket|access|read)\b"),
     _rx(r"\b(?:metodo|campo|atributo|propriedade|method|field|property|member|classe|class)\s+(?:\w+\s+)?(?:publico|public)\b"
         r"|\bmake\s+the\s+(?:method|field|property)\s+public\b|\bpasta\s+public\b|\bpublic/"), 30),
    ("publish", _rx(r"\blanc(?:ar|ou|amos|ando|amento)\b|\bship\b|\b(?:criar|crie|gerar|cortar|fazer|faca|rodar|cut|create|publish|do)\s+(?:a\s+|o\s+|uma\s+|um\s+|the\s+|a\s+new\s+)?release\b"
                    r"|\bliberar\b[^\n]{0,30}?\b(?:todos|todo\s+mundo|usuarios|clientes|versao|producao)\b"),
     _rx(r"\blanc\w*\s+(?:uma\s+|um\s+|a\s+|o\s+)?(?:excec\w*|exception|erro|error|evento|event)"
         r"|\blancamento\s+d[oa]\b|\b(?:landing|pagina|secao)\s+(?:de\s+)?lancamento"), 25),
    # --- destrutivo / irreversível ---
    ("destructive", _rx(r"\brm\s+-[a-z]*(?:rf|fr)[a-z]*\b|\bdrop\b[^\n]{0,20}?\b(?:table|tabela|database|banco|schema|column|coluna|index|users?|policy|all)\b"
                        r"|\btruncate\s+(?:table\b|[a-z_][a-z0-9_]*\s*(?:cascade|;|$))|\bdelete\s+from\b|\breset\s+--hard\b|\bclean\s+-[a-z]*f"
                        r"|--force(?![\w-])|\bdb[:_-]?(?:reset|drop|wipe|nuke|push)\b|\breset-db\b|\b(?:db|database|migrate|migration)\s+reset\b|\bdropar\b"
                        r"|\btruncar\b[^\n]{0,20}?\btabelas?\b"),
     _rx(r"\brm\s+-[a-z]+\s+(?:\./)?(?:node_modules|\.next|dist|build|\.cache|\.turbo|out|coverage|tmp)\b|\bnpm\s+i\w*\s+--force\b"), 25),
    ("destructive", _rx(r"\b(?:remover|remova|remove|limpar|limpe|zerar|zere|resetar|resete|reset|apagar|apague|deletar|delete|excluir|exclua|destruir|"
                        r"wipe|purge|truncar|recri\w+|esvazi\w+|sobrescrev\w+|drop|clear|empty|nuke|erase|destroy|flush|kill|overwrite)\b"
                        r"[^\n]{0,40}?\b(?:banco|tabela|tabelas|dados|coluna|colunas|schema|db|database|table|tables|column|bucket|repositorio|repo|"
                        r"backup|conta|account|producao|registros|records|usuarios?|users?|uploads?|arquivos|pasta|diretorio|folder|migrations?|"
                        r"migrac\w*|storage|data|all)\b"),
     _rx(r"\b(?:remover|remova|remove|limpar|limpe|zerar|zere|resetar|resete|reset|apagar|apague|deletar|delete|excluir|exclua|destruir|wipe|purge|truncar|recri\\w+|esvazi\\w+|sobrescrev\\w+|drop|clear|empty|nuke|erase|destroy|flush|kill|overwrite|limpar|limpe)\b[^\n]{0,40}?"
         r"(?:\b(?:coluna|colunas|column)\s+(?:do|da|de|of\s+the)\s+(?:grid|layout|tabela\s+visual|card|flex)\b"
         r"|\bdados\s+(?:do|da)\s+(?:form\w*|estado|state|modal|componente|tela)\b"
         r"|\b(?:estado|state|form\w*|cache\s+local|localstorage)\b)"), 50),
    ("irreversible", _rx(r"\birreversi\w+|\bpermanent\w*|\bsem\s+volta\b|nao\s+(?:da|tem)\s+(?:pra|para|como)\s+desfazer"),
     _rx(r"\b(?:redirect\w*|redireciona\w*)\s+(?:\w+\s+)?permanent\w*|\bpermanent\w*\s+redirect|\b301\b"
         r"|\bbanner\s+permanente|\bpermanentemente\s+no\s+localstorage"), 25),
    # --- dinheiro ---
    ("money", _rx(r"\b(?:pagamentos?|cobrancas?|cobrar|transferencias?|pix|boletos?|reembols\w+|estorn\w+|refunds?|payments?|stripe|"
                  r"nota\s+fiscal|nfs-?e|nf-?e?|faturas?|invoices?|pricing|checkout|assinaturas?|subscriptions?|billing|cartao|credit\s*card|"
                  r"mercado\s*pago|asaas|pagseguro|pagar\.?me|spedy|pagar|pague|comprar|compre|contratar|contrate|contratacao|renov\w+|transferir|transfira|"
                  r"quitar|dinheiro|money|funds|creditos|credits|mensalidade|payout|purchase|comprovante)\b"),
     _rx(r"\bgit\s+checkout\b|\bcheckout\s+-b\b|\bgh\s+pr\s+checkout\b"
         r"|\b(?:secao|pagina|componente|card|layout|tabela|section|page)\s+de\s+(?:pricing|precos|planos)\b"
         r"|\bcartao\s+(?:de|do|da)\s+(?:produto|perfil|usuario|cliente|servico|post|noticia)\b|\bmock\w*\s+d[oa]\s+stripe\b"
         r"|\brenov\w+\s+(?:o\s+|a\s+)?(?:token|sessao|session|cache)\b"
         r"|\bcheckout\b[^\n]{0,30}\b(?:mock\w*|fake|stub\w*|fixture\w*)\b"), 40),
    ("money", _rx(r"\b(?:alterar|altere|mudar|mude|trocar|troque|atualizar|atualize|definir|reajustar|change|update|set)\b[^\n]{0,30}?"
                  r"\b(?:precos?|valor(?:es)?\s+d[oa]s?\s+(?:plano|planos|produto|mensalidade)|price|prices|mensalidade)\b"
                  r"|\b(?:assinar|assine|contratar|contrate|upgrade|trocar|troque)\b[^\n]{0,20}?\bplan[oe]?s?\b"
                  r"|\b(?:emitir|emita|cancelar|cancele)\b[^\n]{0,15}?\bnotas?\b"
                  r"|\b(?:charge|bill)\s+(?:the|a|this|our)\b|\bbuy\b(?!\s+(?:button|now|botao))|\btransfer\s+(?:the\s+)?(?:money|funds)\b"), None, 0),
    # --- credenciais ---
    ("credentials", _rx(r"\b(?:senhas?|passwords?|passwd|api[\s_-]?keys?|apikey|secrets?|segredos?|credenciai?s?|credentials?|service[\s_-]?role|"
                        r"anon[\s_-]?key|chave\s+anon|private[\s_-]?key|chave\s+privada|access[\s_-]?key|env\s*vars?|variave(?:l|is)\s+de\s+ambiente|"
                        r"environment\s+variables?|bearer|jwt\s+secret|ssh-keygen|gpg)\b|~/\.ssh|\b(?:id_rsa|id_ed25519|id_ecdsa|id_dsa)\b"
                        r"|\.(?:pem|p12|pfx|keystore|jks)\b|(?:^|[\s/])\.(?:netrc|npmrc|pypirc|git-credentials)\b|\bkeychain\b"),
     _rx(r"\b(?:tela|pagina|campo|form\w*|input|forca|fluxo)\s+(?:de\s+|da\s+|do\s+)?(?:recupera\w+\s+de\s+|redefini\w+\s+de\s+)?(?:senha|password)\b|\besqueci\s+(?:minha\s+)?senha\b"
         r"|\b(?:recupera\w+|redefini\w+|reset\w*)\s+de\s+senha\b"
         r"|\bpassword\s+(?:field|input|reset\s+(?:page|screen|form))\b"), 25),
    ("credentials", _rx(r"\b(?:rotacionar|rotacione|rotate|rotation)\b[^\n]{0,30}?\b(?:chaves?|keys?|segredos?|secrets?|tokens?|credenc\w*|credentials?|senhas?|passwords?)\b"), None, 0),
    ("credentials", _rx(r"(?:^|[\s/'\"`])\.env(?![\w.-]*(?:example|sample|template|dist))\b|\benvs\b|\bvercel\s+env\b"
                        r"|\bvariaveis\b[^\n]{0,20}?\b(?:vercel|painel|dashboard|cloudflare|netlify)\b"), None, 0),
    ("credentials", _rx(r"\b[a-z0-9]+_(?:key|token|secret|pass|password|pwd|dsn)\b|\b(?:database|db|redis|mongo|postgres)_url\b"), None, 0),
    ("credentials", _rx(r"\b(?:access|refresh|bearer|jwt|api|auth|github|npm|cloudflare|typesafe|supabase|vercel|resend|evolution)[\s_-]*tokens?\b"
                        r"|\btokens?\s+(?:de\s+)?(?:acesso|auth|jwt|bearer|refresh|access|do\s+github|pessoal|personal|do\s+usuario|da\s+sessao)\b"),
     _rx(r"\b(?:contar|conte|medir|meca|reduzir|reduza|consumo|uso|usage|count|limite|limit|custo|cost|gasto)\b[^\n]{0,30}?\btokens?\b[^\n]{0,25}"), 40),
    ("credentials", _rx(r"\b(?:supabase|openai|anthropic|resend|evolution|stripe|cloudflare|vercel|github|google|typesafe|the|a|minha|nova|my|new)\s+keys?\b"
                        r"|\b(?:hardcod\w*|expor|exponha|expose|commit\w*|colar|cole|paste|logar|console\.log)\b[^\n]{0,30}?\b(?:keys?|tokens?|chaves?|segredos?|secrets?|senhas?)\b"), None, 0),
    ("credentials", _rx(r"\bchaves?\b"),
     _rx(r"\bchaves?\s+(?:estrangeira|primaria|unica|composta|do\s+objeto|de\s+objeto|do\s+dicionario|do\s+map|de\s+ordenacao|"
         r"(?:de\s+)?(?:traducao|i18n|idioma|cache|lista|react|idempot\w+)|estavel)|\bchave-valor\b|\bcomo\s+chave\b"), 25),
    # --- produção / dados reais ---
    ("production_data", _rx(r"\b(?:producao|production|prod)\b"),
     _rx(r"\b(?:build|modo|mode|bundle|compil\w*|minif\w*|otimiz\w*|preview|env|node_env)[\s:=(-]+(?:de\s+|em\s+|of\s+|for\s+|para\s+)?(?:producao|production|prod)\b"
         r"|\b(?:producao|production|prod)\s+(?:build|mode|bundle)\b|\bbuild:prod\b|\bproduction-ready\b|\bpronto\s+pra\s+producao\b"
         r"|\bproducao\s+d[oe]s?\s+(?:videos?|conteudos?|carross\w+|reels?|posts?|textos?|artes?|material)\b"), 25),
    ("production_data", _rx(r"\b(?:banco|base|dados|clientes|usuarios)\s+(?:rea(?:l|is)|de\s+verdade)\b|\b(?:banco|supabase|database|db)\s+remot[oa]\b"
                            r"|\bremote\s+(?:database|db)\b|\blive\s+(?:database|data|db)\b|\bambiente\s+live\b|--remote\b|--linked\b"
                            r"|\b(?:painel|dashboard|console)\s+do\s+supabase\b|\bsql\s+editor\b|\bsupabase\s+(?:cloud|hospedad[oa]|online)\b"
                            r"|\b(?:homolog\w*|hml|staging)\b|\bao\s+vivo\b|\b(?:ambiente|site|app|conta|instancia|api|numero|servidor)\s+rea(?:l|is)\b"
                            r"|\b(?:banco|servidor|vps|conta|projeto)\s+d[oa]s?\s+clientes?\b|\bdados\s+d[oa]s?\s+(?:clientes?|usuarios?|users?|leads?)\b"
                            r"|\b(?:pg_)?dump\b|\bexportar\b[^\n]{0,20}?\b(?:usuarios|clientes|leads|tabela)\b|\bssh\b|\bvps\b"), None, 0),
    ("production_data", _rx(r"\b(?:aplicar|aplique|aplica|aplica-la|aplica-lo|rodar|rode|executar|execute|subir|push)\w*\b[^\n]{0,25}?\b(?:migration\w*|migrac\w+|seeds?|schema)\b[^\n]{0,25}?\b(?:banco|db|database|supabase|ambiente|prod\w*)\b"),
     _rx(r"\b(?:aplicar|aplique|aplica|rodar|rode|executar|execute|subir|push)\w*\b[^\n]{0,70}?\b(?:local\w*|supabase\s+start|migrate\s+dev|docker)\b"), 10),
    ("production_data", _rx(r"\b(?:migration\w*|migrac\w+|seeds?|schema)\b[^\n]{0,40}?\b(?:aplic\w*|rodar|rode|executar|execute|subir|push)\b[^\n]{0,25}?\b(?:banco|db|database|supabase|ambiente|prod\w*)\b"),
     _rx(r"\b(?:migration\w*|migrac\w+|seeds?|schema)\b[^\n]{0,90}?\b(?:local\w*|supabase\s+start|migrate\s+dev|docker)\b"), 10),
    # --- permissões / auth ---
    ("permissions", _rx(r"\b(?:rls|permiss(?:ao|oes|ions?)|autentica(?:cao|coes|r|ndo)|autoriza(?:cao|coes|r|ndo)|authn|authz|authentication|oauth|sso|"
                        r"grant|revoke|chmod|chown|sudo|guard|cors|anonim\w*|anonymous|anon|crontab|launchd)\b|/etc/|\bcurl\b[^\n|]*\|\s*(?:ba|z)?sh\b"),
     _rx(r"\bchmod\s+\+x\b"), 15),
    ("permissions", _rx(r"\bpolic(?:y|ies|ia|ias)\b|\bpoliticas?\b"),
     _rx(r"\b(?:privacy|cookie|content-security|content\s+security)\s+polic\w+|\bpoliticas?\s+de\s+(?:privacidade|cookies?)\b"), 30),
    ("permissions", _rx(r"\bauth\b"), _rx(r"\b(?:tela|pagina|layout|estilo|design)\s+(?:de\s+)?auth\b"), 20),
    ("permissions", _rx(r"\bauthoriz\w*\b(?!\s+header)"), None, 0),
    ("permissions", _rx(r"\broles?\b"),
     _rx(r"\baria[\w-]*\s*roles?|\broles?\s*=|\broles?\s+(?:de\s+)?(?:button|botao|dialog|navigation|tab|img|link|aria|attribute|acessibilidade|a11y)\b|\brole\s+(?:a|o|ate)\b"), 20),
    ("permissions", _rx(r"\b(?:login|logon|sign[\s-]?in|signin|sign[\s-]?up|signup)\b|\bcriar\s+(?:uma\s+)?conta\b|\bcadastr\w+\s+n[oa]\b"
                        r"|\bconectar\s+a\s+conta\b|\baceitar\s+(?:os\s+)?termos\b|\baccept\s+(?:the\s+)?terms\b"
                        r"|\blog(?:ar|ue|a)\s+n[oa]\s+(?:vercel|supabase|cloudflare|github|conta|painel|aws|google)\b"),
     _rx(r"\b(?:tela|screen|pagina|page|layout|estilo|style|css|design|visual|botao|button|form(?:ulario)?|rota|route|fluxo)\s+(?:de\s+|do\s+)?(?:login|logon|sign[\s-]?(?:in|up)|signin|signup)\b"
         r"|\b(?:login|sign[\s-]?(?:in|up))\s+(?:screen|page|form|button|layout|flow)\b|/(?:login|signup|signin)\b|\b(?:apos|depois\s+d)o\s+login\b"), 25),
    ("permissions", _rx(r"\b(?:tornar|torne|promover|promova|dar|conceder|conceda|virar|make|grant|set|adicionar|adicione|setar|marcar|colocar|criar|atualizar|add|mark|update)\b"
                        r"[^\n]{0,30}?\badmin\w*|\bis_admin\b|\bdar\s+acesso\b|\bowner\b"),
     _rx(r"\b(?:tornar|torne|promover|promova|dar|conceder|conceda|virar|make|grant|set|adicionar|adicione|setar|marcar|colocar|criar|atualizar|add|mark|update)\b"
         r"[^\n]{0,30}?\b(?:painel|pagina|tela|layout|rota|menu|dashboard|area)\s+(?:de\s+|do\s+)?admin\w*"), 50),
    # --- veredito de segurança ---
    ("security_verdict", _rx(r"\b(?:vulnerabilidades?|vulnerabilit\w+|seguranca|security|exploit\w*|pentest|cve-\d+|injection|injecao|idor|xss|csrf)\b"),
     _rx(r"\bdependency\s+injection\b|\binjecao\s+de\s+dependencias?\b|\bcontent-security-policy\b|\bmargem\s+de\s+seguranca\b"
         r"|\bcopia\s+de\s+seguranca\b|\bsafe\s+area\b"), 25),
)

# Nomes próprios depois de verbo de contato ("Mandar o resumo pro Alexandre").
NAMED_CONTACT = re.compile(
    r"\b(?:[Mm]and|[Ee]nvi|[Aa]vis|[Rr]espond|[Ff]al|[Cc]obr|[Rr]epass|[Ee]ntreg|[Ee]ncaminh|[Cc]ompartilh|[Nn]otific)\w*"
    r"(?:\s+\S+){0,3}?\s+(?:pro|pra|para|ao|à|a|o|com)\s+(?:(?:o|a)\s+)?[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõç]{2,}")
TECH_NOUNS = frozenset("""servidor server endpoint banco arquivo componente pasta api rota route backend frontend front back
cache repositorio modulo estado state storage bucket formulario form tabela console log logs terminal browser navegador
""".split())
LOWER_CONTACT = re.compile(r"\b(?:mand|envi|avis|respond|repass|entreg|encaminh|compartilh)\w*(?:\s+\S+){0,3}?\s+(?:pro|pra)\s+([a-z]{3,})\b")


def deny_reasons(texts):
    reasons = []
    folded = [fold(value) for value in texts]
    for rule in RULES:
        if rule[0] not in reasons and any(_hits(rule, value) for value in folded):
            reasons.append(rule[0])
    if "third_party_message" not in reasons:
        if any(NAMED_CONTACT.search(clean_case(value)) for value in texts) or any(
                m.group(1) not in TECH_NOUNS for value in folded for m in LOWER_CONTACT.finditer(value)):
            reasons.append("third_party_message")
    return reasons


def _hits(rule, folded):
    _, pattern, exclude, window = rule
    for match in pattern.finditer(folded):
        if exclude is None:
            return True
        lo, hi = max(0, match.start() - window), match.end() + window
        # A exclusão só vale se cobrir o próprio termo encontrado.
        if not any(e.start() <= match.start() and e.end() >= match.end()
                   for e in exclude.finditer(folded, lo, hi)):
            return True
    return False


# ------------------------------------------------------------- segredos

SECRET_STOPWORDS = re.compile(
    r"^(?:required|optional|undefined|null|none|true|false|string|number|boolean|obrigatori\w*|opcional|primaria|estrangeira|"
    r"process\.env\.\w+|import\.meta\.env\.\w+|z\.\w+.*|yup\.\w+.*|env\(\w+\)?)$", re.I)


def _secret_like(value):
    """Valor com cara de segredo: sem parênteses/barras de caminho e com duas classes de caractere."""
    value = value.strip("'\"`.,;")
    if len(value) < 8 or "(" in value or ")" in value or value.count("/") > 1 or SECRET_STOPWORDS.match(value):
        return False
    classes = sum(bool(re.search(p, value)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    return classes >= 2 and bool(re.search(r"\d", value) or re.search(r"[^A-Za-z0-9]", value))


KEY_NAMES = r"(?:api[_-]?key|apikey|password|passwd|pass|pwd|secret|token|authorization|senha|chave|key|private[_-]?key|access[_-]?key|dsn|segredo)"
KEY_VALUE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]*" + KEY_NAMES + r"[A-Za-z0-9_-]*[\"']?\s*[:=]\s*[\"']?([^\s,;\"'`]{8,})", re.I)
KEY_PHRASE = re.compile(r"\b" + KEY_NAMES + r"\b(?:\s+[\w-]+){0,3}?\s*(?:[:=]|\s(?:é|e|eh|is)\s)\s*[\"']?([^\s,;\"'`]{8,})", re.I)
KEY_NEARBY = re.compile(r"\b(?:key|secret|token|senha|chave|password|credencial|pass)\b[^\n]{0,40}?(?<![A-Za-z0-9+=_-])([A-Za-z0-9+=_-]{16,})", re.I)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+(?!auth\w*|token\w*|scheme|header)(?=[A-Za-z0-9._~+/-]*\d)[A-Za-z0-9._~+/-]{12,}", re.I),
    re.compile(r"\bauthorization:\s*basic\s+[A-Za-z0-9+/=]{8,}", re.I),
    re.compile(r"(?<![A-Za-z0-9])(?:sk|rk)[-_](?:live|test|ant|proj|or)?[-_]?[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])(?:gh[pousr]_|github_pat_|glpat-|xox[baprs]-|xapp-|AKIA|ASIA|AIza|sb_secret_|sbp_|whsec_|SG\.|"
               r"APP_USR-|\$aact_|GOCSPX-|figd_|hf_|lin_api_|ntn_|shpat_|dop_v1_)[A-Za-z0-9._/+=-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])npm_[A-Za-z0-9]{36}\b|(?<![A-Za-z0-9])re_[A-Za-z0-9]{16,}\b|(?<![A-Za-z0-9])TEST-\d{10,}"),
    re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}"),
    re.compile(r"\b[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*://[^\s/:@]*:[^\s/@]+@", re.I),
    re.compile(r"https://[a-f0-9]{16,}@[^\s]*sentry", re.I),
)


def has_secret(texts):
    for raw in texts:
        value = clean_case(raw)
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            return True
        for regex in (KEY_VALUE, KEY_PHRASE, KEY_NEARBY):
            if any(_secret_like(m.group(1)) for m in regex.finditer(value)):
                return True
    return False


def redact(value):
    value = clean_case(value)
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[omitido]", value)
    for regex in (KEY_VALUE, KEY_PHRASE, KEY_NEARBY):
        value = regex.sub(lambda m: m.group(0).replace(m.group(1), "[omitido]") if _secret_like(m.group(1)) else m.group(0), value)
    return value
