from core import logger

from tornado import gen
from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError

from core.config import config
from core.events import events
from core.envisalink import get_checksum


class Proxy(object):
    def __init__(self):
        if not getattr(config, 'ENABLEPROXY', True):
            logger.debug('Envisalink Proxy is disabled')
            return

        logger.info('Starting Envisalink Proxy on port ' + str(config.ENVISALINKPROXYPORT))

        self.proxy_server = ProxyServer()
        self.proxy_server.listen(config.ENVISALINKPROXYPORT)


class ProxyServer(TCPServer):
    def __init__(self):
        TCPServer.__init__(self)
        self.connections = {}

        events.register('proxy', self.proxy_event)

    @gen.coroutine
    def handle_stream(self, stream, address):
        fromaddr = f"{address[0]}:{address[1]}"
        logger.info('Proxy Client connected: ' + fromaddr + ' | Active: ' + str(len(self.connections) + 1))


        connection = ProxyConnection(stream, address, self)
        self.connections[fromaddr] = connection

        try:
            yield connection.on_connect()
        finally:
            if fromaddr in self.connections:
                del self.connections[fromaddr]
                logger.info('Proxy Client disconnected: ' + fromaddr + ' | Active: ' + str(len(self.connections)))

    @gen.coroutine
    def proxy_event(self, zone, parameters, input):
        """Broadcast responses from Envisalink to all authenticated proxy clients"""
        if not self.connections:
            return

        for fromaddr, conn in list(self.connections.items()):
            try:
                if conn.authenticated:
                    yield conn.send_raw(input)
            except Exception:
                pass


class ProxyConnection(object):
    def __init__(self, stream, address, server):
        self.stream = stream
        self.address = address
        self.server = server
        self.authenticated = False

        self.stream.set_close_callback(self.on_disconnect)
        self.send_command('5053')

    @gen.coroutine
    def on_connect(self):
        yield self.dispatch_client()

    @gen.coroutine
    def on_disconnect(self):
        pass

    @gen.coroutine
    def dispatch_client(self):
        try:
            while True:
                line = yield self.stream.read_until(b'\r\n')
                line = line.strip()

                # Debug - co dostał proxy od klienta
                line_str = line.decode('ascii', errors='replace')
#                logger.debug(f'PROXY > RX from client [{self.address[0]}:{self.address[1]}]: bytes={line} | str="{line_str}"')

                if not line:
                    continue

                if self.authenticated:
                    # Przekazujemy jako STRING (to jest ważne!)
                    events.put('envisalink', None, line_str)
                    logger.debug(f'CLIENT ({self.address[0]}:{self.address[1]}) RX < ' + line_str)
                else:
                    # Autentykacja
                    password = config.ENVISALINKPROXYPASS
                    checksum = get_checksum('005', password)
                    expected = ('005' + password + checksum).encode('ascii')
                    expected_str = expected.decode('ascii', errors='replace')

 #                   logger.debug(f'PROXY > Auth check | Received="{line_str}" | Expected="{expected_str}"')

                    if line == expected:
                        logger.info(f'Proxy User Authenticated: {self.address[0]}:{self.address[1]}')
                        self.authenticated = True
                        yield self.send_command('5051')
                    else:
                        logger.warning(f'Proxy Authentication FAILED from {self.address[0]}:{self.address[1]}')
                        yield self.send_command('5050')
                        self.stream.close()
                        break

        except StreamClosedError:
            pass
        except Exception as e:
            logger.error(f'Client error: {e}')

    @gen.coroutine
    def send_command(self, data, checksum=True):
        if isinstance(data, bytes):
            data = data.decode('ascii')

        if checksum:
            cs = get_checksum(data, '')
            to_send = (data + cs + '\r\n').encode('ascii')
        else:
            to_send = (data + '\r\n').encode('ascii')

        to_send_str = to_send.decode('ascii', errors='replace')
#        logger.debug(f'PROXY < TX to client [{self.address[0]}:{self.address[1]}]: {to_send_str}')

        try:
            yield self.stream.write(to_send)
        except Exception:
            pass

    @gen.coroutine
    def send_raw(self, data):
        if isinstance(data, str):
            data = data.encode('ascii')
        elif not isinstance(data, (bytes, bytearray)):
            data = str(data).encode('ascii')

        data_str = data.decode('ascii', errors='replace')
#        logger.debug(f'PROXY < TX raw to client [{self.address[0]}:{self.address[1]}]: {data_str}')

        try:
            yield self.stream.write(data)
        except Exception:
            pass
