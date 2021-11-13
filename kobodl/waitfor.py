import logging
import sys
from multiprocessing import Process, Queue

from flask import Flask, request

global value


def _shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


def waitfor() -> str:
    app = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    log.disabled = True
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None

    server = Process(target=app.run, kwargs={'port': 8189, 'ssl_context': 'adhoc'})
    q = Queue()

    @app.route('/', methods=['POST'])
    def index():
        global value
        q.put(request.form.get('value'))
        _shutdown_server()
        return ''

    server.start()
    server.join()
    return q.get(block=True)
