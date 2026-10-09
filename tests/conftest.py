import threading

import pytest
from werkzeug.serving import make_server

from simulators.fake_arm import create_app


@pytest.fixture
def fake_arm_url():
    """Run a fresh fake ARM server on a free local port for one test."""
    server = make_server('127.0.0.1', 0, create_app())
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        yield 'http://127.0.0.1:%d' % server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
