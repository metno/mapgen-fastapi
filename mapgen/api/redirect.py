from fastapi.responses import RedirectResponse
from fastapi import Request, Query, APIRouter
from worker import make_mapfile

router = APIRouter()

@router.get("/api/get_mapserv", response_class=RedirectResponse)
async def get_mapserv(request: Request, 
                           config_dict: str = Query(None, 
                                           title='Mapfile', 
                                           description='Data to fill in a mapfile template')):
    if config_dict:
        # redirect to given or generated link 
        mapfile_url = make_mapfile(config_dict)
    else:
         mapfile_url = "http://nbswms.met.no/thredds/wms_ql/NBS/S1A/2021/05/18/EW/S1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc?SERVICE=WMS&REQUEST=GetCapabilities"
    return mapfile_url


