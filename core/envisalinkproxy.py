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
        logger.info(f'Starting Envisalink Proxy on port {config.ENVISALINKPROXYPORT}')
        self.proxy_server = ProxyServer()
        self.proxy_server.listen(config.ENVISALINKPROXYPORT)


class ProxyServer(TCPServer):
    def __init__(self):
        TCPServer.__init__(self)
        self.connections = {}
        self.connections_per_ip = defaultdict(int)
        # === NEW: Track pending ACKs per command so we can route 500 only to the right client ===
        self.pending_acks = defaultdict(list)

        events.register('proxy', self.proxy_event)
        events.register('proxy_status', self.proxy_status)

        self.status_callback = PeriodicCallback(self.log_active_clients, 60000)
        self.status_callback.start()

    def _can_accept_connection(self, ip):
        max_per_ip = getattr(config, 'PROXY_MAX_CONNECTIONS_PER_IP', 5)
        return self.connections_per_ip[ip] < max_per_ip

    @gen.coroutine
    def proxy_status(self, event_name, zone, parameters, message):
        if not self.connections or not message:
            return
        msg = message + '\r\n' if isinstance(message, str) else str(message) + '\r\n'
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
            logger.warning(f'Connection from {ip} rejected (too many connections)')
            stream.close()
            return

        logger.info(f'Proxy Client connected: {fromaddr} | Active: {len(self.connections) + 1}')
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

            # Clean up any pending ACKs for this client
            self._remove_client_from_pending(connection)
            logger.info(f'Proxy Client disconnected: {fromaddr} | Active: {len(self.connections)}')

    def _remove_client_from_pending(self, client):
        """Remove pending ACK entries when a client disconnects"""
        for cmd_key in list(self.pending_acks.keys()):
            self.pending_acks[cmd_key] = [
                (c, ts) for c, ts in self.pending_acks[cmd_key] if c is not client
            ]
            if not self.pending_acks[cmd_key]:
                del self.pending_acks[cmd_key]

    def cleanup_stale_acks(self):
        """Remove ACK entries older than 60 seconds"""
        now = time.time()
        for cmd_key in list(self.pending_acks.keys()):
            self.pending_acks[cmd_key] = [
                (c, ts) for c, ts in self.pending_acks[cmd_key] if now - ts < 60
            ]
            if not self.pending_acks[cmd_key]:
                del self.pending_acks[cmd_key]

    @gen.coroutine
    def proxy_event(self, zone, parameters, input):
        """Route messages from Envisalink to proxy clients.
        500 ACKs are sent ONLY to the client that issued the command.
        """
        if not self.connections or not input:
            return

        msg = input if isinstance(input, str) else input.decode('ascii', errors='replace')
        msg = msg.strip()

        # === SPECIAL HANDLING FOR 500 ACKs ===
        if msg.startswith('500') and len(msg) >= 6:
            prev_cmd = msg[3:6]   # e.g. "001" from "500001..."

            pending_list = self.pending_acks.get(prev_cmd)
            if pending_list:
                for i, (client, ts) in enumerate(pending_list):
                    if time.time() - ts < 45:  # timeout for pending ACK
                        try:
                            yield client.send_raw(msg + '\r\n')
                            client_ip = f"{client.address[0]}:{client.address[1]}"
                            logger.debug(f'ACK ({prev_cmd}) > {client_ip}')
                            del pending_list[i]
                            if not pending_list:
                                del self.pending_acks[prev_cmd]
                            return
                        except Exception:
                            continue

                # Cleanup stale entries
                if pending_list:
                    self.pending_acks[prev_cmd] = [
                        (c, ts) for c, ts in pending_list if time.time() - ts < 45
                    ]
                    if not self.pending_acks[prev_cmd]:
                        del self.pending_acks[prev_cmd]
#            else:
#                logger.debug(f'[PROXY][ACK] 500{prev_cmd} received but no client was waiting for it')
            return   # Do not broadcast 500 ACKs to everyone

        # === Broadcast everything else to all authenticated clients ===
        for conn in list(self.connections.values()):
            try:
                if conn.authenticated:
                    yield conn.send_raw(msg + '\r\n')
            except Exception:
                pass

    def log_active_clients(self):
        self.cleanup_stale_acks()
        if self.connections:
            logger.debug(f"Proxy active clients: {list(self.connections.keys())}")


class ProxyConnection(object):
    def __init__(self, stream, address, server):
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
                line = yield gen.with_timeout(
                    datetime.timedelta(seconds=300),
                    self.stream.read_until(b'\r\n')
                )
                line = line.strip()
                if not line:
                    continue

                line_str = line.decode('ascii', errors='replace')
                client_ip = f"{self.address[0]}:{self.address[1]}"



                if self.authenticated:
                    logger.debug(f'Client {client_ip} RX < {line_str}')
                    if not self._check_rate_limit():
                        logger.warning(f'Rate limit exceeded for {client_ip} - dropping command')
                        continue

                    # === Track this command so we can route the 500 ACK back to this client ===
                    cmd_key = line_str[:3]
                    self.server.pending_acks[cmd_key].append((self, time.time()))
#                    logger.debug(f'[PROXY] {client_ip} waiting for 500{cmd_key} ACK')

                    events.put('envisalink', None, line_str)

                else:
                    # Login handling
                    password = config.ENVISALINKPROXYPASS
                    expected = ('005' + password + get_checksum('005', password)).encode('ascii')

                    if line == expected:
                        self.authenticated = True
                        logger.info(f'LOGIN SUCCESS from {client_ip}')
                        yield self.send_command('500', '005')
                        yield self.send_command('505', '1')
                    else:
                        logger.warning(f'LOGIN FAILED from {client_ip}')
                        yield self.send_command('505', '0')
                        self.stream.close()
                        break

        except StreamClosedError:
            pass
        except Exception as e:
            logger.error(f'Client error from {self.address[0]}:{self.address[1]}: {e}')

    @gen.coroutine
    def send_command(self, command, data='', checksum=True):
        if isinstance(data, bytes):
            data = data.decode('ascii')
        full = command + data
        if checksum:
            cs = get_checksum(full, '')
            to_send = (full + cs + '\r\n').encode('ascii')
        else:
            to_send = (full + '\r\n').encode('ascii')
        try:
            yield self.stream.write(to_send)
        except Exception:
            pass

    @gen.coroutine
    def send_raw(self, data):
        if isinstance(data, str):
            data = data.encode('ascii')
        try:
            yield self.stream.write(data)
        except Exception:
            pass