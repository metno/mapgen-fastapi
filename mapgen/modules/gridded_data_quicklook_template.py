"""
gridded data quicklook template : module
====================

Copyright 2023 MET Norway

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

"""
Needed entries in the config:
---
  - 'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(metopb|metopc)-(avhrr)-(\d{14})-(\d{14})\.nc$'
    'base_netcdf_directory': '/lustre/storeB/immutable/archive/projects/remotesensing'
    'module': 'mapgen.modules.gridded_data_quicklook_template'
    'module_function': 'gridded_data_quicklook_template'
    'default_dataset': 'air_temperature'

            #The following is not needed for gridded data, but is available
            'mapfile_template': '/mapfile-templates/mapfile.map'
            'map_file_bucket': 's-enda-mapfiles'
            'geotiff_bucket': 'geotiff-products-for-senda'
            'mapfiles_path': '.'
            'geotiff_tmp': '.'

"""
from fastapi import Request, Query
import mapscript

from helpers import handle_request

def _fill_metadata_to_mapfile(netcdf_path, map_object, full_request):
    """Fill in needed metadata to generate the mapfile"""
    return

def _generate_layer(layer):
    """Add to mapfile each layer/variable"""
    return

def gridded_data_quicklook_template(netcdf_path: str,
                                    full_request: Request,
                                    products: list = Query(default=[]),
                                    product_config: dict = {}):

    # Parse the netcdf filename to get start time or reference time
    # Read all variables names from the netcdf file.
    # Loop over all variable names to add layer for each variable including needed dimmensions.
    #   Time
    #   Height
    #   Pressure
    #   Other dimensions
    # Add this to some data structure.
    # Pass this data structure to mapscript to create an in memory config for mapserver/mapscript
    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(netcdf_path, map_object, full_request)

    layers = "all needed layers/variables"
    for satpy_product in layers:
        layer = mapscript.layerObj()
        _generate_layer(layer)
        layer_no = map_object.insertLayer(layer)

    # Handle the request and return results.
    return handle_request(map_object, full_request)

