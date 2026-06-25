cd /volume1/docker/alarmserver/git

#git pull

# Logowanie
docker login

docker build -t mathompl/alarmserver-docker-fixed:latest .

# Tagowanie (na wszelki wypadek)
docker tag mathompl/alarmserver-docker-fixed:latest mathompl/alarmserver-docker-fixed:latest

# Wgrywanie na Docker Hub
docker push mathompl/alarmserver-docker-fixed:latest
