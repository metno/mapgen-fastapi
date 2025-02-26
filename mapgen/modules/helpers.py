"""
Helpers
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

import os
import re
import sys
import yaml
import hashlib
import logging
import datetime
import requests
import tempfile
import mapscript
import traceback
from osgeo import gdal
from lxml import etree
import xml.dom.minidom
from pyproj import CRS
from urllib.parse import parse_qs

import numpy as np
import xarray as xr
from cartopy import crs
import metpy # needed for xarray's metpy accessor
import pandas as pd

logger = logging.getLogger(__name__)

class HTTPError(Exception):
    def __init__(self, response_code='500 Internal Server Error', response=b'', content_type='text/plain'):
        self.response_code = response_code
        self.response = response.encode()
        self.content_type = content_type
 
    def __str__(self):
        return(repr(f"{self.response_code}: {self.response}"))
 
    
def _read_config_file(regexp_config_file):
    logger.debug(f"{regexp_config_file}")
    regexp_config = None
    try:
        if os.path.exists(regexp_config_file):
            with open(regexp_config_file) as f:
                regexp_config = yaml.load(f, Loader=yaml.loader.SafeLoader)
    except Exception as e:
        logger.debug(f"Failed to read yaml config: {regexp_config_file} with {str(e)}")
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
    content_type = 'text/plain'
    response = ''
    response_code = '200'
    if regexp_config:
        try:
            for url_path_regexp_pattern in regexp_config:
                logger.debug(f"{url_path_regexp_pattern}")
                pattern = re.compile(url_path_regexp_pattern['pattern'])
                if pattern.match(netcdf_path):
                    logger.debug(f"Got match. Need to load module: {url_path_regexp_pattern['module']}")
                    regexp_pattern_module = url_path_regexp_pattern
                    break
            else:
                logger.debug(f"Could not find any match for the path {netcdf_path} in the configuration file {regexp_config_file}.")
                logger.debug("Please review your config if you expect this path to be handled.")
            
        except Exception as e:
            logger.debug(f"Exception in the netcdf_path match part with {str(e)}")
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            response = f"Exception raised when regexp. Check the config."
            logger.error(response)
            response_code = '500 Internal Server Error'
    if not regexp_pattern_module:
        response = f"The server have no setup to handle the requested file {netcdf_path}. Check with the maintainers if this could be added."
        logger.error(response)
        response_code = '501 Not Implemented'

    return regexp_pattern_module, response.encode(), response_code, content_type

def handle_request(map_object, full_request):
    ows_req = mapscript.OWSRequest()
    ows_req.type = mapscript.MS_GET_REQUEST
    full_request_string = str(full_request)
    try:
        # Do some cleanup to the query string
        full_request_string = _query_string_cleanup(full_request_string)
        logger.debug(f"Full request string: {full_request_string}")
    except Exception as e:
        logger.error(f"status_code=500, failed to handle query parameters: {str(full_request)}, with error: {str(e)}")
        raise HTTPError(response_code='500 Internal Server Error',
                        response=f"failed to handle query parameters: {str(full_request)}, with error: {str(e)}")
    if 'request=getlegendgraphic' in full_request_string.lower():
        if not 'sld_version' in full_request_string.lower():
            logger.warning("requst is getlegendgraphic, but no sld_version is given. Add SLD_VERSION=1.1.0 to query.")
            full_request_string += '&SLD_VERSION=1.1.0'
    try:
        ows_req.loadParamsFromURL(full_request_string)
    except mapscript.MapServerError:
        ows_req = mapscript.OWSRequest()
        ows_req.type = mapscript.MS_GET_REQUEST
        pass
    if not full_request or (ows_req.NumParams == 1 and 'satpy_products' in full_request):
        logger.debug("Query params are empty or only contains satpy-product query parameter. Force getcapabilities")
        ows_req.setParameter("SERVICE", "WMS")
        ows_req.setParameter("VERSION", "1.3.0")
        ows_req.setParameter("REQUEST", "GetCapabilities")
    else:
        logger.debug(f"ALL query params: {full_request_string}")
    logger.debug(f"NumParams {ows_req.NumParams}")
    logger.debug(f"TYPE {ows_req.type}")
    if ows_req.getValueByName('REQUEST') != 'GetCapabilities':
        logger.debug(f"REQUEST is: {ows_req.getValueByName('REQUEST')}")
        mapscript.msIO_installStdoutToBuffer()
        try:
            _styles = str(ows_req.getValueByName("STYLES"))
            logger.debug(f"STYLES: {_styles}")
            if _styles.lower() in 'contour':
                ows_req.setParameter("STYLES", "")
            if _styles.lower() in 'wind_barbs':
                ows_req.setParameter("STYLES", "")
            if _styles.lower() in 'vector':
                ows_req.setParameter("STYLES", "")
            _style = str(ows_req.getValueByName("STYLE"))
            logger.debug(f"STYLE: {_style}")
            if _style.lower() in 'contour':
                ows_req.setParameter("STYLE", "")
            if _style.lower() in 'wind_barbs':
                ows_req.setParameter("STYLE", "")
            if _style.lower() in 'vector':
                ows_req.setParameter("STYLE", "")
        except TypeError:
            logger.debug("STYLES not in the request. Nothing to reset.")
            pass
        try:
            logger.debug(f"PWD {os.getcwd()}")
            map_object.OWSDispatch( ows_req )
        except Exception as e:
            logger.error(f"status_code=500, mapscript fails to parse query parameters: {str(full_request)}, with error: {str(e)}")
            raise HTTPError(response_code='500 Internal Server Error',
                            response=f"mapscript fails to parse query parameters: {str(full_request)}, with error: {str(e)}")
        content_type = mapscript.msIO_stripStdoutBufferContentType()
        result = mapscript.msIO_getStdoutBufferBytes()
        mapscript.msIO_resetHandlers()
    else:
        try:
            mapscript.msIO_installStdoutToBuffer()
            dispatch_status = map_object.OWSDispatch(ows_req)
        except Exception as e:
            logger.error(f"status_code=500, mapscript fails to parse query parameters: {str(full_request)}, with error: {str(e)}")
            raise HTTPError(response_code='500 Internal Server Error',
                            response=f"mapscript fails to parse query parameters: {str(full_request)}, with error: {str(e)}")
        if dispatch_status != mapscript.MS_SUCCESS:
            logger.debug(f"DISPATCH status {dispatch_status}")
        content_type = mapscript.msIO_stripStdoutBufferContentType()
        mapscript.msIO_stripStdoutBufferContentHeaders()
        _result = mapscript.msIO_getStdoutBufferBytes()

        if content_type == 'application/vnd.ogc.wms_xml; charset=UTF-8':
            content_type = 'text/xml'
        dom = xml.dom.minidom.parseString(_result)
        result = dom.toprettyxml(indent="", newl="").encode()
        mapscript.msIO_resetHandlers()
    logger.info(f"status_code=200, mapscript return successfully.")
    response_code = '200 OK'
    return response_code, result, content_type

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
        logger.debug(f"No rotation {projection}")
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

def _find_summary_from_csw(search_fname, forecast_time, scheme, netloc):
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
        logger.debug(f"CSW Search string {search_string}")
        #netloc = full_request.url.netloc
        if 's-enda' in netloc:
            netloc = netloc.replace("fastapi", "csw")
        else:
            netloc = 'csw.s-enda-dev.k8s.met.no'
        url = (f'{scheme}://{netloc}/?'
                'mode=opensearch&service=CSW&version=2.0.2&request=GetRecords&elementsetname=full&'
            f'typenames=csw:Record&resulttype=results&q={search_string}')
        try:
            xml_string = requests.get(url, timeout=10).text
        except requests.exceptions.Timeout:
            logger.debug("csw request timed out. Skip summary")
            return summary_text
        root = etree.fromstring(xml_string.encode('utf-8'))
        summarys = root.xpath('.//atom:summary', namespaces=root.nsmap)
        for summary in summarys:
            summary_text = summary.text
            break
    else:
        logger.debug("Not enough data to build CSW search_string for summary. Please add if applicable.")
    return summary_text

def _size_x_y(xr_dataset):
    x_l = ['x', 'X', 'Xc', 'xc', 'longitude', 'lon']
    y_l = ['y', 'Y', 'Yc', 'yc', 'latitude', 'lat']
    for x,y in zip(x_l, y_l):
        try:
            return xr_dataset.dims[x], xr_dataset.dims[y]
        except KeyError:
            pass
    logger.warning("Failed to find x and y dimensions in dataset use default 2000 2000")
    return 2000, 2000

def _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, scheme, netloc, xr_dataset, summary_cache, wms_title):
    """"Add all needed web metadata to the generated map file."""
    bn = os.path.basename(orig_netcdf_path)
    if bn not in summary_cache:
        summary = _find_summary_from_csw(bn, forecast_time, scheme, netloc)
        if summary:
            summary_cache[bn] = summary
            logger.debug(f"{summary_cache[bn]}")
        else:
            summary_cache[bn] = "Not Available."
    map_object.web.metadata.set("wms_title", wms_title)
    map_object.web.metadata.set("wms_onlineresource", f"{scheme}://{netloc}/api/get_quicklook{orig_netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:3857 EPSG:3978 EPSG:4269 EPSG:4326 EPSG:25832 EPSG:25833 EPSG:25835 EPSG:32632 EPSG:32633 EPSG:32635 EPSG:32661 EPSG:3575")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")

    # try:
    #     map_object.setSize(xr_dataset.dims['x'], xr_dataset.dims['y'])
    # except KeyError:
    #     try:
    #         map_object.setSize(xr_dataset.dims['X'], xr_dataset.dims['Y'])
    #     except KeyError:
    #         try:
    #             map_object.setSize(xr_dataset.dims['longitude'], xr_dataset.dims['latitude'])
    #         except KeyError:
    #             try:
    #                 map_object.setSize(xr_dataset.dims['Xc'], xr_dataset.dims['Yc'])
    #             except KeyError:
    #                 map_object.setSize(2000, 2000)
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
            logger.debug("Could not detect extent of dataset. Force full Earth.")
            map_object.setExtent(-180, -90, 180, 90)

    # Need to set size of map object after extent is set
    _x, _y = _size_x_y(xr_dataset)
    logger.debug(f"x and y dimensions in dataset {_x} {_y}")
    map_object.setSize(_x, _y)
    return

def _find_projection(ds, variable, grid_mapping_cache):
    # Find projection
    try:
        grid_mapping_name = ds[variable].attrs['grid_mapping']
        if grid_mapping_name not in grid_mapping_cache:
            cs = CRS.from_cf(ds[ds[variable].attrs['grid_mapping']].attrs)
            grid_mapping_cache[grid_mapping_name] = cs.to_proj4()
    except KeyError:
        logger.debug(f"no grid_mapping for variable {variable}. Try Compute.")
        try:
            optimal_bb_area, grid_mapping_name = _compute_optimal_bb_area_from_lonlat(ds, grid_mapping_cache)
            del optimal_bb_area
            optimal_bb_area = None
            logger.debug(f"GRID MAPPING NAME: {grid_mapping_name}")
        except (KeyError, ValueError):
            logger.debug(f"no grid_mapping for variable {variable} and failed to compute. Skip this.")
            return None
    return grid_mapping_name

def _extract_extent(ds, variable):
    """Extract extent of variable."""
    x_l = ['x', 'X', 'Xc', 'xc', 'longitude', 'lon']
    y_l = ['y', 'Y', 'Yc', 'yc', 'latitude', 'lat']
    for x, y in zip(x_l, y_l):
        try:

            ll_x = min(ds[variable].coords[x].data)
            ur_x = max(ds[variable].coords[x].data)
            ll_y = min(ds[variable].coords[y].data)
            ur_y = max(ds[variable].coords[y].data)
            return ll_x,ur_x,ll_y,ur_y
        except KeyError:
            pass
    logger.warning(f"Fail to detect dimmension names from hardcoded values. Try to find dim names from variable")
    dim_names = _find_dim_names(ds, variable)
    try:
        ll_x = min(ds[variable].coords[dim_names[0]].data)
        ur_x = max(ds[variable].coords[dim_names[0]].data)
        ll_y = min(ds[variable].coords[dim_names[1]].data)
        ur_y = max(ds[variable].coords[dim_names[1]].data)
        return ll_x,ur_x,ll_y,ur_y
    except KeyError:
        pass
    logger.debug(f"Failed to recognize extent of variable {variable}, valid is {x_l} and {y_l} or {dim_names}(found in dataset).")
    raise HTTPError(response_code='500 Internal Server Error', response=f"Could not recognize coords for {variable}. Valid for this service are {x_l} and {y_l} or {dim_names}(found in dataset).")

def _find_dim_names(ds, variable):
    dims = ds[variable].dims
    dim_names = []
    for dim in reversed(dims[1:]):
        dim_names.append(dim)
    return dim_names

    # try:
    #     ll_x = min(ds[variable].coords['x'].data)
    #     ur_x = max(ds[variable].coords['x'].data)
    #     ll_y = min(ds[variable].coords['y'].data)
    #     ur_y = max(ds[variable].coords['y'].data)
    # except KeyError:
    #     try:
    #         ll_x = min(ds[variable].coords['X'].data)
    #         ur_x = max(ds[variable].coords['X'].data)
    #         ll_y = min(ds[variable].coords['Y'].data)
    #         ur_y = max(ds[variable].coords['Y'].data)
    #     except KeyError:
    #         try:
    #             ll_x = min(ds[variable].coords['Xc'].data)
    #             ur_x = max(ds[variable].coords['Xc'].data)
    #             ll_y = min(ds[variable].coords['Yc'].data)
    #             ur_y = max(ds[variable].coords['Yc'].data)
    #         except KeyError:
    #             try:
    #                 ll_x = min(ds[variable].coords['longitude'].data)
    #                 ur_x = max(ds[variable].coords['longitude'].data)
    #                 ll_y = min(ds[variable].coords['latitude'].data)
    #                 ur_y = max(ds[variable].coords['latitude'].data)
    #             except KeyError as ke:
    #                 ll_x = min(ds[variable].coords['lon'].data)
    #                 ur_x = max(ds[variable].coords['lon'].data)
    #                 ll_y = min(ds[variable].coords['lat'].data)
    #                 ur_y = max(ds[variable].coords['lat'].data)

    #return ll_x,ur_x,ll_y,ur_y

def find_time_diff(ds, dim_name):
    prev = None
    diff = None
    prev_diff = None
    is_range = True
    diff_string = None
    if len(ds[dim_name].dt.year.data) == 1:
        logger.debug(f"Time diff len {len(ds[dim_name].dt.year.data)}")
        is_range = False
    else:
        for y,m,d,h,minute,s in zip(ds[dim_name].dt.year.data, ds[dim_name].dt.month.data, ds[dim_name].dt.day.data, ds[dim_name].dt.hour.data, ds[dim_name].dt.minute.data, ds[dim_name].dt.second.data):
            stamp = datetime.datetime(y, m, d, h, minute, s)
            if prev:
                diff = stamp - prev
                if prev_diff and diff >= datetime.timedelta(days=28) and diff <= datetime.timedelta(days=31) and prev + diff == stamp:
                    logger.debug(f"Possible monthly range: {prev} {stamp}")
                    diff = "P1M"
                elif prev_diff and diff != prev_diff:
                    logger.debug(f"DIFF {diff} PREV_DIFF {prev_diff}")
                    logger.debug(f"Stamp {stamp} PREV {prev}")
                    # Diff between more than three stamps are different. Can not use range.
                    is_range = False
                    break
                prev_diff = diff
            prev = stamp
    if is_range:
        diff_string = _get_time_diff(diff)
        logger.debug(f"DIFF STRING {diff_string}")
    else:
        logger.debug("Is not range")
    return diff,diff_string,is_range

def _get_time_diff(diff):
    if diff == 'P1M':
        diff_string = diff
    elif diff < datetime.timedelta(hours=1):
        h = int(diff.seconds/60)
        diff_string = f"PT{h}M"
    elif diff < datetime.timedelta(hours=24):
        h = int(diff.seconds/3600)
        diff_string = f"PT{h}H"
    else:
        diff_string = f"P{diff.days}D"
    return diff_string

def _compute_optimal_bb_area_from_lonlat(ds, grid_mapping_cache):
    resample = False
    if 'latitude' in ds and 'longitude' in ds:
        resample = True
        lat = 'latitude'
        lon = 'longitude'
    elif 'lat' in ds and 'lon' in ds:
        resample = True
        lat = 'lat'
        lon = 'lon'
    if resample:
        grid_mapping_name = "calculated_omerc"
        from pyresample import geometry
        try:
            swath_def = geometry.SwathDefinition(lons=ds[lon], lats=ds[lat])
            optimal = swath_def.compute_optimal_bb_area()
            grid_mapping_cache[grid_mapping_name] = optimal.proj_str
        except ValueError as ve:
            logger.exception(f"Failed to setup swath definition and or compute optimal bb area: {str(ve)}")
            raise ValueError
        return optimal, grid_mapping_name
    raise KeyError

def _read_netcdfs_from_ncml(ncml_file):
    # ncml_netcdf_files = []
    # xtree = etree.parse(netcdf_file)
    # for f in xtree.findall(".//{http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2}netcdf"):
    #     ncml_netcdf_files.append(f.attrib['location'])
    # Parse the XML content
    root = etree.parse(ncml_file).getroot()

    # Define the namespace
    ns = {'nc': 'http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2'}

    # Find the 'netcdf' elements
    netcdf_paths = []
    for netcdf in root.xpath('//nc:netcdf/nc:aggregation/nc:netcdf', namespaces=ns):
        netcdf_paths.append(netcdf.get('location'))
    return netcdf_paths

def _generate_getcapabilities(layer, ds, variable, grid_mapping_cache, netcdf_file, last_ds=None, netcdf_files=[], product_config=None):
    """Generate getcapabilities for the netcdf file."""
    grid_mapping_name = _find_projection(ds, variable, grid_mapping_cache)
    if grid_mapping_name == 'calculated_omerc' or not grid_mapping_name:
        # try make a generic bounding box from lat and lon if those exists
        try:
            optimal_bb_area, grid_mapping_name = _compute_optimal_bb_area_from_lonlat(ds, grid_mapping_cache)
            ll_x = optimal_bb_area.area_extent[0]
            ll_y = optimal_bb_area.area_extent[1]
            ur_x = optimal_bb_area.area_extent[2]
            ur_y = optimal_bb_area.area_extent[3]
            del optimal_bb_area
            optimal_bb_area = None
        except (KeyError, ValueError):
            return None
    else:
        ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)
        logger.debug(f"ll_x, ur_x, ll_y, ur_y {ll_x} {ur_x} {ll_y} {ur_y}")
    layer.setProjection(grid_mapping_cache[grid_mapping_name])
    if "units=km" in grid_mapping_cache[grid_mapping_name]:
        layer.units = mapscript.MS_KILOMETERS
    elif "units=m" in grid_mapping_cache[grid_mapping_name]:
        layer.units = mapscript.MS_METERS
    layer.status = 1
    layer.data = f'NETCDF:{netcdf_file}:{variable}'
    layer.type = mapscript.MS_LAYER_RASTER
    layer.name = variable
    wms_title = f"{variable}"
    try:
        wms_title += f": {ds[variable].attrs['long_name']}"
    except (AttributeError, KeyError):
        try:
            wms_title += f": {ds[variable].attrs['short_name']}"
        except (AttributeError, KeyError):
            pass
    logger.debug(f"wms_title {wms_title}")
    layer.metadata.set("wms_title", f"{wms_title}")

    ll_x, ll_y, ur_x, ur_y = _adjust_extent_to_units(ds, variable, grid_mapping_cache, grid_mapping_name, ll_x, ll_y, ur_x, ur_y)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
    dims_list = []
    if 'time' not in ds[variable].dims:
        logger.debug(f"variable {variable} do not contain time variable. wms_timeextent as dimension is not added.")
        # It makes no sense to add time dimension to a variable without timedimension. It can never be found.
        # Removed from code 2024-10-23
        # try:
        #     valid_time = datetime.datetime.fromisoformat(ds.time_coverage_start).strftime('%Y-%m-%dT%H:%M:%SZ')
        #     layer.metadata.set("wms_timeextent", f'{valid_time}')
        # except Exception:
        #     logger.debug("Could not use time_coverange_start global attribute. wms_timeextent is not added")

    for dim_name in ds[variable].dims:
        if dim_name in ['x', 'X', 'Xc', 'xc', 'y', 'Y', 'Yc', 'yc', 'longitude', 'latitude', 'lon', 'lat']:
            continue
        logger.debug(f"Checking dimension: {dim_name}")
        if dim_name in 'time':
            logger.debug("handle time")
            if netcdf_file.endswith('ncml'):
                logger.debug("Need to handle ncml time from all files.")
                last_time = pd.to_datetime(last_ds['time'].data).to_pydatetime()
                first_time = pd.to_datetime(ds['time'].data).to_pydatetime()
                diff = (last_time-first_time)/(len(netcdf_files)-1)
                if len(diff) == 1:
                    diff_string = _get_time_diff(diff[0])
                    start_time = first_time[0].strftime('%Y-%m-%dT%H:%M:%SZ')
                    end_time = last_time[0].strftime('%Y-%m-%dT%H:%M:%SZ')
                    layer.metadata.set("wms_timeextent", f'{start_time}/{end_time}/{diff_string}')
                else:
                    logger.error("Can not calucale wms timeextent in from ncml.")
            else:
                _, diff_string, is_range = find_time_diff(ds, dim_name)
                if is_range:
                    start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                    end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                    layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
                else:
                    logger.debug("Use time list.")
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
                    logger.debug("Rename getcapabilities height dimension to height_dimension.")
                    dim_name = dim_name + "_dimension"
                dims_list.append(dim_name)
                layer.metadata.set(f"wms_{dim_name}_item", dim_name)
                try:
                    layer.metadata.set(f"wms_{dim_name}_units", ds[actual_dim_name].attrs['units'])
                except KeyError:
                    logger.debug(f"Failed to set metadata units for dimmension name {dim_name}. Forcing to 1.")
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

def _adjust_extent_to_units(ds, variable, grid_mapping_cache, grid_mapping_name, ll_x, ll_y, ur_x, ur_y):
    dim_name = _find_dim_names(ds, variable)
    try:
        if "units=m" in grid_mapping_cache[grid_mapping_name]:
            if ds[variable].coords[dim_name[0]].attrs['units'] == 'km':
                logger.debug(f"adjust extent to units VARIBLE: {variable} {dim_name[0]} from km to m")
                ll_x *= 1000
                ur_x *= 1000
            if ds[variable].coords[dim_name[1]].attrs['units'] == 'km':
                logger.debug(f"adjust extent to units VARIBLE: {variable} {dim_name[1]} from km to m")
                ll_y *= 1000
                ur_y *= 1000
    except (KeyError, AttributeError, IndexError):
        logger.warning(f"Could not find units for variable {variable} dimension {dim_name}")
        pass
    return ll_x, ll_y, ur_x, ur_y

def _generate_getcapabilities_vector(layer, ds, variable, grid_mapping_cache, netcdf_file, direction_speed=False, last_ds=None, netcdf_files=[], product_config=None):
    """Generate getcapabilities for vector fiels for the netcdf file."""
    logger.debug("ADDING vector")
    grid_mapping_name = _find_projection(ds, variable, grid_mapping_cache)
    if grid_mapping_name == 'calculated_omerc' or not grid_mapping_name:
        # try make a generic bounding box from lat and lon if those exists
        try:
            optimal_bb_area, grid_mapping_name = _compute_optimal_bb_area_from_lonlat(ds, grid_mapping_cache)
            ll_x = optimal_bb_area.area_extent[0]
            ll_y = optimal_bb_area.area_extent[1]
            ur_x = optimal_bb_area.area_extent[2]
            ur_y = optimal_bb_area.area_extent[3]
            del optimal_bb_area
            optimal_bb_area = None
        except (KeyError, ValueError):
            return None
    else:
        ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, variable)

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
    try:
        layer.metadata.set("wms_title", f'{vector_variable_name} vector from {x_variable} and {y_variable} component')
    except UnboundLocalError:
        layer.metadata.set("wms_title", f'{vector_variable_name} vector from x and y component')
    if direction_speed:
        layer.name = f'{vector_variable_name}_vector_from_direction_and_speed'
        layer.metadata.set("wms_title", f'{vector_variable_name} vector from direction and speed')
    layer.setConnectionType(mapscript.MS_CONTOUR, "")
    ll_x, ll_y, ur_x, ur_y = _adjust_extent_to_units(ds, variable, grid_mapping_cache, grid_mapping_name, ll_x, ll_y, ur_x, ur_y)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
    dims_list = []
    if 'time' not in ds[variable].dims:
        try:
            valid_time = datetime.datetime.fromisoformat(ds.time_coverage_start).strftime('%Y-%m-%dT%H:%M:%SZ')
            layer.metadata.set("wms_timeextent", f'{valid_time}')
        except Exception:
            logger.debug("Could not use time_coverange_start global attribute. wms_timeextent is not added")
    for dim_name in ds[variable].dims:
        if dim_name in ['x', 'X', 'Xc', 'xc', 'y', 'Y', 'Yc', 'yc', 'longitude', 'latitude', 'lon', 'lat']:
            continue
        if dim_name in 'time':
            logger.debug("handle time")
            if netcdf_file.endswith('ncml'):
                logger.debug("Need to handle ncml time from all files.")
                last_time = pd.to_datetime(last_ds['time'].data).to_pydatetime()
                first_time = pd.to_datetime(ds['time'].data).to_pydatetime()
                diff = (last_time-first_time)/(len(netcdf_files)-1)
                if len(diff) == 1:
                    diff_string = _get_time_diff(diff[0])
                    start_time = first_time[0].strftime('%Y-%m-%dT%H:%M:%SZ')
                    end_time = last_time[0].strftime('%Y-%m-%dT%H:%M:%SZ')
                    layer.metadata.set("wms_timeextent", f'{start_time}/{end_time}/{diff_string}')
                else:
                    logger.error("Can not calucale wms timeextent in from ncml.")
            else:
                _, diff_string, is_range = find_time_diff(ds, dim_name)
                if is_range:
                    start_time = min(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                    end_time = max(ds[dim_name].dt.strftime('%Y-%m-%dT%H:%M:%SZ').data)
                    layer.metadata.set("wms_timeextent", f'{start_time:}/{end_time}/{diff_string}')
                else:
                    logger.debug("Use time list.")
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

    logger.debug("ADDing vector at end")

    return True

def _find_dimensions(ds, actual_variable, variable, qp, netcdf_file, last_ds):
    # Find available dimension not larger than 1
    dimension_search = []
    for dim_name in ds[actual_variable].dims:
        if dim_name in ['x', 'X', 'Xc', 'xc', 'y', 'Y', 'Yc', 'yc', 'longitude', 'latitude', 'lon', 'lat']:
            continue
        for _dim_name in [dim_name, f'dim_{dim_name}']:
            if _dim_name == 'height' or _dim_name == 'dim_height':
                logger.debug(f"Can not have a dimension name height as this will conflict with query parameter HEIGHT as the size in image.")
                _dim_name = _dim_name + '_dimension'
            logger.debug(f"search for dim_name {_dim_name} in query parameters.")
            if _dim_name in qp:
                logger.debug(f"Found dimension {_dim_name} in request")
                if dim_name == 'time':
                    _ds = {}
                    _ds['dim_name'] = dim_name
                    _ds['ds_size'] = ds[dim_name].data.size
                    requested_dimensions = datetime.datetime.strptime(qp[_dim_name], "%Y-%m-%dT%H:%M:%SZ")
                    time_as_band = 0
                    if last_ds and netcdf_file.endswith('ncml'):
                        logger.debug("Must find netcdf file for data")
                        ncml_netcdf_files = _read_netcdfs_from_ncml(netcdf_file)
                        last_time = pd.to_datetime(last_ds['time'].data).to_pydatetime()
                        first_time = pd.to_datetime(ds['time'].data).to_pydatetime()
                        diff = ((last_time-first_time)/(len(ncml_netcdf_files)-1))[0]
                        time_stamp = first_time[0]
                        for i in range(len(ncml_netcdf_files)):
                            logger.debug(f"Checking {time_as_band} {time_stamp.strftime('%Y-%m-%dT%H:%M:%SZ')} {requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ')}")
                            if time_stamp == requested_dimensions:
                                logger.debug(f"{time_stamp.strftime('%Y-%m-%dT%H:%M:%SZ')} {requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ')} {requested_dimensions.timestamp()}")
                                break
                            time_as_band += 1
                            time_stamp += diff
                    else:
                        try:
                            time_as_band = ds.indexes["time"].get_loc(requested_dimensions.strftime('%Y-%m-%d %H:%M:%S'))
                            logger.debug(f"{time_as_band} {requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ')} {requested_dimensions.timestamp()}")
                        except KeyError as ke:
                            logger.error(f"status_code=500, Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                            raise HTTPError(response_code='500 Internal Server Error', response=f"Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                        # for d in ds['time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ'):
                        #     logger.debug(f"Checking {time_as_band} {datetime.datetime.strptime(str(d.data), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp()} {d.data} {requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ')}")
                        #     if d == requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ'):
                        #         logger.debug(f"{d} {requested_dimensions.strftime('%Y-%m-%dT%H:%M:%SZ')} {requested_dimensions.timestamp()}")
                        #         break
                        #     time_as_band += 1
                        # else:
                        #     logger.error(f"status_code=500, Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                        #     raise HTTPError(response_code='500 Internal Server Error', response=f"Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                    _ds['selected_band_number'] = time_as_band
                    dimension_search.append(_ds)
                else:
                    logger.debug(f"other dimension {dim_name}")
                    _ds = {}
                    _ds['dim_name'] = dim_name
                    _ds['ds_size'] = ds[dim_name].data.size
                    selected_band_no = 0
                    for d in ds[dim_name].data:
                        logger.debug(f"compare dim value {d} to req value {qp[_dim_name]}")
                        if float(d) == float(qp[_dim_name]):
                            break
                        selected_band_no += 1
                    else:
                        logger.error(f"status_code=500, Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                        raise HTTPError(response_code='500 Internal Server Error', response=f"Could not find matching dimension {dim_name} {qp[_dim_name]} value for layer {variable}.")
                    _ds['selected_band_number'] = selected_band_no
                    dimension_search.append(_ds)
                break
            else:
                if ds[dim_name].data.size == 1:
                    logger.debug(f"Dimension with size 0 {dim_name}")
                    _ds = {}
                    _ds['dim_name'] = dim_name
                    _ds['ds_size'] = ds[dim_name].data.size
                    _ds['selected_band_number'] = 0
                    dimension_search.append(_ds)
                    break
        else:
            logger.debug(f"Could not find {_dim_name}. Make some ugly assumption")
            _ds = {}
            _ds['dim_name'] = dim_name
            _ds['ds_size'] = ds[dim_name].data.size
            _ds['selected_band_number'] = 0
            dimension_search.append(_ds)
    logger.debug(f"Dimension Search: {dimension_search}")
    return dimension_search

def _calc_band_number_from_dimensions(dimension_search):
    band_number = 0
    first = True
    logger.debug(f"Calculate band number from dimension: {dimension_search}")
    #dimension_search.reverse()
    for _ds in dimension_search[::-1]:
        if first:
            band_number += _ds['selected_band_number'] + 1
        else:
            band_number += _ds['selected_band_number']*prev_ds['ds_size']
        first = False
        prev_ds = _ds

    if band_number == 0 and len(dimension_search) == 0:
        logger.warning("Could not calculate band number from empty dimension search. Use 1.")
        band_number = 1
    logger.debug(f"selected band number {band_number}")
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

def _generate_layer(layer, ds, grid_mapping_cache, netcdf_file, qp, map_obj, product_config, wind_rotation_cache, last_ds=None):
    try:
        variable = qp['layer']
    except KeyError:
        variable = qp['layers']
    try:
        style = qp['styles']
    except KeyError:
        try:
            style = qp['style']
        except KeyError:
            logger.warning("Style is not in the request. This is mandatory, but I will set it to raster. This is maybe not what you want.")
            style = 'raster'
    if (variable.endswith("_vector") or variable.endswith("_vector_from_direction_and_speed")) and style == "":
        logger.debug("Empty style. Force wind barbs.")
        style = "Wind_barbs"
    elif style == "":
        logger.debug("Empty style. Force raster.")
        style = 'raster'
    logger.debug(f"Selected style: {style}")
    actual_variable = variable
    #if style in 'contour': #variable.endswith('_contour'):
    #    actual_variable = '_'.join(variable.split("_")[:-1])
    if variable.endswith('_vector'):
        actual_x_variable = '_'.join(['x'] + variable.split("_")[:-1])
        actual_y_variable = '_'.join(['y'] + variable.split("_")[:-1])
        vector_variable_name = variable
        actual_variable = actual_x_variable
        logger.debug(f"VECTOR {vector_variable_name} {actual_x_variable} {actual_y_variable}")
    if variable.endswith("_vector_from_direction_and_speed"):
        actual_x_variable = 'wind_speed'  # Not accurate, used to find crs and other proj info
        actual_y_variable = 'wind_direction'  # Not accurate, used to find crs and other proj info
        vector_variable_name = variable
        actual_variable = actual_x_variable
        logger.debug(f"VECTOR {vector_variable_name} {actual_x_variable} {actual_y_variable}")


    try:
        grid_mapping_name = _find_projection(ds, actual_variable, grid_mapping_cache)

        dimension_search = _find_dimensions(ds, actual_variable, variable, qp, netcdf_file, last_ds)
    except KeyError as ke:
        logger.error(f"status_code=500, Failed with: {str(ke)}.")
        raise HTTPError(response_code='500 Internal Server Error', response=f"Failed with: {str(ke)}.")
    except Exception as ke:
        logger.error(f"status_code=500, Failed with: {str(ke)}.")
        raise HTTPError(response_code='500 Internal Server Error', response=f"Failed with: {str(ke)}.")

    if grid_mapping_name == 'calculated_omerc':
        band_number = 1
    elif netcdf_file.endswith('ncml'):
        band_number = 0
        first = True
        for _ds in dimension_search[::-1]:
            if _ds['dim_name'] == 'time':
                continue
            if first:
                band_number += _ds['selected_band_number'] + 1
            else:
                band_number += _ds['selected_band_number']*prev_ds['ds_size']
            first = False
            prev_ds = _ds
        logger.debug(f"selected band number {band_number}")
    else:
        band_number = _calc_band_number_from_dimensions(dimension_search)
    if variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):
        layer.setProcessingKey('BANDS', f'1,2')
    else:
        layer.setProcessingKey('BANDS', f'{band_number}')

    set_scale_processing_key = False
    layer.setProjection(grid_mapping_cache[grid_mapping_name])

    if "units=km" in grid_mapping_cache[grid_mapping_name]:
        layer.units = mapscript.MS_KILOMETERS
    elif "units=m" in grid_mapping_cache[grid_mapping_name]:
        layer.units = mapscript.MS_METERS
    layer.status = 1
    if variable.endswith('_vector') or variable.endswith("_vector_from_direction_and_speed"):

        if netcdf_file.endswith('ncml'):
            logger.debug("Must find netcdf file for data")
            try:
                ncml_netcdf_files = _read_netcdfs_from_ncml(netcdf_file)
                logger.debug(f"Selected netcdf in list in ncml {ncml_netcdf_files[dimension_search[0]['selected_band_number']]}")
                ds = xr.open_dataset(ncml_netcdf_files[dimension_search[0]["selected_band_number"]], mask_and_scale=False)
            except Exception:
                logger.error("Failed to find and opne correct dataset from ncml file.")
        else:
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
                logger.debug("No scale_factor in attrs, Use 1.")
                scale_factor = 1.
            try:
                add_offset = ds['wind_speed'].attrs['add_offset']
            except KeyError:
                logger.debug("No add_offset in attrs. Use 0.")
                add_offset = 0.
            speed = ds['wind_speed'] * scale_factor + add_offset
            try:
                scale_factor = ds['wind_direction'].attrs['scale_factor']
            except KeyError:
                logger.debug("No scale_factor in attrs. Use 1.")
                scale_factor = 1.
            try:
                add_offset = ds['wind_direction'].attrs['add_offset']
            except KeyError:
                logger.debug("No add_offset in attrs. Use 0.")
                add_offset = 0.
            from_direction = ds['wind_direction'] * scale_factor + add_offset
        else:
            speed = _get_speed(ds[actual_x_variable],
                               ds[actual_y_variable],
                               f'{standard_name_prefix}_speed')
        # te = time.time()
        # logger.debug(f"_get_speed {te - ts}")
        # ts = time.time()
            from_direction = _get_from_direction(ds[actual_x_variable],
                                                 ds[actual_y_variable],
                                                 f'{standard_name_prefix}_from_direction')
        # te = time.time()
        # logger.debug(f"_from_direction {te - ts}")
        # ts = time.time()

            try:
                logger.debug(f"EPSG CRS: {qp['crs']}")
                requested_epsg = int(qp['crs'].split(':')[-1])
            except KeyError:
                requested_epsg = 4326
            logger.debug(f"{requested_epsg}")
            # Rotate wind direction, so it relates to the north pole, rather than to the grid's y direction.            
            unique_dataset_string = generate_unique_dataset_string(ds, actual_x_variable, requested_epsg)
            logger.debug(f"UNIQUE DS STRING {unique_dataset_string}")
            if unique_dataset_string in wind_rotation_cache:
                north = wind_rotation_cache[unique_dataset_string]
            else:
                north = _get_north(actual_x_variable, ds, requested_epsg)
                wind_rotation_cache[unique_dataset_string] = north
            # north = _get_north(actual_x_variable, ds, requested_epsg)
            # te = time.time()
            # logger.debug(f"_get_north {te - ts}")
            # ts = time.time()
            _rotate_relative_to_north(from_direction, north)
            # te = time.time()
            # logger.debug(f"_relative_to_north {te - ts}")
            # ts = time.time()

        new_x = np.cos((90. - from_direction - 180) * np.pi/180) * speed
        new_y = np.sin((90. - from_direction - 180) * np.pi/180) * speed
        ds_xy = xr.Dataset({})
        try:
            new_x.attrs['grid_mapping'] = ds[actual_x_variable].attrs['grid_mapping']
            new_y.attrs['grid_mapping'] = ds[actual_y_variable].attrs['grid_mapping']
            ds_xy[new_x.attrs['grid_mapping']] = ds[new_x.attrs['grid_mapping']]
        except KeyError:
            logger.debug("No grid mapping in dataset. Try use calculate.")
            if grid_mapping_name == 'calculated_omerc':
                from pyresample import geometry, kd_tree
                swath_def = geometry.SwathDefinition(lons=ds['longitude'], lats=ds['latitude'])
                optimal_bb_area = swath_def.compute_optimal_bb_area()
                cf_grid_mapping = 'oblique_mercator'
                new_x.attrs['grid_mapping'] = cf_grid_mapping
                new_y.attrs['grid_mapping'] = cf_grid_mapping
                ds_xy[new_x.attrs['grid_mapping']] = 0
                optimal_cf = optimal_bb_area.crs.to_cf()
                ds_xy[new_x.attrs['grid_mapping']].attrs['azimuth_of_central_line'] = optimal_cf['azimuth_of_central_line']
                ds_xy[new_x.attrs['grid_mapping']].attrs['latitude_of_projection_origin'] = optimal_cf['latitude_of_projection_origin']
                ds_xy[new_x.attrs['grid_mapping']].attrs['longitude_of_projection_origin'] = optimal_cf['longitude_of_projection_origin']
                ds_xy[new_x.attrs['grid_mapping']].attrs['scale_factor_at_projection_origin'] = optimal_cf['scale_factor_at_projection_origin']
                ds_xy[new_x.attrs['grid_mapping']].attrs['false_easting'] = optimal_cf['false_easting']
                ds_xy[new_x.attrs['grid_mapping']].attrs['false_northing'] = optimal_cf['false_northing']

                resampled_new_x = kd_tree.resample_nearest(swath_def, new_x.data, optimal_bb_area, radius_of_influence=10000000)
                resampled_new_y = kd_tree.resample_nearest(swath_def, new_y.data, optimal_bb_area, radius_of_influence=10000000)

                ds_new_x = xr.DataArray(resampled_new_x,
                                        attrs=ds[actual_x_variable].attrs,
                                        dims=['y', 'x'],
                                        coords=[('y', optimal_bb_area.projection_y_coords),
                                                ('x', optimal_bb_area.projection_x_coords)])
                ds_new_x.attrs['grid_mapping'] = cf_grid_mapping
                ds_new_y = xr.DataArray(resampled_new_y,
                                        attrs=ds[actual_y_variable].attrs,
                                        dims=['y', 'x'],
                                        coords=[('y', optimal_bb_area.projection_y_coords),
                                                ('x', optimal_bb_area.projection_x_coords)])
                ds_new_y.attrs['grid_mapping'] = cf_grid_mapping

        if grid_mapping_name == 'calculated_omerc':
            ds_xy[actual_x_variable] = ds_new_x
            ds_xy[actual_y_variable] = ds_new_y
            ds_xy['x'].attrs['long_name'] = "x-coordinate in Cartesian system"
            ds_xy['x'].attrs['standard_name'] = "projection_x_coordinate"
            ds_xy['x'].attrs['units'] = "m"
            ds_xy['y'].attrs['long_name'] = "y-coordinate in Cartesian system"
            ds_xy['y'].attrs['standard_name'] = "projection_y_coordinate"
            ds_xy['y'].attrs['units'] = "m"
        else:
            try:
                logger.debug(f"Droping vars: {new_x.dims} {len(new_x.dims)}")
                if len(new_x.dims) == 2:
                    ds_xy[actual_x_variable] = new_x
                else:
                    ds_xy[actual_x_variable] = new_x.drop_vars(['latitude', 'longitude'])
            except ValueError:
                logger.debug("Failing drop vars")
                ds_xy[actual_x_variable] = new_x
            try:
                if len(new_y.dims) == 2:
                    ds_xy[actual_y_variable] = new_y
                else:
                    ds_xy[actual_y_variable] = new_y.drop_vars(['latitude', 'longitude'])
            except ValueError:
                ds_xy[actual_y_variable] = new_y
        # te = time.time()
        # logger.debug(f"new dataset {te - ts}")
        # ts = time.time()
        # logger.debug(f"GRid mapping {new_x.attrs['grid_mapping']}")
        # logger.debug(f"{ds_xy}")
        # for netcdfs in glob.glob(os.path.join(_get_mapfiles_path(product_config), "netcdf-*")):
        #     shutil.rmtree(netcdfs)
        tmp_netcdf = os.path.join(tempfile.mkdtemp(prefix='netcdf-', dir=_get_mapfiles_path(product_config)),
                                  f"xy-{actual_x_variable}-{actual_y_variable}.nc")
        ds_xy.to_netcdf(tmp_netcdf)
        logger.debug(f"{tmp_netcdf}")
        # for vrts in glob.glob(os.path.join(_get_mapfiles_path(product_config), "vrt-*")):
        #     shutil.rmtree(vrts)

        xvar_vrt_filename = os.path.join(tempfile.mkdtemp(prefix='vrt-', dir=_get_mapfiles_path(product_config)),
                                         f"xvar-{actual_x_variable}-1.vrt")
        logger.debug(f"{xvar_vrt_filename}")
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
        # logger.debug(f"save and create vrts {te - ts}")
        layer.data = variable_file_vrt
    elif netcdf_file.endswith('ncml'):
        logger.debug("Must find netcdf file for data")
        try:
            ncml_netcdf_files = _read_netcdfs_from_ncml(netcdf_file)
            logger.debug(f"Selected netcdf in list in ncml {ncml_netcdf_files[dimension_search[0]['selected_band_number']]}")
            layer.data = f'NETCDF:{ncml_netcdf_files[dimension_search[0]["selected_band_number"]]}:{actual_variable}'
        except FileNotFoundError:
            logger.debug(f"Could not find the ncml xml input file {netcdf_file}.")
        except Exception:
            logger.error(f"status_code=500, Failed to parse ncml file to find individual file.")
            raise HTTPError(response_code='500 Internal Server Error', response=f"Failed to parse ncml file to find individual file.")

    elif grid_mapping_name == 'calculated_omerc':
        logger.debug("Try to resample data on the fly and using gdal vsimem.")
        from pyresample import kd_tree, geometry
        swath_def = geometry.SwathDefinition(lons=ds['longitude'], lats=ds['latitude'])
        optimal_bb_area = swath_def.compute_optimal_bb_area()
        resampled_variable = kd_tree.resample_nearest(swath_def, ds[actual_variable].data, optimal_bb_area, radius_of_influence=10000000)
        min_val = np.nanmin(resampled_variable)
        max_val = np.nanmax(resampled_variable)
        driver = gdal.GetDriverByName('GTiff')
        dst_ds = driver.Create(f'/vsimem/in_memory_output_{actual_variable}.tif',
                               optimal_bb_area.x_size,
                               optimal_bb_area.y_size,
                               1,
                               gdal.GDT_Float32)
        dst_ds.SetProjection(optimal_bb_area.crs_wkt)
        dst_ds.SetGeoTransform((optimal_bb_area.pixel_upper_left[0], optimal_bb_area.pixel_size_x, 0,
                                optimal_bb_area.pixel_upper_left[1], 0, -optimal_bb_area.pixel_size_y))
        dst_ds.GetRasterBand(1).WriteArray(resampled_variable)
        layer.data = f'/vsimem/in_memory_output_{actual_variable}.tif'
        set_scale_processing_key = True
        del dst_ds
        dst_ds = None
        del driver
        driver = None
        del resampled_variable
        resampled_variable = None
        del swath_def
        swath_def = None
    else:
        layer.data = f'NETCDF:{netcdf_file}:{actual_variable}'

    if style in 'contour':
        logger.debug("Style in contour for config")
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
                logger.debug(f"Unknown unit: {ds[actual_variable].attrs['units']}. contour interval may be of for {actual_variable}.")
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
        wms_title = f"{variable}"
        try:
            wms_title += f": {ds[variable].attrs['long_name']}"
        except (AttributeError, KeyError):
            try:
                wms_title += f": {ds[variable].attrs['short_name']}"
            except (AttributeError, KeyError):
                pass
        logger.debug(f"wms_title {wms_title}")
        layer.metadata.set("wms_title", f"{wms_title}")
    if grid_mapping_name == 'calculated_omerc':
        ll_x = optimal_bb_area.area_extent[0]
        ll_y = optimal_bb_area.area_extent[1]
        ur_x = optimal_bb_area.area_extent[2]
        ur_y = optimal_bb_area.area_extent[3]
        del optimal_bb_area
        optimal_bb_area = None
    else:
        ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, actual_variable)
    ll_x, ll_y, ur_x, ur_y = _adjust_extent_to_units(ds, actual_variable, grid_mapping_cache, grid_mapping_name, ll_x, ll_y, ur_x, ur_y)
    logger.debug(f"ll ur {ll_x} {ll_y} {ur_x} {ur_y}")
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
            logger.debug(f"Unknown style {style}. Check your request.")

        try:
            uv_spacing = qp['spacing']
        except KeyError:
            try:
                uv_spacing = qp['dim_spacing']
            except KeyError:
                uv_spacing = 12
        layer.setProcessingKey('UV_SPACING', str(uv_spacing)) #Default 32

    else:
        logger.debug(f"Dimmension search len {len(dimension_search)}")
        if len(dimension_search) == 0:
            logger.debug("Len 0")
            min_val = np.nanmin(ds[actual_variable][:,:].data)
            max_val = np.nanmax(ds[actual_variable][:,:].data)
        elif len(dimension_search) == 1:
            logger.debug(f"Len 1 of {actual_variable}")
            min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
            max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
            if '_FillValue' in ds[actual_variable].attrs:
                if min_val == ds[actual_variable].attrs['_FillValue']:
                    logger.debug(f"Need to rescale min_val {min_val} due to fillvalue, FILLVALUE {ds[actual_variable].attrs['_FillValue']}")
                    masked_fillvalue = np.ma.masked_equal(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data,
                                                    ds[actual_variable].attrs['_FillValue'], copy=False)
                    min_val = masked_fillvalue.min()
                if max_val == ds[actual_variable].attrs['_FillValue']:
                    logger.debug(f"Need to rescale max_val {max_val} due to fillvalue, FILLVALUE {ds[actual_variable].attrs['_FillValue']}")
                    masked_fillvalue = np.ma.masked_equal(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data,
                                                    ds[actual_variable].attrs['_FillValue'], copy=False)
                    max_val = masked_fillvalue.max()
        elif len(dimension_search) == 2:
            logger.debug(f"Len 2 of {actual_variable}")
            try:
                min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
                max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
                if '_FillValue' in ds[actual_variable].attrs:
                    if min_val == ds[actual_variable].attrs['_FillValue']:
                        logger.debug(f"Need to rescale min_val {min_val} due to fillvalue, FILLVALUE {ds[actual_variable].attrs['_FillValue']}")
                        masked_fillvalue = np.ma.masked_equal(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data,
                                                      ds[actual_variable].attrs['_FillValue'], copy=False)
                        min_val = masked_fillvalue.min()
                    if max_val == ds[actual_variable].attrs['_FillValue']:
                        logger.debug(f"Need to rescale max_val {max_val} due to fillvalue, FILLVALUE {ds[actual_variable].attrs['_FillValue']}")
                        masked_fillvalue = np.ma.masked_equal(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data,
                                                      ds[actual_variable].attrs['_FillValue'], copy=False)
                        max_val = masked_fillvalue.max()
            except IndexError:
                ncml_netcdf_files = _read_netcdfs_from_ncml(netcdf_file)
                with xr.open_dataset(ncml_netcdf_files[dimension_search[0]["selected_band_number"]], mask_and_scale=False) as ds_actual:
                    min_val = np.nanmin(ds_actual[actual_variable][0,dimension_search[1]['selected_band_number'],:,:].data)
                    max_val = np.nanmax(ds_actual[actual_variable][0,dimension_search[1]['selected_band_number'],:,:].data)
        # Find which band
        elif len(dimension_search) == 3:
            logger.debug("Len 3")
            min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
            max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
        elif not dimension_search:
            logger.debug("Dimension search empty. Possible calculated field.")
        else:
            logger.error(f"Could not estimate or read min and/or max val of dataset: {actual_variable}")
        try:
            logger.debug(f"MIN:MAX {min_val} {max_val}")
        except UnboundLocalError as le:
            logger.error(f"status_code=500, Failed with: {str(le)}.")
            raise HTTPError(response_code='500 Internal Server Error', response=f"Unspecified internal server error.")
        #Grayscale
        if style in 'contour': #variable.endswith('_contour'):
            logger.debug("Style in contour for style setup.")
            layer.labelitem = 'contour'
            s = mapscript.classObj(layer)
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
                    logger.debug(f"Unknown unit: {ds[actual_variable].attrs['units']}. Label scaling may be of for {actual_variable}.")
                logger.debug(f"Selected label scale {label_scaling} and offset {label_offset}")
            except KeyError:
                pass
            label.setText(f'(tostring(({label_offset}+[contour]/{label_scaling}),"%.0f"))')
            label.color = mapscript.colorObj(red=0, green=0, blue=255)
            #label.font = 'sans'
            # TYPE truetype
            label.size = 10
            label.position = mapscript.MS_CC
            label.force = True
            label.angle = 0 #mapscript.MS_AUTO
            logger.debug(f"{label.convertToString()}")
            s.addLabel(label)
        elif style == 'raster':
            cfa, min_val, max_val = _colormap_from_attribute(ds, actual_variable, layer, min_val, max_val, set_scale_processing_key)
            if not cfa:
                # Use standard linear grayscale
                s = mapscript.classObj(layer)
                s.name = "Linear grayscale using min and max not nan from data"
                s.group = 'raster'
                _style = mapscript.styleObj(s)
                _style.rangeitem = 'pixel'
                _style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
                _style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
                _style.minvalue = float(min_val)
                _style.maxvalue = float(max_val)
            logger.debug(f"After colormap min max {min_val} {max_val}")

    return actual_variable

def _colormap_from_attribute(ds, actual_variable, layer, min_val, max_val, set_scale_processing_key):
    import importlib
    return_val = False
    colormap_dict = {}
    try:
        logger.debug(f"module to load {ds[actual_variable].colormap.split('.')[0]}")
        loaded_module = importlib.import_module(ds[actual_variable].colormap.split(".")[0])
        cm = getattr(loaded_module, 'cm')
        tools = getattr(loaded_module, 'tools')
        colormap = getattr(cm, ds[actual_variable].colormap.split(".")[-1])
        colormap_dict = tools.get_dict(colormap, N=32)
    except ModuleNotFoundError:
        logger.debug(f"Module {ds[actual_variable].colormap} not found. Use build in default.")
        return return_val, min_val, max_val
    except AttributeError as ae:
        logger.debug(f"Attribute not found: {str(ae)}")
        pass
    except Exception:
        raise
    try:
        minmax = ds[actual_variable].minmax.split(' ')
        try:
            logger.debug(f"add_offset {ds[actual_variable].add_offset}")
            min_val = float(minmax[0]) - ds[actual_variable].add_offset
            max_val = float(minmax[1]) - ds[actual_variable].add_offset
        except Exception:
            pass
        try:
            logger.debug(f"scale_factor {ds[actual_variable].scale_factor}")
            min_val = min_val/ds[actual_variable].scale_factor
            max_val = max_val/ds[actual_variable].scale_factor
        except Exception:
            pass

        logger.debug(f"Using from minmax min max {min_val} {max_val}")
        if set_scale_processing_key:
            logger.debug("Setting mapserver processing scale and buckets")
            layer.setProcessingKey('SCALE', f'{min_val:0.1f},{max_val:0.1f}')
            layer.setProcessingKey('SCALE_BUCKETS', '32')
    except AttributeError as ae:
        logger.debug(f"Attribute not found: {str(ae)}. Using calculated min max.")
        logger.debug(f"Using from calculation min max {min_val} {max_val}")
    except Exception:
        raise
    try:
        units = ds[actual_variable].units
    except AttributeError as ae:
        logger.debug(f"Attribute not found: {str(ae)}. No units.")
        units = ""
    if colormap_dict:
        try:
            vals = np.linspace(min_val, max_val, num=33)
            prev_val = vals[0]
            index = 0
            for val in vals[1:]:
                s = mapscript.classObj(layer)
                s.name = f"{ds[actual_variable].colormap} [{prev_val:0.1f}, {val:0.1f}> {units}"
                s.group = 'raster'
                s.setExpression(f'([pixel]>={prev_val:0.1f} and [pixel]<{val:0.1f})')
                _style = mapscript.styleObj(s)
                _style.color = mapscript.colorObj(red=int(colormap_dict['red'][index][1]*256),
                                                green=int(colormap_dict['green'][index][1]*256),
                                                blue=int(colormap_dict['blue'][index][1]*256))
                prev_val = val
                index += 1
            return_val = True
        except AttributeError as ae:
            logger.debug(f"Attribute not found: {str(ae)}")
        except Exception:
            raise

    return return_val, min_val, max_val

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
        logger.debug(f"Pattern match: {mtchs.groups()}")
        return mtchs.groups()
    else:
        logger.error(f"status_code=500, No file name match: {netcdf_path}, match string {pattern_match}.")
        raise HTTPError(response_code='500 Internal Server Error', response=f"No file name match: {netcdf_path}, match string {pattern_match}.")

def _get_mapfiles_path(regexp_pattern_module):
    try:
        return regexp_pattern_module['mapfiles_path']
    except KeyError:
        return "./"

def _parse_request(query_string):
    query_string = _query_string_cleanup(query_string)
    full_request = parse_qs(query_string)

    qp = {k.lower(): v for k, v in full_request.items()}
    logger.debug(f"QP: {qp}")
    qp = {k if (isinstance(v, list) and len(v) == 1) else k:v[0] for k,v in qp.items()}
    logger.debug(f"QP after flatten lists {qp}")
    return qp

def _query_string_cleanup(query_string):
    query_string = query_string.replace("&amp%3b", "&")
    query_string = query_string.replace("&amp%3B", "&")
    query_string = query_string.replace("&amp;", "&")
    query_string = query_string.replace("%3D", "=")
    query_string = query_string.replace("%3d", "=")
    query_string = query_string.replace("%3F", "?")
    query_string = query_string.replace("%3f", "?")
    query_string = query_string.replace("?", "&")
    return query_string
