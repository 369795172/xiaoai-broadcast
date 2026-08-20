"""Static audio file server for speaker pull-playback.

Deliberately boring: ThreadingHTTPServer + directory bind, no-cache headers
so the speaker always fetches the fresh morning_brief.mp3. LAN only.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_DIR = Path.home() / ".xiaomusic" / "music" / "morning"
DEFAULT_PORT = 8091


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def serve(directory: Path, port: int) -> None:
    directory = directory.expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    handler = partial(NoCacheHandler, directory=str(directory))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"serving {directory} on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="xiaoai audio file server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    serve(args.dir, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
