bind = "0.0.0.0:8000"
workers = 2
threads = 4
timeout = 60
graceful_timeout = 30
# Flask-SocketIO + gevent를 쓸 때:
# worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
