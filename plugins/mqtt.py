# -*- coding: utf-8 -*-
"""
MQTT Module for AlarmServer
With debug logging enabled.
"""

import asyncio
import json
from core import logger
from core.config import config
from core.events import events

import aiomqtt


def init():
    """Initialize MQTT module from configuration."""
    config.MQTT_ENABLE = config.read_config_var('mqtt', 'enable', False, 'bool')

    if not config.MQTT_ENABLE:
        logger.debug("[MQTT] Module is disabled in config")
        return

    config.MQTT_BROKER = config.read_config_var('mqtt', 'broker', 'localhost', 'str')
    config.MQTT_PORT = config.read_config_var('mqtt', 'port', 1883, 'int')
    config.MQTT_USERNAME = config.read_config_var('mqtt', 'username', '', 'str')
    config.MQTT_PASSWORD = config.read_config_var('mqtt', 'password', '', 'str')
    config.MQTT_BASE_TOPIC = config.read_config_var('mqtt', 'base_topic', 'alarm', 'str')
    config.MQTT_RETAIN = config.read_config_var('mqtt', 'retain', True, 'bool')

    logger.info("[MQTT] Module enabled -> {}:{}".format(config.MQTT_BROKER, config.MQTT_PORT))

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(mqtt_connection_loop())


async def mqtt_connection_loop():
    """Main connection loop with reconnection."""
    while True:
        try:
            await connect_to_broker()
        except Exception as e:
            logger.error("[MQTT] Connection error: {}. Reconnecting in 10s...".format(e))
            await asyncio.sleep(10)


async def connect_to_broker():
    """Connect to MQTT broker."""
    logger.debug("[MQTT] Attempting to connect to broker...")

    async with aiomqtt.Client(
        hostname=config.MQTT_BROKER,
        port=config.MQTT_PORT,
        username=config.MQTT_USERNAME or None,
        password=config.MQTT_PASSWORD or None,
    ) as client:

        logger.info("[MQTT] Successfully connected to broker")



        events.register('statechange', lambda *args: asyncio.create_task(
            publish_state_change(client, *args)
        ))
        
        events.register('stateinit', lambda *args: asyncio.create_task(
            publish_state_change(client, *args, is_init=True)
        ))

        # Subscribe to commands
        command_topic = "{}/command/#".format(config.MQTT_BASE_TOPIC)
        await client.subscribe(command_topic)
        logger.debug("[MQTT] Subscribed to: {}".format(command_topic))

        # Listen for incoming messages
        async for message in client.messages:
            await process_mqtt_command(message)


async def publish_state_change(client, eventType, type, parameters, code, event, message, defaultStatus, is_init=False):
    """Publish zone/partition state to MQTT."""
    topic = "{}/{}/{}/state".format(config.MQTT_BASE_TOPIC, type, parameters)

    payload = {
        "type": type,
        "id": parameters,
        "code": code,
        "message": message,
        "status": event.get("status", {}),
        "is_init": is_init
    }

    try:
        await client.publish(
            topic,
            payload=json.dumps(payload),
            qos=1,
            retain=config.MQTT_RETAIN
        )
        #logger.debug("[MQTT] Published -> {} | is_init={}".format(topic, is_init))

    except Exception as e:
        logger.error("[MQTT] Publish failed for topic {}: {}".format(topic, e))


async def process_mqtt_command(message):
    """Handle incoming MQTT commands."""
    try:
        topic = str(message.topic)
        payload_raw = message.payload.decode("utf-8", errors="ignore")

        #logger.debug("[MQTT] Command received -> Topic: {} | Payload: {}".format(topic, payload_raw))

        parts = topic.split("/")

        if len(parts) >= 5 and parts[1] == "command":
            entity_type = parts[2]
            entity_id = int(parts[3])
            action = parts[4]

            alarm_code = None
            try:
                data = json.loads(payload_raw)
                if isinstance(data, dict):
                    alarm_code = data.get("code") or data.get("alarm_code")
            except:
                if payload_raw.strip().isdigit():
                    alarm_code = payload_raw.strip()

            params = {"partition": entity_id}
            if alarm_code:
                params["alarmcode"] = alarm_code

            if entity_type == "partition":
                if action == "arm":
                    events.put("alarm_update", "arm", params)
                elif action == "disarm":
                    events.put("alarm_update", "disarm", params)
                elif action == "stayarm":
                    events.put("alarm_update", "stayarm", params)
                elif action == "refresh":
                    events.put("alarm_update", "refresh", {})

    except Exception as e:
        logger.error("[MQTT] Error processing command: {}".format(e))


def stop():
    logger.debug("[MQTT] Module stopped")