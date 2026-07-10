## Envisalink DSC 2DS / 3 / 4 Alarm Server (TPI Proxy & HTTP/JSON API).
AlarmServer enables connections of multiple clients with Envisalink TPI interface.

This is a patched and improved version of the original repo [https://github.com/juggie/AlarmServer](https://github.com/juggie/AlarmServer) 

Docker image:
[mathompl/alarmserver-docker-fixed:latest](https://hub.docker.com/r/mathompl/alarmserver-docker-fixed)

## Problem & Fix

Envisalink connections would sometimes become unresponsive, causing the proxy to hang indefinitely. Restarting AlarmServer or EVL was required.

**Root cause:**  
Envisalink allows only one TCP client at a time. Old connections were not properly closed, preventing new ones from being established.

**This update fixes:**

- better reconnect logic
- if reconnecting fails - reboots Envisalink
- Implements alarmserver<->evl keepalive
- works with HomeAssistant envisalink_new: https://github.com/ufodone/envisalink_new
- beta mqtt broker support
- other minor fixes, code cleanup, error handling, better logging, config cleanup and python 3.8 migration

Proxy now responds custom codes: `999` when not connected to EVL and `998` when it receives malformed command from client.

