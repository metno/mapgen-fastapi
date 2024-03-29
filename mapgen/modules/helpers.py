"""
Helpers
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

import os
import re
import sys
import yaml
import hashlib
import datetime
import requests
import tempfile
import mapscript
import traceback
from osgeo import gdal
from lxml import etree
import xml.dom.minidom
from pyproj import CRS
from fastapi import HTTPException
from fastapi.responses import Response

import numpy as np
import xarray as xr
from cartopy import crs
import metpy # needed for xarray's metpy accessor
import pandas as pd

def _read_config_file(regexp_config_file):
    regexp_config = None
    try:
        if os.path.exists(regexp_config_file):
            with open(regexp_config_file) as f:
                regexp_config = yaml.load(f, Loader=yaml.loader.SafeLoader)
    except Exception as e:
        print(f"Failed to read yaml config: {regexp_config_file} with {str(e)}")
        pass
    return regexp_config

def find_config_for_this_netcdf(netcdf_path):
    default_regexp_config_filename = 'url-path-regexp-patterns.yaml'
    default_regexp_config_dir = '/config'
    if os.path.exists(os.path.join('./', default_regexp_config_filename)):
        regexp_config_file = os.path.join('./', default_regexp_config_filename)
    else:
        regexp_config_file = os.path.join(default_regexp_config_dir,
                                          default_regexp_config_filename)
    regexp_config = _read_config_file(regexp_config_file)
    regexp_pattern_module = None
    if regexp_config:
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
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            raise HTTPException(status_code=500, detail=f"Exception raised when regexp. Check the config.")
    if not regexp_pattern_module:
        raise HTTPException(status_code=501, detail=f"The server have no setup to handle the requested file {netcdf_path}. Check with the maintainer if this could be added.")

    return regexp_pattern_module

def handle_request(map_object, full_request):
    ows_req = mapscript.OWSRequest()
    ows_req.type = mapscript.MS_GET_REQUEST
    full_request_string = str(full_request.query_params)
    try:
        # Replace automatic inserted &amp; instead of plain &
        full_request_string = full_request_string.replace("&amp;", "&")
        full_request_string = full_request_string.replace("&amp%3B", "&")
        print("HER", full_request_string)
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"failed to handle query parameters: {str(full_request.query_params)}, with error: {str(e)}")
    try:
        ows_req.loadParamsFromURL(full_request_string)
    except mapscript.MapServerError:
        ows_req = mapscript.OWSRequest()
        ows_req.type = mapscript.MS_GET_REQUEST
        pass
    if not full_request.query_params or (ows_req.NumParams == 1 and 'satpy_products' in full_request.query_params):
        print("Query params are empty or only contains satpy-product query parameter. Force getcapabilities")
        ows_req.setParameter("SERVICE", "WMS")
        ows_req.setParameter("VERSION", "1.3.0")
        ows_req.setParameter("REQUEST", "GetCapabilities")
    else:
        print("ALL query params: ", full_request_string)
    print("NumParams", ows_req.NumParams)
    print("TYPE", ows_req.type)
    if ows_req.getValueByName('REQUEST') != 'GetCapabilities':
        mapscript.msIO_installStdoutToBuffer()
        try:
            _styles = str(ows_req.getValueByName("STYLES"))
            if _styles.lower() in 'contour':
                ows_req.setParameter("STYLES", "")
            if _styles.lower() in 'wind_barbs':
                ows_req.setParameter("STYLES", "")
            if _styles.lower() in 'vector':
                ows_req.setParameter("STYLES", "")
        except TypeError:
            print("STYLES not in the request. Nothing to reset.")
            pass
        try:
            map_object.OWSDispatch( ows_req )
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"mapscript fails to parse query parameters: {str(full_request.query_params)}, with error: {str(e)}")
        content_type = mapscript.msIO_stripStdoutBufferContentType()
        result = mapscript.msIO_getStdoutBufferBytes()
    else:
        mapscript.msIO_installStdoutToBuffer()
        dispatch_status = map_object.OWSDispatch(ows_req)
        if dispatch_status != mapscript.MS_SUCCESS:
            print("DISPATCH status", dispatch_status)
        content_type = mapscript.msIO_stripStdoutBufferContentType()
        mapscript.msIO_stripStdoutBufferContentHeaders()
        _result = mapscript.msIO_getStdoutBufferBytes()

        if content_type == 'application/vnd.ogc.wms_xml; charset=UTF-8':
            content_type = 'text/xml'
        dom = xml.dom.minidom.parseString(_result)
        result = dom.toprettyxml(indent="", newl="")
    return Response(result, media_type=content_type)

#from typing import Optional
#from . import _util
#from maptor.config import ModelConfiguration



def _get_speed(x_vector: xr.DataArray, y_vector: xr.DataArray, standard_name: str) -> xr.DataArray:
    data = np.sqrt((x_vector**2) + (y_vector**2))
    data.attrs['standard_name'] = standard_name
    data.attrs['units'] = x_vector.attrs['units']
    return data


def _get_from_direction(x_vector: xr.DataArray, y_vector: xr.DataArray, standard_name: str) -> xr.DataArray:
    data = ((np.arctan2(x_vector, y_vector) * 180 / np.pi) + 180) % 360
    data.attrs['standard_name'] = standard_name
    data.attrs['units'] = 'degrees'
    return data


def _north(projection: crs.CRS, requested_epsg, x_in: xr.DataArray, y_in: xr.DataArray) -> np.ndarray:
    x_len = len(x_in)
    y_len = len(y_in)
    shape = [y_len, x_len]

    x = np.tile(x_in, [y_len, 1])
    y = np.tile(y_in, [x_len, 1]).T
    u = np.zeros(shape)
    v = np.ones(shape)

    if isinstance(projection, crs.PlateCarree):
        # No need for rotation
        print("No rotation ", projection)
        north_u = x
        north_v = y
    elif requested_epsg == 4326:
        north_u, north_v = crs.Mercator().transform_vectors(projection, x, y, u, v)
    else:
        north_u, north_v = crs.epsg(requested_epsg).transform_vectors(projection, x, y, u, v)
    north = 90 - (np.arctan2(north_v, north_u) * (180 / np.pi))

    return -north


def _get_north(x_vector_param: str, ds: xr.Dataset, requested_epsg):
    y_coord_name, x_coord_name = ds[x_vector_param].dims[-2:]
    north = _north(
        _get_crs(ds, x_vector_param),
        requested_epsg,
        ds[x_coord_name],
        ds[y_coord_name],
    )
    north = xr.DataArray(
        data=north,
        dims=[y_coord_name, x_coord_name],
    )

    return north


def _get_crs(ds: xr.Dataset, sample_parameter: str) -> crs.CRS:
    ds = ds.metpy.parse_cf([sample_parameter])
    return ds[sample_parameter].metpy.cartopy_crs


def _rotate_relative_to_north(from_direction: xr.DataArray, north: np.ndarray):
    from_direction -= north
    from_direction %= 360

def _find_summary_from_csw(search_fname, forecast_time, full_request):
    summary_text = None
    search_string = ""
    if 'arome_arctic' in search_fname:
        search_string += "Arome-Arctic_"
    if '2_5km' in search_fname:
        search_string += "2.5km_"
    if 'det' in search_fname:
        search_string += "deterministic_"
    if search_string != "":
        search_string += forecast_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        print("CSW Search string", search_string)
        netloc = full_request.url.netloc
        if 's-enda' in netloc:
            netloc = netloc.replace("fastapi", "csw")
        else:
            netloc = 'csw.s-enda-dev.k8s.met.no'
        url = (f'{full_request.url.scheme}://{netloc}/?'
                'mode=opensearch&service=CSW&version=2.0.2&request=GetRecords&elementsetname=full&'
            f'typenames=csw:Record&resulttype=results&q={search_string}')
        try:
            xml_string = requests.get(url, timeout=10).text
        except requests.exceptions.Timeout:
            print("csw request timed out. Skip summary")
            return summary_text
        root = etree.fromstring(xml_string.encode('utf-8'))
        summarys = root.xpath('.//atom:summary', namespaces=root.nsmap)
        for summary in summarys:
            summary_text = summary.text
            break
    else:
        print("Not enough data to build CSW search_string for summary. Please add if applicable.")
    return summary_text

def _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, full_request, xr_dataset, summary_cache, wms_title):
    """"Add all needed web metadata to the generated map file."""
    bn = os.path.basename(orig_netcdf_path)
    if bn not in summary_cache:
        summary = _find_summary_from_csw(bn, forecast_time, full_request)
        if summary:
            summary_cache[bn] = summary
            print(summary_cache[bn])
        else:
            summary_cache[bn] = "Not Available."
    map_object.web.metadata.set("wms_title", wms_title)
    map_object.web.metadata.set("wms_onlineresource", f"{full_request.url.scheme}://{full_request.url.netloc}/api/get_quicklook{orig_netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:3857 EPSG:3978 EPSG:4269 EPSG:4326 EPSG:25832 EPSG:25833 EPSG:25835 EPSG:32632 EPSG:32633 EPSG:32635 EPSG:32661")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")
    try:
        map_object.setSize(xr_dataset.dims['x'], xr_dataset.dims['y'])
    except KeyError:
        try:
            map_object.setSize(xr_dataset.dims['longitude'], xr_dataset.dims['latitude'])
        except KeyError:
            try:
                map_object.setSize(xr_dataset.dims['Xc'], xr_dataset.dims['Yc'])
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
            print("Could not detect extent of dataset. Force full Earth.")
            map_object.setExtent(-180, -90, 180, 90)
    return

def _find_projection(ds, variable, grid_mapping_cache):
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

def _extract_extent(ds, variable):
    try:
        ll_x = min(ds[variable].coords['x'].data)
        ur_x = max(ds[variable].coords['x'].data)
        ll_y = min(ds[variable].coords['y'].data)
        ur_y = max(ds[variable].coords['y'].data)
    except KeyError:
        try:
            ll_x = min(ds[variable].coords['Xc'].data)
            ur_x = max(ds[variable].coords['Xc'].data)
            ll_y = min(ds[variable].coords['Yc'].data)
            ur_y = max(ds[variable].coords['Yc'].data)
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
    diff_string = None
    # try:
    #     print(ds[dim_name].dt)
    # except TypeError:
    #     if ds[dim_name].attrs['units'] == 'seconds since 1970-01-01 00:00:00 +00:00':
    #         ds[dim_name] = pd.TimedeltaIndex(ds[dim_name], unit='s') + datetime.datetime(1970, 1, 1)
    #         ds[dim_name] = pd.to_datetime(ds[dim_name])
    #     else:
    #         print(f"This unit is not implemented: {ds[dim_name].attrs['units']}")
    #         raise HTTPException(status_code=500, detail=f"This unit is not implemented: {ds[dim_name].attrs['units']}")
    if len(ds[dim_name].dt.year.data) == 1:
        print("Time diff len", len(ds[dim_name].dt.year.data))
        is_range = False
    else:
        for y,m,d,h,minute,s in zip(ds[dim_name].dt.year.data, ds[dim_name].dt.month.data, ds[dim_name].dt.day.data, ds[dim_name].dt.hour.data, ds[dim_name].dt.minute.data, ds[dim_name].dt.second.data):
            stamp = datetime.datetime(y, m, d, h, minute, s)
            if prev:
                diff = stamp - prev
                if prev_diff and diff != prev_diff:
                    # Diff between more than three stamps are different. Can not use range.
                    is_range = False
                    break
                prev_diff = diff
            prev = stamp
    if is_range:
        if diff < datetime.timedelta(hours=1):
            h = int(diff.seconds/60)
            diff_string = f"PT{h}M"
        elif diff < datetime.timedelta(hours=24):
            h = int(diff.seconds/3600)
            diff_string = f"PT{h}H"
        else:
            diff_string = f"P{diff.days}D"
        print(f"DIFF STRING {diff_string}")
    else:
        print("Is not range")
    return diff,diff_string,is_range

def _generate_getcapabilities(layer, ds, variable, grid_mapping_cache, netcdf_file):
    """Generate getcapabilities for the netcdf file."""
    grid_mapping_name = _find_projection(ds, variable, grid_mapping_cache)
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
        if dim_name in ['x', 'Xc', 'y', 'Yc', 'longitude', 'latitude']:
            continue
        print(f"Checking dimension: {dim_name}")
        if dim_name in 'time':
            print("handle time")
            _, diff_string, is_range = find_time_diff(ds, dim_name)
            if is_range:
                start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
            else:
                print("Use time list.")
                time_list = []
                for d in ds['time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ'):
                    time_list.append(f"{str(d.data)}")
                start_time = time_list[0]
                layer.metadata.set("wms_timeextent", f'{",".join(time_list)}')
            layer.metadata.set("wms_default", f'{start_time}')
        else:
            if ds[dim_name].data.size > 1:
                actual_dim_name = dim_name
                if dim_name == 'height':
                    print("Rename getcapabilities height dimension to height_dimension.")
                    dim_name = dim_name + "_dimension"
                dims_list.append(dim_name)
                layer.metadata.set(f"wms_{dim_name}_item", dim_name)
                try:
                    layer.metadata.set(f"wms_{dim_name}_units", ds[actual_dim_name].attrs['units'])
                except KeyError:
                    print(f"Failed to set metadata units for dimmension name {dim_name}. Forcing to 1.")
                    layer.metadata.set(f"wms_{dim_name}_units", '1')
                layer.metadata.set(f"wms_{dim_name}_extent", ','.join([str(d) for d in ds[actual_dim_name].data]))
                layer.metadata.set(f"wms_{dim_name}_default", str(max(ds[actual_dim_name].data)))

    if dims_list:
        layer.metadata.set(f"wms_dimensionlist", ','.join(dims_list))

    s = mapscript.classObj(layer)
    s.name = "contour"
    s.group = "contour"
    style = mapscript.styleObj(s)
    style.rangeitem = 'pixel'
    style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
    style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)

    s1 = mapscript.classObj(layer)
    s1.name = "Linear grayscale using min and max not nan from data"
    s1.group = 'raster'
    style1 = mapscript.styleObj(s1)
    style1.rangeitem = 'pixel'
    style1.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
    style1.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)

    return True

def _generate_getcapabilities_vector(layer, ds, variable, grid_mapping_cache, netcdf_file, direction_speed=False):
    """Generate getcapabilities for vector fiels for the netcdf file."""
    print("ADDING vector")
    grid_mapping_name = _find_projection(ds, variable, grid_mapping_cache)
    if not grid_mapping_name:
        return None
    layer.setProjection(grid_mapping_cache[grid_mapping_name])
    layer.status = 1
    if variable.startswith('x_wind'):
        x_variable = variable
        y_variable = x_variable.replace('x', 'y')
        vector_variable_name = '_'.join(variable.split("_")[1:])
    if variable == 'wind_direction':
        vector_variable_name = 'wind'
    layer.data = f'NETCDF:{netcdf_file}:{variable}'
    layer.type = mapscript.MS_LAYER_LINE
    layer.name = f'{vector_variable_name}_vector'
    if direction_speed:
        layer.name = f'{vector_variable_name}_vector_from_direction_and_speed'
    layer.metadata.set("wms_title", f'{vector_variable_name}')
    layer.setConnectionType(mapscript.MS_CONTOUR, "")
    ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
    dims_list = []
    for dim_name in ds[variable].dims:
        if dim_name in ['x', 'Xc', 'y', 'Yc', 'longitude', 'latitude']:
            continue
        if dim_name in 'time':
            print("handle time")
            _, diff_string, is_range = find_time_diff(ds, dim_name)
            if is_range:
                start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
            else:
                print("Use time list.")
                time_list = []
                for d in ds['time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ'):
                    time_list.append(f"{str(d.data)}")
                start_time = time_list[0]
                layer.metadata.set("wms_timeextent", f'{",".join(time_list)}')
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

def _find_dimensions(ds, actual_variable, variable, qp):
    # Find available dimension not larger than 1
    dimension_search = []
    for dim_name in ds[actual_variable].dims:
        if dim_name in ['x', 'Xc', 'y', 'Yc', 'longitude', 'latitude']:
            continue
        for _dim_name in [dim_name, f'dim_{dim_name}']:
            if _dim_name == 'height' or _dim_name == 'dim_height':
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

def _add_wind_barb(map_obj, layer, colour_tripplet, min, max):
    s = mapscript.classObj(layer)
    min_ms = min/1.94384449
    max_ms = max/1.94384449
    s.setExpression(f'([uv_length]>={min_ms} and [uv_length]<{max_ms})')
    # Wind barbs
    style = mapscript.styleObj(s)
    #OUTLINECOLOR {colour_tripplet}
    style.updateFromString(f'STYLE SYMBOL "wind_barb_{min+2}" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} END')
    style.setSymbolByName(map_obj, f"wind_barb_{min+2}")
    return

def _add_wind_barb_50_100(map_obj, layer, colour_tripplet, min, max):
    s = mapscript.classObj(layer)
    min_ms = min/1.94384449
    max_ms = max/1.94384449
    s.setExpression(f'([uv_length]>={min_ms} and [uv_length]<{max_ms})')
    # Wind barbs
    style = mapscript.styleObj(s)
    style.updateFromString(f'STYLE SYMBOL "wind_barb_50_flag" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} POLAROFFSET -24 [uv_angle] END')
    style.setSymbolByName(map_obj, f"wind_barb_50_flag")
    style_base = mapscript.styleObj(s)
    style_base.updateFromString(f'STYLE SYMBOL "wind_barb_{min+2}" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} END')
    style_base.setSymbolByName(map_obj, f"wind_barb_{min+2}")
    return

def _add_wind_barb_100_150(map_obj, layer, colour_tripplet, min, max):
    s = mapscript.classObj(layer)
    min_ms = min/1.94384449
    max_ms = max/1.94384449
    s.setExpression(f'([uv_length]>={min_ms} and [uv_length]<{max_ms})')
    # Wind barbs
    style = mapscript.styleObj(s)
    style.updateFromString(f'STYLE SYMBOL "wind_barb_50_flag" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} POLAROFFSET -24 [uv_angle] END')
    style.setSymbolByName(map_obj, f"wind_barb_50_flag")
    style_100 = mapscript.styleObj(s)
    style_100.updateFromString(f'STYLE SYMBOL "wind_barb_50_flag" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} POLAROFFSET -12 [uv_angle] END')
    style_100.setSymbolByName(map_obj, f"wind_barb_50_flag")
    style_base = mapscript.styleObj(s)
    style_base.updateFromString(f'STYLE SYMBOL "wind_barb_{min+2}" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colour_tripplet} END')
    style_base.setSymbolByName(map_obj, f"wind_barb_{min+2}")
    return

def _generate_layer(layer, ds, grid_mapping_cache, netcdf_file, qp, map_obj, product_config, wind_rotation_cache):
    try:
        variable = qp['layer']
    except KeyError:
        variable = qp['layers']
    try:
        style = qp['styles']
    except KeyError:
        style = qp['style']
    if (variable.endswith("_vector") or variable.endswith("_vector_from_direction_and_speed")) and style == "":
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
    if variable.endswith("_vector_from_direction_and_speed"):
        actual_x_variable = 'wind_speed'  # Not accurate, used to find crs and other proj info
        actual_y_variable = 'wind_direction'  # Not accurate, used to find crs and other proj info
        vector_variable_name = variable
        actual_variable = actual_x_variable
        print("VECTOR", vector_variable_name, actual_x_variable, actual_y_variable)

    dimension_search = _find_dimensions(ds, actual_variable, variable, qp)
    if netcdf_file.endswith('ncml'):
        band_number = 1
    else:
        band_number = _calc_band_number_from_dimensions(dimension_search)
    if variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):
        layer.setProcessingKey('BANDS', f'1,2')
    else:
        layer.setProcessingKey('BANDS', f'{band_number}')

    grid_mapping_name = _find_projection(ds, actual_variable, grid_mapping_cache)
    layer.setProjection(grid_mapping_cache[grid_mapping_name])
    layer.status = 1
    if variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):

        sel_dim = {}
        for _ds in dimension_search:
            sel_dim[_ds['dim_name']] = _ds['selected_band_number']
        ds = ds.isel(**sel_dim)
        # ts = time.time()
        standard_name_prefix = 'wind'
        if variable.endswith("_vector_from_direction_and_speed"):
            try:
                scale_factor = ds['wind_speed'].attrs['scale_factor']
            except KeyError:
                print("No scale_factor in attrs")
                scale_factor = 1.
            try:
                add_offset = ds['wind_speed'].attrs['add_offset']
            except KeyError:
                print("No scale_factor in attrs")
                add_offset = 0.
            speed = ds['wind_speed'] * scale_factor + add_offset
            try:
                scale_factor = ds['wind_direction'].attrs['scale_factor']
            except KeyError:
                print("No scale_factor in attrs")
                scale_factor = 1.
            try:
                add_offset = ds['wind_direction'].attrs['add_offset']
            except KeyError:
                print("No scale_factor in attrs")
                add_offset = 0.
            from_direction = ds['wind_direction'] * scale_factor + add_offset
        else:
            speed = _get_speed(ds[actual_x_variable],
                               ds[actual_y_variable],
                               f'{standard_name_prefix}_speed')
        # te = time.time()
        # print("_get_speed ", te - ts)
        # ts = time.time()
            from_direction = _get_from_direction(ds[actual_x_variable],
                                                 ds[actual_y_variable],
                                                 f'{standard_name_prefix}_from_direction')
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
            unique_dataset_string = generate_unique_dataset_string(ds, actual_x_variable, requested_epsg)
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

        new_x = np.cos((90. - from_direction - 180) * np.pi/180) * speed
        new_y = np.sin((90. - from_direction - 180) * np.pi/180) * speed
        new_x.attrs['grid_mapping'] = ds[actual_x_variable].attrs['grid_mapping']
        new_y.attrs['grid_mapping'] = ds[actual_y_variable].attrs['grid_mapping']
        ds_xy = xr.Dataset({})
        ds_xy[new_x.attrs['grid_mapping']] = ds[new_x.attrs['grid_mapping']]
        try:
            print("Droping vars:", new_x.dims, len(new_x.dims))
            if len(new_x.dims) == 2:
                ds_xy[actual_x_variable] = new_x
            else:
                ds_xy[actual_x_variable] = new_x.drop_vars(['latitude', 'longitude'])
        except ValueError:
            print("Failing drop vars")
            ds_xy[actual_x_variable] = new_x
        try:
            if len(new_y.dims) == 2:
                ds_xy[actual_y_variable] = new_y
            else:
                ds_xy[actual_y_variable] = new_y.drop_vars(['latitude', 'longitude'])
        except ValueError:
            ds_xy[actual_y_variable] = new_y
        # te = time.time()
        # print("new dataset ", te - ts)
        # ts = time.time()
        # print("GRid mapping", new_x.attrs['grid_mapping'])
        # print(ds_xy)
        # for netcdfs in glob.glob(os.path.join(_get_mapfiles_path(product_config), "netcdf-*")):
        #     shutil.rmtree(netcdfs)
        tmp_netcdf = os.path.join(tempfile.mkdtemp(prefix='netcdf-', dir=_get_mapfiles_path(product_config)),
                                  f"xy-{actual_x_variable}-{actual_y_variable}.nc")
        ds_xy.to_netcdf(tmp_netcdf)
        print(tmp_netcdf)
        # for vrts in glob.glob(os.path.join(_get_mapfiles_path(product_config), "vrt-*")):
        #     shutil.rmtree(vrts)

        xvar_vrt_filename = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f"xvar-{actual_x_variable}-1.vrt")
        print(xvar_vrt_filename)
        gdal.BuildVRT(xvar_vrt_filename,
                    [f'NETCDF:{tmp_netcdf}:{actual_x_variable}'],
                    **{'bandList': [1]})
        yvar_vrt_filename = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f"yvar-{actual_y_variable}-1.vrt")
        gdal.BuildVRT(yvar_vrt_filename,
                    [f'NETCDF:{tmp_netcdf}:{actual_y_variable}'],
                    **{'bandList': [1]})
        variable_file_vrt = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f'var-{actual_x_variable}-{actual_y_variable}-{band_number}.vrt')
        gdal.BuildVRT(variable_file_vrt,
                      [f'NETCDF:{tmp_netcdf}:{actual_x_variable}', f'NETCDF:{tmp_netcdf}:{actual_y_variable}'],
                     #[xvar_vrt_filename, yvar_vrt_filename],
                     **{'bandList': [1], 'separate': True})
        # te = time.time()
        # print("save and create vrts ", te - ts) 
        layer.data = variable_file_vrt
    elif netcdf_file.endswith('ncml'):
        print("Must find netcdf file for data")
        from lxml import etree
        try:
            ncml_netcdf_files = []
            xtree = etree.parse(netcdf_file)
            for f in xtree.findall(".//{http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2}netcdf"):
                ncml_netcdf_files.append(f.attrib['location'])
            layer.data = f'NETCDF:{ncml_netcdf_files[dimension_search[0]["selected_band_number"]]}:{actual_variable}'
        except FileNotFoundError:
            print(f"Could not find the ncml xml input file {netcdf_file}.")
        except Exception:
            raise HTTPException(status_code=500, detail=f"Failed to parse ncml file to find individual file.")

    else:
        layer.data = f'NETCDF:{netcdf_file}:{actual_variable}'

    if style in 'contour':
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
    elif variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):
        layer.setConnectionType(mapscript.MS_UVRASTER, "")
        layer.type = mapscript.MS_LAYER_POINT
    else:
        layer.type = mapscript.MS_LAYER_RASTER
    layer.name = variable
    if variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):
        layer.metadata.set("wms_title", '_'.join(variable.split("_")[:-1]))
    else:
        layer.metadata.set("wms_title", variable)
    ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, actual_variable)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")


    if variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):
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
            s.setExpression(f'([uv_length]<{3/1.94384449})')
            # Wind barbs CALM
            _style = mapscript.styleObj(s)
            _style.updateFromString(f'STYLE SYMBOL "wind_barb_0" ANGLE [uv_angle] SIZE 20 WIDTH 1 COLOR {colours_by_name[colour_dimension]} OUTLINECOLOR {colours_by_name[colour_dimension]} END')
            _style.setSymbolByName(map_obj, f"wind_barb_0")

            for max_wind_barb_speed in range(8,53,5):
                min_wind_barb_speed = max_wind_barb_speed - 5
                _add_wind_barb(map_obj, layer, colours_by_name[colour_dimension], min_wind_barb_speed, max_wind_barb_speed)
            for max_wind_barb_speed in range(53,103,5):
                min_wind_barb_speed = max_wind_barb_speed - 5
                _add_wind_barb_50_100(map_obj, layer, colours_by_name[colour_dimension], min_wind_barb_speed, max_wind_barb_speed)
            for max_wind_barb_speed in range(103,108,5):
                min_wind_barb_speed = max_wind_barb_speed - 5
                _add_wind_barb_100_150(map_obj, layer, colours_by_name[colour_dimension], min_wind_barb_speed, max_wind_barb_speed)

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

def generate_unique_dataset_string(ds, actual_x_variable, requested_epsg):
    try:
        unique_dataset_string = hashlib.md5((f"{requested_epsg}"
                                             f"{_get_crs(ds, actual_x_variable)}"
                                             f"{ds['x'].data.size}"
                                             f"{ds['y'].data.size}"
                                             f"{ds['x'][0].data}"
                                             f"{ds['x'][-1].data}"
                                             f"{ds['y'][0].data}"
                                             f"{ds['y'][-1].data}").encode('UTF-8')).hexdigest()
    except KeyError:
        try:
            unique_dataset_string = hashlib.md5((f"{requested_epsg}"
                                                 f"{_get_crs(ds, actual_x_variable)}"
                                                 f"{ds['longitude'].data.size}"
                                                 f"{ds['latitude'].data.size}"
                                                 f"{ds['longitude'][0].data}"
                                                 f"{ds['longitude'][-1].data}"
                                                 f"{ds['latitude'][0].data}"
                                                 f"{ds['latitude'][-1].data}").encode('UTF-8')).hexdigest()
        except KeyError:
            unique_dataset_string = hashlib.md5((f"{requested_epsg}"
                                                 f"{_get_crs(ds, actual_x_variable)}"
                                                 f"{ds['Xc'].data.size}"
                                                 f"{ds['Yc'].data.size}"
                                                 f"{ds['Xc'][0].data}"
                                                 f"{ds['Xc'][-1].data}"
                                                 f"{ds['Yc'][0].data}"
                                                 f"{ds['Yc'][-1].data}").encode('UTF-8')).hexdigest()
    return unique_dataset_string

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
