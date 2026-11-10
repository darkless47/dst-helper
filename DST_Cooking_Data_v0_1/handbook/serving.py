"""An embedded Uvicorn runner for real-socket acceptance tests and local tools."""
import socket
import sys
from threading import Event

import uvicorn

# On Windows, Proactor transports can leave orphaned connections when a browser
# aborts a request (WinError 10054), delaying shutdown. No subprocess I/O is needed.
SERVER_LOOP = 'asyncio:SelectorEventLoop' if sys.platform == 'win32' else 'auto'


class EmbeddedServer:
    def __init__(self, app, host='127.0.0.1', port=0):
        host = '127.0.0.1' if host.casefold() == 'localhost' else host
        self.socket = socket.create_server((host, port))
        self.server_port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(
            app, host=host, port=self.server_port, loop=SERVER_LOOP, ws='none', lifespan='on',
            access_log=False, log_level='warning', proxy_headers=False, timeout_graceful_shutdown=25,
        ))
        self._finished = Event()
        self._running = False

    def serve_forever(self):
        self._running = True
        try:
            self.server.run(sockets=[self.socket])
        finally:
            self._finished.set()

    def shutdown(self):
        self.server.should_exit = True
        if self._running and not self._finished.wait(30):
            raise RuntimeError('Uvicorn did not stop within the shutdown deadline')

    def server_close(self):
        self.shutdown()
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.server_close()
