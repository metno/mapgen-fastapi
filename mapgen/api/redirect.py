"""
fastapi : endpoint
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

import os
import re
import yaml
import importlib
from importlib.abc import Loader

from distutils.command.config import config
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import Request, Query, APIRouter, status
from mapgen.worker import make_mapfile

import boto3
from botocore.exceptions import ClientError

router = APIRouter()

def upload_mapfile_to_ceph(map_file_name, bucket):
    s3_client = boto3.client(service_name='s3',
                             endpoint_url=os.environ['S3_ENDPOINT_URL'],
                             aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                             aws_secret_access_key=os.environ['S3_SECRET_KEY'])
    try:
        s3_client.upload_file(map_file_name, bucket, os.path.basename(map_file_name))
    except ClientError as e:
        print("s3 upload map file failed with: ", str(e))
        return False
    return True   

def get_mapfiles_path(regexp_pattern_module):
    return regexp_pattern_module['mapfiles_path']

def read_config_file(regexp_config_file):
    regexp_config = None
    try:
        if os.path.exists(regexp_config_file):
            with open(regexp_config_file) as f:
                regexp_config = yaml.load(f, Loader=yaml.loader.SafeLoader)
    except Exception as e:
        print(f"Failed to read yaml config: {regexp_config_file} with {str(e)}")
        pass
    return regexp_config


# This handles a path in adition to the endpoint. This path can be to a netcdf file.
@router.get("/api/get_mapserv/{netcdf_path:path}", response_class=RedirectResponse)
async def get_mapserv(netcdf_path: str,
                      request: Request, 
                      config_dict: str = Query(None, 
                                               title='Mapfile', 
                                               description='Data to fill in a mapfile template')):
    default_regexp_config_file = '/config/url-path-regexp-patterns.yaml'
    regexp_config_file = default_regexp_config_file
    regexp_config = read_config_file(regexp_config_file)
    regexp_pattern_module = None
    try:
        for url_path_regexp_pattern in regexp_config:
            print(url_path_regexp_pattern)
            pattern = re.compile(url_path_regexp_pattern['pattern'])
            if pattern.match(netcdf_path):
                print("Got match. Need to load module:", url_path_regexp_pattern['module'])
                regexp_pattern_module = url_path_regexp_pattern
                break
            else:
                print(f"Could not find any match for the path {netcdf_path} in the configuration file {regexp_config_file}.")
                print("Please review your config if you expect this path to be handled.")
    except Exception as e:
        print(f"Exception in the netcdf_path match part with {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"message": "Exception raised when regexp. Check the config."})

    if not regexp_pattern_module:
        return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content={"message": "Could not match against any pattern. Check the config."})

    netcdf_file_name, _ = os.path.splitext(os.path.basename(netcdf_path))
    mapfiles_path = get_mapfiles_path(regexp_pattern_module)
    try:
        os.mkdir(mapfiles_path)
    except FileExistsError:
        pass
    except PermissionError:
        pass
    map_file_name = os.path.join(mapfiles_path, netcdf_file_name + ".map")
    if not os.path.exists(map_file_name):
        if regexp_pattern_module:
            try:
                loaded_module = importlib.import_module(regexp_pattern_module['module'])
            except ModuleNotFoundError as e:
                print("Failed to load module:", regexp_pattern_module['module'], str(e))
                return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"message": f"Failed to load module {regexp_pattern_module['module']}"})
            if loaded_module:
                if not getattr(loaded_module, 'generate_mapfile')(regexp_pattern_module, netcdf_path, netcdf_file_name, map_file_name):
                    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"message": "Could not find any quicklooks. No map file generated."})
                else:
                    if not upload_mapfile_to_ceph(map_file_name, regexp_pattern_module['map_file_bucket']):
                        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"message": f"Failed to upload map_file_name {map_file_name} to ceph."})

    mapfile_url = f"{request.url.scheme}://{request.url.netloc}/mapserver/{netcdf_path}?{request.url.query}"
    
    return mapfile_url

# This handles a only the endpoint, but can take aditional query parameters
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
