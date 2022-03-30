FROM python:3.8
COPY . .
RUN apt-get update
RUN apt-get install -y ffmpeg libsm6 libxext6
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python ./jellyfin.py -d -j" ]
