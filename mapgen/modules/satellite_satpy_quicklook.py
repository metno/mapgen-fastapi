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
import rasterio
from fastapi.responses import HTMLResponse, FileResponse, Response
# from fastapi import Request, Query, APIRouter, status
from fastapi import Request, APIRouter, Query
from satpy import Scene
import mapscript
import math
from datetime import datetime
import xml.dom.minidom

router = APIRouter()

def _get_satpy_products(satpy_products, full_request):
    """Get the product list to handle."""
    # Default
    ms_satpy_products = ['overview']
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

@router.get("/api/get_quicklook/{netcdf_path:path}", response_class=Response)
async def generate_satpy_quicklook(netcdf_path: str,
                                   full_request: Request,
                                   satpy_products: list = Query(default=[])):
    
    print(f'{netcdf_path}')
    print(satpy_products)
    start_time = _parse_filename(netcdf_path)
    print(start_time)
    ms_satpy_products = _get_satpy_products(satpy_products, full_request)
    print("satpy product/layer", ms_satpy_products)

    satpy_products_to_generate = []
    for satpy_product in ms_satpy_products:
        satpy_product_filename = f'{satpy_product}-{start_time:%Y%m%d%H%M%S}.tif'
        satpy_products_to_generate.append({'satpy_product': satpy_product, 'satpy_product_filename': satpy_product_filename} )
    
    _generate_satpy_geotiff(netcdf_path, satpy_products_to_generate)
 
    map_object = mapscript.mapObj()
    _fill_metadata_to_mapfile(netcdf_path, map_object)

    for satpy_product in satpy_products_to_generate:
        layer = mapscript.layerObj()
        _generate_layer(start_time, satpy_product['satpy_product'],
                        satpy_product['satpy_product_filename'], layer)
        layer_no = map_object.insertLayer(layer)
    map_object.save(f'satpy-products-{start_time:%Y%m%d%H%M%S}.map')

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
        print(type(full_request.query_params))
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

def _generate_layer(start_time, satpy_product, satpy_product_filename, layer):
    """Generate a layer based on the metadata from geotiff."""
    dataset = rasterio.open(satpy_product_filename)
    bounds = dataset.bounds
    ll_x = bounds[0]
    ll_y = bounds[1]
    ur_x = bounds[2]
    ur_y = bounds[3]

    layer.setProjection(dataset.crs.to_proj4())
    layer.status = 1
    layer.data = satpy_product_filename
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

def _generate_satpy_geotiff(netcdf_path, satpy_products_to_generate):
    """Generate and save geotiff to local disk in omerc based on actual area."""
    satpy_products = []
    for _satpy_product in satpy_products_to_generate:
        if not os.path.exists(_satpy_product['satpy_product_filename']):
            satpy_products.append(_satpy_product['satpy_product'])
    if not satpy_products:
        print("No products needs to be generated.")
        return
    print("Need to generate: ", satpy_products)
    print(datetime.now(), "Before Scene")
    swath_scene = Scene(filenames=[netcdf_path], reader='satpy_cf_nc')
    print(datetime.now(), "Before load")
    swath_scene.load(satpy_products)
    print(swath_scene.available_composite_names())
    proj_dict = {'proj': 'omerc',
                 'ellps': 'WGS84'}

    print(datetime.now(), "Before compute optimal bb area")
    # bb_area = swath_scene.coarsest_area().compute_optimal_bb_area(proj_dict=proj_dict, resolution=7500)
    bb_area = swath_scene.coarsest_area().compute_optimal_bb_area(proj_dict=proj_dict)
    print(bb_area)
    print(bb_area.pixel_size_x)
    print(bb_area.pixel_size_y)
    
    print(datetime.now(), "Before resample")
    resample_scene = swath_scene.resample(bb_area)
    print(datetime.now(), "Before save")
    for _satpy_product in satpy_products_to_generate:
        if _satpy_product['satpy_product'] in satpy_products:
            resample_scene.save_dataset(_satpy_product['satpy_product'], filename=_satpy_product['satpy_product_filename'])
    print(datetime.now(), "After save")

def _parse_filename(netcdf_path):
    """Parse the netcdf to return start_time."""
    pattern_match = '^.*satellite-thredds/polar-swath/(\d{4})/(\d{2})/(\d{2})/(metopa|metopb|metopc|noaa18|noaa19|noaa20|npp|aqua|terra|fy3d)-(avhrr|viirs-mband|modis-1km|mersi2-1k)-(\d{14})-(\d{14})\.nc$'
    pattern = re.compile(pattern_match)
    mtchs = pattern.match(netcdf_path)
    start_time = None
    if mtchs:
        print("Pattern match:", mtchs.groups()[5])
        start_time = datetime.strptime(mtchs.groups()[5], "%Y%m%d%H%M%S")
    return start_time

@router.get("/{image_path:path}")
async def main(image_path: str):
    """Need this to local images"""
    return FileResponse(image_path)
