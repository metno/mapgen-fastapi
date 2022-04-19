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
