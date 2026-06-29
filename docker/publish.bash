cd ..
VERSION=$(date +"%Y.%m.%d") 


#git pull

# Logowanie
docker login

docker build -t mathompl/alarmserver-docker-fixed:latest .
#docker build -t mathompl/alarmserver-docker-fixed:$VERSION .

# Tagowanie (na wszelki wypadek)
#docker tag mathompl/alarmserver-docker-fixed:latest mathompl/alarmserver-docker-fixed:latest

# Wgrywanie na Docker Hub
docker push mathompl/alarmserver-docker-fixed:latest
#docker push mathompl/alarmserver-docker-fixed:$VERSION
