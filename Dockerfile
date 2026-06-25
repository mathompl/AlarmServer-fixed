FROM python:2.7-alpine3.8

ENV TZ=Europe/Warsaw

EXPOSE 4025
WORKDIR /var/AlarmServer

# Instalacja zależności
RUN apk update && apk add --no-cache tzdata bash

# Kopiujemy wszystko jawnie
COPY . /var/AlarmServer/

# Debug - pokaż co się skopiowało
RUN pwd
RUN ls -la /var/AlarmServer/

# Instalacja Tornado
RUN pip install --no-cache-dir tornado

# Uprawnienia i timezone
RUN chmod +x /var/AlarmServer/run.sh
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

CMD /var/AlarmServer/run.sh
