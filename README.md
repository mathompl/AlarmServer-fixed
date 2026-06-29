## Envisalink DSC 2DS / 3 / 4 Alarm Server (TPI Proxy & HTTP/JSON API).
AlarmServer enables connections of multiple clients with Envisalink TPI interface.

This is a patched and improved version of the original repo [https://github.com/juggie/AlarmServer](https://github.com/juggie/AlarmServer) 

Docker image:
[mathompl/alarmserver-docker-fixed:latest](https://hub.docker.com/r/mathompl/alarmserver-docker-fixed)

## PROBLEM
Envisalink connections randomly become **zombie/stalled** (no data flow, but the connection is never closed), so the proxy **hangs indefinitely**.Sockets logic is flawed, TCP keepalive is not properly configured. 
This caused the AlarmServer to stop receiving events from the Envisalink module without any clear error. 

This version fixes above problems and cleans code a bit.

WEB rest interface doesn't seem to work correctly.

## TODO
Migrate to newest python, fix web rest api.
