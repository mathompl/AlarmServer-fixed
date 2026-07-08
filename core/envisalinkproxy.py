from core import logger
from collections import defaultdict

import time
import datetime
from tornado.ioloop import PeriodicCallback

from tornado import gen
from tornado.tcpserver import TCPServer
from tornado.iostream import StreamClosedError

from core.config import config
from core.events import events
from core.envisalink import get_checksum
from core.envisalinkcommands import get_command_name


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
        self.connections_per_ip = defaultdict(int) 

        events.register('proxy', self.proxy_event)
        events.register('proxy_status', self.proxy_status)
            

        self.status_callback = PeriodicCallback(self.log_active_clients, 60000)  # 60 sekund
        self.status_callback.start()


    def _can_accept_connection(self, ip):
        max_per_ip = getattr(config, 'PROXY_MAX_CONNECTIONS_PER_IP', 5)
        return self.connections_per_ip[ip] < max_per_ip

    @gen.coroutine
    def proxy_status(self, event_name, zone, parameters, message):
        if not self.connections or not message:
            return

        if isinstance(message, str):
            msg = message
            if not msg.endswith('\r\n'):
                msg += '\r\n'
        else:
            msg = str(message) + '\r\n'
        logger.debug(f'PROXY > {message}')


        for conn in list(self.connections.values()):
            try:
                if conn.authenticated:
                    yield conn.send_raw(msg)
            except Exception:
                pass

    @gen.coroutine
    def handle_stream(self, stream, address):
        fromaddr = f"{address[0]}:{address[1]}"
        ip = address[0]
        if not self._can_accept_connection(ip):
            logger.warning(f'Connection from {ip} rejected - too many connections ({self.connections_per_ip[ip]})')
            try:
                stream.close()
            except Exception:
                pass
            return

        logger.info('Proxy Client connected: ' + fromaddr + ' | Active: ' + str(len(self.connections) + 1))
        self.connections_per_ip[ip] += 1

        connection = ProxyConnection(stream, address, self)
        self.connections[fromaddr] = connection

        try:
            yield connection.on_connect()
        finally:
             if fromaddr in self.connections:
                del self.connections[fromaddr]

             self.connections_per_ip[ip] -= 1
             if self.connections_per_ip[ip] <= 0:
                del self.connections_per_ip[ip]

             logger.info(f'Proxy Client disconnected: {fromaddr} | Active: {len(self.connections)}')

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


    def log_active_clients(self):
        if not self.connections:
            logger.info("Proxy: No active clients")
            return

        clients = list(self.connections.keys())
        logger.debug(f"Proxy: Active clients ({len(clients)}): {', '.join(clients)}")


class ProxyConnection(object):
    def __init__(self, stream, address, server):
        # Rate limiting
        self._last_commands = []          
        self._rate_limit = 10 
        self._rate_window = 1.0           

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

    def _check_rate_limit(self):
        now = time.time()

        self._last_commands = [t for t in self._last_commands if now - t < self._rate_window]

        if len(self._last_commands) >= self._rate_limit:
            return False
        self._last_commands.append(now)
        return True

    @gen.coroutine
    def dispatch_client(self):
        try:
            while True:
                try:
                    line = yield gen.with_timeout(
                        datetime.timedelta(seconds=300),
                        self.stream.read_until(b'\r\n')
                    )
                except gen.TimeoutError:
                    logger.warning(f'Client {self.address[0]}:{self.address[1]} timed out (no data for 5 minutes)')
                    self.stream.close()
                    break

                line = line.strip()

                if not line:
                    continue

                line_str = line.decode('ascii', errors='replace')
                core_cmd = line_str[:3] if len(line_str) >= 3 else line_str
        

                data_part = line_str[3:]
                if len(data_part) >= 2 and data_part[-2:].isalnum():   

                    data_part = data_part[:-2]
    
                logger.debug(
                    f'Client {self.address[0]}:{self.address[1]} '
                    f'RX < {core_cmd} - {get_command_name(line_str)} [{data_part}]'
                )

                if not line:
                    continue

                if self.authenticated:

                    if not self._check_rate_limit():
                        logger.warning(f'Rate limit exceeded for {self.address[0]}:{self.address[1]} - dropping command')
                        continue
        
                    events.put('envisalink', None, line_str)
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
