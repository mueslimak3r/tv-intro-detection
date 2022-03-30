FROM python:3.8
COPY . /tv-intro-detection
RUN apt-get update
RUN apt-get install -y ffmpeg libsm6 libxext6
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["python", "/tv-intro-detection/jellyfin.py -d -j"]
