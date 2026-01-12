import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_SEGMENTS = [
    {
        "segment_id": "seg-001",
        "source": "Welcome, adventurer!",
        "target": "",
    },
    {
        "segment_id": "seg-002",
        "source": "Press {0} to open the inventory.",
        "target": "",
    },
]


class MockServerHandler(BaseHTTPRequestHandler):
    server_version = "FoundryMock/1.0"

    def _is_local(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _reject_if_remote(self):
        if not self._is_local():
            self._send_json(
                {"error": "local_only", "detail": "Mock server only accepts localhost traffic."},
                status=HTTPStatus.FORBIDDEN,
            )
            return True
        return False

    def do_POST(self):
        if self._reject_if_remote():
            return

        if self.path == "/login":
            payload = self._read_json()
            username = payload.get("username", "mock_user")
            self._send_json(
                {
                    "token": "mock-token",
                    "user": {"id": 1, "name": username},
                }
            )
            return

        if self.path == "/suggestions":
            payload = self._read_json()
            self._send_json(
                {
                    "status": "ok",
                    "segment_id": payload.get("segment_id"),
                    "suggestion": payload.get("suggestion"),
                },
                status=HTTPStatus.CREATED,
            )
            return

        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_GET(self):
        if self._reject_if_remote():
            return

        if self.path.startswith("/segments"):
            self._send_json({"segments": DEFAULT_SEGMENTS, "page": 1})
            return

        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):
        return


def start_mock_server(host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), MockServerHandler)
    print(f"Mock server running on http://{host}:{port}")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Run FoundryL10n mock API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    start_mock_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
