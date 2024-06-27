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
import os
#import glob
import time
import pandas
import logging
#import shutil
import datetime
import mapscript
from fastapi import Request, Query, HTTPException, BackgroundTasks
import xarray as xr
from mapgen.modules.create_symbol_file import create_symbol_file
from mapgen.modules.helpers import handle_request, _parse_filename, _get_mapfiles_path, _fill_metadata_to_mapfile
from mapgen.modules.helpers import _generate_getcapabilities, _generate_getcapabilities_vector, _generate_layer
from mapgen.modules.helpers import _parse_request

grid_mapping_cache = {}
wind_rotation_cache = {}
summary_cache = {}

logger = logging.getLogger(__name__)

# def _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, full_request, xr_dataset):
#     """"Add all needed web metadata to the generated map file."""
#     bn = os.path.basename(orig_netcdf_path)
#     if bn not in summary_cache:
#         summary = _find_summary_from_csw(bn, forecast_time, full_request)
#         if summary:
#             summary_cache[bn] = summary
#             logger.debug(f"{summary_cache[bn]}")
#         else:
#             summary_cache[bn] = "Arome Arctic"
#     map_object.web.metadata.set("wms_abstract", summary_cache[bn])
#     map_object.web.metadata.set("wms_title", "WMS Arome Arctic")
#     map_object.web.metadata.set("wms_onlineresource", f"{full_request.url.scheme}://{full_request.url.netloc}/api/get_quicklook{orig_netcdf_path}")
#     map_object.web.metadata.set("wms_srs", "EPSG:25833 EPSG:3978 EPSG:4326 EPSG:4269 EPSG:3857 EPSG:32661")
#     map_object.web.metadata.set("wms_enable_request", "*")
#     map_object.setProjection("AUTO")
#     if xr_dataset.dims['x'] and xr_dataset.dims['y']:
#         map_object.setSize(xr_dataset.dims['x'], xr_dataset.dims['y'])
#     else:
#         map_object.setSize(2000, 2000)
#     map_object.units = mapscript.MS_DD
#     map_object.setExtent(float(xr_dataset.attrs['geospatial_lon_min']),
#                          float(xr_dataset.attrs['geospatial_lat_min']),
#                          float(xr_dataset.attrs['geospatial_lon_max']),
#                          float(xr_dataset.attrs['geospatial_lat_max']))
#     return

# def _generate_getcapabilities(layer, ds, variable, grid_mapping_cache, netcdf_file):
#     """Generate getcapabilities for the netcdf file."""
#     grid_mapping_name = _find_projection(ds, variable, grid_mapping_cache)
#     if not grid_mapping_name:
#         return None
#     layer.setProjection(grid_mapping_cache[grid_mapping_name])
#     layer.status = 1
#     layer.data = f'NETCDF:{netcdf_file}:{variable}'
#     layer.type = mapscript.MS_LAYER_RASTER
#     layer.name = variable
#     layer.metadata.set("wms_title", variable)

#     ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)
#     layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
#     dims_list = []
#     for dim_name in ds[variable].dims:
#         if dim_name in ['x', 'y']:
#             continue
#         if dim_name in 'time':
#             #logger.debug(f"handle time")
#             diff, is_range = find_time_diff(ds, dim_name)
#             if is_range:
#                 diff_string = 'PT1H'
#                 if diff == datetime.timedelta(hours=1):
#                     diff_string = "PT1H"
#                 elif diff == datetime.timedelta(hours=3):
#                     diff_string = "PT3H"
#                 elif diff == datetime.timedelta(hours=6):
#                     diff_string = "PT6H"
#                 elif diff == datetime.timedelta(hours=12):
#                     diff_string = "PT12H"
#                 elif diff == datetime.timedelta(hours=24):
#                     diff_string = "PT24H"
#                 else:
#                     logger.debug(f"Do not understand this time interval: {diff}. Assume {diff_string}.")
#                 start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
#                 end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
#                 layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
#             else:
#                 logger.debug(f"time list not implemented.")
#             layer.metadata.set("wms_default", f'{start_time}')
#         else:
#             if ds[dim_name].data.size > 1:
#                 #logger.debug(f"add dimension {dim_name} for variable {variable}.")
#                 dims_list.append(dim_name)
#                 layer.metadata.set(f"wms_{dim_name}_item", dim_name)
#                 try:
#                     layer.metadata.set(f"wms_{dim_name}_units", ds[dim_name].attrs['units'])
#                 except KeyError:
#                     layer.metadata.set(f"wms_{dim_name}_units", '1')
#                 layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[dim_name].data]))
#                 layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[dim_name].data)))
#             # else:
#             #     logger.debug(f"Skipping dimension {dim_name} due to one size dimmension.")

#     if dims_list:
#         layer.metadata.set(f"wms_dimensionlist", ','.join(dims_list))

#     #layer.labelitem = 'contour'
#     s = mapscript.classObj(layer)
#     s.name = "contour"
#     s.group = "contour"
#     style = mapscript.styleObj(s)
#     style.rangeitem = 'pixel'
#     style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
#     style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
#     # style.width = 1
#     # style.color = mapscript.colorObj(red=0, green=0, blue=255)

#     s1 = mapscript.classObj(layer)
#     s1.name = "Linear grayscale using min and max not nan from data"
#     s1.group = 'raster'
#     style1 = mapscript.styleObj(s1)
#     style1.rangeitem = 'pixel'
#     style1.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
#     style1.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
#     #style.minvalue = float(min_val)
#     #style.maxvalue = float(max_val)

#     return True

# def _generate_getcapabilities_vector(layer, ds, variable, grid_mapping_cache, netcdf_file):
#     """Generate getcapabilities for vector fiels for the netcdf file."""
#     logger.debug(f"ADDING vector")
#     grid_mapping_name = _find_projection(ds, variable, grid_mapping_cache)
#     if not grid_mapping_name:
#         return None
#     layer.setProjection(grid_mapping_cache[grid_mapping_name])
#     layer.status = 1
#     if variable.startswith('x_wind'):
#         x_variable = variable
#         y_variable = x_variable.replace('x', 'y')
#         vector_variable_name = '_'.join(variable.split("_")[1:])
#     layer.data = f'NETCDF:{netcdf_file}:{variable}'
#     layer.type = mapscript.MS_LAYER_LINE
#     layer.name = f'{vector_variable_name}_vector'
#     layer.metadata.set("wms_title", f'{vector_variable_name}')
#     layer.setConnectionType(mapscript.MS_CONTOUR, "")
#     ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)
#     layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
#     dims_list = []
#     for dim_name in ds[variable].dims:
#         if dim_name in ['x', 'y']:
#             continue
#         if dim_name in 'time':
#             logger.debug(f"handle time")
#             diff, is_range = find_time_diff(ds, dim_name)
#             if is_range:
#                 diff_string = 'PT1H'
#                 if diff == datetime.timedelta(hours=1):
#                     diff_string = "PT1H"
#                 elif diff == datetime.timedelta(hours=3):
#                     diff_string = "PT3H"
#                 elif diff == datetime.timedelta(hours=6):
#                     diff_string = "PT6H"
#                 elif diff == datetime.timedelta(hours=12):
#                     diff_string = "PT12H"
#                 elif diff == datetime.timedelta(hours=24):
#                     diff_string = "PT24H"
#                 else:
#                     logger.debug(f"Do not understand this time interval: {diff}. Assume {diff_string}.")
#                 start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
#                 end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
#                 layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
#             else:
#                 logger.debug(f"time list not implemented.")
#             layer.metadata.set("wms_default", f'{start_time}')
#         else:
#             if ds[dim_name].data.size > 1:
#                 dims_list.append(dim_name)
#                 layer.metadata.set(f"wms_{dim_name}_item", dim_name)
#                 try:
#                     layer.metadata.set(f"wms_{dim_name}_units", ds[dim_name].attrs['units'])
#                 except KeyError:
#                     layer.metadata.set(f"wms_{dim_name}_units", '1')
#                 layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[dim_name].data]))
#                 layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[dim_name].data)))
#     # Extra dimmensions to handle styling
#     extra_dimmensions = []
#     extra_dimmensions.append({'item': 'Spacing', 'units': 'pixels', 'extent': [2,4,8,12,16,24,32], 'default': 12})
#     extra_dimmensions.append({'item': 'Colour', 'units': '', 'extent': ['blue', 'red', 'green', 'cyan', 'magenta', 'yellow','light-green'],
#                               'default': 'light-green'})
#     for ed in extra_dimmensions:
#         dims_list.append(ed['item'])
#         layer.metadata.set(f"wms_{ed['item']}_item", ed['item'])
#         layer.metadata.set(f"wms_{ed['item']}_units", ed['units'])
#         layer.metadata.set(f"wms_{ed['item']}_extent", ','.join([str(d) for d in ed['extent']]))
#         layer.metadata.set(f"wms_{ed['item']}_default", str(ed['default']))

#     if dims_list:
#         layer.metadata.set(f"wms_dimensionlist", ','.join(dims_list))

#     s = mapscript.classObj(layer)
#     s.name = "Vector"
#     s.group = "Vector"
#     style = mapscript.styleObj(s)
#     style.rangeitem = 'pixel'
#     style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
#     style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)

#     s1 = mapscript.classObj(layer)
#     s1.name = "Wind_Barbs"
#     s1.group = 'Wind_Barbs'
#     style1 = mapscript.styleObj(s1)
#     style1.rangeitem = 'pixel'
#     style1.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
#     style1.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)

#     logger.debug(f"ADDing vector at end")

#     return True

async def arome_arctic_quicklook(netcdf_path: str,
                           full_request: Request,
                           background_task: BackgroundTasks,
                           products: list = Query(default=[]),
                           product_config: dict = {}):
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        logger.error(f"status_code=500, Missing base dir in server config.")
        raise HTTPException(status_code=500, detail="Missing base dir in server config.")

    if not netcdf_path:
        logger.error(f"status_code=404, Missing netcdf path")
        raise HTTPException(status_code=404, detail="Missing netcdf path")
    if not os.path.exists(netcdf_path):
        logger.error(f"status_code=404, Could not find {orig_netcdf_path} in server configured directory.")
        raise HTTPException(status_code=404, detail=f"Could not find {orig_netcdf_path} in server configured directory.")

    ds_disk = xr.open_dataset(netcdf_path)

    #get forecast reference time from dataset
    try:
        forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
    except KeyError:
        logger.debug(f"Could not find forecast time or analysis time from dataset. Try parse from filename.")
        # Parse the netcdf filename to get start time or reference time
        _, _forecast_time = _parse_filename(netcdf_path, product_config)
        forecast_time = datetime.datetime.strptime(_forecast_time, "%Y%m%dT%H")
        logger.debug(f"{forecast_time}")

    # logger.debug(f"{variables}")
    # Loop over all variable names to add layer for each variable including needed dimmensions.
    #   Time
    #   Height
    #   Pressure
    #   Other dimensions
    # Add this to some data structure.
    # Pass this data structure to mapscript to create an in memory config for mapserver/mapscript

    symbol_file = os.path.join(_get_mapfiles_path(product_config), "symbol.sym")
    create_symbol_file(symbol_file)
    qp = _parse_request(full_request)

    map_object = None
    actual_variable = None
    if 'request' in qp and qp['request'] != 'GetCapabilities':
        mapserver_map_file = os.path.join(_get_mapfiles_path(product_config), f'{os.path.basename(orig_netcdf_path)}.map')
        map_object = mapscript.mapObj()
        _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, full_request, ds_disk, summary_cache, "WMS Arome Arctic.")
        map_object.setSymbolSet(symbol_file)
        layer = mapscript.layerObj()
        actual_variable = await _generate_layer(layer, ds_disk, grid_mapping_cache, netcdf_path, qp, map_object, product_config, wind_rotation_cache)
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
            _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, full_request, ds_disk, summary_cache, "WMS Arome Arctic")
            map_object.setSymbolSet(symbol_file)
            # Read all variables names from the netcdf file.
            variables = list(ds_disk.keys())
            for variable in variables:
                layer = mapscript.layerObj()
                if _generate_getcapabilities(layer, ds_disk, variable, grid_mapping_cache, netcdf_path):
                    layer_no = map_object.insertLayer(layer)
                if variable.startswith('x_wind') and variable.replace('x', 'y') in variables:
                    logger.debug(f"Add wind vector layer for {variable}.")
                    layer_contour = mapscript.layerObj()
                    if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path):
                        layer_no = map_object.insertLayer(layer_contour)

    map_object.save(mapserver_map_file)

    ds_disk.close()
    # add background task
    background_task.add_task(clean_data, map_object, actual_variable)
    # Handle the request and return results.
    return await handle_request(map_object, full_request)

async def clean_data(map_object, actual_variable):
    logger.debug(f"I need to clean some data to avoid memory stash: {actual_variable}")
    try:
        for layer in range(map_object.numlayers):
            try:
                for cls in range(map_object.getLayer(0).numclasses):
                    try:
                        for sty in range(map_object.getLayer(0).getClass(0).numstyles):
                            ref = map_object.getLayer(0).getClass(0).removeStyle(0)
                            del ref
                            ref = None
                    except AttributeError:
                        pass
                    ref = map_object.getLayer(0).removeClass(0)
                    del ref
                    ref = None
            except AttributeError:
                pass
            ref = map_object.removeLayer(0)
            del ref
            ref = None
        del map_object
        map_object = None
    except AttributeError:
        pass
