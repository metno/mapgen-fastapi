ARG BASE_IMAGE=ubuntu:22.04
FROM $BASE_IMAGE

LABEL maintainer="massimods@met.no"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get -y dist-upgrade && apt-get install -y apt-utils build-essential git python3-dev python3-venv

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV MAPGEN_REPO=https://github.com/metno/mapgen-fastapi.git \
    MAPGEN_VERSION=main

# Install dependencies:
COPY requirements.txt .
RUN pip install -U pip \
    && pip install -r requirements.txt \
    && pip install "git+${MAPGEN_REPO}@${MAPGEN_VERSION}"

COPY ./start.sh /start.sh

COPY ./gunicorn_conf.py /gunicorn_conf.py

COPY ./start-reload.sh /start-reload.sh
RUN chmod +x /start.sh \
    && chmod +x /start-reload.sh

COPY ./app /app
#RUN git clone --branch upload-map-files-to-ceph https://github.com/metno/mapgen-fastapi.git
# ENV NCPLOTDIR /opt/ncplot/

WORKDIR /app

ENV PYTHONPATH=/app

EXPOSE 80

# Run the start script, it will check for an /app/prestart.sh script (e.g. for migrations)
# And then will start Gunicorn with Uvicorn
CMD ["/start.sh"]