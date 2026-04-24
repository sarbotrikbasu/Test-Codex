#!/usr/bin/env python3
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST = '127.0.0.1'
PORT = 8000
ROOT = Path(__file__).resolve().parent

class HelloHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type='text/html; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            file_path = ROOT / 'hello_frontend.html'
            if file_path.exists():
                self._set_headers(200, 'text/html; charset=utf-8')
                self.wfile.write(file_path.read_bytes())
            else:
                self._set_headers(404)
                self.wfile.write(b'File not found')
        else:
            self._set_headers(404)
            self.wfile.write(b'Not found')

    def do_POST(self):
        if self.path == '/run':
            try:
                result = subprocess.run(
                    ['python', str(ROOT / 'hello.py')],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True,
                )
                self._set_headers(200, 'text/plain; charset=utf-8')
                self.wfile.write(result.stdout.encode('utf-8'))
            except subprocess.CalledProcessError as exc:
                self._set_headers(500, 'text/plain; charset=utf-8')
                self.wfile.write(exc.output.encode('utf-8'))
        else:
            self._set_headers(404)
            self.wfile.write(b'Not found')

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer((HOST, PORT), HelloHandler)
    print(f'Running server at http://{HOST}:{PORT}/')
    server.serve_forever()
