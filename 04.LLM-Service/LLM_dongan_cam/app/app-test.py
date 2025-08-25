from flask import Flask, render_template, session, redirect, url_for
from flask_sock import Sock

app = Flask(__name__)
app.secret_key = "secret"  # 세션 위해 필요
sock = Sock(app)

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@sock.route("/stream")
def stream(ws):
    print("WS connected")
    while True:
        data = ws.receive()
        if data is None:
            break
        print("chunk size:", len(data))

if __name__ == "__main__":
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    server = pywsgi.WSGIServer(("0.0.0.0", 8000), app,
                               handler_class=WebSocketHandler)
    print("Serving HTTP/WS on :8000")
    server.serve_forever()
