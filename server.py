import json
import os
import re
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get("MEGA_BRAIN_BASE_URL", "http://localhost:1234/v1").rstrip("/")
PORT = int(os.environ.get("MEGA_BRAIN_PORT", "4173"))
MAX_CONTEXT_CHARS = int(os.environ.get("MEGA_BRAIN_MAX_CONTEXT", "18000"))
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
TEXT_EXTENSIONS = {
    ".css", ".html", ".js", ".jsx", ".json", ".md", ".py", ".sql", ".ts", ".tsx", ".txt", ".yml", ".yaml"
}


class MegaBrainHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/workspace/write"}:
            self.send_error(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8"))
            if self.path == "/api/workspace/write":
                response = self.write_workspace_file(payload)
            else:
                response = self.forward_to_lm_studio(payload)
            self.send_json(200, response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            self.send_json(error.code, {"error": detail})
        except Exception as error:
            self.send_json(502, {"error": str(error)})

    def do_GET(self):
        if self.path == "/api/workspace":
            self.send_json(200, {"root": str(ROOT), "files": self.workspace_files()})
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

    def write_workspace_file(self, payload):
        relative = str(payload.get("path", "")).replace("\\", "/").strip("/")
        if not relative or relative.startswith("../") or "/../" in f"/{relative}":
            raise ValueError("Caminho de arquivo invalido")
        target = (ROOT / relative).resolve()
        if ROOT not in target.parents and target != ROOT:
            raise ValueError("O arquivo precisa estar dentro do workspace")
        content = payload.get("content")
        if not isinstance(content, str):
            raise ValueError("content precisa ser texto")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": relative}

    def forward_to_lm_studio(self, payload):
        base_url = payload.pop("baseUrl", BASE_URL).rstrip("/")
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
            return json.loads(response.read().decode("utf-8"))

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
