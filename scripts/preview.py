"""See a page change with real data before it goes into a pull request.

The owner, 2026-10-14: "what if I could see the result before you PR and
publish?" This serves the page from the working tree on this laptop and
answers its reads from the live server, as the owner: the page is the new
one, the receipts are the real ones. Insights are computed here, by the
working tree's `build_insights` over the live `/v1/purchases`, so a change to
the insights shows before it is deployed. Anything but a read is refused:
a preview never writes to the live data.

    .venv/bin/python scripts/preview.py            # http://localhost:8765/
    .venv/bin/python scripts/preview.py --shot home.png   # and a phone-sized screenshot

The live server and the owner's password come from GROCERY_URL /
GROCERY_TOKEN, or else from gcloud, as for `dev_inbox.py`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dev_inbox import TIMEOUT_S, server_and_token  # noqa: E402

from grocery_app.insights import build_insights  # noqa: E402

PAGE = ROOT / "src" / "grocery_app" / "api" / "review.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def handler(live: str, token: str) -> type[BaseHTTPRequestHandler]:
    def fetch(path: str) -> tuple[int, str, bytes]:
        request = urllib.request.Request(live + path,
                                         headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return response.status, response.headers.get_content_type(), response.read()
        except urllib.error.HTTPError as error:
            return error.code, "application/json", error.read()

    class Preview(BaseHTTPRequestHandler):
        def send(self, status: int, kind: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (the stdlib's name)
            path = self.path
            if path in ("/", "/index.html"):
                self.send(200, "text/html", PAGE.read_bytes())
            elif path == "/sw.js":
                # No service worker: it would keep this page on the browser.
                self.send(404, "text/plain", b"")
            elif path.split("?")[0] == "/v1/insights":
                status, _, body = fetch("/v1/purchases")
                if status != 200:
                    self.send(status, "application/json", body)
                    return
                doc = build_insights(json.loads(body))
                self.send(200, "application/json", json.dumps(doc).encode())
            else:
                self.send(*fetch(path))

        def refuse(self) -> None:
            self.send(405, "application/json",
                      b'{"detail": "a preview reads only; nothing is written"}')

        do_POST = do_PUT = do_DELETE = do_PATCH = refuse

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Preview


def screenshot(url: str, out: Path) -> None:
    """The page at an iPhone's width, once its reads have come back."""
    profile = Path("/tmp") / "grocery-preview-chrome"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--user-data-dir={profile}", "--window-size=500,900",
                    "--force-device-scale-factor=2", "--virtual-time-budget=15000",
                    f"--screenshot={out.resolve()}", url],
                   check=True, capture_output=True, timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--shot", type=Path, help="save a phone-sized screenshot and stop")
    parser.add_argument("--tab", default="", help="the tab to shoot, e.g. insights")
    args = parser.parse_args()
    live, token = server_and_token()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(live, token))
    url = f"http://localhost:{args.port}/" + (f"#{args.tab}" if args.tab else "")
    if args.shot:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        screenshot(url, args.shot)
        server.shutdown()
        print(args.shot)
        return
    print(f"preview of the working tree with live data, read only: {url}")
    server.serve_forever()


if __name__ == "__main__":
    main()
