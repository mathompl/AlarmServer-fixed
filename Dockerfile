FROM python:3.8-alpine

ENV IP=127.0.0.1
ENV PORT=4025
ENV USERNAME=user
ENV PROXY_USERNAME=user
ENV PROXY_PORT=4025
ENV ALARMCODE=1111
ENV LOGLEVEL=INFO
ENV TZ=Europe/Warsaw

EXPOSE 4025
EXPOSE 8011
EXPOSE 8111
WORKDIR /var/AlarmServer

# Instalacja zależności
RUN apk update && apk add --no-cache tzdata bash

# Kopiujemy wszystko jawnie
COPY . /var/AlarmServer/

# Debug - pokaż co się skopiowało
RUN pwd
RUN ls -la /var/AlarmServer/

# Instalacja Tornado
#RUN pip install --no-cache-dir tornado
RUN pip install --no-cache-dir -r requirements.txt

# Uprawnienia i timezone
RUN chmod +x /var/AlarmServer/run.sh
RUN cp /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

CMD /var/AlarmServer/run.sh
