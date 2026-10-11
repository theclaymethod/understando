#!/usr/bin/env python3
"""PROTOTYPE, throw me away. Serves the explainer-template prototype.

    python3 serve.py [RUN_DIR] [--port 8489]

RUN_DIR holds trust-map.json, refs.resolved.json and explain.json. The default is
the #489 preview run. An optional atlas.layout.json (the hand-drawn map for variant C)
is read from RUN_DIR, then from this folder; without it, C draws one box per cited file. The page reads them at /data/<name> at run time, so no run
data (and no code excerpt of the reviewed repo) lives next to this file.
"""
import http.server
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DATA = {"trust-map.json", "refs.resolved.json", "explain.json", "atlas.layout.json"}
args = [a for a in sys.argv[1:] if not a.startswith("--")]
port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8489
if args and args[0] == str(port):
    args = args[1:]
RUN = pathlib.Path(args[0] if args else "~/.understando/runs/function-intelligence/489/onto/preview").expanduser()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/data/"):
            name = path[len("/data/"):]
            # atlas.layout.json is an optional hand-drawn map: the run folder first, then next to this file.
            found = [d / name for d in (RUN, HERE) if name in DATA and (d / name).is_file()]
            if not found or (name != "atlas.layout.json" and found[0].parent != RUN):
                return self.send_error(404, f"no {name} in {RUN}")
            body = found[0].read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def translate_path(self, path):
        return str(HERE / pathlib.Path(path.split("?", 1)[0]).name)

    def log_message(self, *a):
        pass


print(f"PROTOTYPE explainer templates: http://localhost:{port}/?variant=A  (data: {RUN})")
http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
