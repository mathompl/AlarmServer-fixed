from core import logger
from core.config import config
from core.events import events


def init():
    """
    Dummy handler for 'statechange' and 'stateinit' events.
    Prevents 'No handler registered' warnings when nothing else listens to these events.
    """
    config.DUMMY_STATE_ENABLE = config.read_config_var('dummystates', 'enable', True, 'bool')

    if config.DUMMY_STATE_ENABLE:
        events.register('statechange', dummy_handler)
        events.register('stateinit', dummy_handler)
        
        logger.info('Dummy state handler enabled (statechange + stateinit)')
    else:
        logger.debug('Dummy state handler is disabled in config')


def dummy_handler(eventType, type, parameters, code, event, message, defaultStatus):
    """
    This handler does nothing on purpose.
    It only exists to consume statechange/stateinit events.
    """
    # logger.debug(f"Dummy received state event: type={type}, param={parameters}, code={code}")
    pass