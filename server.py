import json
import csv
import hashlib
import os
import re
import ast
import subprocess
import tempfile
import shutil
import site
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
PROJECTS_DIR = Path(os.environ.get("MEGA_BRAIN_PROJECTS_DIR", r"C:\mega_brain_agent\projects")).expanduser().resolve()
DEFAULT_OBSIDIAN_PATH = Path(os.environ.get("MEGA_BRAIN_OBSIDIAN_VAULT", r"C:\mega_brain_agent\mega_brain_vault")).expanduser().resolve()
ALLOWED_ROOTS = [ROOT, PROJECTS_DIR]
if DEFAULT_OBSIDIAN_PATH.exists():
    ALLOWED_ROOTS.append(DEFAULT_OBSIDIAN_PATH)
for configured_root in os.environ.get("MEGA_BRAIN_ALLOWED_ROOTS", "").split(os.pathsep):
    if configured_root.strip():
        ALLOWED_ROOTS.append(Path(configured_root).expanduser().resolve())
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
TEXT_EXTENSIONS = {
    ".css", ".html", ".js", ".jsx", ".json", ".md", ".py", ".sql", ".ts", ".tsx", ".txt", ".yml", ".yaml", ".csv", ".tsv", ".xml"
}
MODEL_PROFILES = [
    {"id": "auto", "label": "Auto", "description": "Selects a model by task", "window": DEFAULT_CONTEXT_WINDOW},
    {"id": "qwen2.5-coder-14b-instruct", "label": "Qwen Coder 14B", "description": "Implementation and debugging", "window": 8192},
    {"id": "qwen2.5-coder-7b-instruct", "label": "Qwen Coder 7B", "description": "Fast tasks and reading", "window": 8192},
]
WHISPER_MODEL = os.environ.get("MEGA_BRAIN_WHISPER_MODEL", "small")
VOICE_DIR = ROOT / "voices"
PIPER_BINARY = os.environ.get("MEGA_BRAIN_PIPER_BINARY", shutil.which("piper") or str(Path(site.getuserbase()) / "Scripts" / "piper.exe"))
PIPER_EN_VOICE = os.environ.get("MEGA_BRAIN_PIPER_EN_VOICE", str(VOICE_DIR / "en_US-lessac-medium.onnx"))
PIPER_PT_VOICE = os.environ.get("MEGA_BRAIN_PIPER_PT_VOICE", str(VOICE_DIR / "pt_BR-faber-medium.onnx"))
_whisper = None
SKILLS = [
    {"id": "engineering-core", "name": "Engineering Core", "category": "Architecture", "description": "Short plan, small change, verification, and evidence.", "source": "local"},
    {"id": "systematic-debugging", "name": "Systematic Debugging", "category": "Debugging", "description": "Reproduce, isolate, patch, and test.", "source": "addyosmani/agent-skills"},
    {"id": "test-first", "name": "Test First", "category": "Testing", "description": "Choose the smallest test that proves the behavior.", "source": "LambdaTest/agent-skills"},
    {"id": "data-pipelines", "name": "Data Pipelines", "category": "Data", "description": "CSV, JSON, YAML, SQL, and validated Python pipelines.", "source": "local"},
    {"id": "git-review", "name": "Git Review", "category": "Git", "description": "Focused diff, clear history, and review before publishing.", "source": "local"},
]
MUTATION_TERMS = {
    "fix", "change", "create", "implement", "modify", "update", "add", "remove", "refactor", "improve",
    "corrija", "altere", "crie", "implemente", "modifique", "atualize", "adicione", "remova", "refatore", "melhore", "faca", "faça",
}
AGENT_EXECUTION_CONTRACT = """
NON-NEGOTIABLE AGENT CONTRACT:
You are an autonomous coding agent with workspace access through <mega-write> blocks.
When the user requests a code or file change, you MUST perform the change now. Do not give a tutorial, suggestions, partial snippets, or claim you cannot access files.
For an existing file, prefer a small exact edit using:
<mega-edit path=\"relative/path.ext\">
SEARCH:
exact existing text
REPLACE:
replacement text
</mega-edit>
Use <mega-write path=\"relative/path.ext\">full file content</mega-write> only for new or short files.
For a requested change, a response without at least one mega-edit or mega-write block is invalid.
Use only files supplied in workspace context or create a clearly necessary new relative file. After write blocks, state the verification performed in at most three short lines.
""".strip()


class MegaBrainHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/projects", "/api/workspace/write", "/api/workspace/edit", "/api/integrations/github", "/api/transcribe", "/api/speak"}:
            self.send_error(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        try:
            if self.path == "/api/transcribe":
                self.send_json(200, self.transcribe_audio(body))
                return
            if self.path == "/api/speak":
                self.send_audio(200, self.speak_text(json.loads(body.decode("utf-8", errors="replace"))))
                return
            payload = json.loads(body.decode("utf-8", errors="replace"))
            if self.path == "/api/projects":
                response = self.create_project(payload)
            elif self.path == "/api/workspace/write":
                response = self.write_workspace_file(payload)
            elif self.path == "/api/workspace/edit":
                response = self.edit_workspace_file(payload)
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
            root = self.resolve_workspace_root(parse_qs(parsed.query).get("root", [""])[0])
            self.send_json(200, {"root": str(root), "files": self.workspace_files(root)})
            return
        if parsed.path == "/api/config":
            lm = self.lm_status()
            self.send_json(200, {"models": lm["models"], "skills": SKILLS, "contextWindow": lm["contextWindow"], "lm": lm})
            return
        if parsed.path == "/api/lm/status":
            self.send_json(200, self.lm_status())
            return
        if parsed.path == "/api/lm/models":
            self.send_json(200, self.lm_models())
            return
        if parsed.path == "/api/workspace/preview":
            relative = parse_qs(parsed.query).get("path", [""])[0]
            self.send_json(200, self.preview_workspace_file(relative))
            return
        if parsed.path == "/api/obsidian/scan":
            path = parse_qs(parsed.query).get("path", [str(DEFAULT_OBSIDIAN_PATH)])[0]
            self.send_json(200, self.scan_markdown_root(path))
            return
        super().do_GET()

    def resolve_workspace_root(self, configured_path):
        if not configured_path:
            return ROOT
        target = self.resolve_allowed_path(configured_path)
        if not target.is_dir():
            raise NotADirectoryError(str(configured_path))
        if target != ROOT and PROJECTS_DIR not in target.parents:
            raise ValueError("Project workspaces must be inside the projects directory")
        return target

    def workspace_files(self, workspace_root=ROOT):
        files = []
        for path in workspace_root.rglob("*"):
            if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
                continue
            files.append(path.relative_to(workspace_root).as_posix())
        return sorted(files)

    def workspace_context(self, prompt, workspace_root=ROOT):
        words = {word.lower() for word in re.findall(r"[\w.-]+", prompt)}
        candidates = []
        for relative in self.workspace_files(workspace_root):
            path = workspace_root / relative
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            score = sum(1 for word in words if word in relative.lower())
            lowered = relative.lower()
            if words & {"frontend", "front-end", "css", "html", "ui", "interface", "visual", "layout"} and lowered.startswith("frontend/"):
                score += 12
            if words & {"backend", "server", "api", "python", "endpoint"} and relative.endswith("server.py"):
                score += 12
            if words & {"test", "tests", "testing", "teste", "testes"} and ("test" in lowered or relative.endswith("package.json")):
                score += 10
            if words & {"sql", "database", "banco", "dados", "data"} and path.suffix.lower() in {".sql", ".py", ".csv", ".json", ".yaml", ".yml"}:
                score += 8
            if relative in {"agent_prompt.txt", "README.md"}:
                score += 1
            candidates.append((score, relative))

        context = []
        used = 0
        for _, relative in sorted(candidates, key=lambda item: (-item[0], item[1])):
            path = workspace_root / relative
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
        return "\nWorkspace files:\n" + "\n".join(self.workspace_files(workspace_root)) + "\n\nRelevant contents:\n" + "".join(context)

    def resolve_allowed_path(self, relative):
        candidate = Path(str(relative).replace("\\", "/")).expanduser()
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        target = candidate.resolve()
        if not any(root == target or root in target.parents for root in ALLOWED_ROOTS):
            raise ValueError("The path is not inside an approved root")
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
            result["content"] = "PDF detected. Use a local PDF tool to extract text on demand."
        elif suffix in {".xlsx", ".xls", ".parquet", ".db", ".sqlite"}:
            result["content"] = "Structured file detected. Inspect metadata and samples on demand."
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
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ValueError("Enter a repository in the owner/repository format")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Mega-Brain"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}",
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {"connected": True, "repository": data.get("full_name"), "private": data.get("private", False), "defaultBranch": data.get("default_branch")}

    def lm_status(self):
        native_url = BASE_URL.removesuffix("/v1") + "/api/v1/models"
        try:
            request = urllib.request.Request(native_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=10) as response:
                native = json.loads(response.read().decode("utf-8"))
            loaded = []
            for item in native.get("models", []):
                if item.get("type") != "llm" or not item.get("loaded_instances"):
                    continue
                instance = item["loaded_instances"][0]
                window = int(instance.get("config", {}).get("context_length") or item.get("max_context_length") or DEFAULT_CONTEXT_WINDOW)
                model_id = str(instance.get("id") or item.get("key") or "").strip()
                if model_id:
                    loaded.append({"id": model_id, "label": item.get("display_name") or model_id, "description": f"Loaded in LM Studio ({window:,} tokens)", "window": window})
            context_window = max((model["window"] for model in loaded), default=DEFAULT_CONTEXT_WINDOW)
            models = [{"id": "auto", "label": "Auto", "description": "Uses the best loaded model", "window": context_window}, *loaded]
            return {"connected": True, "baseUrl": BASE_URL, "models": models, "contextWindow": context_window, "loadedModelIds": [item["id"] for item in loaded]}
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError) as error:
            return {"connected": False, "baseUrl": BASE_URL, "models": MODEL_PROFILES[:1], "contextWindow": DEFAULT_CONTEXT_WINDOW, "loadedModelIds": [], "error": str(error)}

    def lm_models(self):
        return {"models": self.lm_status()["models"]}

    def create_project(self, payload):
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Project name is required")
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64] or "project"
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        target = PROJECTS_DIR / slug
        suffix = 2
        while target.exists():
            target = PROJECTS_DIR / f"{slug}-{suffix}"
            suffix += 1
        target.mkdir(parents=True)
        (target / ".mega-brain-project.json").write_text(json.dumps({"name": name}, indent=2), encoding="utf-8")
        return {"id": target.name, "name": name, "path": str(target), "relativePath": target.relative_to(PROJECTS_DIR).as_posix()}

    def write_workspace_file(self, payload):
        relative = str(payload.get("path", "")).replace("\\", "/").strip("/")
        if not relative or relative.startswith("../") or "/../" in f"/{relative}":
            raise ValueError("Invalid file path")
        workspace_root = self.resolve_workspace_root(payload.get("workspaceRoot", ""))
        target = (workspace_root / relative).resolve()
        if workspace_root not in target.parents and target != workspace_root:
            raise ValueError("The file must be inside the active project")
        content = payload.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        validation = self.validate_file_content(target, content)
        if not validation["ok"]:
            raise ValueError(validation["message"])
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
                raise OSError(result.stderr.strip() or "Failed to write file")
        else:
            target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": relative, "workspaceRoot": str(workspace_root), "validation": validation}

    def edit_workspace_file(self, payload):
        relative = str(payload.get("path", "")).replace("\\", "/").strip("/")
        search = str(payload.get("search", ""))
        replacement = str(payload.get("replace", ""))
        if not relative or not search:
            raise ValueError("Edit path and SEARCH text are required")
        if relative.startswith("../") or "/../" in f"/{relative}":
            raise ValueError("Invalid file path")
        workspace_root = self.resolve_workspace_root(payload.get("workspaceRoot", ""))
        target = (workspace_root / relative).resolve()
        if workspace_root not in target.parents or not target.is_file():
            raise ValueError("The edit target must be an existing file in the active project")
        content = target.read_text(encoding="utf-8", errors="replace")
        updated = self.apply_edit_content(target, content, search, replacement)
        validation = self.validate_file_content(target, updated)
        if not validation["ok"]:
            raise ValueError(validation["message"])
        target.write_text(updated, encoding="utf-8")
        return {"ok": True, "path": relative, "workspaceRoot": str(workspace_root), "validation": validation}

    def apply_edit_content(self, target, content, search, replacement):
        occurrences = content.count(search)
        if occurrences == 1:
            return content.replace(search, replacement, 1)
        elif target.suffix.lower() == ".css":
            return self.replace_css_rule(content, search, replacement)
        else:
            raise ValueError(f"SEARCH text must match exactly once in {target.name}; found {occurrences} matches")

    def replace_css_rule(self, content, search, replacement):
        selector = search.strip().rstrip("{").strip()
        if not selector or "{" not in replacement:
            raise ValueError("CSS SEARCH text must match exactly once")
        match = re.search(rf"{re.escape(selector)}\s*\{{", content)
        if not match or len(re.findall(rf"{re.escape(selector)}\s*\{{", content)) != 1:
            raise ValueError(f"CSS selector {selector!r} must match exactly once")
        depth = 0
        end = None
        for index in range(match.end() - 1, len(content)):
            if content[index] == "{":
                depth += 1
            elif content[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise ValueError(f"CSS rule {selector!r} is not balanced")
        return f"{content[:match.start()]}{replacement.strip()}{content[end:]}"

    def validate_file_content(self, target, content):
        suffix = target.suffix.lower()
        try:
            if suffix == ".py":
                ast.parse(content)
            elif suffix == ".json":
                json.loads(content)
            elif suffix == ".css" and content.count("{") != content.count("}"):
                raise SyntaxError("unbalanced CSS braces")
        except (SyntaxError, json.JSONDecodeError) as error:
            return {"ok": False, "message": f"Validation failed for {target.name}: {error}"}
        check = "Python syntax parsed" if suffix == ".py" else "JSON parsed" if suffix == ".json" else "File written"
        return {"ok": True, "message": check}

    def forward_to_lm_studio(self, payload):
        base_url = payload.pop("baseUrl", BASE_URL).rstrip("/")
        task_mode = payload.pop("taskMode", "code")
        workspace_root = self.resolve_workspace_root(payload.pop("workspaceRoot", ""))
        selected_model = payload.get("model", "auto")
        if selected_model == "auto":
            selected_model = self.route_model(task_mode, payload.get("messages", []))
            payload["model"] = selected_model
        if payload.get("messages"):
            system_message = next((message for message in payload["messages"] if message.get("role") == "system"), None)
            if system_message:
                system_message["content"] = f"{system_message.get('content', '')}\n\n{AGENT_EXECUTION_CONTRACT}"
            last = payload["messages"][-1]
            if last.get("role") == "user":
                last["content"] += self.workspace_context(last.get("content", ""), workspace_root)
        payload.setdefault("max_tokens", int(os.environ.get("MEGA_BRAIN_MAX_OUTPUT_TOKENS", "4096")))
        result = self.request_completion(base_url, payload)
        if self.requires_write(payload.get("messages", [])):
            for attempt in range(3):
                valid, reason = self.validate_agent_changes(result, workspace_root)
                if valid:
                    break
                if attempt == 2:
                    raise RuntimeError("The model could not produce a safe, applicable file change after two repair attempts")
                result = self.repair_non_agent_response(base_url, payload, result, reason)
        result["mega"] = self.usage_metadata(payload, task_mode, selected_model)
        return result

    def request_completion(self, base_url, payload):
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def requires_write(self, messages):
        user_content = " ".join(str(item.get("content", "")) for item in messages if item.get("role") == "user").lower()
        return any(re.search(rf"\b{re.escape(term)}\b", user_content) for term in MUTATION_TERMS)

    def has_agent_change(self, result):
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return bool(re.search(r"<mega-(?:write|edit)\s+path=\"[^\"]+\">[\s\S]+?</mega-(?:write|edit)>", content))

    def validate_agent_changes(self, result, workspace_root):
        if not self.has_agent_change(result):
            return False, "No mega-write or mega-edit block was returned."
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        writes = list(re.finditer(r"<mega-write\s+path=\"([^\"]+)\">([\s\S]*?)</mega-write>", content))
        edits = list(re.finditer(r"<mega-edit\s+path=\"([^\"]+)\">\s*SEARCH:\s*\n([\s\S]*?)\nREPLACE:\s*\n([\s\S]*?)</mega-edit>", content))
        if not writes and not edits:
            return False, "The agent block format is invalid."
        try:
            for match in writes:
                relative, file_content = match.groups()
                target = self.agent_target(workspace_root, relative, require_existing=False)
                validation = self.validate_file_content(target, file_content)
                if not validation["ok"]:
                    return False, validation["message"]
            for match in edits:
                relative, search, replacement = match.groups()
                target = self.agent_target(workspace_root, relative, require_existing=True)
                existing = target.read_text(encoding="utf-8", errors="replace")
                updated = self.apply_edit_content(target, existing, search, replacement)
                validation = self.validate_file_content(target, updated)
                if not validation["ok"]:
                    return False, validation["message"]
        except (OSError, ValueError) as error:
            return False, str(error)
        return True, "Applicable change"

    def agent_target(self, workspace_root, relative, require_existing):
        normalized = str(relative).replace("\\", "/").strip("/")
        if not normalized or normalized.startswith("../") or "/../" in f"/{normalized}":
            raise ValueError("Agent returned an invalid relative path")
        target = (workspace_root / normalized).resolve()
        if workspace_root not in target.parents:
            raise ValueError("Agent attempted to leave the active project")
        if require_existing and not target.is_file():
            raise ValueError(f"Agent edit target does not exist: {normalized}")
        return target

    def repair_non_agent_response(self, base_url, payload, prior_result, reason):
        prior_answer = prior_result.get("choices", [{}])[0].get("message", {}).get("content", "")
        repair_payload = json.loads(json.dumps(payload))
        repair_payload["messages"].append({
            "role": "user",
            "content": f"The previous agent response was rejected before any file was changed. Reason: {reason}\nExecute the original request again. For existing files return an exact <mega-edit> SEARCH/REPLACE block using text copied from the supplied workspace context. Use <mega-write> only for a new or short file. Do not provide advice.\n\nRejected answer:\n{prior_answer}",
        })
        return self.request_completion(base_url, repair_payload)

    def route_model(self, task_mode, messages):
        loaded = self.lm_status()["loadedModelIds"]
        if not loaded:
            raise RuntimeError("LM Studio has no loaded LLM. Load a model and start the local server.")
        text = " ".join(item.get("content", "") for item in messages[-2:]).lower()
        preferred = os.environ.get("MEGA_BRAIN_COMPLEX_MODEL", "qwen2.5-coder-14b-instruct") if task_mode in {"review", "architecture", "complex"} or any(word in text for word in {"architecture", "refactor", "migration", "security"}) else os.environ.get("MEGA_BRAIN_FAST_MODEL", "qwen2.5-coder-7b-instruct")
        return preferred if preferred in loaded else loaded[0]

    def usage_metadata(self, payload, task_mode, selected_model):
        chars = sum(len(item.get("content", "")) for item in payload.get("messages", []))
        window = next((item["window"] for item in self.lm_status()["models"] if item["id"] == selected_model), DEFAULT_CONTEXT_WINDOW)
        estimated = max(1, chars // 4)
        return {"model": selected_model, "taskMode": task_mode, "estimatedTokens": estimated, "contextWindow": window, "percent": min(100, round(estimated / window * 100, 1))}

    def send_json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def transcribe_audio(self, body):
        global _whisper
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError("Voice input is not installed. Run voice_setup.ps1 first.") from error
        if not body:
            raise ValueError("No audio received")
        if _whisper is None:
            device = os.environ.get("MEGA_BRAIN_WHISPER_DEVICE", "cuda")
            compute_type = os.environ.get("MEGA_BRAIN_WHISPER_COMPUTE", "float16" if device == "cuda" else "int8")
            _whisper = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as audio_file:
            audio_file.write(body)
            audio_path = audio_file.name
        try:
            segments, info = _whisper.transcribe(audio_path, language=None, vad_filter=True, beam_size=5)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return {"text": text, "language": info.language, "duration": info.duration}
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    def speak_text(self, payload):
        text = str(payload.get("text", "")).strip()
        language = str(payload.get("language", "en_US"))
        voice = PIPER_PT_VOICE if language.startswith("pt") else PIPER_EN_VOICE
        if not text or not voice:
            raise RuntimeError("Configure MEGA_BRAIN_PIPER_EN_VOICE and MEGA_BRAIN_PIPER_PT_VOICE first.")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output_file:
            output_path = output_file.name
        try:
            result = subprocess.run([PIPER_BINARY, "--model", voice, "--output_file", output_path], input=text, text=True, capture_output=True, check=False)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "Piper failed to synthesize audio")
            return Path(output_path).read_bytes()
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    def send_audio(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server():
    server = ThreadingHTTPServer(("localhost", PORT), MegaBrainHandler)
    print(f"Mega Brain em http://localhost:{PORT}/frontend/")
    print(f"Proxy LM Studio: {BASE_URL}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
