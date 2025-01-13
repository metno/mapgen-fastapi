"""
gridded data quicklook : module
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
from mapgen.modules.helpers import handle_request, _fill_metadata_to_mapfile, _parse_filename, _get_mapfiles_path
from mapgen.modules.helpers import _generate_getcapabilities, _generate_getcapabilities_vector, _generate_layer
from mapgen.modules.helpers import _parse_request, _read_netcdfs_from_ncml, HTTPError

grid_mapping_cache = {}
summary_cache = {}
wind_rotation_cache = {}

logger = logging.getLogger(__name__)

def generic_quicklook(netcdf_path: str,
                      query_string: str,
                      http_host: str,
                      url_scheme: str,
                      satpy_products: list = [],
                      product_config: dict = {}):
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if netcdf_path.startswith(product_config['base_netcdf_directory']):
            logger.debug("Request with full path. Please fix your request. Depricated from version 2.0.0.")
        elif os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        logger.error(f"status_code=500, Missing base dir in server config.")
        raise HTTPError(response_code='500', response="Missing base dir in server config.")

    if not netcdf_path:
        logger.error(f"status_code=404, Missing netcdf path {orig_netcdf_path}")
        raise HTTPError(response_code='404', response="Missing netcdf path")

    # Read all variables names from the netcdf file.
    is_ncml = False
    last_ds_disk = None
    try:
        ds_disk = xr.open_dataset(netcdf_path, mask_and_scale=False)
    except ValueError:
        try:
            if netcdf_path.endswith('ncml'):
                netcdf_files = _read_netcdfs_from_ncml(netcdf_path)
                ds_disk = xr.open_dataset(netcdf_files[0], mask_and_scale=False)
                last_ds_disk = xr.open_dataset(netcdf_files[-1], mask_and_scale=False)
                # import xncml
                # ds_disk = xncml.open_ncml("./output.xml")
                is_ncml = True
        except Exception as e:
            logger.error(f"status_code=500, Can not open file. Either not existing or ncml file: {e}")
            raise HTTPError(response_code='500 Internal Server Error', response=f"Can not open file. Either not existing or ncml file: {e}")
    except FileNotFoundError:
        logger.error(f"status_code=500, File Not Found: {netcdf_path}.")
        raise HTTPError(response_code='500 Internal Server Error', response=f"File Not Found: {orig_netcdf_path}.")

    #get forecast reference time from dataset
    try:
        if is_ncml:
            try:
                if len(ds_disk['forecast_reference_time'].data) > 1:
                    if ds_disk['forecast_reference_time'].attrs['units'] == 'seconds since 1970-01-01 00:00:00 +00:00':
                        forecast_time = datetime.timedelta(seconds=ds_disk['forecast_reference_time'].data[0]) + datetime.datetime(1970,1,1)
                    else:
                        logger.error(f"status_code=500, This unit is not implemented: {ds_disk['forecast_reference_time'].attrs['units']}.")
                        raise HTTPError(response_code='500', response=f"This unit is not implemented: {ds_disk['forecast_reference_time'].attrs['units']}")
            except TypeError as te:
                forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
            try:
                logger.debug(f"{ds_disk['time'].dt}")
            except (TypeError, AttributeError):
                if ds_disk['time'].attrs['units'] == 'seconds since 1970-01-01 00:00:00 +00:00':
                    ds_disk['time'] = pandas.TimedeltaIndex(ds_disk['time'], unit='s') + datetime.datetime(1970, 1, 1)
                    ds_disk['time'] = pandas.to_datetime(ds_disk['time'])
                else:
                    logger.error(f"status_code=500, This unit is not implemented: {ds_disk['time'].attrs['units']}.")
                    raise HTTPError(response_code='500', response=f"This unit is not implemented: {ds_disk['time'].attrs['units']}")

        else:
            forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
    except KeyError:
        try:
            logger.debug("Could not find forecast time or analysis time from dataset. Try parse from filename.")
            # Parse the netcdf filename to get start time or reference time
            _, _forecast_time = _parse_filename(netcdf_path, product_config)
            forecast_time = datetime.datetime.strptime(_forecast_time, "%Y%m%dT%H")
            logger.debug(f"{forecast_time}")
        except ValueError:
            logger.debug("Could not find any forecast_reference_time. Try use time_coverage_start.")
            try:
                forecast_time = datetime.datetime.fromisoformat(ds_disk.time_coverage_start)
                logger.debug(f"{forecast_time}")
            except Exception as ex:
                logger.debug(f"Could not find any forecast_reference_time. Use now. Last unhandled exception: {str(ex)}")
                forecast_time = datetime.datetime.now()

    symbol_file = os.path.join(_get_mapfiles_path(product_config), "symbol.sym")
    create_symbol_file(symbol_file)
 
    qp = _parse_request(query_string)

    layer_no = 0
    map_object = None
    actual_variable = None
    if 'request' in qp and qp['request'] != 'GetCapabilities':
        mapserver_map_file = os.path.join(_get_mapfiles_path(product_config), f'{os.path.basename(orig_netcdf_path)}.map')
        map_object = mapscript.mapObj()
        _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, url_scheme, http_host, ds_disk, summary_cache, "Generic netcdf WMS")
        map_object.setSymbolSet(symbol_file)
        layer = mapscript.layerObj()
        actual_variable = _generate_layer(layer, ds_disk, grid_mapping_cache, netcdf_path, qp, map_object, product_config, wind_rotation_cache, last_ds_disk)
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
            _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, url_scheme, http_host, ds_disk, summary_cache, "Generic netcdf WMS")
            map_object.setSymbolSet(symbol_file)
            # Read all variables names from the netcdf file.
            variables = list(ds_disk.keys())
            netcdf_files = []
            if netcdf_path.endswith('ncml'):
                netcdf_files = _read_netcdfs_from_ncml(netcdf_path)
            for variable in variables:
                if variable in ['longitude', 'latitude', 'forecast_reference_time', 'projection_lambert', 'p0', 'ap', 'b']:
                    logger.debug(f"Skipping variable or dimension: {variable}")
                    continue
                layer = mapscript.layerObj()
                if _generate_getcapabilities(layer, ds_disk, variable, grid_mapping_cache, netcdf_path, last_ds_disk, netcdf_files, product_config):
                    layer_no = map_object.insertLayer(layer)
                if variable.startswith('x_wind') and variable.replace('x', 'y') in variables:
                    logger.debug(f"Add wind vector layer for {variable}.")
                    layer_contour = mapscript.layerObj()
                    if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path, direction_speed=False, last_ds=last_ds_disk, netcdf_files=netcdf_files, product_config=product_config):
                        layer_no = map_object.insertLayer(layer_contour)
                if variable == 'wind_direction' and 'wind_speed' in variables:
                    logger.debug(f"Add wind vector layer based on wind direction and speed for {variable}.")
                    layer_contour = mapscript.layerObj()
                    if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path, direction_speed=True, last_ds=last_ds_disk, netcdf_files=netcdf_files, product_config=product_config):
                        layer_no = map_object.insertLayer(layer_contour)

    if layer_no == 0 and not map_object:
        logger.debug(f"No layers {layer_no} or no map_object {map_object}")
        logger.error(f"status_code=500, Could not find any variables to turn into OGC WMS layers. One "
                     "reason can be your data does not have a valid grid_mapping (Please see CF "
                     "grid_mapping), or internal resampling failed.")
        raise HTTPError(response_code='500 Internal Server Error', response=("Could not find any variables to turn into OGC WMS layers. One reason can be your data does "
                                                     "not have a valid grid_mapping (Please see CF grid_mapping), or internal resampling failed."))

    map_object.save(os.path.join(_get_mapfiles_path(product_config), f'generic-{forecast_time:%Y%m%d%H%M%S}.map'))

    # Handle the request and return results.
    return handle_request(map_object, query_string)
