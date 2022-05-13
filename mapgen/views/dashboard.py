"""
dashboard : endpoint
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

import base64
import fastapi
from typing import List
from mapgen.models.datasource import Datasource
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from fastapi import Query
import json

templates = Jinja2Templates(directory='/app/templates')
router = fastapi.APIRouter()

# placeholder to fill an a template (html+js viewer or mapfile etc.) 
@router.get("/dashboard", name='dashboard', response_model=Datasource)
async def get_dashboard(request: Request,
                        data: str = Query(None,
                                                 title="dict of data",
                                                 description="dict of data and meta informations")):
    decode_data = base64.urlsafe_b64decode(data)
    #input_data = json.dumps(json.loads(decode_data), indent=4, sort_keys=True) 
    #print(input_data)
    