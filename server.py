import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get("MEGA_BRAIN_BASE_URL", "http://localhost:1234/v1").rstrip("/")
PORT = int(os.environ.get("MEGA_BRAIN_PORT", "4173"))


class MegaBrainHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8"))
            response = self.forward_to_lm_studio(payload)
            self.send_json(200, response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            self.send_json(error.code, {"error": detail})
        except Exception as error:
            self.send_json(502, {"error": str(error)})

    def forward_to_lm_studio(self, payload):
        base_url = payload.pop("baseUrl", BASE_URL).rstrip("/")

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
