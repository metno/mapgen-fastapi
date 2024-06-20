"""
main app
====================

Copyright 2022 MET Norway

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import fastapi
from starlette.middleware.cors import CORSMiddleware
import uvicorn
from mapgen.views import dashboard
from mapgen.modules import get_quicklook

import logging
from gunicorn import glogging


logging_cfg = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'KeyValueFormatter': {
            'format': (
                '[%(asctime)s] [%(process)d] '
                '[%(levelname)s] %(message)s'
            )
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'KeyValueFormatter',
        }
    },
    'loggers': {
        'gunicorn.access': {
            'propagate': True,
        },
        'gunicorn.error': {
            'propagate': True,
        },
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console'],
    }
}

def configure_logging():
    logging.config.dictConfig(logging_cfg)

app = fastapi.FastAPI(title="MapGen",
                      description="API for handeling OGC WMS request to data. Each data type needs an implemented module and a corresponding config.",
                      version="1.0.0",
                      docs_url=None,
                      redoc_url=None,
                      )

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_PROCESSING_SECOND = 600


def configure_routing():
    app.include_router(dashboard.router)
    app.include_router(get_quicklook.router)

def configure():
    configure_logging()
    configure_routing()


if __name__ == '__main__':
    configure()
    uvicorn.run(app, port=8999, host='localhost')
else:
    configure()
