# -*- coding: utf-8 -*-
# vim: fileencoding=utf-8
"""
Envisalink Client for AlarmServer
Handles TCP connection to Envisalink 2DS/3/4.
"""

import requests
import time
import sys
import re
import socket
import datetime
from tornado import gen
from tornado.tcpclient import TCPClient
from tornado.iostream import StreamClosedError
from socket import gaierror

from core.envisalinkdefs import evl_ResponseTypes
from core.envisalinkdefs import evl_Defaults
from core.envisalinkdefs import evl_ArmModes

from core import logger
import tornado.ioloop

from core.config import config
from core.events import events


def get_message_type(code):
    """Return human readable message type for given TPI code"""
    return evl_ResponseTypes[code]


def to_chars(string):
    """Convert string to list of ASCII values"""
    return [ord(char) for char in string]


def get_checksum(code, data):
    """Calculate TPI checksum"""
    return ("%02X" % sum(to_chars(code) + to_chars(data)))[-2:]


class Client:
    """
    Main Envisalink TCP Client
    """

    def __init__(self):
        logger.debug("Starting Envisalink Client")

        events.register('alarm_update', self.request_action)
        events.register('envisalink', self.envisalink_proxy)
        self.tcpclient = TCPClient()
        self._connection = None
        self._terminator = b"\r\n"
        self._retrydelay = 30
        self._max_attempts = 5
        self._last_activity = time.time()
        self._pending_poll = False
        self._reconnecting = False
        self._reconnect_attempt = 1
        self.do_connect()
        self.busy = True
        # Periodic keepalive
        tornado.ioloop.PeriodicCallback(self.keepalive_poll, 10000).start()

    def update_activity(self):
        """Update last activity timestamp"""
        self._last_activity = time.time()

    def reboot_envisalink(self):
        """Hard reboot of the Envisalink module"""
        url = f"http://{config.ENVISALINKHOST}/3?A=2"
        
        try:
            auth = requests.auth.HTTPBasicAuth(
                getattr(config, 'ENVISALINKUSER', 'user'), 
                config.ENVISALINKPASS
            )
            r = requests.get(url, auth=auth, timeout=10)
            
            if r.status_code in (200, 204):
                logger.warning("Envisalink reboot command sent successfully!")
                return True
            else:
                logger.error(f"Envisalink reboot failed - HTTP status: {r.status_code}")
                return False
        except Exception as e:
            logger.error(f"Envisalink reboot error: {type(e).__name__} - {e}")
            return False

    def keepalive_poll(self):
        """Periodic connection health check"""
        if self._connection is None or self._reconnecting or self.busy:
            return

        if not self._pending_poll:
            self._pending_poll = True
            logger.debug("Sending keepalive command '000'")
            self.send_command("000")

    @gen.coroutine
    def do_connect(self, reconnect=False):
        """Establish connection to the Envisalink module and perform login"""
        self.busy = True
        while self._connection is None:

            logger.info(
                f"Connecting to {config.ENVISALINKHOST}:{config.ENVISALINKPORT} "
                f"(attempt {self._reconnect_attempt}/{self._max_attempts})"
            )

            if self._reconnecting:
                self._reconnect_attempt += 1

                yield gen.sleep(3)

                if self._reconnect_attempt > self._max_attempts:
                    logger.error(f"Max reconnection attempts ({self._max_attempts}) reached. Rebooting Envisalink.")
                    self.reboot_envisalink()
                    self._reconnect_attempt = 0
                    #sys.exit(0)

            try:
                self._connection = yield gen.with_timeout(
                    datetime.timedelta(seconds=10),
                    self.tcpclient.connect(config.ENVISALINKHOST, config.ENVISALINKPORT)
                )

                # TCP Keepalive
                if (self._connection and hasattr(self._connection, 'socket') and self._connection.socket):
                    sock = self._connection.socket
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 15)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 8)
                        logger.debug("TCP Keepalive enabled (60/15/8)")
                    except Exception as e:
                        logger.warning(f"Failed to set keepalive: {e}")

                self._pending_poll = False
                self._last_activity = time.time()

            except (StreamClosedError, gen.TimeoutError) as e:
                logger.warning(f'Connection failed or timeout ({type(e).__name__}) - retrying...')
                yield gen.sleep(self._retrydelay)
                continue

            except Exception as e:
                logger.error(f"Unexpected error during connect: {type(e).__name__} - {e}")
                yield gen.sleep(self._retrydelay)
                continue

            except gaierror:
                logger.error(f'Unable to resolve hostname {config.ENVISALINKHOST}. Exiting.')
                sys.exit(0)

            yield gen.sleep(0.5)

            # === Initial read after connect ===
            try:
                logger.info(f"Connected to Envisalink {config.ENVISALINKHOST}:{config.ENVISALINKPORT}")

                # === LOGIN ===
                success = yield self.perform_login()
                if not success:
                    logger.error("Login failed - reconnecting...")
                    self._connection = None
                    yield gen.sleep(self._retrydelay)
                    continue

                self._reconnecting = False
                self._reconnect_attempt = 1
                self.busy = False
                self.handle_line(None)    

                return

            except Exception as e:
                logger.warning(f"Initial read failed ({type(e).__name__}) - retrying")
                self._connection = None
                yield gen.sleep(self._retrydelay)
                continue


    @gen.coroutine
    def perform_login(self):
        """Perform Envisalink login sequence - sequential way"""
        logger.info("=== LOGIN SEQUENCE START ===")
        self._logging_in = True

        try:
            # Step 1: Wait for initial message (should be 505 3)
            logger.debug("Waiting for initial login message...")
            line = yield gen.with_timeout(
                datetime.timedelta(seconds=15),
                self._connection.read_until(self._terminator)
            )

            logger.info(f"RAW RECEIVED: {repr(line)}")
            parsed = self.parse_tpi_message(line)
            if parsed:
                code, parameters, _, message = parsed
                logger.info(f"Received: {code} {parameters} - {message}")

            if not parsed or code != 505 or parameters != '3':
                logger.error("Did not receive password request (505 3)")
                return False

            # Step 2: Send password
            logger.info("Password requested - sending login command")
            yield gen.sleep(0.15)
            logger.info("SENDING password...")
            self.send_command('005', config.ENVISALINKPASS)

            # Step 3: Wait for Command Acknowledge (500)
            logger.debug("Waiting for command acknowledge...")
            line = yield gen.with_timeout(
                datetime.timedelta(seconds=10),
                self._connection.read_until(self._terminator)
            )

            logger.info(f"RAW RECEIVED: {repr(line)}")
            parsed = self.parse_tpi_message(line)
            if parsed:
                code, parameters, _, message = parsed
                logger.info(f"Received: {code} {parameters} - {message}")

            if code != 500:
                logger.warning("Did not receive command acknowledge (500)")

            # Step 4: Wait for final login status (505 1)
            logger.debug("Waiting for login status...")
            line = yield gen.with_timeout(
                datetime.timedelta(seconds=10),
                self._connection.read_until(self._terminator)
            )

            logger.info(f"RAW RECEIVED: {repr(line)}")
            parsed = self.parse_tpi_message(line)
            if parsed:
                code, parameters, _, message = parsed
                logger.info(f"Received: {code} {parameters} - {message}")

                if code == 505 and parameters == '1':
                    logger.info("LOGIN SUCCESS")
                    yield gen.sleep(0.3)
                    self.send_command('001')
                    logger.info("=== LOGIN SEQUENCE FINISHED SUCCESSFULLY ===")
                    return True
                elif code == 505 and parameters == '0':
                    logger.error("LOGIN FAILED - Wrong password")
                    sys.exit(1)

            logger.error("Did not receive login confirmation (505 1)")
            return False

        except gen.TimeoutError:
            logger.error("Timeout during login sequence")
            return False

            
        except StreamClosedError:
            logger.error("StreamClosedError during login sequence")
            return False

        except Exception as e:
            logger.error(f"Error during login: {type(e).__name__} - {e}")
            return False
        finally:
            self._logging_in = False

    @gen.coroutine
    def _reconnect(self):


        try:
          logger.info("Trying to reconnect ...")
          self._connection.close()
          self._connection = None
          self._connected = False
          self._reconnecting = True
          yield self.do_connect(reconnect=True)
        except Exception as e:
            logger.error(f"Error during reconnection: {e}")


    @gen.coroutine
    def send_command(self, code, data='', checksum=True):
        """Send command to Envisalink"""
        self.update_activity()

        if checksum:
            to_send = code + data + get_checksum(code, data) + '\r\n'
        else:
            to_send = code + data + '\r\n'

        try:
            yield self._connection.write(to_send.encode('ascii'))
            logger.debug(f'TX > {to_send[:-1]}')
        except (StreamClosedError, AttributeError, TypeError):
            pass

    def parse_tpi_message(self, rawinput):
        """Parse raw TPI message from Envisalink"""
        if isinstance(rawinput, bytes):
            input_str = rawinput.decode('ascii', errors='ignore')
        else:
            input_str = str(rawinput)
    
        input_str = input_str.strip()
    
        if config.ENVISALINKLOGRAW:
            logger.debug(f'RX RAW < "{input_str}"')
    
        if re.match(r'^\d\d:\d\d:\d\d ', input_str):
            input_str = input_str[9:]
    
        if not re.match(r'^[0-9a-fA-F]{5,}$', input_str):
            logger.warning(f'Received invalid TPI message: {repr(rawinput)}')
            return None
    
        code = int(input_str[:3])
        parameters = input_str[3:][:-2]
    
        try:
            event = get_message_type(code)
        except KeyError:
            logger.warning(f'Received unknown TPI code: "{input_str[:3]}", parameters: "{parameters}"')
            return None
    
        rcksum = int(input_str[-2:], 16)
        ccksum = int(get_checksum(input_str[:3], parameters), 16)
        if rcksum != ccksum:
            logger.warning('Received invalid TPI checksum')
            return None
    
        message = self.format_event(event, parameters)
        return code, parameters, event, message

    @gen.coroutine
    def dispatch_event(self, code, parameters, event, message, rawinput=None):
        """Dispatch normal (non-login) events to appropriate handler"""
        try:
            handler_name = event.get('handler')
            if handler_name:
                handler = f"handle_{handler_name}"
            else:
                handler = "handle_event"
        except Exception:
            handler = "handle_event"

        # Skip login handler - login is handled in perform_login
        if handler == 'handle_login' or code in (505, 5053):
            #logger.debug(f"Login-related event {code} skipped in normal dispatch")
            return

        try:
            func = getattr(self, handler)
        except AttributeError:
            logger.error(f"Handler function doesn't exist: {handler}")
            return

        # Normal event handling
        if rawinput is not None:
            events.put('proxy', None, rawinput)

        func(code, parameters, event, message)

    @gen.coroutine
    def handle_line(self, rawinput):
        """Main line processing loop"""
        while True:
            self.update_activity()
            self._pending_poll = False
    
            if not rawinput:
                try:
                    rawinput = yield gen.with_timeout(
                        datetime.timedelta(seconds=25),
                        self._connection.read_until(self._terminator)
                    )
                except Exception:
                    break

            parsed = self.parse_tpi_message(rawinput)
            if not parsed:
                break

            code, parameters, event, message = parsed
            logger.debug(f'RX < {code} - {message}')

            try:
                yield self.dispatch_event(code, parameters, event, message, rawinput)
            except Exception as e:
                logger.error(f"Error handling event {code}: {e}")

            # === Read next message ===
            try:
                rawinput = yield gen.with_timeout(
                    datetime.timedelta(seconds=25),
                    self._connection.read_until(self._terminator)
                )
            except gen.TimeoutError:
                logger.warning("Read timeout from EVL - forcing reconnect")
                tornado.ioloop.IOLoop.current().add_callback(self._reconnect)
                break

            except StreamClosedError:
                logger.debug("StreamClosedError in handle_line - forcing reconnect")
                tornado.ioloop.IOLoop.current().add_callback(self._reconnect)
                break

            except Exception as e:
                logger.warning(f"Unexpected error in handle_line: {type(e).__name__} - reconnecting")
                tornado.ioloop.IOLoop.current().add_callback(self._reconnect)
                break

    def format_event(self, event, parameters):
        """Format event message for logging"""
        if 'type' in event:
            if event['type'] == 'partition':
                p = int(parameters[0]) if len(parameters) > 0 else 0
                if p in config.PARTITIONNAMES:
                    return event['name'].format(str(config.PARTITIONNAMES[p]))
            elif event['type'] == 'zone':
                z = int(parameters) if parameters.isdigit() else 0
                if z in config.ZONENAMES:
                    return event['name'].format(str(config.ZONENAMES[z]))
        return event['name'].format(str(parameters))

    def handle_event(self, code, parameters, event, message):
        """Default handler for events"""
        if 'type' not in event:
            return

        parameters = int(parameters)
        try:
            defaultStatus = evl_Defaults[event['type']]
        except (IndexError, KeyError):
            defaultStatus = {}

        if ((event['type'] == 'zone' and parameters in config.ZONENAMES) or
                (event['type'] == 'partition' and parameters in config.PARTITIONNAMES)):
            events.put('alarm', event['type'], parameters, code, event, message, defaultStatus)
        else:
            logger.debug(f'Ignoring unhandled event {event.get("type")}')

    def handle_zone(self, code, parameters, event, message):
        """Handler for zone events"""
        self.handle_event(code, parameters[1:], event, message)

    def handle_partition(self, code, parameters, event, message):
        """Handler for partition events"""
        self.handle_event(code, parameters[0], event, message)

    def request_action(self, eventType, type, parameters):
        """Handle actions requested from AlarmServer"""
        try:
            partition = str(parameters['partition'])
        except (TypeError, KeyError):
            partition = None

        if type == 'arm':
            self.send_command('030', partition)
        elif type == 'stayarm':
            self.send_command('031', partition)
        elif type == 'armwithcode':
            self.send_command('033', partition + str(parameters.get('alarmcode', '')))
        elif type == 'disarm':
            if 'alarmcode' in parameters:
                self.send_command('040', partition + str(parameters['alarmcode']))
            else:
                self.send_command('040', partition + str(config.ALARMCODE))
        elif type == 'refresh':
            self.send_command('001')
        elif type == 'ping':
            self.send_command('000')

    @gen.coroutine
    def envisalink_proxy(self, eventType, type, parameters, *args):
        """Forward command from Proxy clients to real Envisalink"""
        if self._connection is None or self._reconnecting:
            status = "999 Envisalink OFFLINE - command not sent\r\n"
            events.put('proxy_status', None, None, status)
            return False

        try:
            if isinstance(parameters, str):
                to_send = parameters + '\r\n'
            else:
                to_send = parameters

            yield self._connection.write(to_send.encode('ascii'))
            logger.debug(f'PROXY > {to_send.strip()}')
        except (StreamClosedError, AttributeError, TypeError) as e:
            logger.debug(f'Proxy forward error: {e}')


if __name__ == "__main__":
    client = Client()
    tornado.ioloop.IOLoop.current().start()