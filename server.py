import json
import csv
import hashlib
import os
import re
import subprocess
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get("MEGA_BRAIN_BASE_URL", "http://localhost:1234/v1").rstrip("/")
PORT = int(os.environ.get("MEGA_BRAIN_PORT", "4173"))
MAX_CONTEXT_CHARS = int(os.environ.get("MEGA_BRAIN_MAX_CONTEXT", "18000"))
DEFAULT_CONTEXT_WINDOW = int(os.environ.get("MEGA_BRAIN_CONTEXT_WINDOW", "8192"))
ALLOWED_ROOTS = [ROOT]
for configured_root in os.environ.get("MEGA_BRAIN_ALLOWED_ROOTS", "").split(os.pathsep):
    if configured_root.strip():
        ALLOWED_ROOTS.append(Path(configured_root).expanduser().resolve())
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
TEXT_EXTENSIONS = {
    ".css", ".html", ".js", ".jsx", ".json", ".md", ".py", ".sql", ".ts", ".tsx", ".txt", ".yml", ".yaml", ".csv", ".tsv", ".xml"
}
MODEL_PROFILES = [
    {"id": "auto", "label": "Auto", "description": "Escolhe o modelo pelo tipo de tarefa", "window": DEFAULT_CONTEXT_WINDOW},
    {"id": "qwen2.5-coder-14b-instruct", "label": "Qwen Coder 14B", "description": "Implementacao e debugging", "window": 8192},
    {"id": "qwen2.5-coder-7b-instruct", "label": "Qwen Coder 7B", "description": "Tarefas rapidas e leitura", "window": 8192},
]
SKILLS = [
    {"id": "engineering-core", "name": "Engineering Core", "category": "Arquitetura", "description": "Plano curto, mudanca pequena, verificacao e evidencia.", "source": "local"},
    {"id": "systematic-debugging", "name": "Systematic Debugging", "category": "Debugging", "description": "Reproduzir, isolar causa, corrigir e testar.", "source": "addyosmani/agent-skills"},
    {"id": "test-first", "name": "Test First", "category": "Testes", "description": "Escolher o teste minimo que prova o comportamento.", "source": "LambdaTest/agent-skills"},
    {"id": "data-pipelines", "name": "Data Pipelines", "category": "Dados", "description": "CSV, JSON, YAML, SQL e pipelines Python com validacao.", "source": "local"},
    {"id": "git-review", "name": "Git Review", "category": "Git", "description": "Diff pequeno, historico claro e revisao antes de publicar.", "source": "local"},
]


class MegaBrainHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/workspace/write", "/api/integrations/github"}:
            self.send_error(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8"))
            if self.path == "/api/workspace/write":
                response = self.write_workspace_file(payload)
            elif self.path == "/api/integrations/github":
                response = self.connect_github(payload)
            else:
                response = self.forward_to_lm_studio(payload)
            self.send_json(200, response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            self.send_json(error.code, {"error": detail})
        except Exception as error:
            self.send_json(502, {"error": str(error)})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/workspace":
            self.send_json(200, {"root": str(ROOT), "files": self.workspace_files()})
            return
        if parsed.path == "/api/config":
            self.send_json(200, {"models": MODEL_PROFILES, "skills": SKILLS, "contextWindow": DEFAULT_CONTEXT_WINDOW})
            return
        if parsed.path == "/api/workspace/preview":
            relative = parse_qs(parsed.query).get("path", [""])[0]
            self.send_json(200, self.preview_workspace_file(relative))
            return
        if parsed.path == "/api/obsidian/scan":
            path = parse_qs(parsed.query).get("path", [""])[0]
            self.send_json(200, self.scan_markdown_root(path))
            return
        super().do_GET()

    def workspace_files(self):
        files = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
                continue
            files.append(path.relative_to(ROOT).as_posix())
        return sorted(files)

    def workspace_context(self, prompt):
        words = {word.lower() for word in re.findall(r"[\w.-]+", prompt)}
        candidates = []
        for relative in self.workspace_files():
            path = ROOT / relative
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            score = sum(1 for word in words if word in relative.lower())
            if relative in {"agent_prompt.txt", "README.md"}:
                score += 1
            candidates.append((score, relative))

        context = []
        used = 0
        for _, relative in sorted(candidates, key=lambda item: (-item[0], item[1])):
            path = ROOT / relative
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            remaining = MAX_CONTEXT_CHARS - used
            if remaining <= 200:
                break
            content = content[: min(5000, remaining)]
            context.append(f"\n--- {relative} ---\n{content}")
            used += len(content)
        return "\nArquivos disponiveis no workspace:\n" + "\n".join(self.workspace_files()) + "\n\nConteudo relevante:\n" + "".join(context)

    def resolve_allowed_path(self, relative):
        candidate = Path(str(relative).replace("\\", "/")).expanduser()
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        target = candidate.resolve()
        if not any(root == target or root in target.parents for root in ALLOWED_ROOTS):
            raise ValueError("O caminho nao esta em uma raiz permitida")
        return target

    def preview_workspace_file(self, relative):
        target = self.resolve_allowed_path(relative)
        if not target.is_file():
            raise FileNotFoundError(str(relative))
        suffix = target.suffix.lower()
        stat = target.stat()
        result = {"path": str(target), "size": stat.st_size, "type": suffix or "file", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        if suffix in TEXT_EXTENSIONS:
            result["content"] = target.read_text(encoding="utf-8", errors="replace")[:6000]
        elif suffix == ".pdf":
            result["content"] = "PDF detectado. Use uma ferramenta PDF local para extrair texto sob demanda."
        elif suffix in {".xlsx", ".xls", ".parquet", ".db", ".sqlite"}:
            result["content"] = "Formato estruturado detectado. O agente deve inspecionar apenas metadados e amostras sob demanda."
        return result

    def scan_markdown_root(self, configured_path):
        target = self.resolve_allowed_path(configured_path)
        if not target.is_dir():
            raise NotADirectoryError(str(configured_path))
        notes = []
        for path in target.rglob("*.md"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            notes.append({"path": path.relative_to(target).as_posix(), "size": path.stat().st_size})
        return {"root": str(target), "notes": sorted(notes, key=lambda item: item["path"])[:500]}

    def connect_github(self, payload):
        token = str(payload.get("token", "")).strip()
        repository = str(payload.get("repository", "")).strip().strip("/")
        if not token or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ValueError("Informe um token e repositorio no formato usuario/repositorio")
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}",
            headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "User-Agent": "Mega-Brain"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {"connected": True, "repository": data.get("full_name"), "private": data.get("private", False), "defaultBranch": data.get("default_branch")}

    def write_workspace_file(self, payload):
        relative = str(payload.get("path", "")).replace("\\", "/").strip("/")
        if not relative or relative.startswith("../") or "/../" in f"/{relative}":
            raise ValueError("Caminho de arquivo invalido")
        target = (ROOT / relative).resolve()
        if ROOT not in target.parents and target != ROOT:
            raise ValueError("O arquivo precisa estar dentro do workspace")
        content = payload.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            command = (
                "$content = [Console]::In.ReadToEnd(); "
                "$encoding = New-Object System.Text.UTF8Encoding($false); "
                "[System.IO.File]::WriteAllText($env:MEGA_BRAIN_TARGET, $content, $encoding)"
            )
            child_env = os.environ.copy()
            child_env["MEGA_BRAIN_TARGET"] = str(target)
            powershell = os.environ.get(
                "MEGA_BRAIN_POWERSHELL",
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            )
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                input=content,
                text=True,
                capture_output=True,
                env=child_env,
                check=False,
            )
            if result.returncode:
                raise OSError(result.stderr.strip() or "Falha ao gravar arquivo")
        else:
            target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": relative}

    def forward_to_lm_studio(self, payload):
        base_url = payload.pop("baseUrl", BASE_URL).rstrip("/")
        task_mode = payload.pop("taskMode", "code")
        selected_model = payload.get("model", "auto")
        if selected_model == "auto":
            selected_model = self.route_model(task_mode, payload.get("messages", []))
            payload["model"] = selected_model
        if payload.get("messages"):
            last = payload["messages"][-1]
            if last.get("role") == "user":
                last["content"] += self.workspace_context(last.get("content", ""))

        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer lm-studio",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
        result["mega"] = self.usage_metadata(payload, task_mode, selected_model)
        return result

    def route_model(self, task_mode, messages):
        text = " ".join(item.get("content", "") for item in messages[-2:]).lower()
        if task_mode in {"review", "architecture", "complex"} or any(word in text for word in {"arquitetura", "refator", "migrat", "seguranca"}):
            return os.environ.get("MEGA_BRAIN_COMPLEX_MODEL", "qwen2.5-coder-14b-instruct")
        return os.environ.get("MEGA_BRAIN_FAST_MODEL", "qwen2.5-coder-7b-instruct")

    def usage_metadata(self, payload, task_mode, selected_model):
        chars = sum(len(item.get("content", "")) for item in payload.get("messages", []))
        window = next((item["window"] for item in MODEL_PROFILES if item["id"] == selected_model), DEFAULT_CONTEXT_WINDOW)
        estimated = max(1, chars // 4)
        return {"model": selected_model, "taskMode": task_mode, "estimatedTokens": estimated, "contextWindow": window, "percent": min(100, round(estimated / window * 100, 1))}

    def send_json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("localhost", PORT), MegaBrainHandler)
    print(f"Mega Brain em http://localhost:{PORT}/frontend/")
    print(f"Proxy LM Studio: {BASE_URL}")
    server.serve_forever()
