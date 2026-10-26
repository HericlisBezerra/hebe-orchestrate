#!/usr/bin/env python3
"""Ponte entre o orquestrador HeBe (Claude Code) e o Codex — experimento ``for-claude+gpt``.

O Claude continua coordenando. O Codex entra em dois papéis:

- ``review``: segunda lente de OUTRO fornecedor, somente leitura (revisão adversarial
  do plugin oficial ``openai-codex``). Sem ``--base`` revisa a árvore de trabalho (o que
  ainda não foi commitado); com ``--base`` revisa os commits ``base..HEAD`` e recusa
  árvore suja. Devolve um JSON compacto com veredito e achados.
- ``build``: constrói uma frente especificada numa worktree própria, fora da árvore de
  trabalho do Claude. O companion pede sandbox ``workspace-write`` e, no piloto, o Codex
  não conseguiu commitar; confira a configuração com ``doctor``. O Claude roda os testes,
  revisa o diff, commita e integra.

Cada uso grava uma linha no diário privado ``~/.config/hebe-brain/codex-experiment.jsonl``
(modo 0600) para medir eficiência e qualidade durante o experimento; ``outcome`` registra
o desfecho depois e ``report`` resume.

Proteções: texto com segredo e pastas bloqueadas pela política são recusados antes de
qualquer chamada; ``--copy`` só aceita pastas ignoradas pelo Git, sem symlink e sem nome
de segredo; o Codex recebe um ambiente mínimo; o diário nunca guarda o texto do pedido,
o foco nem a resposta do Codex. Somente biblioteca padrão.
"""

import argparse
from datetime import datetime, timedelta, timezone
import fnmatch
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time

if __package__:
    from . import jev, jev_rules as rules
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import jev
    import jev_rules as rules


LEDGER = "codex-experiment.jsonl"
POLICY = "codex-bridge.json"
LEDGER_ROTATE_BYTES = 10 * 1024 * 1024
# O plugin openai-codex 1.0.6 só aceita esforço até xhigh; max/ultra exigem o CLI direto.
EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_REVIEW_MODEL = "gpt-6.1-sol"
# Piloto (2026-10-26): Astra high 6,5/10 em 10 min; Sol high 6/10 em 16,5 min. n=1 cada.
DEFAULT_BUILD_MODEL = "gpt-6-astra"
DEFAULT_BUILD_EFFORT = "high"
MODEL_RE = re.compile(r"^gpt-[a-z0-9][a-z0-9.\-]{1,40}$")
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
REVIEW_OUTCOMES = ("confirmed", "mixed", "noise")
BUILD_OUTCOMES = ("accepted", "reworked", "rejected")
# Proxy grosseiro de tokens do lado do Claude: caracteres lidos ou escritos / 3,6.
CHARS_PER_TOKEN = 3.6
MAX_BRIEF = 64 * 1024
MAX_FOCUS = 2000
MAX_BODY = 900
COMPANION_GLOB = "~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs"
ENV_KEEP = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME", "SHELL", "TERM",
            "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS")
ENV_PREFIXES = ("CODEX_",)
# Nunca repassar: a transcrição do Claude e o endpoint de um broker que pode ter o ambiente completo.
ENV_DROP = ("CODEX_COMPANION_TRANSCRIPT_PATH", "CODEX_COMPANION_APP_SERVER_ENDPOINT", "CODEX_HOME")
GIT_SAFE = ("-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null")
UNTRACKED_SCAN_BYTES = 256 * 1024

LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock",
             "poetry.lock", "uv.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock"}
MANIFESTS = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod", "composer.json", "Gemfile"}
NOTE_NAMES = {"Brain.md", "AGENTS.md", "CLAUDE.md"}
SECRET_NAMES = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "credentials*", "secrets*",
                ".aws", ".ssh", ".gnupg", ".netrc", "*.keystore", "id_rsa*", "id_ed25519*")
# Dentro de uma pasta copiada (ex.: node_modules) o nome sozinho gera falso positivo;
# recusa-se .env*, chaves com "PRIVATE KEY" no conteúdo, keystores binários e pastas de credencial.
NESTED_ALWAYS = (".env", ".env.*", ".netrc", "*.p12", "*.pfx", "*.keystore", "id_rsa", "id_ed25519")
NESTED_DIRS = (".ssh", ".aws", ".gnupg")
NESTED_KEY_FILES = ("*.pem", "*.key", "id_rsa*", "id_ed25519*")
SCAN_LIMIT = 400_000

BUILD_RULES = """

---
Regras desta delegação (orquestrador HeBe, experimento for-claude+gpt):
- Trabalhe só nesta pasta. Não faça commit nem push: o coordenador revisa e commita.
- Não tome decisão de produto que o pedido não tomou. Não desligue nem remova funcionalidade, não mude contrato entre sistemas (formato de payload, recibo, API pública, nomes de alarme/rota já usados), não adicione dependência nem mude lockfile, não crie Brain.md, vault/, ADR ou notas, não versione logs nem arquivos de resultado de teste (cite a saída na resposta), não diga em comentário que nada mudou quando mudou.
- Se achar que algo disso é necessário, NÃO faça: liste em "Decisões pendentes".
- Rode os testes que existirem e cite a saída real resumida. Diga o que não conseguiu rodar.
- Resposta final curta (até 25 linhas): o que mudou por item, testes (saída real), Decisões pendentes, o que não validou.
"""


class BridgeError(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


def now():
    return datetime.now(timezone.utc)


def stamp(moment=None):
    return (moment or now()).isoformat(timespec="seconds")


def tokens(chars):
    return int(round(chars / CHARS_PER_TOKEN))


def new_id(prefix):
    return f"{prefix}-{now():%Y%m%dT%H%M%S}-{secrets.token_hex(3)}"


# ---------------------------------------------------------------- armazenamento privado

def _open_private(create=True):
    try:
        return jev.private_directory(create=create)
    except FileNotFoundError:
        return None
    except jev.JevError as error:
        raise BridgeError(str(error)) from None


def read_private(name):
    directory = _open_private(create=False)
    if directory is None:
        return None
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise BridgeError(f"{name} inseguro; exige arquivo próprio com modo 0600.")
            return stream.read(LEDGER_ROTATE_BYTES * 2)
    finally:
        os.close(directory)


def write_private_json(name, data):
    directory = _open_private(create=True)
    temporary = f".{name}.{secrets.token_hex(6)}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory)
        except OSError:
            pass
        raise
    finally:
        os.close(directory)


def append_ledger(entry):
    directory = _open_private(create=True)
    try:
        try:
            info = os.stat(LEDGER, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_size > LEDGER_ROTATE_BYTES:
                os.replace(LEDGER, LEDGER + ".1", src_dir_fd=directory, dst_dir_fd=directory)
        except FileNotFoundError:
            pass
        fd = os.open(LEDGER, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "ab") as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
                raise BridgeError("Diário do experimento inseguro; exige arquivo próprio com modo 0600.")
            stream.write((json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    finally:
        os.close(directory)


def read_ledger():
    entries = []
    for name in (LEDGER + ".1", LEDGER):
        raw = read_private(name)
        if not raw:
            continue
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                entries.append(item)
    return entries


def load_policy():
    raw = read_private(POLICY)
    if not raw:
        return {"schema_version": 1, "deny_paths": []}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise BridgeError("Política do Codex inválida; corrija ou apague ~/.config/hebe-brain/codex-bridge.json.") from None
    if not isinstance(data, dict) or not isinstance(data.get("deny_paths", []), list):
        raise BridgeError("Política do Codex inválida.")
    return {"schema_version": 1, "deny_paths": [str(p) for p in data.get("deny_paths", [])]}


def _inside(child, parent):
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def _same_or_inside(child, parent):
    """Como _inside, mas pela identidade do arquivo (macOS tem caminhos sem diferenciar caixa)."""
    if _inside(child, parent):
        return True
    try:
        parent_stat = os.stat(parent)
    except OSError:
        return False
    current = child
    while True:
        try:
            if os.path.samestat(os.stat(current), parent_stat):
                return True
        except OSError:
            pass
        upper = os.path.dirname(current)
        if upper == current:
            return False
        current = upper


def check_policy(path):
    """Recusa se o alvo estiver dentro de uma pasta bloqueada OU contiver uma.

    O companion revisa a raiz Git inteira e o build copia o repositório inteiro para a
    worktree, então bloquear só uma subpasta não basta: o repositório que a contém também
    fica bloqueado.
    """
    real = os.path.realpath(path)
    for denied in load_policy()["deny_paths"]:
        base = os.path.realpath(os.path.expanduser(denied))
        if _same_or_inside(real, base) or _same_or_inside(base, real):
            raise BridgeError(f"Pasta bloqueada para o Codex pela política local ({denied}). "
                              "Siga só no Claude ou peça liberação ao usuário.", code=4)


def check_secret(*texts):
    if rules.has_secret([t for t in texts if t]):
        raise BridgeError("O texto contém algo com cara de segredo; nada foi enviado ao Codex. "
                          "Remova o valor e cite só onde ele mora.", code=4)


# ---------------------------------------------------------------- runtime do Codex

def companion_command():
    override = os.environ.get("HEBE_CODEX_COMPANION_CMD")
    if override:
        return shlex.split(override)
    explicit = os.environ.get("HEBE_CODEX_COMPANION")
    candidates = [explicit] if explicit else glob.glob(os.path.expanduser(COMPANION_GLOB))
    candidates = [c for c in candidates if c and os.path.isfile(c)]
    if not candidates:
        raise BridgeError("Plugin openai-codex não encontrado (codex-companion.mjs). Rode /codex:setup.", code=3)

    def version_key(path):
        version = Path(path).parts[-3]
        return [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", version)]

    node = shutil.which("node")
    if not node:
        raise BridgeError("node não encontrado no PATH.", code=3)
    return [node, sorted(candidates, key=version_key)[-1]]


def bridge_state_dir():
    root = os.environ.get("HEBE_CODEX_STATE") or os.path.expanduser("~/.cache/hebe-orchestrator/companion-data")
    os.makedirs(root, mode=0o700, exist_ok=True)
    return root


def companion_env():
    """Ambiente mínimo e estado próprio da ponte.

    - O Codex executa comandos e não precisa ver segredos da sessão do Claude.
    - ``CLAUDE_PLUGIN_DATA`` próprio + endpoint de broker inexistente forçam o companion a
      subir um app-server direto por chamada, com ESTE ambiente, em vez de reaproveitar um
      broker criado com o ambiente completo de outra sessão.
    """
    extra = tuple(p.strip() for p in os.environ.get("HEBE_CODEX_ENV_PASSTHROUGH", "").split(",") if p.strip())
    env = {}
    for key, value in os.environ.items():
        if key in ENV_DROP:
            continue
        if key in ENV_KEEP or key.startswith(ENV_PREFIXES) or (extra and key.startswith(extra)):
            env[key] = value
    state = bridge_state_dir()
    env["CLAUDE_PLUGIN_DATA"] = state
    env["CODEX_COMPANION_APP_SERVER_ENDPOINT"] = "unix:" + os.path.join(state, "no-broker.sock")
    env["CODEX_HOME"] = codex_home()
    return env


SUPPORTED_COMPANION = "1.0.6"
ISOLATED_LOGIN_HINT = ("Login isolado do Codex ausente. Rode uma vez no terminal: "
                       "CODEX_HOME=~/.cache/hebe-orchestrator/codex-home codex login "
                       "(ou ... codex login --device-auth). É um login separado do seu Codex principal.")


def codex_home():
    """CODEX_HOME isolado da ponte: login próprio, sem MCP, plugins, memória nem AGENTS.md global.

    Decisão do @advisor (2026-10-26): nunca copiar nem linkar ~/.codex/auth.json — o refresh
    token rotativo seria compartilhado e uma renovação de um lado deslogaria o outro.
    """
    return os.environ.get("HEBE_CODEX_HOME") or os.path.expanduser("~/.cache/hebe-orchestrator/codex-home")


def _user_codex_config():
    try:
        return (Path.home() / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return ""


def isolated_config_text():
    user = _user_codex_config()
    lines = ["# Gerado pela ponte do orquestrador HeBe (experimento for-claude+gpt). Reescrito a cada chamada.",
             'approval_policy = "never"', 'sandbox_mode = "workspace-write"']
    for key in ("model", "model_reasoning_effort", "service_tier", "model_context_window"):
        match = re.search(rf'^{key}\s*=\s*(.+)$', user, re.M)
        if match:
            lines.append(f"{key} = {match.group(1).strip()}")
    lines += ["", "[sandbox_workspace_write]", "network_access = false",
              "", "[shell_environment_policy]", 'inherit = "core"',
              "", "[features]", "memories = false"]
    for plugin in sorted(set(re.findall(r'^\[plugins\."([^"]+)"\]\s*$', user, re.M))):
        lines += ["", f'[plugins."{plugin}"]', "enabled = false"]
    return "\n".join(lines) + "\n"


def ensure_codex_home():
    """Garante o home isolado com as invariantes; o Codex pode reescrever o config, então refaz sempre."""
    home = codex_home()
    os.makedirs(home, mode=0o700, exist_ok=True)
    info = os.stat(home)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise BridgeError(f"{home} precisa pertencer a você e ter modo 0700.")
    for name in ("AGENTS.md", "AGENTS.override.md"):
        try:
            os.unlink(os.path.join(home, name))
        except FileNotFoundError:
            pass
    config = os.path.join(home, "config.toml")
    temporary = config + f".{secrets.token_hex(4)}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(isolated_config_text())
    os.replace(temporary, config)
    return home


def check_isolated_login(home):
    override = os.environ.get("HEBE_CODEX_LOGIN_CMD")
    command = shlex.split(override) if override else [shutil.which("codex") or "codex", "login", "status"]
    env = dict(companion_env(), CODEX_HOME=home)
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise BridgeError(ISOLATED_LOGIN_HINT, code=3) from None
    if done.returncode != 0:
        raise BridgeError(ISOLATED_LOGIN_HINT, code=3)


def prepare_codex():
    """Resolve o companion, garante o home isolado e confere o login antes de qualquer envio."""
    command = companion_command()
    home = ensure_codex_home()
    check_isolated_login(home)
    return command


class Interrupted(Exception):
    def __init__(self, cancel):
        super().__init__("interrompido")
        self.cancel = cancel


def run_companion(arguments, timeout, command=None, owner_cwd=None):
    """Roda o companion num grupo de processos próprio. Em timeout ou interrupção, encerra só esse grupo."""
    command = command or companion_command()
    started = time.monotonic()
    child = subprocess.Popen(command + arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             stdin=subprocess.DEVNULL, env=companion_env(), start_new_session=True)
    try:
        out, err = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        cancel = stop_process_group(child)
        return None, "", "timeout", time.monotonic() - started, cancel
    except KeyboardInterrupt:
        raise Interrupted(stop_process_group(child)) from None
    return child.returncode, out, err, time.monotonic() - started, {}


def stop_process_group(child):
    """Encerra o companion E o app-server que ele subiu (mesmo grupo), e confirma que acabou.

    Em modo direto o cancel do próprio companion não alcança o turno; matar o grupo é o que
    para o Codex de verdade. Só o grupo desta chamada é atingido.
    """
    import signal
    group = child.pid
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            break
        try:
            child.communicate(timeout=wait)
        except subprocess.TimeoutExpired:
            continue
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            break
    try:
        os.killpg(group, 0)
        alive = True
    except ProcessLookupError:
        alive = False
    except PermissionError:
        alive = True
    return {"cancelled": [] if alive else [f"pgid:{group}"], "failed": [f"pgid:{group}"] if alive else []}


def git(cwd, *arguments, check=True):
    done = subprocess.run(["git", *GIT_SAFE, "-C", cwd, *arguments], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)
    if check and done.returncode != 0:
        raise BridgeError(f"git {' '.join(arguments[:2])} falhou: {done.stderr.strip()[:300]}")
    return done.stdout


def validate_model(model):
    if not MODEL_RE.match(model or ""):
        raise BridgeError("Modelo inválido; use um id do Codex como gpt-6.1-sol ou gpt-6-astra.")
    return model


def is_bridge_worktree(path):
    root = os.path.realpath(worktree_root(create=False))
    return _inside(os.path.realpath(path), root)


# ---------------------------------------------------------------- review

def _raw_git(top, *arguments):
    return subprocess.run(["git", *GIT_SAFE, "-C", top, *arguments], capture_output=True,
                          stdin=subprocess.DEVNULL).stdout


def check_review_content(top, base):
    """O companion embute no prompt o diff e o conteúdo dos arquivos novos; nada disso pode ter segredo."""
    if base:
        diffs = [_raw_git(top, "diff", "--no-ext-diff", "--no-textconv", f"{base}...HEAD")]
        untracked = []
    else:
        diffs = [_raw_git(top, "diff", "--no-ext-diff", "--no-textconv", "HEAD"),
                 _raw_git(top, "diff", "--no-ext-diff", "--no-textconv", "--cached")]
        untracked = [n for n in _raw_git(top, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if n]
    for name in untracked:
        text = name.decode("utf-8", "replace")
        base_name = os.path.basename(text).lower()
        if any(fnmatch.fnmatch(base_name, pattern) for pattern in SECRET_NAMES):
            raise BridgeError(f"Arquivo novo com nome de segredo ({text}) iria para o Codex. Ignore-o no Git "
                              "ou remova antes de revisar.", code=4)
        try:
            with open(os.path.join(top, text), "rb") as stream:
                diffs.append(stream.read(UNTRACKED_SCAN_BYTES))
        except OSError:
            continue
    for blob in diffs:
        text = blob.decode("utf-8", "replace")
        for start in range(0, len(text), 200_000):
            if rules.has_secret([text[start:start + 200_200]]):
                raise BridgeError("O conteúdo a revisar tem algo com cara de segredo; nada foi enviado ao Codex. "
                                  "Remova o valor (cite só onde ele mora) e revise de novo.", code=4)

def compact_review(code, stdout):
    if code != 0:
        raise ValueError("companion terminou com erro")
    data = json.loads(stdout)
    if not isinstance(data, dict):
        raise ValueError("saída não é objeto")
    codex = data.get("codex") if isinstance(data.get("codex"), dict) else {}
    if codex.get("status") not in (None, 0):
        raise ValueError("Codex terminou com erro")
    result = data.get("result") if isinstance(data.get("result"), dict) else None
    if result is None and isinstance(codex.get("stdout"), str):
        result = json.loads(codex["stdout"])
    if result is None and "verdict" in data:
        result = data
    if not isinstance(result, dict) or not isinstance(result.get("verdict"), str) \
            or not isinstance(result.get("findings", []), list):
        raise ValueError("revisão sem veredito ou achados")
    findings = []
    for item in result.get("findings") or []:
        if not isinstance(item, dict):
            continue
        findings.append({
            "severity": item.get("severity"),
            "title": item.get("title"),
            "file": item.get("file"),
            "line": item.get("line_start"),
            "body": (item.get("body") or "")[:MAX_BODY],
            "recommendation": (item.get("recommendation") or "")[:MAX_BODY // 2],
        })
    return {"verdict": result["verdict"], "summary": result.get("summary"), "findings": findings}


def cmd_review(args):
    cwd = os.path.realpath(args.cwd)
    if not os.path.isdir(cwd):
        raise BridgeError("Pasta inexistente.")
    top = os.path.realpath(git(cwd, "rev-parse", "--show-toplevel").strip())
    check_policy(top)
    if len(args.focus or "") > MAX_FOCUS:
        raise BridgeError("Foco longo demais; resuma em até 2000 caracteres.")
    check_secret(args.focus)
    model = validate_model(args.model)
    branch = git(top, "branch", "--show-current", check=False).strip()
    if not args.allow_self and (is_bridge_worktree(top) or branch.startswith("codex/")):
        raise BridgeError("Esta árvore foi construída pelo Codex; o Codex não revisa o próprio trabalho. "
                          "Revise com o @reviewer (Opus).", code=4)
    dirty = bool(git(top, "status", "--porcelain").strip())
    if args.base:
        git(top, "rev-parse", "--verify", f"{args.base}^{{commit}}")
        if dirty:
            raise BridgeError("Há mudanças não commitadas que a revisão por --base não veria. "
                              "Rode sem --base para revisar a árvore de trabalho, ou commite antes.")
        scope = ["--base", args.base, "--scope", "branch"]
    else:
        if not dirty:
            raise BridgeError("Árvore limpa e sem --base: não há o que revisar. Use --base <commit> para revisar commits.")
        scope = ["--scope", "working-tree"]
    check_review_content(top, args.base)
    command = prepare_codex()
    arguments = ["adversarial-review", "--cwd", top, *scope, "--model", model, "--json"]
    if args.focus:
        arguments += ["--", args.focus]
    try:
        code, out, _, seconds, cancel = run_companion(arguments, timeout=args.timeout, command=command, owner_cwd=top)
    except Interrupted as interrupted:
        append_ledger({"id": new_id("rv"), "ts": stamp(), "kind": "review", "model": model, "ok": False,
                       "error": "interrompido", "repo": os.path.basename(top), "label": args.label,
                       **interrupted.cancel})
        raise BridgeError("Revisão interrompida; o job desta chamada foi cancelado.", code=3) from None
    entry = {"id": new_id("rv"), "ts": stamp(), "kind": "review", "model": model, "effort": "padrão",
             "scope": "branch" if args.base else "working-tree", "repo": os.path.basename(top),
             "label": args.label, "duration_s": round(seconds, 1)}
    if code is None:
        entry.update(ok=False, error="timeout", **cancel)
        append_ledger(entry)
        raise BridgeError("O Codex não terminou a revisão no prazo; job cancelado: "
                          f"{cancel.get('cancelled') or 'nenhum confirmado'}. Siga com o @reviewer (Opus) e avise "
                          "que a independência caiu.", code=3)
    try:
        review = compact_review(code, out)
    except (ValueError, TypeError, AttributeError):
        entry.update(ok=False, error="saida_invalida", exit=code)
        append_ledger(entry)
        raise BridgeError("O Codex não devolveu uma revisão válida. Siga com o @reviewer (Opus) e avise "
                          "que a independência caiu.", code=3) from None
    counts = {}
    for finding in review["findings"]:
        counts[finding["severity"] or "?"] = counts.get(finding["severity"] or "?", 0) + 1
    text = json.dumps(review, ensure_ascii=False)
    entry.update(ok=True, verdict=review["verdict"], findings=counts, return_chars=len(text),
                 claude_tokens_est=tokens(len(text) + len(args.focus or "")))
    append_ledger(entry)
    review.update(ledger_id=entry["id"], model=model, scope=entry["scope"])
    print(json.dumps(review, ensure_ascii=False, indent=1))
    return 0


# ---------------------------------------------------------------- build

def normalize_allow(allow):
    prefixes = []
    for raw in allow or []:
        if not raw.strip():
            raise BridgeError("--allow vazio; use '.' para permitir o repositório inteiro.")
        value = os.path.normpath(raw.strip()).strip("/")
        if value in ("", "."):
            return []
        if ".." in Path(value).parts:
            raise BridgeError(f"--allow inválido: {raw}")
        prefixes.append(value)
    return prefixes


def scope_report(worktree, base, allow, main_tree_changed=()):
    git(worktree, "add", "-A", "-N", ".", check=False)
    changed = []
    for line in git(worktree, "diff", "--name-status", "--no-renames", base).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changed.append((parts[0][:1], parts[-1]))
    flags = []
    prefixes = normalize_allow(allow)
    for status, path in changed:
        name = os.path.basename(path)
        if prefixes and not any(path == p or path.startswith(p + "/") for p in prefixes):
            flags.append({"file": path, "reason": "fora das pastas permitidas"})
        if name in LOCKFILES:
            flags.append({"file": path, "reason": "lockfile alterado (dependência)"})
        elif name in MANIFESTS:
            flags.append({"file": path, "reason": "manifesto de dependências alterado — conferir"})
        if name in NOTE_NAMES or "/vault/" in f"/{path}" or "/adr/" in f"/{path}".lower():
            flags.append({"file": path, "reason": "nota/Brain/vault/ADR criada ou alterada (fora do pedido?)"})
        if status == "A" and (name.endswith(".log") or "/results/" in f"/{path}/"):
            flags.append({"file": path, "reason": "log ou resultado de teste versionado"})
        if status == "D":
            flags.append({"file": path, "reason": "arquivo apagado"})
    for main_path in main_tree_changed or ():
        flags.append({"file": f"(árvore principal) {main_path}",
                      "reason": "a árvore do Claude mudou durante a construção — se não foi você editando em "
                                "paralelo, o sandbox não segurou; confira antes de qualquer coisa"})
    stat_line = git(worktree, "diff", "--shortstat", base).strip()
    return {"files": [p for _, p in changed], "shortstat": stat_line, "flags": flags}


def validate_copy(top, relative):
    value = os.path.normpath((relative or "").strip()).strip("/")
    if not value or value == "." or ".." in Path(value).parts:
        raise BridgeError(f"--copy inválido: {relative}")
    source = os.path.join(top, value)
    for part_index in range(1, len(Path(value).parts) + 1):
        if os.path.islink(os.path.join(top, *Path(value).parts[:part_index])):
            raise BridgeError(f"--copy recusado: {value} passa por symlink.", code=4)
    if not os.path.isdir(source):
        raise BridgeError(f"--copy só aceita pastas existentes: {value}")
    for part in Path(value).parts:
        if any(fnmatch.fnmatch(part.lower(), pattern) for pattern in SECRET_NAMES):
            raise BridgeError(f"--copy recusado: {value} tem nome de segredo.", code=4)
    ignored = subprocess.run(["git", "-C", top, "check-ignore", "-q", value], capture_output=True)
    if ignored.returncode != 0:
        raise BridgeError(f"--copy só aceita pasta ignorada pelo Git (ex.: node_modules): {value}")
    scan_copy(source, value)
    return value


def _has_private_key(path):
    try:
        with open(path, "rb") as stream:
            return b"PRIVATE KEY" in stream.read(64 * 1024)
    except OSError:
        return True


def scan_copy(source, label):
    """Recusa a pasta inteira se algo dentro dela parecer segredo ou apontar para fora."""
    root = os.path.realpath(source)
    seen = 0
    for current, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            seen += 1
            if seen > SCAN_LIMIT:
                raise BridgeError(f"--copy recusado: {label} é grande demais para conferir ({SCAN_LIMIT}+ entradas).")
            full = os.path.join(current, name)
            relative = os.path.relpath(full, source)
            lower = name.lower()
            if os.path.islink(full):
                target = os.path.realpath(full)
                if os.path.isabs(os.readlink(full)) or not _inside(target, root):
                    raise BridgeError(f"--copy recusado: {label}/{relative} é um symlink absoluto ou para fora da pasta.", code=4)
                continue
            if name in dirs and any(fnmatch.fnmatch(lower, p) for p in NESTED_DIRS):
                raise BridgeError(f"--copy recusado: {label}/{relative} parece pasta de credenciais.", code=4)
            if name in files:
                if any(fnmatch.fnmatch(lower, p) for p in NESTED_ALWAYS) and not lower.endswith((".example", ".sample")):
                    raise BridgeError(f"--copy recusado: {label}/{relative} parece arquivo de segredo.", code=4)
                if any(fnmatch.fnmatch(lower, p) for p in NESTED_KEY_FILES) and _has_private_key(full):
                    raise BridgeError(f"--copy recusado: {label}/{relative} contém chave privada.", code=4)


def copy_into(source_root, target_root, relative):
    source = os.path.join(source_root, relative)
    target = os.path.join(target_root, relative)
    if os.path.exists(target):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    clone = ["cp", "-Rc", source, target] if sys.platform == "darwin" else ["cp", "-R", "--reflink=auto", source, target]
    if subprocess.run(clone, capture_output=True).returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        if subprocess.run(["cp", "-R", source, target], capture_output=True).returncode != 0:
            raise BridgeError(f"Falha ao copiar {relative} para a worktree.")
    return True


def worktree_root(create=True):
    root = os.environ.get("HEBE_CODEX_WORKTREES") or os.path.expanduser("~/.cache/hebe-orchestrator/codex-worktrees")
    if create:
        os.makedirs(root, mode=0o700, exist_ok=True)
    return root


def tree_fingerprint(top):
    """Estado da árvore do Claude por caminho: refs, stash e conteúdo de cada arquivo sujo ou novo.

    Arquivos ignorados pelo Git (ex.: node_modules) ficam de fora.
    """
    refs = b"\n".join(line for line in _raw_git(top, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
                      if not line.startswith(b"refs/heads/codex/"))  # as branches da própria ponte não contam
    state = {"(refs)": hashlib.sha256(refs + _raw_git(top, "rev-parse", "HEAD")
                                      + _raw_git(top, "stash", "list")).hexdigest()}
    names = set(n for n in _raw_git(top, "diff", "--name-only", "-z", "HEAD").split(b"\0") if n)
    names |= set(n for n in _raw_git(top, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if n)
    for name in names:
        text = name.decode("utf-8", "surrogateescape")
        digest = hashlib.sha256()
        try:
            with open(os.path.join(top, text), "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            digest.update(b"(ausente)")
        state[text] = digest.hexdigest()
    return state


def changed_paths(before, after):
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def remove_worktree(top, path, branch):
    git(top, "worktree", "remove", "--force", path, check=False)
    shutil.rmtree(path, ignore_errors=True)
    git(top, "worktree", "prune", check=False)
    if branch:
        git(top, "branch", "-D", branch, check=False)


def read_brief(path):
    if not os.path.isfile(path) or os.path.islink(path):
        raise BridgeError("O briefing precisa ser um arquivo comum (sem symlink, FIFO ou pasta).")
    with open(path, "rb") as stream:
        if os.fstat(stream.fileno()).st_size > MAX_BRIEF:
            raise BridgeError("Briefing maior que 64 KiB; resuma ou divida a frente.")
        raw = stream.read(MAX_BRIEF + 1)
    try:
        brief = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BridgeError("Briefing precisa estar em UTF-8.") from None
    if not brief.strip():
        raise BridgeError("Briefing vazio.")
    return brief


def cmd_build(args):
    repo = os.path.realpath(args.repo)
    top = os.path.realpath(git(repo, "rev-parse", "--show-toplevel").strip())
    check_policy(top)
    if not LABEL_RE.match(args.label):
        raise BridgeError("--label deve ser curto, minúsculo, com letras, números e hífen.")
    if args.effort not in EFFORTS:
        raise BridgeError(f"Esforço inválido; o plugin aceita {', '.join(EFFORTS)}.")
    model = validate_model(args.model)
    brief = read_brief(args.brief)
    check_secret(brief)
    copies = [validate_copy(top, rel) for rel in args.copy or []]
    normalize_allow(args.allow)
    command = prepare_codex()
    base_sha = git(top, "rev-parse", "--verify", f"{args.base or 'HEAD'}^{{commit}}").strip()
    tag = f"{now():%Y%m%d-%H%M%S}"
    branch = f"codex/{args.label}-{tag}"
    path = os.path.join(worktree_root(), f"{os.path.basename(top)}-{args.label}-{tag}")
    main_before = tree_fingerprint(top)
    entry = {"id": new_id("bd"), "ts": stamp(), "kind": "build", "model": model, "effort": args.effort,
             "repo": os.path.basename(top), "label": args.label, "worktree": path, "branch": branch}
    git(top, "worktree", "add", "-q", "-b", branch, path, base_sha)
    prompt_file = None
    try:  # preparação: se falhar aqui, nada do Codex existe ainda e a worktree some
        copied = [rel for rel in copies if copy_into(top, path, rel)]
        prompt = brief.rstrip() + BUILD_RULES
        handle, prompt_file = tempfile.mkstemp(prefix="codex-brief-", suffix=".md")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(prompt)
    except BaseException:
        if prompt_file and os.path.exists(prompt_file):
            os.unlink(prompt_file)
        remove_worktree(top, path, branch)
        entry.update(ok=False, error="falha_antes_do_codex")
        append_ledger(entry)
        raise
    try:  # execução: daqui em diante a worktree é preservada para inspeção
        code, out, _, seconds, cancel = run_companion(
            ["task", "--write", "--cwd", path, "--model", model, "--effort", args.effort,
             "--json", "--prompt-file", prompt_file], timeout=args.timeout, command=command, owner_cwd=path)
    except Interrupted as interrupted:
        entry.update(ok=False, error="interrompido", copied=copied, **interrupted.cancel)
        append_ledger(entry)
        raise BridgeError(f"Construção interrompida; o job desta chamada foi cancelado. A worktree ficou em {path} "
                          "para inspeção (apague com cleanup --force).", code=3) from None
    finally:
        if os.path.exists(prompt_file):
            os.unlink(prompt_file)
    entry.update(duration_s=round(seconds, 1), copied=copied)
    main_changed = changed_paths(main_before, tree_fingerprint(top))
    if code is None:
        entry.update(ok=False, error="timeout", main_tree_changed=len(main_changed), **cancel)
        append_ledger(entry)
        raise BridgeError(f"O Codex não terminou no prazo; os jobs desta chamada foram cancelados. A worktree "
                          f"ficou em {path} para inspeção (apague com cleanup --force). Siga a frente no Claude.",
                          code=3)
    try:
        result = json.loads(out)
        summary = result.get("rawOutput") or "" if isinstance(result, dict) else ""
    except json.JSONDecodeError:
        summary = ""
    scope = scope_report(path, base_sha, args.allow, main_changed)
    ok = bool(summary) and code == 0
    entry.update(ok=ok, exit=code, return_chars=len(summary), brief_chars=len(prompt),
                 claude_tokens_est=tokens(len(summary) + len(prompt)), shortstat=scope["shortstat"],
                 scope_flags=len(scope["flags"]), main_tree_changed=len(main_changed))
    append_ledger(entry)
    report = {"ledger_id": entry["id"], "ok": ok, "model": model, "effort": args.effort,
              "worktree": path, "branch": branch, "base": base_sha, "duration_s": entry["duration_s"],
              "summary": summary, "diff": scope["shortstat"], "files": scope["files"],
              "scope_flags": scope["flags"],
              "next": ("Rode os testes na worktree, revise o diff com o @reviewer (Opus) — o Codex construiu —, "
                       "resolva cada scope_flag, commite na branch e integre. Depois: outcome --id e cleanup.")
              if ok else ("O Codex falhou ou não respondeu. Inspecione a worktree se houver diff; senão, "
                          "apague com cleanup --force e siga a frente no Claude.")}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if ok else 3


def cmd_cleanup(args):
    path = os.path.realpath(args.worktree)
    if not is_bridge_worktree(path) or path == os.path.realpath(worktree_root(create=False)):
        raise BridgeError("Só removo worktrees criadas pela ponte (em ~/.cache/hebe-orchestrator/codex-worktrees).")
    if not os.path.isdir(path):
        raise BridgeError("Worktree inexistente.")
    branch = git(path, "branch", "--show-current", check=False).strip()
    dirty = git(path, "status", "--porcelain").strip()
    if dirty and not args.force:
        raise BridgeError("A worktree tem mudanças não commitadas; commite, ou use --force para descartar.")
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    top = os.path.dirname(common) if os.path.basename(common) == ".git" else common
    git(top, "worktree", "remove", *(["--force"] if args.force else []), path)
    deleted = False
    if branch.startswith("codex/"):
        # Nunca -D: uma branch com commits não integrados fica, para ninguém perder trabalho.
        deleted = subprocess.run(["git", *GIT_SAFE, "-C", top, "branch", "-d", branch],
                                 capture_output=True).returncode == 0
    print(json.dumps({"removed": path, "branch": branch, "branch_deleted": deleted,
                      "note": None if deleted or not branch else
                      f"A branch {branch} tem commits não integrados e foi mantida; apague com git branch -D se for o caso."},
                     ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- experimento

def cmd_outcome(args):
    check_secret(args.note)
    ref = next((e for e in read_ledger() if e.get("id") == args.id), None)
    if ref is None:
        raise BridgeError("Id não encontrado no diário.")
    allowed = REVIEW_OUTCOMES if ref.get("kind") == "review" else BUILD_OUTCOMES
    if args.result not in allowed:
        raise BridgeError(f"Resultado inválido para {ref.get('kind')}; use {', '.join(allowed)}.")
    entry = {"ts": stamp(), "kind": "outcome", "ref": args.id, "result": args.result,
             "real": args.real, "false": args.false, "missed": args.missed,
             "claude_review_model": args.reviewer, "note": (args.note or "")[:300]}
    append_ledger(entry)
    print(json.dumps({"ok": True, "ref": args.id, "result": args.result}, ensure_ascii=False))
    return 0


def cmd_report(args):
    since = now() - timedelta(days=args.days)
    entries = read_ledger()
    outcomes = {e.get("ref"): e for e in entries if e.get("kind") == "outcome"}
    groups = {}
    for e in entries:
        if e.get("kind") not in ("review", "build"):
            continue
        try:
            when = datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError):
            continue
        if when < since:
            continue
        key = (e["kind"], e.get("model"), e.get("effort"))
        g = groups.setdefault(key, {"n": 0, "ok": 0, "seconds": 0.0, "claude_tokens_est": 0, "findings": 0,
                                    "scope_flags": 0, "outcomes": {}, "real": 0, "false": 0, "missed": 0})
        g["n"] += 1
        g["ok"] += 1 if e.get("ok") else 0
        g["seconds"] += e.get("duration_s") or 0
        g["claude_tokens_est"] += e.get("claude_tokens_est") or 0
        g["findings"] += sum((e.get("findings") or {}).values())
        g["scope_flags"] += e.get("scope_flags") or 0
        out = outcomes.get(e.get("id"))
        if out:
            g["outcomes"][out["result"]] = g["outcomes"].get(out["result"], 0) + 1
            for field in ("real", "false", "missed"):
                g[field] += out.get(field) or 0
    rows = []
    for (kind, model, effort), g in sorted(groups.items(), key=lambda kv: tuple(str(k) for k in kv[0])):
        judged = g["real"] + g["false"]
        rows.append({
            "kind": kind, "model": model, "effort": effort, "runs": g["n"],
            "ok_rate": round(g["ok"] / g["n"], 2),
            "avg_minutes": round(g["seconds"] / g["n"] / 60, 1),
            "avg_claude_tokens_est": round(g["claude_tokens_est"] / g["n"]),
            "avg_findings": round(g["findings"] / g["n"], 1) if kind == "review" else None,
            "precision": round(g["real"] / judged, 2) if judged else None,
            "missed_reported": g["missed"] if kind == "review" else None,
            "avg_scope_flags": round(g["scope_flags"] / g["n"], 1) if kind == "build" else None,
            "outcomes": g["outcomes"],
            "without_outcome": g["n"] - sum(g["outcomes"].values()),
        })
    print(json.dumps({"since": stamp(since), "days": args.days, "groups": rows}, ensure_ascii=False, indent=1))
    return 0


def cmd_policy(args):
    policy = load_policy()
    if args.action == "show":
        print(json.dumps(policy, ensure_ascii=False, indent=1))
        return 0
    if not args.path:
        raise BridgeError("Informe a pasta.")
    path = os.path.realpath(os.path.expanduser(args.path))
    paths = [p for p in policy["deny_paths"] if os.path.realpath(os.path.expanduser(p)) != path]
    if args.action == "deny":
        paths.append(path)
    policy["deny_paths"] = sorted(set(paths))
    write_private_json(POLICY, policy)
    print(json.dumps(policy, ensure_ascii=False, indent=1))
    return 0


def cmd_doctor(_args):
    report = {"ledger": str(Path.home() / ".config" / "hebe-brain" / LEDGER), "codex_home": codex_home(),
              "state_dir": bridge_state_dir()}
    problems = []
    try:
        command = companion_command()
        report["companion"] = command[-1]
        version = Path(command[-1]).parts[-3] if len(Path(command[-1]).parts) >= 3 else "?"
        report["companion_version"] = version
        if "HEBE_CODEX_COMPANION_CMD" not in os.environ and version != SUPPORTED_COMPANION:
            problems.append(f"Plugin openai-codex {version}: a ponte foi validada na {SUPPORTED_COMPANION} "
                            "(modo direto e formato de saída). Revalide antes de confiar.")
    except BridgeError as error:
        problems.append(str(error))
    try:
        home = ensure_codex_home()
        report["isolated_config"] = "sem MCP, plugins desligados, memória desligada, sem AGENTS.md, rede da sandbox desligada"
        try:
            check_isolated_login(home)
            report["isolated_login"] = True
        except BridgeError as error:
            report["isolated_login"] = False
            problems.append(str(error))
        codex = shutil.which("codex")
        if codex and "HEBE_CODEX_LOGIN_CMD" not in os.environ:
            listed = subprocess.run([codex, "mcp", "list"], capture_output=True, text=True, timeout=60,
                                    stdin=subprocess.DEVNULL, env=dict(companion_env(), CODEX_HOME=home))
            report["isolated_mcp_list"] = (listed.stdout or listed.stderr).strip()[:400]
    except (BridgeError, OSError, subprocess.TimeoutExpired) as error:
        problems.append(str(error))
    report["policy"] = load_policy()
    report["runs_total"] = sum(1 for e in read_ledger() if e.get("kind") in ("review", "build"))
    report["problems"] = problems
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if not problems else 3


def _sigterm_as_interrupt(_signum, _frame):
    raise KeyboardInterrupt


def main(argv=None):
    import signal
    signal.signal(signal.SIGTERM, _sigterm_as_interrupt)
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Confere plugin, login do Codex, sandbox, política e diário.")

    review = sub.add_parser("review", help="Revisão adversarial do Codex (somente leitura).")
    review.add_argument("--cwd", required=True)
    review.add_argument("--base", default=None,
                        help="Revisa os commits base..HEAD (exige árvore limpa). Sem ele, revisa a árvore de trabalho.")
    review.add_argument("--model", default=DEFAULT_REVIEW_MODEL)
    review.add_argument("--focus", default="")
    review.add_argument("--label", default="")
    review.add_argument("--allow-self", action="store_true", help="Permite revisar árvore construída pelo Codex.")
    review.add_argument("--timeout", type=int, default=30 * 60)

    build = sub.add_parser("build", help="Construção pelo Codex numa worktree própria.")
    build.add_argument("--repo", required=True)
    build.add_argument("--brief", required=True, help="Arquivo com o pedido completo.")
    build.add_argument("--label", required=True)
    build.add_argument("--model", default=DEFAULT_BUILD_MODEL)
    build.add_argument("--effort", default=DEFAULT_BUILD_EFFORT)
    build.add_argument("--base", default="HEAD")
    build.add_argument("--copy", action="append", help="Pasta ignorada pelo Git a copiar (ex.: node_modules).")
    build.add_argument("--allow", action="append", help="Pasta onde o Codex pode mexer (checagem de escopo).")
    build.add_argument("--timeout", type=int, default=45 * 60)

    cleanup = sub.add_parser("cleanup", help="Remove uma worktree criada pela ponte e a branch codex/.")
    cleanup.add_argument("--worktree", required=True)
    cleanup.add_argument("--force", action="store_true")

    outcome = sub.add_parser("outcome", help="Registra o desfecho de uma revisão ou construção.")
    outcome.add_argument("--id", required=True)
    outcome.add_argument("--result", required=True,
                         help="review: confirmed|mixed|noise · build: accepted|reworked|rejected")
    outcome.add_argument("--real", type=int, default=None, help="Achados confirmados (review).")
    outcome.add_argument("--false", type=int, default=None, help="Achados falsos ou irrelevantes (review).")
    outcome.add_argument("--missed", type=int, default=None, help="Problemas que o Codex deixou passar e outro achou.")
    outcome.add_argument("--reviewer", default=None, help="Modelo do Claude que revisou/adjudicou.")
    outcome.add_argument("--note", default="")

    report = sub.add_parser("report", help="Resumo do experimento.")
    report.add_argument("--days", type=int, default=30)

    policy = sub.add_parser("policy", help="Pastas bloqueadas para o Codex.")
    policy.add_argument("action", choices=("show", "deny", "allow"))
    policy.add_argument("path", nargs="?")

    args = parser.parse_args(argv)
    handlers = {"doctor": cmd_doctor, "review": cmd_review, "build": cmd_build, "cleanup": cmd_cleanup,
                "outcome": cmd_outcome, "report": cmd_report, "policy": cmd_policy}
    try:
        return handlers[args.command](args)
    except BridgeError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return error.code
    except OSError as error:
        print(json.dumps({"ok": False, "error": f"Falha de arquivo: {error.strerror}"}, ensure_ascii=False))
        return 2
    except Exception as error:  # contrato: sempre JSON e código conhecido
        print(json.dumps({"ok": False, "error": f"Erro inesperado: {type(error).__name__}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
