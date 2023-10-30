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
import mapscript
import traceback
import xml.dom.minidom
from fastapi import HTTPException
from fastapi.responses import Response

import numpy as np
import xarray as xr
from cartopy import crs
import metpy # needed for xarray's metpy accessor

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
    try:
        ows_req.loadParamsFromURL(str(full_request.query_params))
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
        print("ALL query params: ", str(full_request.query_params))
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

    if requested_epsg == 4326:
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
