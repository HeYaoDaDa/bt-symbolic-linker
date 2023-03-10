FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

VOLUME /data

CMD [ "python", "./main.py", "/data/config.json", "/data/cache.json", "/data/flag"]