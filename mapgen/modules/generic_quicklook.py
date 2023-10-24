"""
gridded data quicklook : module
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
import pandas
import datetime
import mapscript
from fastapi import Request, Query, HTTPException
import numpy as np
import xarray as xr
from osgeo import gdal
from pyproj import CRS
from mapgen.modules.helpers import handle_request

grid_mapping_cache = {}

def _fill_metadata_to_mapfile(orig_netcdf_path, map_object, full_request, xr_dataset):
    """"Add all needed web metadata to the generated map file."""
    map_object.web.metadata.set("wms_title", "WMS")
    map_object.web.metadata.set("wms_onlineresource", f"{full_request.url.scheme}://{full_request.url.netloc}/api/get_quicklook{orig_netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:25833 EPSG:3978 EPSG:4326 EPSG:4269 EPSG:3857 EPSG:32661")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")
    try:
        map_object.setSize(xr_dataset.dims['x'], xr_dataset.dims['y'])
    except KeyError:
        try:
            map_object.setSize(xr_dataset.dims['longitude'], xr_dataset.dims['latitude'])
        except KeyError:
            map_object.setSize(2000, 2000)
    map_object.units = mapscript.MS_DD
    try:
        map_object.setExtent(float(xr_dataset.attrs['geospatial_lon_min']),
                            float(xr_dataset.attrs['geospatial_lat_min']),
                            float(xr_dataset.attrs['geospatial_lon_max']),
                            float(xr_dataset.attrs['geospatial_lat_max']))
    except KeyError:
        try:
            map_object.setExtent(float(np.nanmin(xr_dataset['longitude'].data)),
                                 float(np.nanmin(xr_dataset['latitude'].data)),
                                 float(np.nanmax(xr_dataset['longitude'].data)),
                                 float(np.nanmax(xr_dataset['latitude'].data)))
        except KeyError:
            print("Could not detect extent of datdaset. Force full Earth.")
            map_object.setExtent(-180, -90, 180, 90)
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
        if dim_name in ['x', 'y', 'longitude', 'latitude']:
            continue
        print(f"Checking dimension: {dim_name}")
        if dim_name in 'time':
            print("handle time")
            diff, is_range = find_time_diff(ds, dim_name)
            if is_range:
                diff_string = 'PT1H'
                if diff == datetime.timedelta(hours=1):
                    diff_string = "PT1H"
                elif diff == datetime.timedelta(hours=3):
                    diff_string = "PT3H"
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
                actual_dim_name = dim_name
                if dim_name == 'height':
                    print("Rename getcapabilities height dimension to height_dimension.")
                    dim_name = dim_name + "_dimension"
                dims_list.append(dim_name)
                layer.metadata.set(f"wms_{dim_name}_item", dim_name)
                try:
                    layer.metadata.set(f"wms_{dim_name}_units", ds[actual_dim_name].attrs['units'])
                except KeyError:
                    print(f"Failed to set metadata units for dimmension name {dim_name}")
                layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[actual_dim_name].data]))
                layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[actual_dim_name].data)))
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
        if dim_name in ['x', 'y', 'longitude', 'latitude']:
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
                    layer.metadata.set(f"wms_{dim_name}_units", "1")
                layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[dim_name].data]))
                layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[dim_name].data)))
    if dims_list:
        layer.metadata.set(f"wms_dimensionlist", ','.join(dims_list))

    print("ADDing vector at end")

    return True

def _extract_extent(ds, variable):
    try:
        ll_x = min(ds[variable].coords['x'].data)
        ur_x = max(ds[variable].coords['x'].data)
        ll_y = min(ds[variable].coords['y'].data)
        ur_y = max(ds[variable].coords['y'].data)
    except KeyError:
        ll_x = min(ds[variable].coords['longitude'].data)
        ur_x = max(ds[variable].coords['longitude'].data)
        ll_y = min(ds[variable].coords['latitude'].data)
        ur_y = max(ds[variable].coords['latitude'].data)

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
        if dim_name in ['x', 'y', 'longitude', 'latitude']:
            continue
        for _dim_name in [f'{dim_name}', f'dim_{dim_name}']:
            if _dim_name == 'height':
                print(f"Can not have a dimension name height as this will conflict with query parameter HEIGHT as the size in image.")
                _dim_name = _dim_name + '_dimension'
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

def _generate_layer(layer, ds, grid_mapping_cache, netcdf_file, qp, map_obj, product_config):
    try:
        variable = qp['layer']
    except KeyError:
        variable = qp['layers']
    try:
        style = qp['styles']
    except KeyError:
        style = qp['style']
    if style == "":
        print("Empty style. force raster.")
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
        gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "xvar.vrt"),
                    [f'NETCDF:{netcdf_file}:{actual_x_variable}'],
                    **{'bandList': [band_number]})
        gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "yvar.vrt"),
                    [f'NETCDF:{netcdf_file}:{actual_y_variable}'],
                    **{'bandList': [band_number]})
        gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "var.vrt"),
                    [os.path.join(_get_mapfiles_path(product_config), 'xvar.vrt'),
                     os.path.join(_get_mapfiles_path(product_config), 'yvar.vrt')],
                    **{'separate': True})
        layer.data = os.path.join(_get_mapfiles_path(product_config), 'var.vrt')
    else:
        layer.data = f'NETCDF:{netcdf_file}:{actual_variable}'

    if style in 'contour': #variable.endswith('_contour'):
        print("Style in contour for config")
        layer.type = mapscript.MS_LAYER_LINE
        layer.setConnectionType(mapscript.MS_CONTOUR, "")
        layer.setProcessingKey('CONTOUR_INTERVAL', f'{500}')
        layer.setProcessingKey('CONTOUR_ITEM', 'contour')
        layer.setGeomTransform('smoothsia(generalize([shape], 0.25*[data_cellsize]))')
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
        s = mapscript.classObj(layer)
        style = mapscript.styleObj(s)
        style.updateFromString('STYLE SYMBOL "horizline" ANGLE [uv_angle] SIZE [uv_length] WIDTH 3 COLOR 100 255 0 END')
        style.setSymbolByName(map_obj, "horizline")
        layer.setProcessingKey('UV_SIZE_SCALE', '2')

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
        else:
            print("Undefined lenght of dimension search ", len(dimension_search))
        print("MIN:MAX ", min_val, max_val)
        # print(ds[actual_variable].attrs)
        # if 'scale_factor' in ds[actual_variable].attrs:
        #     print("Setting scale factor to the data.")
        #     min_val *= ds[actual_variable].attrs['scale_factor']
        #     max_val *= ds[actual_variable].attrs['scale_factor']
        #     print("Scaled with scale_factor MIN:MAX ", min_val, max_val)
        #     layer.setProcessingKey("SCALE",f'{min_val},{max_val}')
        #     layer.setProcessingKey("SCALE_BUCKETS", "256")
        #Grayscale
        s = mapscript.classObj(layer)
        if style in 'contour': #variable.endswith('_contour'):
            print("Style in contour for style setup.")
            layer.labelitem = 'contour'
            s.name = "contour"
            style = mapscript.styleObj(s)
            style.width = 1
            style.color = mapscript.colorObj(red=0, green=0, blue=255)
            label = mapscript.labelObj()
            label.setText('(tostring(([contour]/100),"%.0f"))')
            #label.setText("(tostring(([contour]/100),'%.0f'))")
            print(label.convertToString())
            label.color = mapscript.colorObj(red=0, green=0, blue=255)
            #label.font = 'sans'
            # TYPE truetype
            label.size = 10
            label.position = mapscript.MS_CC
            label.force = True
            label.angle = 0 #mapscript.MS_AUTO
            s.addLabel(label)
        else:
            print("Raster scaling")
            s.name = "Linear grayscale using min and max not nan from data"
            s.group = 'raster'
            style = mapscript.styleObj(s)
            style.rangeitem = 'pixel'
            style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
            style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
            style.minvalue = float(min_val)
            style.maxvalue = float(max_val)

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

def generic_quicklook(netcdf_path: str,
                      full_request: Request,
                      products: list = Query(default=[]),
                      product_config: dict = {}):
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if netcdf_path.startswith(product_config['base_netcdf_directory']):
            print("Request with full path. Please fix your request. Depricated from version 2.0.0.")
        elif os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        raise HTTPException(status_code=500, detail="Missing base dir in server config.")

    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")

    # Read all variables names from the netcdf file.
    ds_disk = xr.open_dataset(netcdf_path, mask_and_scale=False)
    variables = list(ds_disk.keys())

    #get forecast reference time from dataset
    try:
        forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
    except KeyError:
        print("Could not find forecast time or analysis time from dataset. Try parse from filename.")
        # Parse the netcdf filename to get start time or reference time
        _, _forecast_time = _parse_filename(netcdf_path, product_config)
        forecast_time = datetime.datetime.strptime(_forecast_time, "%Y%m%dT%H")
        print(forecast_time)

    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(orig_netcdf_path, map_object, full_request, ds_disk)

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

    symbol_obj = mapscript.symbolSetObj()
    symbol_obj.appendSymbol(symbol)
    symbol_obj.save(os.path.join(_get_mapfiles_path(product_config), "symbol.sym"))
    map_object.setSymbolSet(os.path.join(_get_mapfiles_path(product_config),"symbol.sym"))

    qp = {k.lower(): v for k, v in full_request.query_params.items()}
    print(qp)
    if 'request' in qp and qp['request'] != 'GetCapabilities':
        layer = mapscript.layerObj()
        if _generate_layer(layer, ds_disk, grid_mapping_cache, netcdf_path, qp, map_object, product_config):
            layer_no = map_object.insertLayer(layer)
    else:
        for variable in variables:
            layer = mapscript.layerObj()
            if _generate_getcapabilities(layer, ds_disk, variable, grid_mapping_cache, netcdf_path):
                layer_no = map_object.insertLayer(layer)
            if variable.startswith('x_wind') and variable.replace('x', 'y') in variables:
                print(f"Add wind vector layer for {variable}.")
                layer_contour = mapscript.layerObj()
                if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path):
                    layer_no = map_object.insertLayer(layer_contour)

    map_object.save(os.path.join(_get_mapfiles_path(product_config), f'generic-{forecast_time:%Y%m%d%H%M%S}.map'))

    # Handle the request and return results.
    return handle_request(map_object, full_request)
