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
import re
import glob
#import time
import hashlib
import pandas
import shutil
import datetime
import tempfile
import mapscript
from fastapi import Request, Query, HTTPException
import numpy as np
import xarray as xr
from osgeo import gdal
from pyproj import CRS
from mapgen.modules.helpers import handle_request, _get_from_direction, _get_north, _get_speed, _rotate_relative_to_north, _get_crs

grid_mapping_cache = {}
wind_rotation_cache = {}

def _fill_metadata_to_mapfile(orig_netcdf_path, map_object, full_request, xr_dataset):
    """"Add all needed web metadata to the generated map file."""
    map_object.web.metadata.set("wms_title", "WMS Arome Arctic")
    map_object.web.metadata.set("wms_onlineresource", f"{full_request.url.scheme}://{full_request.url.netloc}/api/get_quicklook{orig_netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:25833 EPSG:3978 EPSG:4326 EPSG:4269 EPSG:3857 EPSG:32661")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")
    if xr_dataset.dims['x'] and xr_dataset.dims['y']:
        map_object.setSize(xr_dataset.dims['x'], xr_dataset.dims['y'])
    else:
        map_object.setSize(2000, 2000)
    map_object.units = mapscript.MS_DD
    map_object.setExtent(float(xr_dataset.attrs['geospatial_lon_min']),
                         float(xr_dataset.attrs['geospatial_lat_min']),
                         float(xr_dataset.attrs['geospatial_lon_max']),
                         float(xr_dataset.attrs['geospatial_lat_max']))
    return

def _find_projection(ds, variable):
    # Find projection
    try:
        grid_mapping_name = ds[variable].attrs['grid_mapping']
        if grid_mapping_name not in grid_mapping_cache:
            cs = CRS.from_cf(ds[ds[variable].attrs['grid_mapping']].attrs)
            grid_mapping_cache[grid_mapping_name] = cs.to_proj4()
    except KeyError:
        print(f"no grid_mapping for variable {variable}. Skipping this.")
        return None
    return grid_mapping_name

def _generate_getcapabilities(layer, ds, variable, grid_mapping_cache, netcdf_file):
    """Generate getcapabilities for the netcdf file."""
    grid_mapping_name = _find_projection(ds, variable)
    if not grid_mapping_name:
        return None
    layer.setProjection(grid_mapping_cache[grid_mapping_name])
    layer.status = 1
    layer.data = f'NETCDF:{netcdf_file}:{variable}'
    layer.type = mapscript.MS_LAYER_RASTER
    layer.name = variable
    layer.metadata.set("wms_title", variable)

    ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
    dims_list = []
    for dim_name in ds[variable].dims:
        if dim_name in ['x', 'y']:
            continue
        if dim_name in 'time':
            #print("handle time")
            diff, is_range = find_time_diff(ds, dim_name)
            if is_range:
                diff_string = 'PT1H'
                if diff == datetime.timedelta(hours=1):
                    diff_string = "PT1H"
                elif diff == datetime.timedelta(hours=3):
                    diff_string = "PT3H"
                elif diff == datetime.timedelta(hours=6):
                    diff_string = "PT6H"
                elif diff == datetime.timedelta(hours=12):
                    diff_string = "PT12H"
                elif diff == datetime.timedelta(hours=24):
                    diff_string = "PT24H"
                else:
                    print(f"Do not understand this time interval: {diff}. Assume {diff_string}.")
                start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
            else:
                print("time list not implemented.")
            layer.metadata.set("wms_default", f'{start_time}')
        else:
            if ds[dim_name].data.size > 1:
                #print(f"add dimension {dim_name} for variable {variable}.")
                dims_list.append(dim_name)
                layer.metadata.set(f"wms_{dim_name}_item", dim_name)
                try:
                    layer.metadata.set(f"wms_{dim_name}_units", ds[dim_name].attrs['units'])
                except KeyError:
                    layer.metadata.set(f"wms_{dim_name}_units", '1')
                layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[dim_name].data]))
                layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[dim_name].data)))
            # else:
            #     print(f"Skipping dimension {dim_name} due to one size dimmension.")

    if dims_list:
        layer.metadata.set(f"wms_dimensionlist", ','.join(dims_list))

    #layer.labelitem = 'contour'
    s = mapscript.classObj(layer)
    s.name = "contour"
    s.group = "contour"
    style = mapscript.styleObj(s)
    style.rangeitem = 'pixel'
    style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
    style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
    # style.width = 1
    # style.color = mapscript.colorObj(red=0, green=0, blue=255)

    s1 = mapscript.classObj(layer)
    s1.name = "Linear grayscale using min and max not nan from data"
    s1.group = 'raster'
    style1 = mapscript.styleObj(s1)
    style1.rangeitem = 'pixel'
    style1.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
    style1.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
    #style.minvalue = float(min_val)
    #style.maxvalue = float(max_val)

    return True

def _generate_getcapabilities_vector(layer, ds, variable, grid_mapping_cache, netcdf_file):
    """Generate getcapabilities for vector fiels for the netcdf file."""
    print("ADDING vector")
    grid_mapping_name = _find_projection(ds, variable)
    if not grid_mapping_name:
        return None
    layer.setProjection(grid_mapping_cache[grid_mapping_name])
    layer.status = 1
    if variable.startswith('x_wind'):
        x_variable = variable
        y_variable = x_variable.replace('x', 'y')
        vector_variable_name = '_'.join(variable.split("_")[1:])
    layer.data = f'NETCDF:{netcdf_file}:{variable}'
    layer.type = mapscript.MS_LAYER_LINE
    layer.name = f'{vector_variable_name}_vector'
    layer.metadata.set("wms_title", f'{vector_variable_name}')
    layer.setConnectionType(mapscript.MS_CONTOUR, "")
    ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
    dims_list = []
    for dim_name in ds[variable].dims:
        if dim_name in ['x', 'y']:
            continue
        if dim_name in 'time':
            print("handle time")
            diff, is_range = find_time_diff(ds, dim_name)
            if is_range:
                diff_string = 'PT1H'
                if diff == datetime.timedelta(hours=1):
                    diff_string = "PT1H"
                elif diff == datetime.timedelta(hours=3):
                    diff_string = "PT3H"
                elif diff == datetime.timedelta(hours=6):
                    diff_string = "PT6H"
                elif diff == datetime.timedelta(hours=12):
                    diff_string = "PT12H"
                elif diff == datetime.timedelta(hours=24):
                    diff_string = "PT24H"
                else:
                    print(f"Do not understand this time interval: {diff}. Assume {diff_string}.")
                start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
            else:
                print("time list not implemented.")
            layer.metadata.set("wms_default", f'{start_time}')
        else:
            if ds[dim_name].data.size > 1:
                dims_list.append(dim_name)
                layer.metadata.set(f"wms_{dim_name}_item", dim_name)
                try:
                    layer.metadata.set(f"wms_{dim_name}_units", ds[dim_name].attrs['units'])
                except KeyError:
                    layer.metadata.set(f"wms_{dim_name}_units", '1')
                layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[dim_name].data]))
                layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[dim_name].data)))
    # Extra dimmensions to handle styling
    extra_dimmensions = []
    extra_dimmensions.append({'item': 'Spacing', 'units': 'pixels', 'extent': [2,4,8,12,16,24,32], 'default': 12})
    extra_dimmensions.append({'item': 'Colour', 'units': '', 'extent': ['blue', 'red', 'green', 'cyan', 'magenta', 'yellow','light-green'],
                              'default': 'light-green'})
    for ed in extra_dimmensions:
        dims_list.append(ed['item'])
        layer.metadata.set(f"wms_{ed['item']}_item", ed['item'])
        layer.metadata.set(f"wms_{ed['item']}_units", ed['units'])
        layer.metadata.set(f"wms_{ed['item']}_extent", ','.join([str(d) for d in ed['extent']]))
        layer.metadata.set(f"wms_{ed['item']}_default", str(ed['default']))

    if dims_list:
        layer.metadata.set(f"wms_dimensionlist", ','.join(dims_list))

    s = mapscript.classObj(layer)
    s.name = "Vector"
    s.group = "Vector"
    style = mapscript.styleObj(s)
    style.rangeitem = 'pixel'
    style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
    style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)

    s1 = mapscript.classObj(layer)
    s1.name = "Wind_Barbs"
    s1.group = 'Wind_Barbs'
    style1 = mapscript.styleObj(s1)
    style1.rangeitem = 'pixel'
    style1.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
    style1.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)

    print("ADDing vector at end")

    return True

def _extract_extent(ds, variable):
    ll_x = min(ds[variable].coords['x'].data)
    ur_x = max(ds[variable].coords['x'].data)
    ll_y = min(ds[variable].coords['y'].data)
    ur_y = max(ds[variable].coords['y'].data)
    return ll_x,ur_x,ll_y,ur_y

def find_time_diff(ds, dim_name):
    prev = None
    diff = None
    prev_diff = None
    is_range = True
    for y,m,d,h,minute,s in zip(ds[dim_name].dt.year.data, ds[dim_name].dt.month.data, ds[dim_name].dt.day.data, ds[dim_name].dt.hour.data, ds[dim_name].dt.minute.data, ds[dim_name].dt.second.data):
        stamp = datetime.datetime(y, m, d, h, minute, s)
        if prev:
            diff = stamp - prev
            if prev_diff and diff != prev_diff:
                is_range = False
                break
            prev_diff = diff
        prev = stamp
    return diff,is_range

def _find_dimensions(ds, actual_variable, variable, qp):
    # Find available dimension not larger than 1
    dimension_search = []
    for dim_name in ds[actual_variable].dims:
        if dim_name in ['x', 'y']:
            continue
        for _dim_name in [dim_name,f'dim_{dim_name}']:
            print(f"search for dim_name {_dim_name} in query parameters.")
            if _dim_name in qp:
                print(f"Found dimension {_dim_name} in request")
                if dim_name == 'time':
                    _ds = {}
                    _ds['dim_name'] = dim_name
                    _ds['ds_size'] = ds[dim_name].data.size
                    requested_dimensions = datetime.datetime.strptime(qp[_dim_name], "%Y-%m-%dT%H:%M:%SZ")
                    time_as_band = 0
                    for d in ds['time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ'):
                        print(f"Checking {time_as_band} {datetime.datetime.strptime(str(d.data), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp()} {d.data} {requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ')}")
                        if d == requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ'):
                            print(d,requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ'), requested_dimensions.timestamp())
                            break
                        time_as_band += 1
                    else:
                        print("could not find a mathcing dimension value.")
                        raise HTTPException(status_code=500, detail=f"Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                    _ds['selected_band_number'] = time_as_band
                    dimension_search.append(_ds)
                else:
                    print(f"other dimension {dim_name}")
                    _ds = {}
                    _ds['dim_name'] = dim_name
                    _ds['ds_size'] = ds[dim_name].data.size
                    selected_band_no = 0
                    for d in ds[dim_name].data:
                        print(f"compare dim value {d} to req value {qp[_dim_name]}")
                        if float(d) == float(qp[_dim_name]):
                            break
                        selected_band_no += 1
                    else:
                        print("could not find a mathcing dimension value.")
                        raise HTTPException(status_code=500, detail=f"Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                    _ds['selected_band_number'] = selected_band_no
                    dimension_search.append(_ds)
                break
            else:
                if ds[dim_name].data.size == 1:
                    print(f"Dimension with size 0 {dim_name}")
                    _ds = {}
                    _ds['dim_name'] = dim_name
                    _ds['ds_size'] = ds[dim_name].data.size
                    _ds['selected_band_number'] = 0
                    dimension_search.append(_ds)
                    break
        else:
            print(f"Could not find {_dim_name}. Make some ugly assumption")
            _ds = {}
            _ds['dim_name'] = dim_name
            _ds['ds_size'] = ds[dim_name].data.size
            _ds['selected_band_number'] = 0
            dimension_search.append(_ds)
    print(dimension_search)
    return dimension_search

def _calc_band_number_from_dimensions(dimension_search):
    band_number = 0
    first = True
    #dimension_search.reverse()
    for _ds in dimension_search[::-1]:
        if first:
            band_number += _ds['selected_band_number'] + 1
        else:
            band_number += _ds['selected_band_number']*prev_ds['ds_size']
        first = False
        prev_ds = _ds

    print(f"selected band number {band_number}")
    return band_number

def _add_wind_barb(map_obj, layer, colour_tripplet, min, max):
    s = mapscript.classObj(layer)
    min_ms = min/1.94384449
    max_ms = max/1.94384449
    s.setExpression(f'([uv_length]>={min_ms} and [uv_length]<{max_ms})')
    # Wind barbs
    style = mapscript.styleObj(s)
    style.updateFromString(f'STYLE SYMBOL "wind_barb_{min+2}" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} OUTLINECOLOR {colour_tripplet} END')
    style.setSymbolByName(map_obj, f"wind_barb_{min+2}")
    return

# def _add_wind_barb_line_flag(map_obj, layer, colour_tripplet, min, max):
#     s = mapscript.classObj(layer)
#     s.setExpression(f'([uv_length]>{min} and [uv_length]<={max})')

#     style_flag = mapscript.styleObj(s)
#     style_flag.updateFromString(f'STYLE SYMBOL "wind_barb_flag_{max}" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} END')
#     style_flag.setSymbolByName(map_obj, f"wind_barb_flag_{max}")

#     style_line = mapscript.styleObj(s)
#     style_line.updateFromString(f'STYLE SYMBOL "wind_barb_line_{max}" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} END')
#     style_line.setSymbolByName(map_obj, f"wind_barb_line_{max}")

#     return

def _generate_layer(layer, ds, grid_mapping_cache, netcdf_file, qp, map_obj, product_config):
    try:
        variable = qp['layer']
    except KeyError:
        variable = qp['layers']
    try:
        style = qp['styles']
    except KeyError:
        style = qp['style']
    if variable.endswith("_vector") and style == "":
        print("Empty style. Force wind barbs.")
        style = "Wind_barbs"
    elif style == "":
        print("Empty style. Force raster.")
        style = 'raster'
    print(f"Selected style: {style}")

    actual_variable = variable
    #if style in 'contour': #variable.endswith('_contour'):
    #    actual_variable = '_'.join(variable.split("_")[:-1])
    if variable.endswith('_vector'):
        actual_x_variable = '_'.join(['x'] + variable.split("_")[:-1])
        actual_y_variable = '_'.join(['y'] + variable.split("_")[:-1])
        vector_variable_name = variable
        actual_variable = actual_x_variable
        print("VECTOR", vector_variable_name, actual_x_variable, actual_y_variable)

    dimension_search = _find_dimensions(ds, actual_variable, variable, qp)
    band_number = _calc_band_number_from_dimensions(dimension_search)
    if variable.endswith('_vector'):
        layer.setProcessingKey('BANDS', f'1,2')
    else:
        layer.setProcessingKey('BANDS', f'{band_number}')

    grid_mapping_name = _find_projection(ds, actual_variable)
    layer.setProjection(grid_mapping_cache[grid_mapping_name])
    layer.status = 1
    if variable.endswith('_vector'):
        # actual_x_variable = 'x_wind_10m'
        # actual_y_variable = 'y_wind_10m'

        sel_dim = {}
        for _ds in dimension_search:
            sel_dim[_ds['dim_name']] = _ds['selected_band_number']
        # ts = time.time()
        # print("selected dimmensions:", sel_dim)
        ds = ds.isel(**sel_dim)
        # te = time.time()
        # print("isel ", te -ts)

        #ds = ds.sel(height7=1, method='nearest', drop=True)
        # print(ds.dims)
        #grid_mapping_name = ds['x_wind_10m'].attrs['grid_mapping']
        #grid_mapping = ds[grid_mapping_name]

        # ts = time.time()
        standard_name_prefix = 'wind'
        speed = _get_speed(
            ds[actual_x_variable],
            ds[actual_y_variable],
            f'{standard_name_prefix}_speed'
        )
        # te = time.time()
        # print("_get_speed ", te - ts)
        # ts = time.time()
        from_direction = _get_from_direction(
            ds[actual_x_variable],
            ds[actual_y_variable],
            f'{standard_name_prefix}_from_direction'
        )
        # te = time.time()
        # print("_from_direction ", te - ts)
        # ts = time.time()

        try:
            print("EPSG CRS:",qp['crs'])
            requested_epsg = int(qp['crs'].split(':')[-1])
        except KeyError:
            requested_epsg = 4326
        print(requested_epsg)
        # Rotate wind direction, so it relates to the north pole, rather than to the grid's y direction.
        unique_dataset_string = hashlib.md5((f"{requested_epsg}"
                                             f"{_get_crs(ds, actual_x_variable)}"
                                             f"{ds['x'].data.size}"
                                             f"{ds['y'].data.size}"
                                             f"{ds['x'][0].data}"
                                             f"{ds['x'][-1].data}"
                                             f"{ds['y'][0].data}"
                                             f"{ds['y'][-1].data}").encode('UTF-8')).hexdigest()
        print("UNIQUE DS STRING", unique_dataset_string)
        if unique_dataset_string in wind_rotation_cache:
            north = wind_rotation_cache[unique_dataset_string]
        else:
            north = _get_north(actual_x_variable, ds, requested_epsg)
            wind_rotation_cache[unique_dataset_string] = north
        # north = _get_north(actual_x_variable, ds, requested_epsg)
        # te = time.time()
        # print("_get_north ", te - ts) 
        # ts = time.time()
        _rotate_relative_to_north(from_direction, north)
        # te = time.time()
        # print("_relative_to_north ", te - ts)
        # ts = time.time()

        #print("from direction", from_direction)
        new_x = np.cos((90. - from_direction - 180) * np.pi/180) * speed
        new_y = np.sin((90. - from_direction - 180) * np.pi/180) * speed
        new_x.attrs['grid_mapping'] = ds[actual_x_variable].attrs['grid_mapping']
        new_y.attrs['grid_mapping'] = ds[actual_y_variable].attrs['grid_mapping']
        #print("Newx:", new_x)
        ds_xy = xr.Dataset({})
        ds_xy[new_x.attrs['grid_mapping']] = ds[new_x.attrs['grid_mapping']]
        ds_xy[actual_x_variable] = new_x.drop_vars(['latitude', 'longitude'])
        ds_xy[actual_y_variable] = new_y.drop_vars(['latitude', 'longitude'])
        # te = time.time()
        # print("new dataset ", te - ts)
        # ts = time.time()
        # print("GRid mapping", new_x.attrs['grid_mapping'])
        #ds_xy[new_x.attrs['grid_mapping']] = ds[new_x.attrs['grid_mapping']].drop_vars(['time', 'height7'])
        # print(ds_xy)
        # for netcdfs in glob.glob(os.path.join(_get_mapfiles_path(product_config), "netcdf-*")):
        #     shutil.rmtree(netcdfs)
        tmp_netcdf = os.path.join(tempfile.mkdtemp(prefix='netcdf-', dir=_get_mapfiles_path(product_config)),
                                  f"xy-{actual_x_variable}-{actual_y_variable}.nc")
        ds_xy.to_netcdf(tmp_netcdf)
        # for vrts in glob.glob(os.path.join(_get_mapfiles_path(product_config), "vrt-*")):
        #     shutil.rmtree(vrts)

        # xvar_vrt_filename = tempfile.mkstemp(suffix=".vrt",
        #                                      prefix=f'xvar-{actual_x_variable}-1-',
        #                                      dir=_get_mapfiles_path(product_config))
        xvar_vrt_filename = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f"xvar-{actual_x_variable}-1.vrt")
        gdal.BuildVRT(xvar_vrt_filename,
                    [f'NETCDF:{tmp_netcdf}:{actual_x_variable}'],
                    **{'bandList': [1]})
        # yvar_vrt_filename = tempfile.mkstemp(suffix=".vrt",
        #                                      prefix=f'yvar-{actual_x_variable}-1-',
        #                                      dir=_get_mapfiles_path(product_config))
        yvar_vrt_filename = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f"yvar-{actual_y_variable}-1.vrt")
        gdal.BuildVRT(yvar_vrt_filename,
                    [f'NETCDF:{tmp_netcdf}:{actual_y_variable}'],
                    **{'bandList': [1]})
        # gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "xvar.vrt"),
        #             [f'NETCDF:{netcdf_file}:{actual_x_variable}'],
        #             **{'bandList': [band_number]})
        # gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "yvar.vrt"),
        #             [f'NETCDF:{netcdf_file}:{actual_y_variable}'],
        #             **{'bandList': [band_number]})

        # variable_file_vrt = tempfile.mkstemp(suffix=".vrt",
        #                                      prefix=f'var-{actual_x_variable}-{actual_y_variable}-{band_number}-',
        #                                      dir=_get_mapfiles_path(product_config))
        variable_file_vrt = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f'var-{actual_x_variable}-{actual_y_variable}-{band_number}.vrt')
        #variable_file_vrt = f'var-{actual_x_variable}-{actual_y_variable}-{band_number}.vrt'
        gdal.BuildVRT(variable_file_vrt,
                      [f'NETCDF:{tmp_netcdf}:{actual_x_variable}', f'NETCDF:{tmp_netcdf}:{actual_y_variable}'],
                     #[xvar_vrt_filename, yvar_vrt_filename],
                     **{'bandList': [1], 'separate': True})
        # te = time.time()
        # print("save and create vrts ", te - ts) 
        layer.data = variable_file_vrt
    else:
        layer.data = f'NETCDF:{netcdf_file}:{actual_variable}'

    if style in 'contour': #variable.endswith('_contour'):
        print("Style in contour for config")
        layer.type = mapscript.MS_LAYER_LINE
        layer.setConnectionType(mapscript.MS_CONTOUR, "")
        interval = 1000
        smoothsia = 1.
        try:
            if ds[actual_variable].attrs['units'] == 'Pa':
                interval = 500
                smoothsia = 0.25
            elif ds[actual_variable].attrs['units'] == 'K':
                interval = 2
                smoothsia = 0.25
            elif ds[actual_variable].attrs['units'] == '1' and 'relative_humidity' in actual_variable:
                interval = 0.1
                smoothsia = 0.25
            elif ds[actual_variable].attrs['units'] == '%':
                interval = 10
                smoothsia = 0.25
            elif ds[actual_variable].attrs['units'] == 'm/s':
                interval = 2.5
                smoothsia = 0.25
            else:
                print(f"Unknown unit: {ds[actual_variable].attrs['units']}. contour interval may be of for {actual_variable}.")
        except KeyError:
            pass
        layer.setProcessingKey('CONTOUR_INTERVAL', f'{interval}')
        layer.setProcessingKey('CONTOUR_ITEM', 'contour')
        layer.setGeomTransform(f'smoothsia(generalize([shape], {smoothsia}*[data_cellsize]))')
    elif variable.endswith('_vector'):
        layer.setConnectionType(mapscript.MS_UVRASTER, "")
        layer.type = mapscript.MS_LAYER_POINT
    else:
        layer.type = mapscript.MS_LAYER_RASTER
    layer.name = variable
    if variable.endswith('_vector'):
        layer.metadata.set("wms_title", '_'.join(variable.split("_")[:-1]))
    else:
        layer.metadata.set("wms_title", variable)
    ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, actual_variable)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")


    if variable.endswith('_vector'):
        # style.updateFromString('STYLE SYMBOL "horizline" ANGLE [uv_angle] SIZE [uv_length] WIDTH 3 COLOR 100 255 0 END')
        # style.setSymbolByName(map_obj, "horizline")
        colours_by_name = {}
        colours_by_name['light-green'] = "100 255 0"
        colours_by_name['blue'] = "0 0 255"
        colours_by_name['red'] = "255 0 0"
        colours_by_name['green'] = "0 255 0"
        colours_by_name['cyan'] = "0 255 255"
        colours_by_name['magenta'] = "255 0 255"
        colours_by_name['yellow'] = "255 255 0"
        try:
            colour_dimension = qp['colour']
        except KeyError:
            try:
                colour_dimension = qp['dim_colour']
            except KeyError:
                colour_dimension = 'light-green'

        if style.lower() == "wind_barbs":
            # Wind barbs
            layer.classitem = "uv_length"
            s = mapscript.classObj(layer)
            s.setExpression(f'([uv_length]<=2/1.94384449)')
            # Wind barbs CALM
            _style = mapscript.styleObj(s)
            _style.updateFromString(f'STYLE SYMBOL "wind_barb_0" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colours_by_name[colour_dimension]} OUTLINECOLOR {colours_by_name[colour_dimension]} END')
            _style.setSymbolByName(map_obj, f"wind_barb_0")

            for max_wind_barb_speed in range(8,58,5):
                min_wind_barb_speed = max_wind_barb_speed - 5
                _add_wind_barb(map_obj, layer, colours_by_name[colour_dimension], min_wind_barb_speed, max_wind_barb_speed)

        elif style.lower() == "vector":
            # Vectors
            s = mapscript.classObj(layer)
            _style = mapscript.styleObj(s)
            _style.updateFromString(f'STYLE SYMBOL "vector_arrow" ANGLE [uv_angle] SIZE [uv_length] WIDTH 3 COLOR {colours_by_name[colour_dimension]} END')
            _style.setSymbolByName(map_obj, "vector_arrow")
            #layer.setProcessingKey('UV_SIZE_SCALE', '2')
        else:
            print(f"Unknown style {style}. Check your request.")

        try:
            uv_spacing = qp['spacing']
        except KeyError:
            try:
                uv_spacing = qp['dim_spacing']
            except KeyError:
                uv_spacing = 12
        layer.setProcessingKey('UV_SPACING', str(uv_spacing)) #Default 32

        # #style.autoangle = "[uv_angle]"
        # style.angle = 43
        # #"[uv_angle]"
        #style.size = style.size*2
        # #"[uv_length]"
        # style.width = 3
        # style.color = mapscript.colorObj(red=100, green=255, blue=0)
    else:
        if len(dimension_search) == 1:
            print("Len 1")
            min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
            max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
        elif len(dimension_search) == 2:
            print("Len 2 of ", actual_variable)
            min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
            max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
        # Find which band
        elif len(dimension_search) == 3:
            print("Len 3")
            min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
            max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
        print("MIN:MAX ",min_val, max_val)
        #Grayscale
        s = mapscript.classObj(layer)
        if style in 'contour': #variable.endswith('_contour'):
            print("Style in contour for style setup.")
            layer.labelitem = 'contour'
            s.name = "contour"
            _style = mapscript.styleObj(s)
            _style.width = 1
            _style.color = mapscript.colorObj(red=0, green=0, blue=255)
            label = mapscript.labelObj()
            label_scaling = 1
            label_offset = 0
            try:
                if ds[actual_variable].attrs['units'] == 'Pa':
                    label_scaling = 100
                elif ds[actual_variable].attrs['units'] == 'K':
                    label_scaling = 1
                    label_offset = -273.15
                elif ds[actual_variable].attrs['units'] == '1' and 'relative_humidity' in actual_variable:
                    label_scaling = 0.01
                elif ds[actual_variable].attrs['units'] == '%':
                    label_scaling = 1
                elif ds[actual_variable].attrs['units'] == 'm/s':
                    label_scaling = 1
                else:
                    print(f"Unknown unit: {ds[actual_variable].attrs['units']}. Label scaling may be of for {actual_variable}.")
                print(f"Selected label scale {label_scaling} and offset {label_offset}")
            except KeyError:
                pass
            label.setText(f'(tostring(({label_offset}+[contour]/{label_scaling}),"%.0f"))')
            print(label.convertToString())
            label.color = mapscript.colorObj(red=0, green=0, blue=255)
            #label.font = 'sans'
            # TYPE truetype
            label.size = 10
            label.position = mapscript.MS_CC
            label.force = True
            label.angle = 0 #mapscript.MS_AUTO
            s.addLabel(label)
        elif style == 'raster':
            s.name = "Linear grayscale using min and max not nan from data"
            s.group = 'raster'
            _style = mapscript.styleObj(s)
            _style.rangeitem = 'pixel'
            _style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
            _style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
            _style.minvalue = float(min_val)
            _style.maxvalue = float(max_val)

    return True

def _parse_filename(netcdf_path, product_config):
    """Parse the netcdf to return start_time."""
    pattern_match = product_config['pattern']
    pattern = re.compile(pattern_match)
    mtchs = pattern.match(netcdf_path)
    if mtchs:
        print("Pattern match:", mtchs.groups())
        return mtchs.groups()
    else:
        print("No match: ", netcdf_path)
        raise HTTPException(status_code=500, detail=f"No file name match: {netcdf_path}, match string {pattern_match}.")

def _get_mapfiles_path(regexp_pattern_module):
    try:
        return regexp_pattern_module['mapfiles_path']
    except KeyError:
        return "./"

def arome_arctic_quicklook(netcdf_path: str,
                           full_request: Request,
                           products: list = Query(default=[]),
                           product_config: dict = {}):
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        raise HTTPException(status_code=500, detail="Missing base dir in server config.")

    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")
    if not os.path.exists(netcdf_path):
        raise HTTPException(status_code=404, detail=f"Could not find {orig_netcdf_path} in server configured directory.")

    ds_disk = xr.open_dataset(netcdf_path)

    #get forecast reference time from dataset
    try:
        forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
    except KeyError:
        print("Could not find forecast time or analysis time from dataset. Try parse from filename.")
        # Parse the netcdf filename to get start time or reference time
        _, _forecast_time = _parse_filename(netcdf_path, product_config)
        forecast_time = datetime.datetime.strptime(_forecast_time, "%Y%m%dT%H")
        print(forecast_time)

    # print(variables)
    # Loop over all variable names to add layer for each variable including needed dimmensions.
    #   Time
    #   Height
    #   Pressure
    #   Other dimensions
    # Add this to some data structure.
    # Pass this data structure to mapscript to create an in memory config for mapserver/mapscript
    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(orig_netcdf_path, map_object, full_request, ds_disk)

    symbol_file = os.path.join(_get_mapfiles_path(product_config), "symbol.sym")
    if not os.path.exists(symbol_file):
        symbol_obj = mapscript.symbolSetObj()
        symbol = mapscript.symbolObj("horizline")
        symbol.name = "horizline"
        symbol.type = mapscript.MS_SYMBOL_VECTOR
        po = mapscript.pointObj()
        po.setXY(0, 0)
        lo = mapscript.lineObj()
        lo.add(po)
        po.setXY(1, 0)
        lo.add(po)
        symbol.setPoints(lo)
        symbol_obj.appendSymbol(symbol)

        # Create vector arrow
        symbol_wa = mapscript.symbolObj("vector_arrow")
        symbol_wa.name = "vector_arrow"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(10,3))
        lo.add(mapscript.pointObj(6,6))
        lo.add(mapscript.pointObj(7,3.75))
        lo.add(mapscript.pointObj(0,3.75))
        lo.add(mapscript.pointObj(0,2.25))
        lo.add(mapscript.pointObj(7,2.25))
        lo.add(mapscript.pointObj(6,0))
        lo.add(mapscript.pointObj(10,3))
        symbol_wa.setPoints(lo)
        symbol_wa.anchorpoint_x = 1.
        symbol_wa.anchorpoint_y = 0.5
        symbol_wa.filled = True
        symbol_obj.appendSymbol(symbol_wa)

        # # Create wind barb 5 kn
        # symbol_wa = mapscript.symbolObj("wind_barb_5")
        # symbol_wa.name = "wind_barb_5"
        # symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        # lo = mapscript.lineObj()
        # lo.add(mapscript.pointObj(2,8.2))
        # lo.add(mapscript.pointObj(26,8.2))
        # lo.add(mapscript.pointObj(-99,-99))
        # lo.add(mapscript.pointObj(4,8.2))
        # lo.add(mapscript.pointObj(3,3.5))
        # symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        # symbol_wa.filled = False
        # symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 0 kn
        symbol_wa = mapscript.symbolObj("wind_barb_0")
        symbol_wa.name = "wind_barb_0"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 10 kn
        symbol_wa = mapscript.symbolObj("wind_barb_5")
        symbol_wa.name = "wind_barb_5"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(3,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)


        # Create wind barb 10 kn
        symbol_wa = mapscript.symbolObj("wind_barb_10")
        symbol_wa.name = "wind_barb_10"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)


        # Create wind barb 15 kn
        symbol_wa = mapscript.symbolObj("wind_barb_15")
        symbol_wa.name = "wind_barb_15"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(3,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 20 kn
        symbol_wa = mapscript.symbolObj("wind_barb_20")
        symbol_wa.name = "wind_barb_20"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 25 kn
        symbol_wa = mapscript.symbolObj("wind_barb_25")
        symbol_wa.name = "wind_barb_25"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(5,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 30 kn
        symbol_wa = mapscript.symbolObj("wind_barb_30")
        symbol_wa.name = "wind_barb_30"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 35 kn
        symbol_wa = mapscript.symbolObj("wind_barb_35")
        symbol_wa.name = "wind_barb_35"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(7,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 40 kn
        symbol_wa = mapscript.symbolObj("wind_barb_40")
        symbol_wa.name = "wind_barb_40"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 45 kn
        symbol_wa = mapscript.symbolObj("wind_barb_45")
        symbol_wa.name = "wind_barb_45"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(9,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # # Create wind barb line 50
        # symbol_wa = mapscript.symbolObj("wind_barb_line_50")
        # symbol_wa.name = "wind_barb_line_50"
        # symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        # lo = mapscript.lineObj()
        # lo.add(mapscript.pointObj(2,8.2))
        # lo.add(mapscript.pointObj(26,8.2))
        # symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        # symbol_wa.filled = False
        # symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 50 kn
        symbol_wa = mapscript.symbolObj("wind_barb_50")
        symbol_wa.name = "wind_barb_50"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(4.4,0))
        lo.add(mapscript.pointObj(6.8,8.2))
        lo.add(mapscript.pointObj(26,8.2)) # Join start
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = True
        symbol_obj.appendSymbol(symbol_wa)

        symbol_obj.save(symbol_file)
    map_object.setSymbolSet(os.path.join(_get_mapfiles_path(product_config), symbol_file))

    qp = {k.lower(): v for k, v in full_request.query_params.items()}
    print(qp)
    if 'request' in qp and qp['request'] != 'GetCapabilities':
        layer = mapscript.layerObj()
        if _generate_layer(layer, ds_disk, grid_mapping_cache, netcdf_path, qp, map_object, product_config):
            layer_no = map_object.insertLayer(layer)
    else:
        # Read all variables names from the netcdf file.
        variables = list(ds_disk.keys())
        for variable in variables:
            layer = mapscript.layerObj()
            if _generate_getcapabilities(layer, ds_disk, variable, grid_mapping_cache, netcdf_path):
                layer_no = map_object.insertLayer(layer)
            if variable.startswith('x_wind') and variable.replace('x', 'y') in variables:
                print(f"Add wind vector layer for {variable}.")
                layer_contour = mapscript.layerObj()
                if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path):
                    layer_no = map_object.insertLayer(layer_contour)

    map_object.save(os.path.join(tempfile.mkdtemp(prefix='map-', dir=_get_mapfiles_path(product_config)), f'arome-arctic-{forecast_time:%Y%m%d%H%M%S}.map'))

    # Handle the request and return results.
    return handle_request(map_object, full_request)

