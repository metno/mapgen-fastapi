"""
gridded data quicklook template : module
====================

Copyright 2023,2024 MET Norway

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
import os
import pandas
import logging
import datetime
import mapscript
import xarray as xr
from mapgen.modules.create_symbol_file import create_symbol_file
from mapgen.modules.helpers import handle_request, _parse_filename, _get_mapfiles_path, _fill_metadata_to_mapfile
from mapgen.modules.helpers import _generate_getcapabilities, _generate_getcapabilities_vector, _generate_layer
from mapgen.modules.helpers import _parse_request, HTTPError

grid_mapping_cache = {}
wind_rotation_cache = {}
summary_cache = {}

logger = logging.getLogger(__name__)

def arome_arctic_quicklook(netcdf_path: str,
                           query_string: str,
                           http_host: str,
                           url_scheme: str,
                           satpy_products: list = [],
                           product_config: dict = {},
                           api = None):
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        logger.error(f"status_code=500, Missing base dir in server config.")
        raise HTTPError(response_code='500 Internal Server Error', response="Missing base dir in server config.")

    if not os.path.exists(netcdf_path):
        logger.error(f"status_code=404, Could not find {orig_netcdf_path} in server configured directory.")
        raise HTTPError(response_code='404 Not Found', response=f"Could not find {orig_netcdf_path} in server configured directory.")

    ds_disk = xr.open_dataset(netcdf_path)

    #get forecast reference time from dataset
    try:
        forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
    except KeyError:
        logger.debug(f"Could not find forecast time or analysis time from dataset. Try parse from filename.")
        # Parse the netcdf filename to get start time or reference time
        _, _forecast_time = _parse_filename(netcdf_path, product_config)
        forecast_time = datetime.datetime.strptime(_forecast_time, "%Y%m%dT%H")
        logger.debug(f"Forecast time: {forecast_time}")

    symbol_file = os.path.join(_get_mapfiles_path(product_config), "symbol.sym")
    create_symbol_file(symbol_file)
    qp = _parse_request(query_string)

    map_object = None
    actual_variable = None
    if 'request' in qp and qp['request'] != 'GetCapabilities':
        mapserver_map_file = os.path.join(_get_mapfiles_path(product_config), f'{os.path.basename(orig_netcdf_path)}.map')
        map_object = mapscript.mapObj()
        _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, url_scheme, http_host, ds_disk, summary_cache, "WMS Arome Arctic.", api)
        map_object.setSymbolSet(symbol_file)
        layer = mapscript.layerObj()
        actual_variable = _generate_layer(layer, ds_disk, grid_mapping_cache, netcdf_path, qp, map_object, product_config, wind_rotation_cache)
        if actual_variable:
            layer_no = map_object.insertLayer(layer)
    else:
        # Assume getcapabilities
        mapserver_map_file = os.path.join(_get_mapfiles_path(product_config), f'{os.path.basename(orig_netcdf_path)}-getcapabilities.map')
        if os.path.exists(mapserver_map_file):
            logger.debug(f"Reuse existing getcapabilities map file {mapserver_map_file}")
            map_object = mapscript.mapObj(mapserver_map_file)
        else:
            map_object = mapscript.mapObj()
            _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, url_scheme, http_host, ds_disk, summary_cache, "WMS Arome Arctic", api)
            map_object.setSymbolSet(symbol_file)
            # Read all variables names from the netcdf file.
            variables = list(ds_disk.keys())
            for variable in variables:
                if variable in ['forecast_reference_time', 'p0', 'ap', 'b', 'projection_lambert']:
                    logger.debug(f"Skipping variable or dimension: {variable}")
                    continue
                layer = mapscript.layerObj()
                if _generate_getcapabilities(layer, ds_disk, variable, grid_mapping_cache, netcdf_path, product_config=product_config):
                    layer_no = map_object.insertLayer(layer)
                if variable.startswith('x_wind') and variable.replace('x', 'y') in variables:
                    logger.debug(f"Add wind vector layer for {variable}.")
                    layer_contour = mapscript.layerObj()
                    if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path, product_config=product_config):
                        layer_no = map_object.insertLayer(layer_contour)

    map_object.save(mapserver_map_file)

    ds_disk.close()
    # Handle the request and return results.
    return handle_request(map_object, query_string)
