## Envisalink DSC 2DS / 3 / 4 Alarm Server (TPI Proxy & HTTP/JSON API).
AlarmServer enables connections of multiple clients with Envisalink TPI interface.

This is a patched and improved version of the original repo [https://github.com/juggie/AlarmServer](https://github.com/juggie/AlarmServer) 

Docker image:
[mathompl/alarmserver-docker-fixed:latest](https://hub.docker.com/r/mathompl/alarmserver-docker-fixed)

## FIXES

Envisalink connections would randomly become **zombie/stalled** (no data flow, but the connection was not closed), so the proxy would **hang indefinitely**.Reconnecting logic was unreliable, TCP keepalive was not properly configured

This caused the AlarmServer to stop receiving events from the Envisalink module without any clear error.

