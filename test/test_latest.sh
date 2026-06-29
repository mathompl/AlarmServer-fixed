#!/bin/bash
# ================================================
# AlarmServer - Clean Startup Script (ENV Friendly)
# ================================================

# ==================== ENVIRONMENT VARIABLES ====================
# You can set these from Docker / docker-compose / shell
IP=192.168.1.4
PORT=4025
PROXY_PORT=4025
USERNAME=admin
PROXY_USERNAME=user
ALARMCODE=1111
LOGLEVEL=DEBUG
TZ="Europe/Warsaw"
# ============================================================

CONFIG_TEMPLATE="/volume1/docker/alarmserver/git/config/alarmserver.cfg"
CONFIG_TEMP="/tmp/alarmserver_running.cfg"

echo "=== AlarmServer - Starting with ENV configuration ==="
echo "IP:            $IP"
echo "PORT:          $PORT"
echo "PROXY_PORT:    $PROXY_PORT"
echo "USERNAME:      $USERNAME"
echo "PROXY_USER:    $PROXY_USERNAME"
echo "ALARMCODE:     *****"
echo "TZ:            $TZ"
echo "=============================================="

# 1. Copy clean template
cp "$CONFIG_TEMPLATE" "$CONFIG_TEMP"

# 2. Replace placeholders using ENV values
# 2. Replace {EVL_XXX} placeholders
sed -i "s/{IP}/$IP/g"                    "$CONFIG_TEMP"
sed -i "s/{PORT}/$PORT/g"                "$CONFIG_TEMP"
sed -i "s/{PROXY_PORT}/$PROXY_PORT/g"    "$CONFIG_TEMP"
sed -i "s/{USERNAME}/$USERNAME/g"        "$CONFIG_TEMP"
sed -i "s/{PROXY_USERNAME}/$PROXY_USERNAME/g" "$CONFIG_TEMP"
sed -i "s/{ALARMCODE}/$ALARMCODE/g"      "$CONFIG_TEMP"
sed -i "s/{LOGLEVEL}/$LOGLEVEL/g"        "$CONFIG_TEMP"

echo "Setting timezone to: $TZ"
ln -snf /usr/share/zoneinfo/$TZ /etc/localtime
echo $TZ > /etc/timezone

echo "Temporary config ready. Starting AlarmServer..."


python ./alarmserver.py -c "$CONFIG_TEMP"

# Optional cleanup
rm -f "$CONFIG_TEMP"
