"""
satellite thredds module : module
====================

Copyright 2022,2024 MET Norway

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
from satpy import Scene
import mapscript
from glob import glob
from datetime import datetime
#from urllib.parse import parse_qs

from mapgen.modules.helpers import handle_request
from mapgen.modules.helpers import _parse_request, HTTPError

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
            ms_satpy_products = full_request['layers']
        except KeyError:
            try:
                ms_satpy_products = full_request['LAYERS']
            except KeyError:
                try:
                    ms_satpy_products = full_request['layer']
                except KeyError:
                    try:
                        ms_satpy_products = full_request['LAYER']
                    except KeyError:
                        pass
    if not isinstance(ms_satpy_products, list):
        ms_satpy_products = [ms_satpy_products]
    return ms_satpy_products

def _get_mapfiles_path(regexp_pattern_module):
    return regexp_pattern_module['mapfiles_path']

def generate_satpy_quicklook(netcdf_path: str,
                             query_string: str,
                             http_host: str,
                             url_scheme: str,
                             satpy_products: list = [],
                             product_config: dict = {},
                             api = None):
    
    full_request = _parse_request(query_string)

    #full_request = parse_qs(query_string)
    logger.debug(f"Request query_params: {full_request}")
    logger.debug(f"Request url scheme: {url_scheme}")
    logger.debug(f"Request url netloc: {http_host}")
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if netcdf_path.startswith(product_config['base_netcdf_directory']):
            logger.debug(f"Request with full path. Please fix your request. Depricated from version 2.0.0.")
        elif os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        logger.error(f"status_code=500, Missing base dir in server config.")
        raise HTTPError(response_code='500 Internal Server Error', response="Missing base dir in server config.")

    logger.debug(f"{satpy_products}")

    resolution = None
    bucket = product_config['geotiff_bucket']
    if 'mersi2-qk' in netcdf_path:
        resolution = 250
    elif 'mersi2-1k' in netcdf_path:
        resolution = 1000
    
    (_path, _platform_name, _, _start_time, _end_time) = _parse_filename(netcdf_path, product_config)
    start_time = datetime.strptime(_start_time, "%Y%m%d%H%M%S")
    similar_netcdf_paths = _search_for_similar_netcdf_paths(_path, _platform_name, _start_time, _end_time, netcdf_path)
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
        if not _generate_satpy_geotiff(similar_netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
            logger.error(f"status_code=500, Some part of the generate failed.")
            raise HTTPError(response_code='500 Internal Server Error', response="Some part of the generate failed.")
    except KeyError as ke:
        if 'Unknown datasets' in str(ke):
            logger.error(f"status_code=500, Layer can not be made for this dataset {str(ke)}")
            raise HTTPError(response_code='500 Internal Server Error', response=f"Layer can not be made for this dataset {str(ke)}")

    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(orig_netcdf_path, map_object, url_scheme, http_host)

    for satpy_product in satpy_products_to_generate:
        layer = mapscript.layerObj()
        if _generate_layer(start_time,
                        satpy_product['satpy_product'],
                        satpy_product['satpy_product_filename'],
                        satpy_product['bucket'],
                        layer):
            layer_no = map_object.insertLayer(layer)
    map_object.save(os.path.join(_get_mapfiles_path(product_config), f'satpy-products-{start_time:%Y%m%d%H%M%S}.map'))
    return handle_request(map_object, query_string)

def _generate_layer(start_time, satpy_product, satpy_product_filename, bucket, layer):
    """Generate a layer based on the metadata from geotiff."""
    try:
        logger.debug(f"Rasterio open")
        dataset = rasterio.open(f's3://{bucket}/{start_time:%Y/%m/%d}/{satpy_product_filename}')
        logger.debug(f"Rasterio opened")
    except rasterio.errors.RasterioIOError:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        return False
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
    return True

def _fill_metadata_to_mapfile(orig_netcdf_path, map_object, url_scheme, netloc):
    """"Add all needed web metadata to the generated map file."""
    map_object.web.metadata.set("wms_title", "WMS senda fastapi")
    map_object.web.metadata.set("wms_onlineresource", f"{url_scheme}://{netloc}/api/get_quicklook{orig_netcdf_path}")
    map_object.web.metadata.set("wms_srs", "EPSG:3857 EPSG:3978 EPSG:4269 EPSG:4326 EPSG:25832 EPSG:25833 EPSG:25835 EPSG:32632 EPSG:32633 EPSG:32635 EPSG:32661")
    map_object.web.metadata.set("wms_enable_request", "*")
    map_object.setProjection("AUTO")
    map_object.setSize(10000, 10000)
    map_object.units = mapscript.MS_DD
    map_object.setExtent(-90, 20, 90, 90)

def _generate_key(start_time, satpy_product_filename):
    return os.path.join(f'{start_time:%Y/%m/%d}', os.path.basename(satpy_product_filename))

def _upload_geotiff_to_ceph(filenames, start_time, product_config):
    """Uploads the generated GeoTIFF files to the configured S3/CEPH object store.

    Args:
        filenames (list): A list of dictionaries, where each dictionary contains the following keys:
            - 'satpy_product_filename': The filename of the GeoTIFF file to be uploaded.
            - 'bucket': The name of the S3/CEPH bucket to upload the file to.
        start_time (datetime): The start time of the satellite data, used to generate the S3/CEPH object key.
        product_config (dict): A dictionary containing configuration options, including the path to the temporary GeoTIFF directory.

    Returns:
        bool: True if the upload was successful

    Raises:
        HTTPError: If there was an error uploading the file to S3/CEPH.
    """
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
        logger.error(f"status_code=500, Failed to upload file to s3.")
        raise HTTPError(response_code='500 Internal Server Error', response="Failed to upload file to s3.")
    finally:
        s3_client.close()
        del s3_client
        s3_client = None
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
        if e.response['Error']['Code'] == "403" or e.response['Error']['Code'] == "404":
            logger.debug(f"Failed to load object from s3 with code: {e.response['Error']['Code']}")
            logger.debug(f"With message {str(e)}")
            logger.debug("Assume object does not exist.")
            exists = False
        else:
            # Something else has gone wrong.
            logger.debug(f"With message {str(e)}")
            logger.debug("Assume object does not exist.")
            exists = False
    else:
        # The object does exist.
        logger.debug(f"Already on object store")
        exists = True
    finally:
        del s3
        s3 = None
    return exists

def _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
    """Generate and save geotiff to local disk in omerc based on actual area."""
    return_val = True
    satpy_products = []
    for _satpy_product in satpy_products_to_generate:
        if not _exists_on_ceph(_satpy_product, start_time) and not os.path.exists(os.path.join(product_config.get('geotiff_tmp'), _satpy_product['satpy_product_filename'])):
            satpy_products.append(_satpy_product['satpy_product'])
    if not satpy_products:
        logger.debug(f"No products needs to be generated.")
        return True
    logger.debug(f"Need to generate: {satpy_products} from {netcdf_paths}")
    logger.debug(f"Before Scene")
    try:
        swath_scene = Scene(filenames=netcdf_paths, reader='satpy_cf_nc')
    except (ValueError, OSError) as ve:
        traceback.print_exc()
        logger.error(f"Scene creation failed with: {str(ve)}")
        return False
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
    except ValueError:
        logger.error("Failed to compute optimal area. Several reasons could cause this. Please see previous log lines.")
        return_val = False
        return return_val
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
            if os.path.exists(os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename)):
                logger.warning(f"File {os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename)} "
                               "already exists locally. Probably after a previous failed generation. Need to delete "
                               "this file before saving again.")
                os.remove(os.path.join(product_config.get('geotiff_tmp'), tmp_satpy_product_filename))
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
        logger.error(f"status_code=500, No file name match: {netcdf_path}, match string {pattern_match}.")
        raise HTTPError(response_code='500 Internal Server Error', response=f"No file name match: {netcdf_path}, match string {pattern_match}.")

def _search_for_similar_netcdf_paths(path, platform_name, start_time, end_time, netcdf_path):
    if 'fy3d' in platform_name or 'aqua' in platform_name or 'terra' in platform_name:
        similar_netcdf_paths = [netcdf_path]
    else:
        similar_netcdf_paths = glob(f'{path}{platform_name}-*-{start_time}-{end_time}.nc')
    return similar_netcdf_paths
