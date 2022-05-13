"""
worker : methods
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

import json
import base64
# methods to perform some processing
# the worker can be used on the main machine
# or we can, later on. send them to celery + rabbitmq

from starlette.templating import Jinja2Templates


templates = Jinja2Templates(directory='/app/templates')

def make_mapfile(mapfile_dict):
    response = parse_spec(mapfile_dict)
    return response

def parse_spec(mapfile_dict):
    # this should: 
    # - parse the config
    # - chose the appropriate routine to generate a mapfile
    # - save it in the sharfed volume
    try:
        decode_data = base64.urlsafe_b64decode(mapfile_dict)
        mapfile_dict = json.loads(decode_data)
        print(mapfile_dict)
    except UnicodeDecodeError:
        return False
    return True



