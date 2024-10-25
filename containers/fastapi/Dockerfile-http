FROM docker.io/mambaorg/micromamba:1.5.1-jammy

LABEL maintainer="trygveas@met.no"

ENV MAPGEN_REPO=https://github.com/metno/mapgen-fastapi.git \
    MAPGEN_VERSION=httpserver

COPY ./app /app
# Install dependencies:
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yaml /tmp/environment.yaml
RUN micromamba install -y -n base --file /tmp/environment.yaml

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    git lsof less\
    && rm -rf /var/lib/apt/lists/*
USER $MAMBA_USER
RUN /opt/conda/bin/pip install "git+${MAPGEN_REPO}@${MAPGEN_VERSION}" xncml

#COPY --chown=$MAMBA_USER:$MAMBA_USER ./start.sh /start.sh

#COPY --chown=$MAMBA_USER:$MAMBA_USER ./gunicorn_conf.py /gunicorn_conf.py

#COPY --chown=$MAMBA_USER:$MAMBA_USER ./start-reload.sh /start-reload.sh
#RUN chmod +x /start.sh \
#    && chmod +x /start-reload.sh

WORKDIR /app

#EXPOSE 80

# Run the start script, it will check for an /app/prestart.sh script (e.g. for migrations)
# And then will start Gunicorn with Uvicorn
#CMD ["/start.sh"]
CMD ["/opt/conda/bin/python", "/opt/conda/lib/python3.12/site-packages/mapgen/main.py"]
