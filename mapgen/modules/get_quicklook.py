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

import os
import importlib

from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
# from fastapi import Request, Query, APIRouter, status
from fastapi import Request, APIRouter, Query, HTTPException, status

from mapgen.modules.helpers import find_config_for_this_netcdf

router = APIRouter()

@router.get("/api/get_quicklook{netcdf_path:path}", response_class=Response)
async def get_quicklook(netcdf_path: str,
                        full_request: Request,
                        products: list = Query(default=[])):
    print("Request query_params:", str(full_request.query_params))
    print("Request url scheme:", full_request.url.scheme)
    print("Request url netloc:", full_request.url.netloc)
    netcdf_path = netcdf_path.replace("//", "/")
    print(f'{netcdf_path}')
    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")
    print(products)
    product_config = find_config_for_this_netcdf(netcdf_path)

    # Load module from config
    try:
        loaded_module = getattr(importlib.import_module(product_config['module']), product_config['module_function'])
    except (AttributeError, ModuleNotFoundError) as e:
        print("Failed to load module:", product_config['module'], str(e))
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content={"message": f"Failed to load function {product_config['module_function']} " 
                                                f"from module {product_config['module']}. "
                                                "Check the server config."})

    # Call module
    return loaded_module(netcdf_path, full_request, products, product_config)

@router.get("/{image_path:path}")
async def main(image_path: str):
    """Need this to local images"""
    print("image path:", image_path)
    print("CWD: ", os.getcwd())
    return FileResponse(image_path)
