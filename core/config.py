import configparser
from core import logger

MAXPARTITIONS = 16
MAXZONES = 128
MAXALARMUSERS = 47

PROXY_MAX_CONNECTIONS_PER_IP = 5


class config:
    _config = None

    @staticmethod
    def load(configfile):
        logger.debug('Loading config file: %s' % configfile)
        
        config._config = configparser.ConfigParser()

        if config._config.read(configfile) == []:
            raise RuntimeError('Unable to load config file: %s' % configfile)

        config.LOGURLREQUESTS = config.read_config_var('alarmserver', 'logurlrequests', True, 'bool')
        config.HTTPSPORT = config.read_config_var('alarmserver', 'httpsport', 8111, 'int')
        config.HTTPS = config.read_config_var('alarmserver', 'https', True, 'bool')
        config.CERTFILE = config.read_config_var('alarmserver', 'certfile', 'server.crt', 'str')
        config.KEYFILE = config.read_config_var('alarmserver', 'keyfile', 'server.key', 'str')
        config.HTTPPORT = config.read_config_var('alarmserver', 'httpport', 8011, 'int')
        config.HTTP = config.read_config_var('alarmserver', 'http', False, 'bool')
        config.WEBAUTHUSER = config.read_config_var('alarmserver', 'webauthuser', False, 'str')
        config.WEBAUTHPASS = config.read_config_var('alarmserver', 'webauthpass', False, 'str')
        config.MAXEVENTS = config.read_config_var('alarmserver', 'maxevents', 10, 'int')
        config.MAXALLEVENTS = config.read_config_var('alarmserver', 'maxallevents', 100, 'int')
        config.ENVISALINKHOST = config.read_config_var('envisalink', 'host', 'envisalink', 'str')
        config.ENVISALINKPORT = config.read_config_var('envisalink', 'port', 4025, 'int')
        config.ENVISALINKPASS = config.read_config_var('envisalink', 'pass', 'user', 'str')
        config.ENVISALINKKEEPALIVE = config.read_config_var('envisalink', 'keepalive', 60, 'int')
        config.ENVISALINKLOGRAW = config.read_config_var('envisalink', 'lograwmessage', False, 'bool')
        config.ENABLEPROXY = config.read_config_var('envisalink', 'enableproxy', True, 'bool')
        config.ENVISALINKPROXYPORT = config.read_config_var('envisalink', 'proxyport', config.ENVISALINKPORT, 'int')
        config.ENVISALINKPROXYPASS = config.read_config_var('envisalink', 'proxypass', config.ENVISALINKPASS, 'str')
        config.ALARMCODE = config.read_config_var('envisalink', 'alarmcode', 1111, 'int')
        config.IGNORE_UNKNOWN_ZONES = config.read_config_var('alarmserver', 'ignore_unknown_zones', True, 'bool')
        config.EVENTTIMEAGO = config.read_config_var('alarmserver', 'eventtimeago', True, 'bool')
        config.LOGLEVEL = config.read_config_var('alarmserver', 'loglevel', 'INFO', 'str')
        config.LOGFILE = config.read_config_var('alarmserver', 'logfile', '', 'str')



        if config.LOGFILE == '':
            config.LOGTOFILE = False
        else:
            config.LOGTOFILE = True

        # Partition names
        config.PARTITIONNAMES = {}
        for i in range(1, MAXPARTITIONS + 1):
            partition = config.read_config_var('alarmserver', f'partition{i}', False, 'str', True)
            if partition:
                config.PARTITIONNAMES[i] = partition

        # Zone names
        config.ZONENAMES = {}
        for i in range(1, MAXZONES + 1):
            zone = config.read_config_var('alarmserver', f'zone{i}', False, 'str', True)
            if zone:
                config.ZONENAMES[i] = zone

        # User names
        config.ALARMUSERNAMES = {}
        for i in range(1, MAXALARMUSERS + 1):
            user = config.read_config_var('alarmserver', f'user{i}', False, 'str', True)
            if user:
                config.ALARMUSERNAMES[i] = user

    @staticmethod
    def defaulting(section, variable, default, quiet=False):
        if not quiet:
            logger.debug(f'Config option {variable} not set in [{section}] defaulting to: \'{default}\'')

    @staticmethod
    def read_config_var(section, variable, default, vtype='str', quiet=False):
        try:
            if vtype == 'str':
                return config._config.get(section, variable)
            elif vtype == 'bool':
                return config._config.getboolean(section, variable)
            elif vtype == 'int':
                return config._config.getint(section, variable)
            elif vtype == 'list':
                return config._config.get(section, variable).split(",")
            elif vtype == 'listint':
                return [int(i) for i in config._config.get(section, variable).split(",")]
        except (configparser.NoSectionError, configparser.NoOptionError):
            config.defaulting(section, variable, default, quiet)
            return default