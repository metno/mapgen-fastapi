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
import boto3
import logging
import botocore
import rasterio
import traceback
from fastapi import Request, Query, HTTPException, BackgroundTasks
from satpy import Scene
import mapscript
from glob import glob
from datetime import datetime

from mapgen.modules.helpers import handle_request

boto3.set_stream_logger('botocore', logging.CRITICAL)
boto3.set_stream_logger('boto3', logging.CRITICAL)

logger = logging.getLogger(__name__)

def _get_satpy_products(satpy_products, full_request, default_dataset):
    """Get the product list to handle."""
    # Default
    ms_satpy_products = [default_dataset]
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

async def generate_satpy_quicklook(netcdf_path: str,
                             full_request: Request,
                             background_task: BackgroundTasks,
                             satpy_products: list = Query(default=[]),
                             product_config: dict = {}):
    
    logger.debug(f"Request query_params: {str(full_request.query_params)}")
    logger.debug(f"Request url scheme: {full_request.url.scheme}")
    logger.debug(f"Request url netloc: {full_request.url.netloc}")
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if netcdf_path.startswith(product_config['base_netcdf_directory']):
            logger.debug(f"Request with full path. Please fix your request. Depricated from version 2.0.0.")
        elif os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        raise HTTPException(status_code=500, detail="Missing base dir in server config.")

    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")
    logger.debug(f"{satpy_products}")

    resolution = None
    bucket = product_config['geotiff_bucket']
    if 'mersi2-qk' in netcdf_path:
        resolution = 250
    elif 'mersi2-1k' in netcdf_path:
        resolution = 1000
    
    (_path, _platform_name, _, _start_time, _end_time) = _parse_filename(netcdf_path, product_config)
    start_time = datetime.strptime(_start_time, "%Y%m%d%H%M%S")
    similar_netcdf_paths = await _search_for_similar_netcdf_paths(_path, _platform_name, _start_time, _end_time, netcdf_path)
    logger.debug(f"Similar netcdf paths: {similar_netcdf_paths}")
    ms_satpy_products = _get_satpy_products(satpy_products, full_request, product_config['default_dataset'])
    logger.debug(f"satpy product/layer {ms_satpy_products}")

    satpy_products_to_generate = []
    for satpy_product in ms_satpy_products:

        satpy_product_filename = f'{satpy_product}-{start_time:%Y%m%d_%H%M%S}.tif'
        satpy_products_to_generate.append({'satpy_product': satpy_product,
                                           'satpy_product_filename': satpy_product_filename,
                                           'bucket': bucket})
    
    
    try:
        if not await _generate_satpy_geotiff(similar_netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
            raise HTTPException(status_code=500, detail=f"Some part of the generate failed.")
    except KeyError as ke:
        if 'Unknown datasets' in str(ke):
            raise HTTPException(status_code=500, detail=f"Layer can not be made for this dataset {str(ke)}")

    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(orig_netcdf_path, map_object, full_request)

    for satpy_product in satpy_products_to_generate:
        layer = mapscript.layerObj()
        await _generate_layer(start_time,
                        satpy_product['satpy_product'],
                        satpy_product['satpy_product_filename'],
                        satpy_product['bucket'],
                        layer)
        layer_no = map_object.insertLayer(layer)
    map_object.save(os.path.join(_get_mapfiles_path(product_config), f'satpy-products-{start_time:%Y%m%d%H%M%S}.map'))
    background_task.add_task(clean_data, map_object)
    return await handle_request(map_object, full_request)

async def clean_data(map_object):
    logger.debug(f"I need to clean some data to avoid memort stash")
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

async def _generate_layer(start_time, satpy_product, satpy_product_filename, bucket, layer):
    """Generate a layer based on the metadata from geotiff."""
    try:
        logger.debug(f"Rasterio open")
        dataset = rasterio.open(f's3://{bucket}/{start_time:%Y/%m/%d}/{satpy_product_filename}')
        logger.debug(f"Rasterio opened")
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
    dataset = None
    logger.debug(f"Complete generate layer")

def _fill_metadata_to_mapfile(orig_netcdf_path, map_object, full_request):
    """"Add all needed web metadata to the generated map file."""
    map_object.web.metadata.set("wms_title", "WMS senda fastapi")
    map_object.web.metadata.set("wms_onlineresource", f"{full_request.url.scheme}://{full_request.url.netloc}/api/get_quicklook{orig_netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:3857 EPSG:3978 EPSG:4269 EPSG:4326 EPSG:25832 EPSG:25833 EPSG:25835 EPSG:32632 EPSG:32633 EPSG:32635 EPSG:32661")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")
    map_object.setSize(10000, 10000)
    map_object.units = mapscript.MS_DD
    map_object.setExtent(-90, 20, 90, 90)

def _generate_key(start_time, satpy_product_filename):
    return os.path.join(f'{start_time:%Y/%m/%d}', os.path.basename(satpy_product_filename))

def _upload_geotiff_to_ceph(filenames, start_time, product_config):

    logger.debug(f"Upload: {str(filenames)}")
    s3_client = boto3.client(service_name='s3',
                             endpoint_url=os.environ['S3_ENDPOINT_URL'],
                             aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                             aws_secret_access_key=os.environ['S3_SECRET_KEY'])
    logger.debug(f"After client")
    try:
        for f in filenames:
            logger.debug(f"uploading {os.path.join(product_config.get('geotiff_tmp'), f['satpy_product_filename'])}")
            key = _generate_key(start_time, f['satpy_product_filename'])
            s3_client.upload_file(os.path.join(product_config.get('geotiff_tmp'), f['satpy_product_filename']), f['bucket'], key)
            s3_client.put_object_acl(Bucket=f['bucket'], Key=key, ACL='public-read')
            response = s3_client.head_object(Bucket=f['bucket'], Key=key)
            if response['ContentLength'] == 0:
                logger.error(f"object {f['bucket']}/{key} has size 0 after upload. This will cause problems. Deleting...")
                delete_response = s3_client.delete_object(Bucket=f['bucket'], Key=key)
                if delete_response['DeleteMarker']:
                    logger.error(f"object {f['bucket']}/{key} with size 0 has been deleted.")
                else:
                    logger.error(f"object {f['bucket']}/{key} failed to be deleted.")
            else:
                logger.debug(f"Successfully uploaded object {f['bucket']}/{key} with size {response['ContentLength']} bytes.")
            os.remove(os.path.join(product_config.get('geotiff_tmp'), f['satpy_product_filename']))
    except Exception as e:
        logger.debug(f"Failed to upload file to s3 {str(e)}")
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        raise HTTPException(status_code=500, detail="Failed to upload file to s3.")
    finally:
        s3_client.close()
    logger.debug(f"Done uploading")
    return True

def _exists_on_ceph(satpy_product, start_time):
    exists = False
    logger.debug(f"Start check exists")
    s3 = boto3.resource('s3',
                        endpoint_url=os.environ['S3_ENDPOINT_URL'],
                        aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                        aws_secret_access_key=os.environ['S3_SECRET_KEY'])

    try:
        logger.debug(f"Generate ceph bucket/prefix(object) key ...")
        key = _generate_key(start_time, satpy_product['satpy_product_filename'])
        logger.debug(f"load object ...")
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
        logger.debug(f"Already on object store")
        exists = True
    finally:
        del s3
        s3 = None
    return exists

async def _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
    """Generate and save geotiff to local disk in omerc based on actual area."""
    satpy_products = []
    for _satpy_product in satpy_products_to_generate:
        if not _exists_on_ceph(_satpy_product, start_time) and not os.path.exists(os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename'])):
            satpy_products.append(_satpy_product['satpy_product'])
    if not satpy_products:
        logger.debug(f"No products needs to be generated.")
        return True
    logger.debug(f"Need to generate: {satpy_products}")
    logger.debug(f"Before Scene")
    swath_scene = Scene(filenames=netcdf_paths, reader='satpy_cf_nc')
    logger.debug(f"Before load, resolution: {resolution}")
    swath_scene.load(satpy_products, resolution=resolution)
    logger.debug(f"Available composites names: {swath_scene.available_composite_names()}")
    proj_dict = {'proj': 'omerc',
                 'ellps': 'WGS84'}

    logger.debug(f"Before compute optimal bb area")
    try:
        bb_area = swath_scene.coarsest_area().compute_optimal_bb_area(proj_dict=proj_dict)
        logger.debug(f"{bb_area}")
        logger.debug(f"{bb_area.pixel_size_x}")
        logger.debug(f"{bb_area.pixel_size_y}")
    except KeyError:
        # Need a backup overview area if bb_area doesn't work
        logger.debug(f"Can not compute bb area. Use euro4 as backup.")
        bb_area = 'euro4'
    logger.debug(f"Before resample")
    resample_scene = swath_scene.resample(bb_area)
    logger.debug(f"Before save")
    products_to_upload_to_ceph = []
    for _satpy_product in satpy_products_to_generate:
        if _satpy_product['satpy_product'] in satpy_products:
            tmp_satpy_product_filename = '.' + _satpy_product['satpy_product_filename']
            resample_scene.save_dataset(_satpy_product['satpy_product'],
                                        filename=os.path.join(product_config.get('geotiff_tmp'),
                                                              tmp_satpy_product_filename),
                                        tiled=True,
                                        blockxsize=256, blockysize=256,
                                        overviews=[2, 4, 8, 16])
            if os.path.exists(os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename)):
                if not os.stat(os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename)).st_size:
                    logger.warning(f"file size 0 {os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename)}. Removing.")
                    os.remove(os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename))
                else:
                    os.rename(os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename),
                            os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename']))
            if os.path.exists(os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename'])):
                products_to_upload_to_ceph.append(_satpy_product)
    logger.debug(f"After save {str(products_to_upload_to_ceph)}")
    return_val = True
    if not products_to_upload_to_ceph or not _upload_geotiff_to_ceph(products_to_upload_to_ceph, resample_scene.start_time, product_config):
        return_val = False
    swath_scene.unload()
    resample_scene.unload()
    del swath_scene
    del bb_area
    del resample_scene
    swath_scene = None
    bb_area = None
    resample_scene = None
    return return_val

def _parse_filename(netcdf_path, product_config):
    """Parse the netcdf to return start_time."""
    pattern_match = product_config['pattern']
    pattern = re.compile(pattern_match)
    mtchs = pattern.match(netcdf_path)
    if mtchs:
        logger.debug(f"Pattern match: {mtchs.groups()}")
        return mtchs.groups()
    else:
        logger.debug(f"No match: {netcdf_path}")
        raise HTTPException(status_code=500, detail=f"No file name match: {netcdf_path}, match string {pattern_match}.")

async def _search_for_similar_netcdf_paths(path, platform_name, start_time, end_time, netcdf_path):
    if 'fy3d' in platform_name or 'aqua' in platform_name or 'terra' in platform_name:
        similar_netcdf_paths = [netcdf_path]
    else:
        similar_netcdf_paths = glob(f'{path}{platform_name}-*-{start_time}-{end_time}.nc')
    return similar_netcdf_paths
