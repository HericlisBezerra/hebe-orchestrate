#!/usr/bin/env python3
"""Connect TypeSafe locally; send only explicitly supplied evaluation JSON.

Python standard library only. Credentials never enter the Brain or repository.
The setup page listens on loopback only and closes after one successful setup.
"""

import argparse
from datetime import datetime, timezone
import getpass
import http.client
import http.server
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
import urllib.error
import urllib.request
import warnings


API_ROOT = "https://api.typesafe.ai/v1"
DEFAULT_MODEL = "jev-latest"
MAX_INPUT = 1024 * 1024
MAX_RESPONSE = 2 * 1024 * 1024
MAX_SETUP = 8192
KEY_FILE = "typesafe.json"
SETUP_LIFETIME = 15 * 60


class JevError(Exception):
    """Messages must be safe to display without payloads or credentials."""


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def key_value(value):
    if not isinstance(value, str):
        raise JevError("Informe uma chave TypeSafe válida.")
    value = value.strip()
    if not value or len(value) > 4096 or any(not 33 <= ord(c) <= 126 for c in value):
        raise JevError("Formato da chave TypeSafe inválido; conteúdo omitido.")
    return value


def strict_json(raw, limit):
    if len(raw) > limit:
        raise JevError("JSON excede o limite local de tamanho.")

    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise JevError("JSON contém chave duplicada.")
            result[name] = value
        return result

    def invalid_constant(_):
        raise JevError("JSON contém número não finito.")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
        pending = [(value, 0)]
        count = 0
        while pending:
            item, depth = pending.pop()
            count += 1
            if depth > 32 or count > 100000:
                raise JevError("JSON excede o limite local de estrutura.")
            if isinstance(item, dict):
                pending.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
            elif isinstance(item, float) and not math.isfinite(item):
                raise JevError("JSON contém número não finito.")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise JevError("JSON inválido; conteúdo omitido.") from None


def private_directory(create=False):
    """Walk fixed directories using fds, rejecting symlinks and unsafe owners."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(str(Path.home()), flags)
    try:
        home = os.fstat(fd)
        if home.st_uid != os.getuid() or stat.S_IMODE(home.st_mode) & 0o022:
            raise JevError("A pasta do usuário precisa ter proprietário e permissões seguros.")
        for name, private in ((".config", False), ("hebe-brain", True)):
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            mode = stat.S_IMODE(info.st_mode)
            if info.st_uid != os.getuid() or mode & (0o077 if private else 0o022):
                raise JevError("Armazenamento inseguro: ~/.config/hebe-brain deve pertencer ao usuário e ter modo 0700.")
        return fd
    except BaseException:
        os.close(fd)
        raise


def safe_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
        raise JevError("Arquivo de credenciais inseguro; use arquivo regular próprio com modo 0600.")


def stored_credentials():
    try:
        directory = private_directory()
    except FileNotFoundError:
        return None
    try:
        try:
            fd = os.open(KEY_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        except OSError:
            raise JevError("Arquivo de credenciais indisponível ou inseguro; configure novamente.") from None
        with os.fdopen(fd, "rb") as stream:
            safe_file(os.fstat(stream.fileno()))
            data = strict_json(stream.read(MAX_SETUP + 1), MAX_SETUP)
        if not isinstance(data, dict) or data.get("schema_version", 1) != 1:
            raise JevError("Arquivo de credenciais inválido; configure novamente.")
        if data.get("api_key") == "":
            return None
        return key_value(data.get("api_key"))
    finally:
        os.close(directory)


def active_credentials(required=True):
    if "TYPESAFE_API_KEY" in os.environ:
        return key_value(os.environ["TYPESAFE_API_KEY"]), "environment"
    key = stored_credentials()
    if key is not None:
        return key, "local_file"
    if required:
        raise JevError("TypeSafe não configurado. Execute configure --web ou configure em um terminal.")
    return None, None


def save_credentials(key):
    directory = private_directory(create=True)
    temporary = ".typesafe-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        try:
            safe_file(os.stat(KEY_FILE, dir_fd=directory, follow_symlinks=False))
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({"schema_version": 1, "api_key": key, "validated_at": timestamp()}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, KEY_FILE, src_dir_fd=directory, dst_dir_fd=directory)
        created = False
        os.fsync(directory)
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_api(endpoint, key, payload=None):
    # Fixed HTTPS origin, no environment proxy, redirects or automatic retries.
    if endpoint not in ("models", "systemone"):
        raise JevError("Endpoint não permitido.")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if body is not None and len(body) > MAX_INPUT:
        raise JevError("Pedido excede o limite local de 1 MiB.")
    request = urllib.request.Request(API_ROOT + "/" + endpoint, data=body,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                 "Content-Type": "application/json", "User-Agent": "HeBe-Jev/1"},
        method="GET" if body is None else "POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise JevError("TypeSafe retornou status inesperado.")
            if response.headers.get_content_type() != "application/json":
                raise JevError("TypeSafe retornou formato inesperado.")
            return strict_json(response.read(MAX_RESPONSE + 1), MAX_RESPONSE)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        messages = {401: "Chave TypeSafe recusada.", 403: "A conta não tem acesso a esta operação.",
                    422: "TypeSafe recusou o formato do pedido.", 429: "Limite TypeSafe atingido.",
                    529: "TypeSafe está temporariamente sobrecarregado."}
        raise JevError(messages.get(code, "TypeSafe não concluiu a operação (HTTP %d)." % code)
                       + " Nenhuma repetição automática foi feita.") from None
    except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException):
        message = "Não foi possível confirmar a resposta de TypeSafe."
        if payload is not None:
            message += " A avaliação pode ter sido processada; confira o uso antes de reenviar."
        raise JevError(message + " Nenhuma repetição automática foi feita.") from None


def model_list(key):
    data = request_api("models", key)
    if not isinstance(data, dict) or not isinstance(data.get("models"), list) or len(data["models"]) > 1000:
        raise JevError("Catálogo TypeSafe inválido.")
    cards = []
    for item in data["models"]:
        if not isinstance(item, dict) or any(not isinstance(item.get(field), str)
                for field in ("name", "description", "release_date")):
            raise JevError("Catálogo TypeSafe inválido.")
        cards.append({field: item[field] for field in ("name", "description", "release_date")})
    return cards


def description(value, nullable=False):
    return (nullable and value is None) or isinstance(value, (str, dict, list))


def evaluation_input(filename, model_override):
    try:
        fd = os.open(filename, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise JevError("--file exige um arquivo JSON regular.")
            data = strict_json(stream.read(MAX_INPUT + 1), MAX_INPUT)
    except OSError:
        raise JevError("Não foi possível ler o arquivo de avaliação.") from None
    if not isinstance(data, dict) or set(data) - {"model", "state", "questions"}:
        raise JevError("Use objeto JSON com state, questions e model opcional.")
    if not description(data.get("state")):
        raise JevError("state deve ser texto, objeto ou lista JSON.")
    questions = data.get("questions")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 256:
        raise JevError("questions deve conter entre 1 e 256 perguntas nomeadas.")
    for name, question in questions.items():
        if not name or len(name) > 256 or not isinstance(question, dict):
            raise JevError("Pergunta inválida; use identificador de até 256 caracteres e objeto tipado.")
        if set(question) - {"type", "instructions", "criteria"} or not description(question.get("instructions")):
            raise JevError("Perguntas aceitam type, instructions e criteria.")
        kind, criteria = question.get("type"), question.get("criteria")
        if kind == "noul":
            if "criteria" in question and (not isinstance(criteria, dict) or set(criteria) - {"true", "false"}
                    or not all(description(v) for v in criteria.values())):
                raise JevError("Noul criteria aceita descrições true e false.")
        elif kind == "choice":
            if not isinstance(criteria, dict) or not 1 <= len(criteria) <= 255 or not all(
                    k and description(v, nullable=True) for k, v in criteria.items()):
                raise JevError("Choice exige criteria com 1 a 255 opções descritas.")
        elif kind == "score":
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10 or not all(description(v) for v in criteria):
                raise JevError("Score exige criteria com 2 a 10 níveis descritos.")
        else:
            raise JevError("Tipo de pergunta deve ser noul, choice ou score.")
    model = model_override if model_override is not None else data.get("model", DEFAULT_MODEL)
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
        raise JevError("Identificador de modelo inválido.")
    return {"model": model, "state": data["state"], "questions": questions}


def evaluation_preview(payload):
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    kinds = {"noul": 0, "choice": 0, "score": 0}
    for question in payload["questions"].values():
        kinds[question["type"]] += 1
    state = payload["state"]
    state_type = "object" if isinstance(state, dict) else "array" if isinstance(state, list) else "string"
    return {
        "valid": True,
        "network_used": False,
        "credential_used": False,
        "model": payload["model"],
        "state_type": state_type,
        "question_count": len(payload["questions"]),
        "question_types": kinds,
        "request_bytes": len(encoded),
        "question_ids": list(payload["questions"]),
    }


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def evaluation_output(data, questions):
    bad = "Resposta TypeSafe incompatível com as perguntas; conteúdo omitido."
    if not isinstance(data, dict) or not isinstance(data.get("model"), str):
        raise JevError(bad)
    answers, usage = data.get("answers"), data.get("usage")
    if not isinstance(answers, dict) or set(answers) != set(questions) or not isinstance(usage, dict):
        raise JevError(bad)
    for field in ("input_tokens", "output_tokens"):
        if type(usage.get(field)) is not int or usage[field] < 0:
            raise JevError(bad)
    output = {}
    for name, question in questions.items():
        answer = answers[name]
        kind = question["type"]
        if not isinstance(answer, dict) or answer.get("type") != kind:
            raise JevError(bad)
        if kind == "noul":
            if not probability(answer.get("noul")):
                raise JevError(bad)
            output[name] = {"type": kind, "noul": answer["noul"]}
            continue
        probs = answer.get("probabilities")
        expected = set(question["criteria"]) if kind == "choice" else {str(i) for i in range(len(question["criteria"]))}
        if (not isinstance(probs, dict) or set(probs) != expected or not all(probability(v) for v in probs.values())
                or abs(sum(probs.values()) - 1) > 0.02 or not probability(answer.get("confidence"))):
            raise JevError(bad)
        result = {"type": kind, "probabilities": probs, "confidence": answer["confidence"]}
        if kind == "choice":
            if not isinstance(answer.get("choice"), str) or answer["choice"] not in expected:
                raise JevError(bad)
            result["choice"] = answer["choice"]
        else:
            score, legend = answer.get("score"), answer.get("legend")
            if (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= len(expected) - 1
                    or not isinstance(legend, dict) or set(legend) != expected):
                raise JevError(bad)
            result.update(score=score, legend=legend)
        output[name] = result
    return {"model": data["model"], "answers": output,
            "usage": {field: usage[field] for field in ("input_tokens", "output_tokens")}}


def redact(value, key):
    if isinstance(value, str):
        return value.replace(key, "[redacted]") if key else value
    if isinstance(value, dict):
        return {redact(k, key): redact(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    return value


def emit(value, key=None):
    print(json.dumps(redact(value, key), ensure_ascii=False, allow_nan=False), flush=True)


SETUP_HTML = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conectar Jev · HeBe</title><style nonce="__NONCE__">
:root{color-scheme:dark;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0c121a;color:#e8eff8}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:26px;background:radial-gradient(ellipse at 50% 0,#163246 0,transparent 60%),#0c121a}main{width:min(100%,500px);border:1px solid #273847;background:#101b26;border-radius:24px;padding:36px;box-shadow:0 24px 90px #0005}.brand{font-size:12px;font-weight:750;letter-spacing:.17em;color:#7ce0d5}.badge{display:inline-block;margin:28px 0 12px;font-size:12px;padding:5px 9px;border-radius:20px;background:#173834;color:#a9e4d8}h1{font-size:32px;letter-spacing:-.04em;margin:0 0 14px}p{font-size:15px;color:#abc0d0;line-height:1.65}label{display:block;font-size:13px;font-weight:650;margin:28px 0 9px}input{width:100%;border:1px solid #3b5063;border-radius:12px;padding:15px;background:#0b141e;color:#fff;font:inherit;outline:none}input:focus{border-color:#70ddcc;box-shadow:0 0 0 3px #70ddcc18}button{width:100%;margin-top:14px;border:0;border-radius:12px;padding:15px;font:inherit;font-weight:750;background:#85e4d3;color:#102522;cursor:pointer}button:disabled{opacity:.55;cursor:wait}.small{font-size:12px;margin-top:20px;overflow-wrap:anywhere}.status{min-height:24px;margin:18px 0 0;font-size:14px;color:#b9efdf}.status.error{color:#ffc2ba}a{color:#91dcd6}code{color:#d2e1eb;font-size:11px}@media(max-width:520px){main{padding:26px}h1{font-size:28px}}
</style></head><body><main><div class="brand">HEBE / TYPESAFE</div><span class="badge">Configuração local</span>
<h1>Conecte seu Jev.</h1><p>Sua chave fica neste computador. Vamos validá-la com a TypeSafe antes de salvar.</p>
<form id="setup" autocomplete="off"><label for="key">Chave da API TypeSafe</label><input id="key" type="password" autocomplete="off" autocapitalize="none" spellcheck="false" required maxlength="4096" placeholder="Cole sua chave aqui"><button id="connect" type="submit">Conectar TypeSafe</button></form>
<p id="status" class="status" role="status" aria-live="polite"></p><p class="small">Ainda não tem uma chave? Abra o <a href="https://console.typesafe.ai" target="_blank" rel="noopener noreferrer">painel da TypeSafe</a>.</p>
<p class="small">Nenhuma nota do Brain será enviada. As avaliações só acontecem quando você as solicitar.<br>Arquivo local: <code>~/.config/hebe-brain/typesafe.json</code></p>
</main><script nonce="__NONCE__">
const form=document.getElementById('setup'),key=document.getElementById('key'),button=document.getElementById('connect'),status=document.getElementById('status');
form.addEventListener('submit',async(event)=>{event.preventDefault();button.disabled=true;status.className='status';status.textContent='Validando conexão…';let value=key.value;key.value='';try{const response=await fetch('__CONFIGURE_PATH__',{method:'POST',headers:{'Content-Type':'application/json','X-HeBe-CSRF':'__TOKEN__'},body:JSON.stringify({api_key:value}),cache:'no-store',credentials:'omit',redirect:'error'});value='';const result=await response.json();if(!response.ok)throw new Error(result.error||'Conexão não confirmada.');status.textContent=result.message;button.textContent='Conectado';key.disabled=true;}catch(error){value='';status.className='status error';status.textContent=error.message==='Failed to fetch'?'A sessão local terminou. Abra configure --web novamente.':error.message;button.disabled=false;}});
</script></body></html>'''


class SetupServer(http.server.HTTPServer):
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        # No tracebacks, request bodies, paths or headers in server logs.
        pass


def configure_web():
    capability = secrets.token_urlsafe(32)
    setup_path = "/setup/" + capability
    configure_path = setup_path + "/configure"
    token, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    page = (SETUP_HTML.replace("__TOKEN__", token).replace("__NONCE__", nonce)
            .replace("__CONFIGURE_PATH__", configure_path).encode("utf-8"))
    completed = False
    success = None

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "HeBeLocal"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def reply(self, status, data, content_type="application/json; charset=utf-8"):
            raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'nonce-" + nonce
                             + "'; style-src 'nonce-" + nonce + "'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def send_error(self, code, message=None, explain=None):
            self.reply(code, {"error": "Requisição local recusada."})

        def allowed(self, post=False):
            if self.headers.get_all("Host", []) != [host]:
                return False
            origins = self.headers.get_all("Origin", [])
            if (post and origins != [origin]) or (not post and origins and origins != [origin]):
                return False
            if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
                return False
            if post:
                values = self.headers.get_all("X-HeBe-CSRF", [])
                if len(values) != 1 or not secrets.compare_digest(values[0], token):
                    return False
            return True

        def do_GET(self):
            if not self.allowed() or self.path != setup_path:
                self.reply(403, {"error": "Página local indisponível."})
                return
            self.reply(200, page, "text/html; charset=utf-8")

        def do_POST(self):
            nonlocal completed, success
            if not self.allowed(post=True) or self.path != configure_path:
                self.reply(403, {"error": "Requisição local recusada."})
                return
            if self.headers.get_all("Content-Type", []) != ["application/json"] or self.headers.get("Transfer-Encoding"):
                self.reply(400, {"error": "Formato local inválido."})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,5}", lengths[0]) or not 1 <= int(lengths[0]) <= MAX_SETUP:
                self.reply(413, {"error": "Pedido local excede o limite."})
                return
            try:
                raw = self.rfile.read(int(lengths[0]))
                if len(raw) != int(lengths[0]):
                    raise JevError("Pedido local incompleto.")
                data = strict_json(raw, MAX_SETUP)
                if not isinstance(data, dict) or set(data) != {"api_key"}:
                    raise JevError("Informe somente a chave no formulário.")
                key = key_value(data["api_key"])
                cards = model_list(key)
                save_credentials(key)
                overridden = "TYPESAFE_API_KEY" in os.environ
                message = "Chave validada e salva. Você pode fechar esta página."
                if overridden:
                    message += " A variável TYPESAFE_API_KEY tem prioridade nas chamadas deste processo."
                success = {"configured": True, "validated": True, "saved_source": "local_file",
                           "environment_override": overridden, "models_available": len(cards)}
                completed = True
                self.reply(200, {"connected": True, "message": message})
            except JevError as exc:
                self.reply(400, {"error": str(exc)})
            except (OSError, ValueError, RecursionError):
                self.reply(400, {"error": "Não foi possível validar ou salvar a chave. Verifique conexão e permissões locais."})

    with SetupServer(("127.0.0.1", 0), Handler) as server:
        host = "127.0.0.1:%d" % server.server_port
        origin = "http://" + host
        server.timeout = 1
        emit({"setup_url": origin + setup_path, "expires_in_seconds": SETUP_LIFETIME,
              "message": "Abra esta URL no navegador deste computador. Não envie a chave no chat."})
        deadline = time.monotonic() + SETUP_LIFETIME
        while not completed and time.monotonic() < deadline:
            server.handle_request()
    if not completed:
        raise JevError("A configuração local expirou. Execute configure --web novamente.")
    return success


def configure_terminal():
    if not sys.stdin.isatty():
        raise JevError("configure exige terminal interativo; use configure --web para entrada protegida no navegador.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            key = key_value(getpass.getpass("Chave TypeSafe (oculta): "))
        except getpass.GetPassWarning:
            raise JevError("Entrada oculta indisponível. Use configure --web.") from None
    cards = model_list(key)
    save_credentials(key)
    return {"configured": True, "validated": True, "saved_source": "local_file",
            "environment_override": "TYPESAFE_API_KEY" in os.environ, "models_available": len(cards)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure", help="Valida a chave e salva fora do Brain; entrada oculta.")
    configure.add_argument("--web", action="store_true", help="Mostra URL local temporária com formulário protegido.")
    sub.add_parser("status", help="Mostra somente presença e origem locais; não verifica conexão nem usa rede.")
    sub.add_parser("models", help="Consulta os modelos disponíveis na conta.")
    preview = sub.add_parser("preview", help="Valida e resume o JSON localmente, sem credencial nem rede.")
    preview.add_argument("--file", required=True, help="JSON regular com state, questions e model opcional (até 1 MiB).")
    preview.add_argument("--model", help="Sobrescreve model do arquivo; padrão jev-latest.")
    evaluate = sub.add_parser("evaluate", help="Envia somente o JSON informado; pode consumir créditos TypeSafe.")
    evaluate.add_argument("--file", required=True, help="JSON regular com state, questions e model opcional (até 1 MiB).")
    evaluate.add_argument("--model", help="Sobrescreve model do arquivo; padrão jev-latest.")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            emit(configure_web() if args.web else configure_terminal())
        elif args.command == "preview":
            emit(evaluation_preview(evaluation_input(args.file, args.model)))
        else:
            # Validate caller data before touching credentials or the network.
            payload = evaluation_input(args.file, args.model) if args.command == "evaluate" else None
            key, source = active_credentials(required=args.command != "status")
            if key is None:
                emit({"configured": False, "source": None, "connection_checked": False})
            elif args.command == "status":
                emit({"configured": True, "source": source, "connection_checked": False}, key)
            elif args.command == "models":
                cards = model_list(key)
                emit({"connected": True, "source": source, "checked_at": timestamp(), "models": cards}, key)
            else:
                emit(evaluation_output(request_api("systemone", key, payload), payload["questions"]), key)
        return 0
    except JevError as exc:
        message = str(exc)
    except KeyboardInterrupt:
        message = "Operação interrompida; nenhuma repetição automática foi feita."
    except (OSError, ValueError, EOFError, RecursionError):
        message = "Operação indisponível. Verifique formato, rede e permissões locais; conteúdo omitido."
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
