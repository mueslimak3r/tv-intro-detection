FROM python:3.8
COPY . /app
RUN apt-get update
RUN apt-get install -y ffmpeg libsm6 libxext6
RUN pip install --no-cache-dir -r /app/requirements.txt
WORKDIR /app
ENTRYPOINT ["python"]
CMD ["jellyfin.py", "-d", "-j"]

VOLUME /config
