# -*- coding: utf-8 -*-
"""
Envisalink Client for AlarmServer
Handles TCP connection to Envisalink 2DS/3/4.
"""

import time
import sys
import re
import os
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
        logger.debug('Starting Envisalink Client')

        events.register('alarm_update', self.request_action)
        events.register('envisalink', self.envisalink_proxy)

        self.tcpclient = TCPClient()
        self._connection = None
        self._terminator = b"\r\n"
        self._retrydelay = 20
        self._last_activity = time.time()
        self._pending_poll = False
        self._reconnecting = False

        self.do_connect()

        # Periodic keepalive
        tornado.ioloop.PeriodicCallback(self.keepalive_poll, 8000).start()

    def keepalive_poll(self):
        """Periodic connection health check"""
        if self._connection is None or self._reconnecting:
            return

        try:
            if hasattr(self._connection, 'closed') and self._connection.closed():
                logger.debug("keepalive_poll: connection already closed")
                self._connection = None
                return
        except Exception:
            self._connection = None
            return

        inactivity = time.time() - self._last_activity
        logger.debug("keepalive_poll: inactivity = %.1f seconds" % inactivity)

        # Watchdog
        if inactivity > 60:
            logger.critical("WATCHDOG: No response from Envisalink for %d seconds! Exiting..." % int(inactivity))
            sys.exit(1)

        # Zombie connection
        if inactivity > 20:
            logger.warning("Zombie connection detected (%.1f seconds of inactivity) - forcing reconnect" % inactivity)
            self._pending_poll = False
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

            if not self._reconnecting:
                self._reconnecting = True
                tornado.ioloop.IOLoop.current().add_callback(self._reconnect)
            return

        # Send keepalive
        if not self._pending_poll:
            self._pending_poll = True
            logger.debug("Sending keepalive command '000'")
            self.send_command("000")

    def update_activity(self):
        self._last_activity = time.time()

    @gen.coroutine
    def do_connect(self, reconnect=False):
        if reconnect:
            delay = min(self._retrydelay, 60)
            logger.warning('Connection lost, reconnecting in %s seconds...' % delay)
            yield gen.sleep(delay)
            self._retrydelay = min(self._retrydelay * 1.5, 60)
        else:
            self._retrydelay = 20

        while self._connection is None:
            logger.debug('Connecting to {}:{}'.format(config.ENVISALINKHOST, config.ENVISALINKPORT))

            try:
                self._connection = yield gen.with_timeout(
                    datetime.timedelta(seconds=20),
                    self.tcpclient.connect(config.ENVISALINKHOST, config.ENVISALINKPORT)
                )

                # TCP Keepalive
                if (self._connection is not None and
                        hasattr(self._connection, 'socket') and
                        self._connection.socket is not None):
                    sock = self._connection.socket
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 15)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 8)
                        logger.debug("TCP Keepalive enabled (60/15/8)")
                    except Exception as e:
                        logger.warning("Failed to set keepalive: %s" % str(e))

                self._connection.set_close_callback(self.handle_close)

                self._pending_poll = False
                self._last_activity = time.time()

            except (StreamClosedError, gen.TimeoutError):
                logger.warning('Connection failed or timeout - retrying...')
                self._connection = None
                yield gen.sleep(5)
                continue

            except gaierror:
                logger.error('Unable to resolve hostname %s. Exiting.' % config.ENVISALINKHOST)
                sys.exit(0)

            try:
                line = yield gen.with_timeout(
                    datetime.timedelta(seconds=15),
                    self._connection.read_until(self._terminator)
                )
                logger.debug("Connected to %s:%i" % (config.ENVISALINKHOST, config.ENVISALINKPORT))
                self.handle_line(line)
                self._retrydelay = 20
                break
            except Exception:
                logger.warning("Initial read failed - retrying")
                self._connection = None
                yield gen.sleep(5)
                continue

    @gen.coroutine
    def handle_close(self):
        logger.warning("Envisalink connection closed")
        self._connection = None
        if not self._reconnecting:
            self._reconnecting = True
            tornado.ioloop.IOLoop.current().add_callback(self._reconnect)

    @gen.coroutine
    def _reconnect(self):
        try:
            yield self.do_connect(reconnect=True)
        finally:
            self._reconnecting = False

    @gen.coroutine
    def send_command(self, code, data='', checksum=True):
        self.update_activity()

        if checksum:
            to_send = code + data + get_checksum(code, data) + '\r\n'
        else:
            to_send = code + data + '\r\n'

        try:
            yield self._connection.write(to_send.encode('ascii'))
            logger.debug('TX > ' + to_send[:-1])
        except (StreamClosedError, AttributeError, TypeError):
            pass

    @gen.coroutine
    def handle_line(self, rawinput):
        """Main line processing loop"""
        while True:
            self.update_activity()
            self._pending_poll = False

            if not rawinput:
                return

            # Python 3 bytes fix
            if isinstance(rawinput, bytes):
                input_str = rawinput.decode('ascii', errors='ignore')
            else:
                input_str = str(rawinput)

            input_str = input_str.strip()

            if config.ENVISALINKLOGRAW:
                logger.debug('RX RAW < "' + input_str + '"')

            if re.match(r'^\d\d:\d\d:\d\d ', input_str):
                input_str = input_str[9:]

            if not re.match(r'^[0-9a-fA-F]{5,}$', input_str):
                logger.warning('Received invalid TPI message: ' + repr(rawinput))
                return

            code = int(input_str[:3])
            parameters = input_str[3:][:-2]

            try:
                event = get_message_type(int(code))
            except KeyError:
                logger.warning('Received unknown TPI code: "%s", parameters: "%s"' % (input_str[:3], parameters))
                return

            rcksum = int(input_str[-2:], 16)
            ccksum = int(get_checksum(input_str[:3], parameters), 16)
            if rcksum != ccksum:
                logger.warning('Received invalid TPI checksum')
                return

            message = self.format_event(event, parameters)
            logger.debug('RX < ' + str(code) + ' - ' + message)

            try:
                handler = "handle_%s" % event['handler']
            except KeyError:
                handler = "handle_event"

            try:
                func = getattr(self, handler)
                if handler != 'handle_login':
                    events.put('proxy', None, rawinput)
            except AttributeError:
                logger.error("Handler function doesn't exist: " + handler)
                return

            func(code, parameters, event, message)

            try:
                rawinput = yield gen.with_timeout(
                    datetime.timedelta(seconds=25),
                    self._connection.read_until(self._terminator)
                )
            except gen.TimeoutError:
                logger.warning("Read timeout from EVL - forcing reconnect")
                self._connection = None
                if not self._reconnecting:
                    self._reconnecting = True
                    tornado.ioloop.IOLoop.current().add_callback(self._reconnect)
                break
            except StreamClosedError:
                logger.debug("StreamClosedError in handle_line")
                self._connection = None
                break

    def format_event(self, event, parameters):
        """Format event message"""
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

    def handle_login(self, code, parameters, event, message):
        if parameters == '3':
            self.send_command('005', config.ENVISALINKPASS)
        elif parameters == '1':
            self.send_command('001')
        elif parameters == '0':
            logger.warning('Incorrect Envisalink password')
            sys.exit(0)

    def handle_event(self, code, parameters, event, message):
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
            logger.debug('Ignoring unhandled event %s' % event['type'])

    def handle_zone(self, code, parameters, event, message):
        self.handle_event(code, parameters[1:], event, message)

    def handle_partition(self, code, parameters, event, message):
        self.handle_event(code, parameters[0], event, message)

    def request_action(self, eventType, type, parameters):
        try:
            partition = str(parameters['partition'])
        except (TypeError, KeyError):
            partition = None

        if type == 'arm':
            self.send_command('030', partition)
        elif type == 'stayarm':
            self.send_command('031', partition)
        elif type == 'armwithcode':
            self.send_command('033', partition + str(parameters['alarmcode']))
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
        try:
            # Dodajemy \r\n - to jest kluczowe!
            if isinstance(parameters, str):
                to_send = parameters + '\r\n'
            else:
                to_send = parameters

            yield self._connection.write(to_send.encode('ascii'))
            logger.debug('PROXY > ' + to_send.strip())
        except (StreamClosedError, AttributeError, TypeError) as e:
            logger.debug(f'Proxy forward error: {e}')


if __name__ == "__main__":
    client = Client()
    tornado.ioloop.IOLoop.current().start()
