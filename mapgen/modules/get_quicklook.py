"""
satellite thredds module : module
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

import gc
import os
import sys
import logging

from typing import Annotated
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
# from fastapi import Request, Query, APIRouter, status
from fastapi import Request, APIRouter, Query, HTTPException, status, BackgroundTasks, Header

from mapgen.modules.helpers import find_config_for_this_netcdf

import mapgen.modules.arome_arctic_quicklook
import mapgen.modules.generic_quicklook
import mapgen.modules.satellite_satpy_quicklook

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/api/get_quicklook{netcdf_path:path}", response_class=Response, include_in_schema=False)
async def get_quicklook(netcdf_path: str,
                        full_request: Request,
                        background_tasks: BackgroundTasks,
                        products: list = Query(default=[]),
                        user_agent: Annotated[str | None, Header()] = None,
                        origin: Annotated[str | None, Header()] = None):
    logger.debug(f"Request query_params: {str(full_request.query_params)}")
    logger.debug(f"Request url scheme: {full_request.url.scheme}")
    logger.debug(f"Request url netloc: {full_request.url.netloc}")
    logger.debug(f"Headers: user_agent:{user_agent}, origin:{origin}")
    netcdf_path = netcdf_path.replace("//", "/")
    logger.debug(f'{netcdf_path}')
    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")
    logger.debug(f"{products}")
    product_config = find_config_for_this_netcdf(netcdf_path)

    # Load module from config
    try:
        loaded_module = getattr(sys.modules[product_config['module']], product_config['module_function'])
    except (AttributeError, ModuleNotFoundError) as e:
        logger.debug(f"Failed to load module: {product_config['module']} {str(e)}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content={"message": f"Failed to load function {product_config['module_function']} " 
                                                f"from module {product_config['module']}. "
                                                "Check the server config."})

    # Call module
    response = await loaded_module(netcdf_path, full_request, background_tasks, products, product_config)
    background_tasks.add_task(clean_data)
    return response

async def clean_data():
    gc.collect()

@router.get("/{image_path:path}", include_in_schema=False)
async def main(image_path: str):
    """Need this to local images"""
    logger.debug(f"image path: {image_path}")
    logger.debug(f"CWD: {os.getcwd()}")
    return FileResponse(image_path)
