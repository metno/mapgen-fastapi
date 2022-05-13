"""
Datasource : CLASS
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

from typing import Optional

import pydantic
from pydantic import BaseModel


class Datasource(BaseModel):
    data: dict = pydantic.Field(default={"": ""},
                                example={
                                    "id1": {
                                        "title": "Title",
                                        "feature_type": "NA",
                                        "resources": {
                                            "OGC:WMS": [
                                                "http://nbswms.met.no/thredds/wms_ql/NBS/S1A/2021/05/18/EW/S1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc?SERVICE=WMS&REQUEST=GetCapabilities"]
                                        }
                                    }                                                                        
                                })
    email: str = pydantic.Field(default='me@you.web', example='epiesasha@me.com')
    project: Optional[str] = pydantic.Field(default='WMS', example='Mapserver')
