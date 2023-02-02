ARG BASE_IMAGE=ubuntu:22.04
FROM $BASE_IMAGE

LABEL maintainer="massimods@met.no"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get -y dist-upgrade && apt-get install -y apt-utils build-essential git python3-dev python3-venv python3-mapscript
#cmake libpng-dev libcurl4-gnutls-dev libjpeg8-dev libaprutil1-dev libapr1-dev libpixman-1-dev libgdal-dev libpq-dev libsqlite3-dev libtiff-dev libgeotiff-dev libgeos-dev swig libfreetype-dev
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV MAPGEN_REPO=https://github.com/metno/mapgen-fastapi.git \
    MAPGEN_VERSION=main

COPY ./app /app
# Install dependencies:
COPY requirements.txt .
RUN python3 -m venv $VIRTUAL_ENV \
    && pip install -U pip \
    && pip install -r requirements.txt \
    && pip install "git+${MAPGEN_REPO}@${MAPGEN_VERSION}"
    # && ln -s /opt/venv/lib/python3.10/site-packages/mapgen/favicon.ico /app
    # && git clone https://github.com/MapServer/mapserver.git /tmp/mapserver \
    # && cd /tmp/mapserver \
    # && git checkout tags/rel-8-0-0 \
    # && mkdir -p /tmp/mapserver/build && cd /tmp/mapserver/build \
    # && cmake .. -DWITH_POSTGRESQL=1 -DWITH_TIFF=1 -DWITH_GEOTIFF=1 -DWITH_MEMCACHE=1 -DWITH_CURL=1 -DWITH_PYTHON=1 -DWITH_PROTOBUFC=0 -DWITH_FRIBIDI=0 -DWITH_HARFBUZZ=0 -DWITH_CAIRO=0 -DWITH_FCGI=0 -DWITH_PYMAPSCRIPT_ANNOTATIONS=1 \
    # && make install \
    # && make clean

COPY ./start.sh /start.sh

COPY ./gunicorn_conf.py /gunicorn_conf.py

COPY ./start-reload.sh /start-reload.sh
RUN chmod +x /start.sh \
    && chmod +x /start-reload.sh

#RUN git clone --branch upload-map-files-to-ceph https://github.com/metno/mapgen-fastapi.git
# ENV NCPLOTDIR /opt/ncplot/

WORKDIR /app

ENV PYTHONPATH=/app:/lib/python3/dist-packages/

EXPOSE 80

# Run the start script, it will check for an /app/prestart.sh script (e.g. for migrations)
# And then will start Gunicorn with Uvicorn
CMD ["/start.sh"]