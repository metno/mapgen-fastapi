import os
import re
#import yaml
import importlib
from importlib.abc import Loader

from distutils.command.config import config
from fastapi.responses import RedirectResponse
from fastapi import Request, Query, APIRouter
from worker import make_mapfile

router = APIRouter()

# This handles a path in adition to the endpoint. This path can be to a netcdf file.
@router.get("/api/get_mapserv/{netcdf_path:path}", response_class=RedirectResponse)
async def get_mapserv(netcdf_path: str,
                      request: Request, 
                      config_dict: str = Query(None, 
                                               title='Mapfile', 
                                               description='Data to fill in a mapfile template')):
    print("1",netcdf_path)
    print("URL", request.url)
    print("METHOD", request.method)
    print("PATH PARAMS", request.path_params)
    print("CONFIG_DICT", config_dict)
    print("CURRENT DIR", os.getcwd())
    default_regexp_config_file = '/config/url-path-regexp-patterns.yaml'
    regexp_config_file = default_regexp_config_file
    #if os.path.exists(regexp_config_file):
    #    with open(regexp_config_file) as f:
    #        regexp_config = yaml.load(f, Loader=yaml.loader.SafeLoader)
    regexp_config = {}
    regexp_config['url_paths_regexp_pattern'] = [{'pattern': 'first', 'module': 'first_module'},
                                                 {'pattern': '^satellite-thredds/polar-swath/(\d{4})/(\d{2})/(\d{2})/(metopa|metopb|metopc|noaa18|noaa19)-avhrr-(\d{14})-(\d{14})\.nc$',
                                                  'module': 'modules.satellite_thredds_module',
                                                  'mapfile_template': '/app/templates/mapfile.map'},
                                                 {'pattern':'another', 'module': 'third_module'}]
    regexp_pattern_module = None
    try:
        for url_path_regexp_pattern in regexp_config['url_paths_regexp_pattern']:
            print(url_path_regexp_pattern)
            pattern = re.compile(url_path_regexp_pattern['pattern'])
            if pattern.match(netcdf_path):
                print("Got match. Need to load module:", url_path_regexp_pattern['module'])
                regexp_pattern_module = url_path_regexp_pattern
                break
            else:
                print("No match")
    except Exception:
        print("Something failed")
    netcdf_file_name, _ = os.path.splitext(os.path.basename(netcdf_path))
    map_file_name = os.path.join("/mapfiles", netcdf_file_name + ".map")
    if not os.path.exists(map_file_name):
        if regexp_pattern_module:
            try:
                loaded_module = importlib.import_module(regexp_pattern_module['module'])
            except ModuleNotFoundError as e:
                print("Failed to load module:", regexp_pattern_module['module'], str(e))
            if loaded_module:
                getattr(loaded_module, 'generate_mapfile')(regexp_pattern_module, netcdf_file_name, map_file_name)

    mapfile_url = f"https://fastapi-dev.s-enda.k8s.met.no/mapserver?map={map_file_name}&request=getcapabilities&service=wms"
    # if config_dict:
    #     # redirect to given or generated link 
    #     mapfile_url = make_mapfile(config_dict)
    # else:
    #      mapfile_url = "http://nbswms.met.no/thredds/wms_ql/NBS/S1A/2021/05/18/EW/S1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc?SERVICE=WMS&REQUEST=GetCapabilities"

    return mapfile_url

# This handles a only the endpoint, but can take aditional query parameters
@router.get("/api/get_mapserv", response_class=RedirectResponse)
async def get_mapserv(request: Request, 
                           config_dict: str = Query(None, 
                                           title='Mapfile', 
                                           description='Data to fill in a mapfile template')):
    print("2", request.method)
    print(request.query_params)
    print(request.path_params)
    if config_dict:
        # redirect to given or generated link 
        mapfile_url = make_mapfile(config_dict)
    else:
         mapfile_url = "http://nbswms.met.no/thredds/wms_ql/NBS/S1A/2021/05/18/EW/S1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc?SERVICE=WMS&REQUEST=GetCapabilities"
    return mapfile_url


