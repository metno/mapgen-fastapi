#!/bin/sh
if [ -z "${PREFIX}" ]; then
    PREFIX_PARAM="";
else
    PREFIX_PARAM="--prefix ${PREFIX}";
fi
bokeh serve --port ${PORT} --address 0.0.0.0 --allow-websocket-origin ${ORIGIN} ${PREFIX_PARAM} --log-level ${LOG_LEVEL} /app

# BOKEH_ALLOW_WS_ORIGIN="127.0.0.1:7000,localhost:7000,0.0.0.0:7000"