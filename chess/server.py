"""Local UI for chess diagnostics. Start with API key in environment."""
import json,os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import probe
import knight
import tracking
from typesafe_sdk import TypeSafeError

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data,kind='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path.split('?')[0] in ('/tracking','/tracking.html'):
            self.send(200,Path(__file__).with_name('tracking.html').read_bytes(),'text/html; charset=utf-8')
        elif self.path.split('?')[0] in ('/','/index.html'):
            self.send(200,Path(__file__).with_name('index.html').read_bytes(),'text/html; charset=utf-8')
        else:self.send(404,b'{}')
    def do_POST(self):
        if self.path not in ('/api/probe','/api/tracking'):self.send(404,b'{}');return
        try:
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
            if self.path=='/api/tracking':
                result=tracking.ask(int(body.get('index',1)),int(body.get('plies',12)),body.get('condition','base'))
                import chess,chess.svg
                board=chess.Board(result['fen'])
                result['svg']=chess.svg.board(board,size=640,coordinates=True)
                self.send(200,json.dumps(result).encode());return
            if body.get('stage')=='white_knight':
                result=knight.ask(int(body.get('index',1)),body.get('encoding','pgn'),body.get('condition','base'))
            else:
                result=probe.ask(int(body.get('index',1)),body.get('stage','occupied'),body.get('encoding','fen'),body.get('condition','base'))
            result['svg']=probe.svg_for(result);self.send(200,json.dumps(result).encode())
        except (ValueError,KeyError,TypeError) as e:self.send(400,json.dumps({'error':str(e)}).encode())
        except TypeSafeError as e:self.send(502,json.dumps({'error':str(e)}).encode())

if __name__=='__main__':
    if not os.environ.get('TYPESAFE_API_KEY'):raise SystemExit('Inject TYPESAFE_API_KEY through op run')
    port=int(os.environ.get('PORT',3461));print(f'Chess: http://localhost:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
