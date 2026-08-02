import json
import os
import sys
import urllib.error
import urllib.request
import re
from pathlib import Path


BASE_URL = os.environ.get("MEGA_BRAIN_BASE_URL", "http://localhost:1234/v1").rstrip("/")
MODEL = os.environ.get("MEGA_BRAIN_MODEL", "local-model")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSTEM_PROMPT = (ROOT / "agent_prompt.txt").read_text(encoding="utf-8")
SYSTEM_PROMPT = os.environ.get("MEGA_BRAIN_SYSTEM", DEFAULT_SYSTEM_PROMPT)
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
TEXT_EXTENSIONS = {".css", ".html", ".js", ".jsx", ".json", ".md", ".py", ".sql", ".ts", ".tsx", ".txt", ".yml", ".yaml"}


def workspace_context(prompt):
    files = []
    for path in ROOT.rglob("*"):
        if path.is_file() and not any(part in IGNORED_DIRS for part in path.parts):
            files.append(path.relative_to(ROOT).as_posix())
    words = {word.lower() for word in re.findall(r"[\w.-]+", prompt)}
    candidates = sorted(
        (sum(word in relative.lower() for word in words), relative) for relative in files
        if Path(relative).suffix.lower() in TEXT_EXTENSIONS
    )
    chunks = []
    used = 0
    for _, relative in reversed(candidates):
        remaining = 16000 - used
        if remaining <= 200:
            break
        try:
            content = (ROOT / relative).read_text(encoding="utf-8")[: min(4000, remaining)]
        except (OSError, UnicodeDecodeError):
            continue
        chunks.append(f"\n--- {relative} ---\n{content}")
        used += len(content)
    return "\nArquivos do workspace:\n" + "\n".join(files) + "\n\nTrechos relevantes:\n" + "".join(chunks)


def apply_writes(answer):
    pattern = r'<mega-write\s+path="([^"]+)">([\s\S]*?)</mega-write>'
    for relative, content in re.findall(pattern, answer):
        relative = relative.replace("\\", "/").strip("/")
        target = (ROOT / relative).resolve()
        if not relative or relative.startswith("../") or ROOT not in target.parents:
            raise RuntimeError(f"Caminho fora do workspace: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"[salvo] {relative}")


def chat(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
    }

    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer lm-studio",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Nao consegui conectar ao LM Studio. Confira Developer > Local Server."
        ) from error

    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def compact_messages(messages):
    return [messages[0], *messages[-6:]]


def run_once(prompt):
    answer = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt + workspace_context(prompt)},
        ]
    )
    apply_writes(answer)
    print(answer)


def run_interactive():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("Mega Brain CLI. Digite /sair para encerrar.")

    while True:
        prompt = input("\nvoce> ").strip()

        if not prompt:
            continue
        if prompt in {"/sair", "/exit"}:
            break

        messages.append({"role": "user", "content": prompt + workspace_context(prompt)})

        try:
            answer = chat(compact_messages(messages))
            messages.append({"role": "assistant", "content": answer})
            apply_writes(answer)
            print(f"\nmega brain> {answer}")
        except RuntimeError as error:
            print(f"\nErro: {error}", file=sys.stderr)


def main():
    prompt = " ".join(sys.argv[1:]).strip()
    if prompt:
        run_once(prompt)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
