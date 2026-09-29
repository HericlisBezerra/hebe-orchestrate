#!/usr/bin/env python3
"""Decisões assertivas com TypeSafe/Jev para o orquestrador HeBe (Claude Code e Codex).

Três poderes, cada um liberado explicitamente com ``authorize``:

- ``plan_gate``: aprova um plano local e reversível sem esperar o usuário.
- ``tiebreak``: escolhe entre opções reversíveis de baixo impacto.
- ``escalation``: decide se a saída de um subagente sobe de nível ou é aceita.

Regras duras rodam em código ANTES de qualquer rede: mensagens a terceiros,
ações irreversíveis, publicação, credenciais, dinheiro, produção, permissões e
veredito de segurança nunca são decididos pelo Jev. Sem autorização, credencial
ou resposta confiável, a decisão cai no fluxo conservador do orquestrador.

Somente biblioteca padrão. Chave, resumos enviados e log ficam fora do Git.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import unicodedata

if __package__:
    from . import jev, jev_rules as rules
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import jev
    import jev_rules as rules


CONFIG_FILE = "jev-decide.json"
LOG_FILE = "jev-decisions.jsonl"
MAX_INPUT = 64 * 1024
KINDS = ("plan_gate", "tiebreak", "escalation")
DEFAULT_THRESHOLDS = {"plan_gate": 0.85, "tiebreak": 0.65, "escalation": 0.80}
# Resultado quando o Jev não decide (sem autorização, abstenção, falha ou segredo).
FALLBACK = {"plan_gate": "ask_user", "tiebreak": "model_decides", "escalation": "escalate"}
# Resultado quando uma regra dura bloqueia: o usuário decide, ou o nível sobe.
HARD_RULE = {"plan_gate": "ask_user", "tiebreak": "human_required", "escalation": "escalate"}
FLAGS = frozenset({
    "third_party_message", "irreversible", "destructive", "publish", "deploy", "push",
    "credentials", "money", "production_data", "permissions", "security_verdict",
})

RESERVED_IDS = frozenset({"proceed", "ask_user", "model_decides", "human_required", "accept", "escalate"})
MIN_THRESHOLD = {"plan_gate": 0.70, "tiebreak": 0.50, "escalation": 0.70}
TIEBREAK_MIN_CONFIDENCE = 0.50
# O limiar configurável do plan_gate vale para "seguro" (o que protege o usuário).
# Escopo errado custa só trabalho a mais; por isso tem limiar próprio, fixo.
SCOPE_THRESHOLD = 0.70
LOG_ROTATE_BYTES = 5 * 1024 * 1024


FIELDS = {
    "plan_gate": ({"kind", "summary", "actions"}, {"context", "flags"}),
    "tiebreak": ({"kind", "summary", "criterion", "options"}, {"context", "flags"}),
    "escalation": ({"kind", "summary", "output_summary"}, {"signals", "flags"}),
}
OPTION_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


class DecideError(Exception):
    """Mensagens seguras para exibir: nunca incluem conteúdo enviado ou chave."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text(value, limit, field, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise DecideError("%s deve ser texto." % field)
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise DecideError("%s contém caracteres inválidos." % field)
    value = rules.strip_format(unicodedata.normalize("NFKC", value)).strip()
    if not value or len(value) > limit:
        raise DecideError("%s deve ser texto não vazio de até %d caracteres." % (field, limit))
    if any(ord(c) < 32 and c not in "\t\n\r" for c in value):
        raise DecideError("%s contém caracteres de controle." % field)
    return value


def text_list(value, limit, item_limit, field, required=True):
    if not required and (value is None or value == []):
        return []
    if not isinstance(value, list) or not 1 <= len(value) <= limit:
        raise DecideError("%s deve ser lista com 1 a %d itens." % (field, limit))
    return [text(item, item_limit, field) for item in value]


def validate(data):
    if not isinstance(data, dict) or data.get("kind") not in KINDS:
        raise DecideError("Informe kind: plan_gate, tiebreak ou escalation.")
    kind = data["kind"]
    required, optional = FIELDS[kind]
    missing, extra = required - set(data), set(data) - required - optional
    if missing or extra:
        raise DecideError("Campos para %s: obrigatórios %s; opcionais %s." % (
            kind, sorted(required), sorted(optional)))
    flags = data.get("flags", [])
    if not isinstance(flags, list) or len(flags) > 20 or not all(isinstance(f, str) for f in flags):
        raise DecideError("flags deve ser lista de até 20 nomes.")
    clean = []
    for flag in flags:
        name = re.sub(r"[^a-z0-9_]", "", rules.fold(flag))[:40] or "vazia"
        if name not in clean:
            clean.append(name)
    request = {"kind": kind, "summary": text(data["summary"], 4000, "summary"), "flags": clean}
    if kind == "plan_gate":
        request["actions"] = text_list(data["actions"], 40, 400, "actions")
        request["context"] = text(data.get("context"), 2000, "context", required=False)
    elif kind == "tiebreak":
        request["criterion"] = text(data["criterion"], 600, "criterion")
        request["context"] = text(data.get("context"), 2000, "context", required=False)
        options = data["options"]
        if not isinstance(options, dict) or not 2 <= len(options) <= 8:
            raise DecideError("options deve ter de 2 a 8 opções {id: descrição}.")
        for key in options:
            if not isinstance(key, str) or not OPTION_ID.fullmatch(key):
                raise DecideError("IDs de opção usam a-z, 0-9, _ e -, até 40 caracteres.")
            if key in RESERVED_IDS:
                raise DecideError("ID de opção não pode ser uma palavra de decisão (%s)." % ", ".join(sorted(RESERVED_IDS)))
        request["options"] = {k: text(v, 400, "options") for k, v in options.items()}
    else:
        request["output_summary"] = text(data["output_summary"], 4000, "output_summary")
        request["signals"] = text_list(data.get("signals"), 20, 300, "signals", required=False)
    return request


def texts_of(request):
    values = [request["summary"]]
    for field in ("context", "criterion", "output_summary"):
        if request.get(field):
            values.append(request[field])
    values.extend(request.get("actions", []))
    values.extend(request.get("signals", []))
    values.extend(request.get("options", {}).values())
    return values


def hard_rules(request):
    """Motivos que impedem o Jev de decidir; lista vazia libera."""
    reasons = []
    for flag in request["flags"]:
        reason = flag if flag in FLAGS else "flag_desconhecida:" + flag
        if reason not in reasons:
            reasons.append(reason)
    extra = rules.deny_reasons(texts_of(request))
    if request["kind"] == "plan_gate":
        extra += rules.action_reasons(request["actions"])
    elif request["kind"] == "tiebreak":
        extra += rules.option_reasons(request["options"].values())
    for reason in extra:
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def has_secret(request):
    return rules.has_secret(texts_of(request))


def build_payload(request, model):
    kind = request["kind"]
    if kind == "plan_gate":
        state = {"pedido": request["summary"], "acoes_planejadas": request["actions"]}
        if request["context"]:
            state["contexto"] = request["context"]
        questions = {
            "seguro": {"type": "noul", "instructions": (
                "Todas as ações planejadas são locais e reversíveis (desfeitas por git ou apagando o que foi "
                "criado), sem efeito fora da máquina, sem dados de produção, dinheiro, credenciais, permissões "
                "ou mensagens para outras pessoas?"),
                "criteria": {"true": "Sim: tudo é local e reversível.",
                             "false": "Não, ou não dá para garantir: há efeito externo, irreversível ou sensível."}},
            "no_escopo": {"type": "noul", "instructions": (
                "As ações planejadas fazem o que o pedido exige, sem acrescentar mudanças que o pedido não pede? "
                "Passos de apoio necessários para concluir e verificar o pedido — ajustar imports e referências, "
                "rodar testes, lint ou build, ler o código — contam como parte do escopo."),
                "criteria": {"true": "Sim: o plano cobre o pedido e seus passos de apoio, sem mudanças extras.",
                             "false": "Não: falta parte do pedido ou o plano muda coisas que o pedido não pede."}},
        }
    elif kind == "tiebreak":
        state = {"decisao": request["summary"], "criterio": request["criterion"], "opcoes": request["options"]}
        if request["context"]:
            state["contexto"] = request["context"]
        questions = {
            "escolha": {"type": "choice", "instructions": "Qual opção atende melhor ao critério da decisão?",
                        "criteria": request["options"]},
            "alguma_adequada": {"type": "noul", "instructions": (
                "Pelo menos uma das opções atende bem ao critério, sem ser apenas a menos ruim?"),
                "criteria": {"true": "Sim: existe opção adequada.",
                             "false": "Não: todas as opções falham no critério."}},
        }
    else:
        state = {"tarefa": request["summary"], "saida_do_agente": request["output_summary"]}
        if request["signals"]:
            state["sinais_observados"] = request["signals"]
        questions = {
            "escalar": {"type": "noul", "instructions": (
                "A saída do agente mostra que o resultado ainda não é confiável: incerteza declarada, "
                "contradição, verificação não executada, escopo diferente do pedido ou tarefa acima da "
                "capacidade do agente?"),
                "criteria": {"true": "Sim: precisa de um modelo mais forte ou de outra rodada.",
                             "false": "Não: a saída está consistente e verificada o suficiente para seguir."}},
        }
    return {"model": model, "state": state, "questions": questions}


def judge(kind, answers, threshold):
    """Aplica o limiar às respostas validadas. Devolve (decisão, modo, motivo, sinais)."""
    if kind == "plan_gate":
        safe, scope = answers["seguro"]["noul"], answers["no_escopo"]["noul"]
        signals = {"seguro": safe, "no_escopo": scope}
        if safe >= threshold and scope >= SCOPE_THRESHOLD:
            return "proceed", "jev", "Plano local e reversível acima do limiar, e dentro do escopo.", signals
        return "ask_user", "abstain", "Probabilidade abaixo do limiar; aprovação volta para o usuário.", signals
    if kind == "tiebreak":
        choice = answers["escolha"]
        top = choice["probabilities"][choice["choice"]]
        adequate = answers["alguma_adequada"]["noul"]
        signals = {"escolha": choice["choice"], "p_escolha": top, "confidence": choice["confidence"],
                   "alguma_adequada": adequate}
        if adequate < threshold:
            return "model_decides", "abstain", "Nenhuma opção parece adequada; o modelo reavalia.", signals
        if top >= threshold and choice["confidence"] >= TIEBREAK_MIN_CONFIDENCE:
            return choice["choice"], "jev", "Opção escolhida acima do limiar.", signals
        return "model_decides", "abstain", "Opções equilibradas; o modelo decide e registra.", signals
    p = answers["escalar"]["noul"]
    signals = {"escalar": p}
    if p <= 1 - threshold:
        return "accept", "jev", "Saída consistente; baixa probabilidade de precisar escalar.", signals
    return "escalate", "jev" if p >= threshold else "abstain", (
        "Sinais de resultado não confiável." if p >= threshold else "Incerto; na dúvida, sobe."), signals


# ---- armazenamento privado (~/.config/hebe-brain, modo 0700; arquivos 0600) ----

def read_private(name, limit=MAX_INPUT, tail=False):
    """Lê arquivo privado; com tail=True devolve só os últimos ``limit`` bytes."""
    directory = jev.private_directory()
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        except OSError:
            raise DecideError("Arquivo %s inseguro ou indisponível." % name) from None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 \
                    or stat.S_IMODE(info.st_mode) != 0o600:
                raise DecideError("Arquivo %s inseguro; exige arquivo próprio com modo 0600." % name)
            if tail and info.st_size > limit:
                stream.seek(info.st_size - limit)
                return stream.read(limit).split(b"\n", 1)[-1]
            return stream.read(limit + 1)
    finally:
        os.close(directory)


def write_private(name, data):
    directory = jev.private_directory(create=True)
    temporary = ".%s-%s.tmp" % (name, secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory)
        except OSError:
            pass
        raise
    finally:
        os.close(directory)


def append_log(entry):
    directory = jev.private_directory(create=True)
    try:
        try:
            info = os.stat(LOG_FILE, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_size > LOG_ROTATE_BYTES:
                os.replace(LOG_FILE, LOG_FILE + ".1", src_dir_fd=directory, dst_dir_fd=directory)
        except FileNotFoundError:
            pass
        fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "ab") as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
                raise DecideError("Log de decisões inseguro; exige arquivo próprio com modo 0600.")
            stream.write((json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    finally:
        os.close(directory)


def load_config():
    try:
        raw = read_private(CONFIG_FILE)
    except FileNotFoundError:
        return None
    if raw is None:
        return None
    try:
        data = jev.strict_json(raw, MAX_INPUT)
    except jev.JevError:
        raise DecideError("Configuração de decisões inválida; rode authorize novamente.") from None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("powers"), list):
        raise DecideError("Configuração de decisões inválida; rode authorize novamente.")
    thresholds = dict(DEFAULT_THRESHOLDS)
    configured = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    for kind, value in configured.items():
        if kind in thresholds and jev.probability(value) and value >= MIN_THRESHOLD[kind]:
            thresholds[kind] = value
    model = data.get("model", jev.DEFAULT_MODEL)
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
        model = jev.DEFAULT_MODEL
    return {"powers": [p for p in data["powers"] if p in KINDS], "thresholds": thresholds, "model": model,
            "authorized_at": data.get("authorized_at")}


# ---- decisão ----

def decide(request, config, send=True):
    kind = request["kind"]
    threshold = (config or {}).get("thresholds", DEFAULT_THRESHOLDS).get(kind, DEFAULT_THRESHOLDS[kind])
    model = (config or {}).get("model", jev.DEFAULT_MODEL)
    secret = has_secret(request)
    result = {"kind": kind, "threshold": threshold, "model_requested": model, "signals": {},
              "secret_detected": secret}

    blocked = hard_rules(request)
    if blocked:
        return dict(result, decision=HARD_RULE[kind], mode="hard_rule", blocked_by=blocked,
                    reason="Regra dura: o Jev não decide este tipo de ação.")
    if config is None or kind not in config["powers"]:
        return dict(result, decision=FALLBACK[kind], mode="not_authorized",
                    reason="Poder não autorizado; nada foi enviado.")
    if secret:
        return dict(result, decision=FALLBACK[kind], mode="refused_secret",
                    reason="O resumo parece conter segredo; nada foi enviado.")
    payload = build_payload(request, model)
    if not send:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return dict(result, decision=None, mode="dry_run", would_send=True,
                    question_ids=list(payload["questions"]), request_bytes=len(encoded.encode("utf-8")),
                    reason="Validado localmente; nada foi enviado.")
    try:
        key, _ = jev.active_credentials(required=True)
        data = jev.request_api("systemone", key, payload)
        validated = jev.evaluation_output(data, payload["questions"])
    except jev.JevError as exc:
        return dict(result, decision=FALLBACK[kind], mode="unavailable", reason=str(exc))
    decision, mode, reason, signals = judge(kind, validated["answers"], threshold)
    return dict(result, decision=decision, mode=mode, reason=reason, signals=signals,
                model=validated["model"], usage=validated["usage"])


def record(request, result, config):
    """Registra a decisão para auditoria — só quando o Jev foi configurado."""
    if config is None:
        result["log"] = "desativado"
        return result
    fingerprint = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    result["decision_id"] = fingerprint[:12] + "-" + secrets.token_hex(3)
    entry = {"at": now(), "decision_id": result["decision_id"], "kind": result["kind"],
             "decision": result["decision"], "mode": result["mode"], "reason": result["reason"],
             "signals": result.get("signals", {}), "blocked_by": result.get("blocked_by", []),
             "threshold": result["threshold"], "model": result.get("model"),
             "summary": None if (result.get("secret_detected") or "credentials" in result.get("blocked_by", []))
             else rules.redact(request["summary"])[:200],
             "fingerprint": fingerprint}
    try:
        append_log(entry)
    except (OSError, DecideError, jev.JevError):
        result["log"] = "falhou"
    return result


def read_request(filename):
    if filename in (None, "-"):
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    else:
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise DecideError("--file exige arquivo JSON regular.")
                raw = stream.read(MAX_INPUT + 1)
        except OSError:
            raise DecideError("Não foi possível ler o arquivo; symlinks não são aceitos.") from None
    try:
        return jev.strict_json(raw, MAX_INPUT)
    except jev.JevError as exc:
        raise DecideError(str(exc)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Mostra poderes, limiares e presença da credencial. Sem rede.")
    authorize = sub.add_parser("authorize", help="Registra a autorização permanente dos poderes informados.")
    authorize.add_argument("--powers", required=True, help="Lista separada por vírgula: " + ",".join(KINDS))
    for kind in KINDS:
        authorize.add_argument("--" + kind.replace("_", "-"), type=float, dest=kind,
                               help="Limiar de %s (%.2f a 1; padrão %.2f; os demais são preservados)." % (
                                   kind, MIN_THRESHOLD[kind], DEFAULT_THRESHOLDS[kind]))
    sub.add_parser("revoke", help="Revoga todos os poderes; nada mais é enviado.")
    run = sub.add_parser("decide", help="Lê o pedido JSON (stdin ou --file) e devolve a decisão.")
    run.add_argument("--file", help="JSON regular; padrão stdin.")
    run.add_argument("--dry-run", action="store_true", help="Valida e aplica regras duras sem enviar.")
    log = sub.add_parser("log", help="Mostra as últimas decisões registradas.")
    log.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            config = load_config()
            _, source = jev.active_credentials(required=False)
            print(json.dumps({"authorized_powers": config["powers"] if config else [],
                              "thresholds": config["thresholds"] if config else DEFAULT_THRESHOLDS,
                              "model": config["model"] if config else jev.DEFAULT_MODEL,
                              "authorized_at": config["authorized_at"] if config else None,
                              "credential": source or "ausente", "network_used": False}, ensure_ascii=False))
        elif args.command == "authorize":
            powers = [p.strip() for p in args.powers.split(",") if p.strip()]
            if not powers or set(powers) - set(KINDS):
                raise DecideError("Poderes válidos: " + ", ".join(KINDS))
            previous = load_config()
            thresholds = dict(previous["thresholds"]) if previous else dict(DEFAULT_THRESHOLDS)
            for kind in KINDS:
                value = getattr(args, kind)
                if value is not None:
                    if not MIN_THRESHOLD[kind] <= value <= 1:
                        raise DecideError("Limiar de %s deve ficar entre %.2f e 1." % (kind, MIN_THRESHOLD[kind]))
                    thresholds[kind] = value
            config = {"schema_version": 1, "powers": sorted(set(powers)), "thresholds": thresholds,
                      "model": jev.DEFAULT_MODEL, "authorized_at": now()}
            write_private(CONFIG_FILE, (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            print(json.dumps({"authorized_powers": config["powers"], "thresholds": thresholds}, ensure_ascii=False))
        elif args.command == "revoke":
            write_private(CONFIG_FILE, (json.dumps({"schema_version": 1, "powers": [], "revoked_at": now()})
                                        + "\n").encode("utf-8"))
            print(json.dumps({"authorized_powers": [], "revoked": True}))
        elif args.command == "decide":
            request = validate(read_request(args.file))
            config = load_config()
            result = decide(request, config, send=not args.dry_run)
            if not args.dry_run:
                result = record(request, result, config)
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        else:
            try:
                raw = read_private(LOG_FILE, limit=4 * 1024 * 1024, tail=True) or b""
            except FileNotFoundError:
                raw = b""
            lines = [line for line in raw.decode("utf-8", "replace").splitlines() if line.strip()]
            for line in lines[-max(1, min(args.limit, 500)):]:
                print(line)
    except (DecideError, jev.JevError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    except OSError as exc:
        print(json.dumps({"ok": False, "error": "Falha de sistema de arquivos (%s); trate como decisão não tomada."
                          % type(exc).__name__}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
