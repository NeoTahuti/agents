import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("MEGA_BRAIN_BASE_URL", "http://localhost:1234/v1").rstrip("/")
MODEL = os.environ.get("MEGA_BRAIN_MODEL", "local-model")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSTEM_PROMPT = (ROOT / "agent_prompt.txt").read_text(encoding="utf-8")
SYSTEM_PROMPT = os.environ.get("MEGA_BRAIN_SYSTEM", DEFAULT_SYSTEM_PROMPT)


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


def run_once(prompt):
    answer = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
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

        messages.append({"role": "user", "content": prompt})

        try:
            answer = chat(messages)
            messages.append({"role": "assistant", "content": answer})
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
