"""
satellite thredds module : module
====================

Copyright 2022 MET Norway

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
import boto3
import botocore
import rasterio
import traceback
from fastapi.responses import HTMLResponse, FileResponse, Response
# from fastapi import Request, Query, APIRouter, status
from fastapi import Request, APIRouter, Query, HTTPException
from satpy import Scene
import mapscript
from glob import glob
from datetime import datetime
import xml.dom.minidom

router = APIRouter()

def _get_satpy_products(satpy_products, full_request):
    """Get the product list to handle."""
    # Default
    ms_satpy_products = ['overview']
    # ms_satpy_products = ['night_overview']
    if satpy_products:
        ms_satpy_products = satpy_products
    else:
        try:
            ms_satpy_products = [full_request.query_params['layers']]
        except KeyError:
            try:
                ms_satpy_products = [full_request.query_params['LAYERS']]
            except KeyError:
                try:
                    ms_satpy_products = [full_request.query_params['layer']]
                except KeyError:
                    try:
                        ms_satpy_products = [full_request.query_params['LAYER']]
                    except KeyError:
                        pass
    return ms_satpy_products

def _get_mapfiles_path(regexp_pattern_module):
    return regexp_pattern_module['mapfiles_path']

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

def _parse_config(netcdf_path):
    default_regexp_config_file = '/config/url-path-regexp-patterns.yaml'
    regexp_config_file = default_regexp_config_file
    regexp_config = _read_config_file(regexp_config_file)
    if regexp_config:
        regexp_pattern_module = None
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
    else:
        regexp_pattern_module = {'mapfiles_path': '.',
                                 'geotiff_tmp': '.'}
    if not regexp_pattern_module:
        raise HTTPException(status_code=501, detail=f"Could not match against any pattern. Check the config.")

    return regexp_pattern_module

@router.get("/api/get_quicklook/{netcdf_path:path}", response_class=Response)
async def generate_satpy_quicklook(netcdf_path: str,
                                   full_request: Request,
                                   satpy_products: list = Query(default=[])):
    
    print(f'{netcdf_path}')
    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")
    print(satpy_products)
    product_config = _parse_config(netcdf_path)
    
    (_path, _platform_name, _, _start_time, _end_time) = _parse_filename(netcdf_path)
    start_time = datetime.strptime(_start_time, "%Y%m%d%H%M%S")
    similar_netcdf_paths = _search_for_similar_netcdf_paths(_path, _platform_name, _start_time, _end_time)
    print("Similar netcdf paths:", similar_netcdf_paths)
    ms_satpy_products = _get_satpy_products(satpy_products, full_request)
    print("satpy product/layer", ms_satpy_products)

    bucket = 'geotiff-products-for-senda'
    if 'iband' in netcdf_path:
        bucket = 'geotiff-products-for-senda-iband'
    elif 'dnb' in netcdf_path:
        bucket = 'geotiff-products-for-senda-dnb'
    elif 'modis-qkm' in netcdf_path:
        bucket = 'geotiff-products-for-senda-modis-qkm'
    elif 'modis-hkm' in netcdf_path:
        bucket = 'geotiff-products-for-senda-modis-hkm'
    elif 'mersi2-qk' in netcdf_path:
        bucket = 'geotiff-products-for-senda-mersi2-qk'

    satpy_products_to_generate = []
    for satpy_product in ms_satpy_products:

        satpy_product_filename = f'{satpy_product}-{start_time:%Y%m%d%H%M%S}.tif'
        satpy_products_to_generate.append({'satpy_product': satpy_product,
                                           'satpy_product_filename': satpy_product_filename,
                                           'bucket': bucket})
    
    
    try:
        if not _generate_satpy_geotiff(similar_netcdf_paths, satpy_products_to_generate, start_time, product_config):
            raise HTTPException(status_code=500, detail=f"Some part of the generate failed.")
    except KeyError as ke:
        if 'Unknown datasets' in str(ke):
            raise HTTPException(status_code=500, detail=f"Layer can not be made for this dataset {str(ke)}")

    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(netcdf_path, map_object)

    for satpy_product in satpy_products_to_generate:
        layer = mapscript.layerObj()
        _generate_layer(start_time,
                        satpy_product['satpy_product'],
                        satpy_product['satpy_product_filename'],
                        satpy_product['bucket'],
                        layer)
        layer_no = map_object.insertLayer(layer)
    map_object.save(os.path.join(_get_mapfiles_path(product_config), f'satpy-products-{start_time:%Y%m%d%H%M%S}.map'))

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
        map_object.OWSDispatch( ows_req )
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

def _generate_layer(start_time, satpy_product, satpy_product_filename, bucket, layer):
    """Generate a layer based on the metadata from geotiff."""
    try:
        dataset = rasterio.open(f's3://{bucket}/{start_time:%Y/%m/%d}/{satpy_product_filename}')
    except rasterio.errors.RasterioIOError:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        return None
    bounds = dataset.bounds
    ll_x = bounds[0]
    ll_y = bounds[1]
    ur_x = bounds[2]
    ur_y = bounds[3]

    layer.setProjection(dataset.crs.to_proj4())
    layer.status = 1
    layer.data = f'/vsis3/{bucket}/{start_time:%Y/%m/%d}/{satpy_product_filename}'
    layer.type = mapscript.MS_LAYER_RASTER
    layer.name = satpy_product
    layer.metadata.set("wms_title", satpy_product)
    layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")
    layer.metadata.set("wms_timeextent", f'{start_time:%Y-%m-%dT%H:%M:%S}Z/{start_time:%Y-%m-%dT%H:%M:%S}Z')
    layer.metadata.set("wms_default", f'{start_time:%Y-%m-%dT%H:%M:%S}Z')
    dataset.close()

def _fill_metadata_to_mapfile(netcdf_path, map_object):
    """"Add all needed web metadata to the generated map file."""
    map_object.web.metadata.set("wms_title", "WMS senda fastapi localhost")
    map_object.web.metadata.set("wms_onlineresource", f"http://localhost:9000/api/get_quicklook/{netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:25833 EPSG:3978 EPSG:4326 EPSG:4269 EPSG:3857")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")
    map_object.setSize(10000, 10000)
    map_object.units = mapscript.MS_DD
    map_object.setExtent(-90, 20, 90, 90)

def _generate_key(start_time, satpy_product_filename):
    return os.path.join(f'{start_time:%Y/%m/%d}', os.path.basename(satpy_product_filename))

def _upload_geotiff_to_ceph(filenames, start_time, product_config):

    print("Upload:", str(filenames))
    s3_client = boto3.client(service_name='s3',
                             endpoint_url=os.environ['S3_ENDPOINT_URL'],
                             aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                             aws_secret_access_key=os.environ['S3_SECRET_KEY'])
    print("After client")
    try:
        for f in filenames:
            print(f"uploading {os.path.join(product_config.get('geotiff_tmp'), f['satpy_product_filename'])}")
            key = _generate_key(start_time, f['satpy_product_filename'])
            s3_client.upload_file(os.path.join(product_config.get('geotiff_tmp'), f['satpy_product_filename']), f['bucket'], key)
            s3_client.put_object_acl(Bucket=f['bucket'], Key=key, ACL='public-read')
    except Exception as e:
        print("Failed to upload file to s3", str(e))
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        raise HTTPException(status_code=500, detail="Failed to upload file to s3.")
    print("Done uploading")
    return True

def _exists_on_ceph(satpy_product, start_time):
    exists = False
    s3 = boto3.resource('s3',
                        endpoint_url=os.environ['S3_ENDPOINT_URL'],
                        aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                        aws_secret_access_key=os.environ['S3_SECRET_KEY'])

    try:
        key = _generate_key(start_time, satpy_product['satpy_product_filename'])
        s3.Object(satpy_product['bucket'], key).load()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            exists = False
        else:
            # Something else has gone wrong.
            exists = False
            raise
    else:
        # The object does exist.
        print("Already on object store")
        exists = True
    return exists

def _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, start_time, product_config):
    """Generate and save geotiff to local disk in omerc based on actual area."""
    satpy_products = []
    for _satpy_product in satpy_products_to_generate:
        if not _exists_on_ceph(_satpy_product, start_time) and not os.path.exists(os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename'])):
            satpy_products.append(_satpy_product['satpy_product'])
    if not satpy_products:
        print("No products needs to be generated.")
        return True
    print("Need to generate: ", satpy_products)
    print(datetime.now(), "Before Scene")
    swath_scene = Scene(filenames=netcdf_paths, reader='satpy_cf_nc')
    print(datetime.now(), "Before load")
    swath_scene.load(satpy_products)
    print("Available composites names:", swath_scene.available_composite_names())
    proj_dict = {'proj': 'omerc',
                 'ellps': 'WGS84'}

    print(datetime.now(), "Before compute optimal bb area")
    #bb_area = swath_scene.coarsest_area().compute_optimal_bb_area(proj_dict=proj_dict, resolution=7500)
    bb_area = swath_scene.coarsest_area().compute_optimal_bb_area(proj_dict=proj_dict)
    print(bb_area)
    print(bb_area.pixel_size_x)
    print(bb_area.pixel_size_y)
    
    print(datetime.now(), "Before resample")
    resample_scene = swath_scene.resample(bb_area)
    print(datetime.now(), "Before save")
    products_to_upload_to_ceph = []
    for _satpy_product in satpy_products_to_generate:
        if _satpy_product['satpy_product'] in satpy_products:
            resample_scene.save_dataset(_satpy_product['satpy_product'], filename=os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename']))
            if os.path.exists(os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename'])):
                products_to_upload_to_ceph.append(_satpy_product)
    print(datetime.now(), "After save", str(products_to_upload_to_ceph))
    if not _upload_geotiff_to_ceph(products_to_upload_to_ceph, resample_scene.start_time, product_config):
        return False
    return True

def _parse_filename(netcdf_path):
    """Parse the netcdf to return start_time."""
    pattern_match = '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(metopa|metopb|metopc|noaa18|noaa19|noaa20|npp|aqua|terra|fy3d)-(avhrr|viirs-mband|viirs-dnb|modis-1km|mersi2-1k)-(\d{14})-(\d{14})\.nc$'
    pattern = re.compile(pattern_match)
    mtchs = pattern.match(netcdf_path)
    # start_time = None
    if mtchs:
        print("Pattern match:", mtchs.groups())
        # start_time = datetime.strptime(mtchs.groups()[5], "%Y%m%d%H%M%S")
        return mtchs.groups()
    else:
        print("No match: ", netcdf_path)
        raise HTTPException(status_code=500, detail=f"No file name match: {netcdf_path}, match string {pattern_match}")
    return None

def _search_for_similar_netcdf_paths(path, platform_name, start_time, end_time):
    similar_netcdf_paths = glob(f'{path}{platform_name}-*-{start_time}-{end_time}.nc')
    return similar_netcdf_paths

@router.get("/{image_path:path}")
async def main(image_path: str):
    """Need this to local images"""
    print("image path:", image_path)
    print("CWD: ", os.getcwd())
    return FileResponse(image_path)
