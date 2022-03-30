FROM python:3.8
COPY . /tv-intro-detection
RUN apt-get update
RUN apt-get install -y ffmpeg libsm6 libxext6
RUN pip install --no-cache-dir -r /tv-intro-detection/requirements.txt
WORKDIR /tv-intro-detection
ENTRYPOINT ["python"]
CMD [ "jellyfin.py -d -j" ]
VOLUME /tv-intro-detection
