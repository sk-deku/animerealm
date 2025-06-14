FROM python:latest

RUN apt update && apt upgrade -y

RUN apt install git curl python3-pip ffmpeg -y


RUN pip install -U pip

COPY requirements.txt /requirements.txt

RUN cd/

RUN pip install -U-r requirements.txt

RUN mkdir /animerealm

WORKDIR /animerealm

COPY start.sh/start.sh

CMD [/bin/bash", "/start.sh"]
