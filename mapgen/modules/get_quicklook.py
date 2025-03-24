"""
satellite thredds module : module
====================

Copyright 2022,2024 MET Norway

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

import sys
import logging

from mapgen.modules.helpers import find_config_for_this_netcdf, HTTPError

import mapgen.modules.arome_arctic_quicklook
import mapgen.modules.generic_quicklook
import mapgen.modules.satellite_satpy_quicklook

logger = logging.getLogger(__name__)

def get_quicklook(netcdf_path: str,
                  query_string,
                  http_host,
                  url_scheme,
                  products=[],
                  api=None):
    logger.debug(f"Request query_params: {query_string}")
    logger.debug(f"Request url scheme: {url_scheme} and host {http_host}")
    logger.debug(f"Selected api {api}")
    netcdf_path = netcdf_path.replace("//", "/")
    logger.debug(f'{netcdf_path}')
    if not netcdf_path:
        response_code = '404 Not Found'
        response = b'Missing netcdf path\n'
        content_type = 'text/plain'
    else:        
        logger.debug(f"{products}")
        if api == 'klimakverna':
            product_config, response, response_code, content_type = find_config_for_this_netcdf(netcdf_path,
                                                                                                regexp_config_filename='klimakverna-url-path-regexp-patterns.yaml')
        else:
            product_config, response, response_code, content_type = find_config_for_this_netcdf(netcdf_path)
        if product_config:
            # Load module from config
            try:
                loaded_module = getattr(sys.modules[product_config['module']], product_config['module_function'])
                # Call module
                response_code, response, content_type = loaded_module(netcdf_path, query_string, http_host, url_scheme, products, product_config)
            except HTTPError as he:
                response_code = he.response_code
                response = he.response
                content_type = he.content_type
            except (AttributeError, ModuleNotFoundError) as e:
                logger.debug(f"Failed to load module: {product_config['module']} {str(e)}")
                response_code = '500'
                response = (f"Failed to load function {product_config['module_function']} " 
                            f"from module {product_config['module']}. "
                            "Check the server config.").encode()
                content_type = 'text/plain'
            except OSError as oe:
                logger.debug(f"Unable to access netcdf file {netcdf_path}: {str(oe)}")
                response_code = '404 Not Found'
                response = (f"Unable to access netcdf file {netcdf_path}.").encode()
                content_type = 'text/plain'
            except Exception as e:
                logger.debug(f"Unknown exception {str(e)}")
                response_code = '500 Internal Server Error'
                response = (f"Unknown server error. Please contact the server administrator.").encode()
                content_type = 'text/plain'
    return response_code, response, content_type
