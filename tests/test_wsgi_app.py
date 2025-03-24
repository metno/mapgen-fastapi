# test_myapp.py
import os
import sys
import logging
import botocore
import datetime
import rasterio
import unittest
from webtest import TestApp
from mapgen.main import app
from unittest.mock import patch, MagicMock
from mapgen.modules.helpers import _parse_request, HTTPError
from mapgen.modules.get_quicklook import get_quicklook
from mapgen.modules.satellite_satpy_quicklook import _upload_geotiff_to_ceph, _exists_on_ceph, _generate_satpy_geotiff

def test_no_path():
    test_app = TestApp(app)

    res = test_app.get('/', status='*')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '404 Not Found'
    assert res.body == b"These aren't the droids you're looking for.\n"

def test_random_path():
    test_app = TestApp(app)

    res = test_app.get('/dsfgsgr', status='*')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '404 Not Found'
    assert res.body == b"These aren't the droids you're looking for.\n"

def test_robots():
    test_app = TestApp(app)

    res = test_app.get('/robots.txt')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '200 OK'
    assert res.body == b"User-agent: *\nDisallow: /\n"

def test_favicon():
    test_app = TestApp(app)

    res = test_app.get('/favicon.ico')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '200 OK'

def test_get_quicklook():
    test_app = TestApp(app)

    res = test_app.get('/api/get_quicklook', status='*')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '404 Not Found'
    assert res.body == b"Missing netcdf path\n"

def test_post():
    test_app = TestApp(app)

    res = test_app.post('/api/get_quicklook', status='*')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '400 Bad Request'
    assert res.body == b"Your are not welcome here!\n"

def test_options():
    test_app = TestApp(app)

    res = test_app.options('', status='*')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '200 OK'
    assert res.body == b""

def test_get_quicklook_test1(caplog):
    """Test for a none existing netcdf file"""
    test_app = TestApp(app)

    caplog.set_level(logging.DEBUG)
    res = test_app.get('/api/get_quicklook/test1.nc', status='*')
    sys.stderr.write(res.status)
    print(res.status)
    print(res.body)
    assert res.status == '500 Internal Server Error'
    assert res.body == b"File Not Found: /test1.nc."

def test_parse_request():
    req= "REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_lowercase():
    req= "request=GetCapabilities&service=WMS&version=1.3.0"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_extra_questionmark():
    req= "request=GetCapabilities&service=WMS&version=1.3.0?service=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_with_ampersand():
    req= "request=GetCapabilities&service=WMS&version=1.3.0&amp;service=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_with_ampersand_html():
    req= "request=GetCapabilities&service=WMS&version=1.3.0&amp%3bservice=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_with_ampersand_html2():
    req= "request=GetCapabilities&service=WMS&version=1.3.0&amp%3Bservice=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_with_question_mark_html():
    req= "request=GetCapabilities&service=WMS&version=1.3.0%3Fservice=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_with_question_mark_html2():
    req= "request=GetCapabilities&service=WMS&version=1.3.0%3fservice=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

def test_parse_request_various():
    req= "REQUEST=GetCapabilities&amp%3Brequest=GetCapabilities%3FSERVICE%3DWMS&amp%3Bversion=1.3.0&service=WMS"
    result = _parse_request(req)
    assert result == {'request': 'GetCapabilities', 'version': '1.3.0', 'service': 'WMS'}

@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
def test_get_quicklook_satpy_ordinary(rasterio_open, generate_satpy_geotiff):
    """Test satpy ordinary netcdf file"""
    generate_satpy_geotiff.return_value = True
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)

    netcdf_path = "satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '200 OK'
    expected_result = b'<?xml version="1.0" ?><WMS_Capabilities xmlns="http://www.opengis.net/wms" xmlns:sld="http://www.opengis.net/sld" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ms="http://mapserver.gis.umn.edu/mapserver" version="1.3.0" xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd  http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/sld_capabilities.xsd  http://mapserver.gis.umn.edu/mapserver http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?service=WMS&amp;version=1.3.0&amp;request=GetSchemaExtension">\n<Service>\n  <Name>WMS</Name>\n  <Title>WMS senda fastapi</Title>\n  <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/>\n  <ContactInformation>\n  </ContactInformation>\n  <MaxWidth>4096</MaxWidth>\n  <MaxHeight>4096</MaxHeight>\n</Service>\n\n<Capability>\n  <Request>\n    <GetCapabilities>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetCapabilities>\n    <GetMap>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <Format>application/x-pdf</Format>\n      <Format>image/svg+xml</Format>\n      <Format>image/tiff</Format>\n      <Format>application/vnd.mapbox-vector-tile</Format>\n      <Format>application/x-protobuf</Format>\n      <Format>application/json</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetMap>\n    <GetFeatureInfo>\n      <Format>text/plain</Format>\n      <Format>application/vnd.ogc.gml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetFeatureInfo>\n    <sld:DescribeLayer>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:DescribeLayer>\n    <sld:GetLegendGraphic>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:GetLegendGraphic>\n    <ms:GetStyles>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </ms:GetStyles>\n  </Request>\n  <Exception>\n    <Format>XML</Format>\n    <Format>INIMAGE</Format>\n    <Format>BLANK</Format>\n  </Exception>\n  <sld:UserDefinedSymbolization SupportSLD="1" UserLayer="0" UserStyle="1" RemoteWFS="0" InlineFeature="0" RemoteWCS="0"/>\n  <Layer>\n    <Name>MS</Name>\n    <Title>WMS senda fastapi</Title>\n    <Abstract>MS</Abstract>\n    <CRS>EPSG:3857</CRS>\n    <CRS>EPSG:3978</CRS>\n    <CRS>EPSG:4269</CRS>\n    <CRS>EPSG:4326</CRS>\n    <CRS>EPSG:25832</CRS>\n    <CRS>EPSG:25833</CRS>\n    <CRS>EPSG:25835</CRS>\n    <CRS>EPSG:32632</CRS>\n    <CRS>EPSG:32633</CRS>\n    <CRS>EPSG:32635</CRS>\n    <CRS>EPSG:32661</CRS>\n    <EX_GeographicBoundingBox>\n        <westBoundLongitude>-90.000000</westBoundLongitude>\n        <eastBoundLongitude>90.000000</eastBoundLongitude>\n        <southBoundLatitude>-35.000000</southBoundLatitude>\n        <northBoundLatitude>145.000000</northBoundLatitude>\n    </EX_GeographicBoundingBox>\n    <Layer queryable="0" opaque="0" cascaded="0">\n        <Name>hr_overview</Name>\n        <Title>hr_overview</Title>\n        <CRS>EPSG:4326</CRS>\n        <EX_GeographicBoundingBox>\n            <westBoundLongitude>1.000000</westBoundLongitude>\n            <eastBoundLongitude>3.000000</eastBoundLongitude>\n            <southBoundLatitude>2.000000</southBoundLatitude>\n            <northBoundLatitude>4.000000</northBoundLatitude>\n        </EX_GeographicBoundingBox>\n        <BoundingBox CRS="EPSG:4326" minx="2.000000" miny="1.000000" maxx="4.000000" maxy="3.000000"/>\n        <Dimension name="time" units="ISO8601" nearestValue="0">2024-01-17T14:47:43Z/2024-01-17T14:47:43Z</Dimension>\n        <MetadataURL type="TC211">\n          <Format>text/xml</Format>\n          <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?request=GetMetadata&amp;layer=hr_overview"/>\n        </MetadataURL>\n    </Layer>\n  </Layer>\n</Capability>\n</WMS_Capabilities>'
    #expected_result = b'<?xml version="1.0" ?><WMS_Capabilities xmlns="http://www.opengis.net/wms" xmlns:sld="http://www.opengis.net/sld" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ms="http://mapserver.gis.umn.edu/mapserver" version="1.3.0" xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd  http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/sld_capabilities.xsd  http://mapserver.gis.umn.edu/mapserver http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?service=WMS&amp;version=1.3.0&amp;request=GetSchemaExtension">\n<Service>\n  <Name>WMS</Name>\n  <Title>WMS senda fastapi</Title>\n  <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/>\n  <ContactInformation>\n  </ContactInformation>\n  <MaxWidth>4096</MaxWidth>\n  <MaxHeight>4096</MaxHeight>\n</Service>\n\n<Capability>\n  <Request>\n    <GetCapabilities>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetCapabilities>\n    <GetMap>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <Format>application/x-pdf</Format>\n      <Format>image/svg+xml</Format>\n      <Format>image/tiff</Format>\n      <Format>application/vnd.mapbox-vector-tile</Format>\n      <Format>application/x-protobuf</Format>\n      <Format>application/json</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetMap>\n    <GetFeatureInfo>\n      <Format>text/plain</Format>\n      <Format>application/vnd.ogc.gml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetFeatureInfo>\n    <sld:DescribeLayer>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:DescribeLayer>\n    <sld:GetLegendGraphic>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:GetLegendGraphic>\n    <ms:GetStyles>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </ms:GetStyles>\n  </Request>\n  <Exception>\n    <Format>XML</Format>\n    <Format>INIMAGE</Format>\n    <Format>BLANK</Format>\n  </Exception>\n  <sld:UserDefinedSymbolization SupportSLD="1" UserLayer="0" UserStyle="1" RemoteWFS="0" InlineFeature="0" RemoteWCS="0"/>\n  <Layer>\n    <Name>MS</Name>\n    <Title>WMS senda fastapi</Title>\n    <Abstract>MS</Abstract>\n    <CRS>EPSG:3857</CRS>\n    <CRS>EPSG:3978</CRS>\n    <CRS>EPSG:4269</CRS>\n    <CRS>EPSG:4326</CRS>\n    <CRS>EPSG:25832</CRS>\n    <CRS>EPSG:25833</CRS>\n    <CRS>EPSG:25835</CRS>\n    <CRS>EPSG:32632</CRS>\n    <CRS>EPSG:32633</CRS>\n    <CRS>EPSG:32635</CRS>\n    <CRS>EPSG:32661</CRS>\n    <EX_GeographicBoundingBox>\n        <westBoundLongitude>-90.000000</westBoundLongitude>\n        <eastBoundLongitude>90.000000</eastBoundLongitude>\n        <southBoundLatitude>-35.000000</southBoundLatitude>\n        <northBoundLatitude>145.000000</northBoundLatitude>\n    </EX_GeographicBoundingBox>\n    <Layer queryable="0" opaque="0" cascaded="0">\n        <Name>hr_overview</Name>\n        <Title>hr_overview</Title>\n                                      <EX_GeographicBoundingBox>\n            <westBoundLongitude>1.000000</westBoundLongitude>\n            <eastBoundLongitude>3.000000</eastBoundLongitude>\n            <southBoundLatitude>2.000000</southBoundLatitude>\n            <northBoundLatitude>4.000000</northBoundLatitude>\n        </EX_GeographicBoundingBox>\n                                                                                                                <Dimension name="time" units="ISO8601" nearestValue="0">2024-01-17T14:47:43Z/2024-01-17T14:47:43Z</Dimension>\n        <MetadataURL type="TC211">\n          <Format>text/xml</Format>\n          <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost/api/get_quicklooksatellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?request=GetMetadata&amp;layer=hr_overview"/>\n        </MetadataURL>\n    </Layer>\n  </Layer>\n</Capability>\n</WMS_Capabilities>'
    assert result == expected_result
    assert content_type == "text/xml; charset=UTF-8"

@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_base(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with base path"""
    generate_satpy_geotiff.return_value = True
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '200 OK'
    expected_result = b'<?xml version="1.0" ?><WMS_Capabilities xmlns="http://www.opengis.net/wms" xmlns:sld="http://www.opengis.net/sld" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ms="http://mapserver.gis.umn.edu/mapserver" version="1.3.0" xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd  http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/sld_capabilities.xsd  http://mapserver.gis.umn.edu/mapserver http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?service=WMS&amp;version=1.3.0&amp;request=GetSchemaExtension">\n<Service>\n  <Name>WMS</Name>\n  <Title>WMS senda fastapi</Title>\n  <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/>\n  <ContactInformation>\n  </ContactInformation>\n  <MaxWidth>4096</MaxWidth>\n  <MaxHeight>4096</MaxHeight>\n</Service>\n\n<Capability>\n  <Request>\n    <GetCapabilities>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetCapabilities>\n    <GetMap>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <Format>application/x-pdf</Format>\n      <Format>image/svg+xml</Format>\n      <Format>image/tiff</Format>\n      <Format>application/vnd.mapbox-vector-tile</Format>\n      <Format>application/x-protobuf</Format>\n      <Format>application/json</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetMap>\n    <GetFeatureInfo>\n      <Format>text/plain</Format>\n      <Format>application/vnd.ogc.gml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetFeatureInfo>\n    <sld:DescribeLayer>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:DescribeLayer>\n    <sld:GetLegendGraphic>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:GetLegendGraphic>\n    <ms:GetStyles>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </ms:GetStyles>\n  </Request>\n  <Exception>\n    <Format>XML</Format>\n    <Format>INIMAGE</Format>\n    <Format>BLANK</Format>\n  </Exception>\n  <sld:UserDefinedSymbolization SupportSLD="1" UserLayer="0" UserStyle="1" RemoteWFS="0" InlineFeature="0" RemoteWCS="0"/>\n  <Layer>\n    <Name>MS</Name>\n    <Title>WMS senda fastapi</Title>\n    <Abstract>MS</Abstract>\n    <CRS>EPSG:3857</CRS>\n    <CRS>EPSG:3978</CRS>\n    <CRS>EPSG:4269</CRS>\n    <CRS>EPSG:4326</CRS>\n    <CRS>EPSG:25832</CRS>\n    <CRS>EPSG:25833</CRS>\n    <CRS>EPSG:25835</CRS>\n    <CRS>EPSG:32632</CRS>\n    <CRS>EPSG:32633</CRS>\n    <CRS>EPSG:32635</CRS>\n    <CRS>EPSG:32661</CRS>\n    <EX_GeographicBoundingBox>\n        <westBoundLongitude>-90.000000</westBoundLongitude>\n        <eastBoundLongitude>90.000000</eastBoundLongitude>\n        <southBoundLatitude>-35.000000</southBoundLatitude>\n        <northBoundLatitude>145.000000</northBoundLatitude>\n    </EX_GeographicBoundingBox>\n    <Layer queryable="0" opaque="0" cascaded="0">\n        <Name>hr_overview</Name>\n        <Title>hr_overview</Title>\n        <CRS>EPSG:4326</CRS>\n        <EX_GeographicBoundingBox>\n            <westBoundLongitude>1.000000</westBoundLongitude>\n            <eastBoundLongitude>3.000000</eastBoundLongitude>\n            <southBoundLatitude>2.000000</southBoundLatitude>\n            <northBoundLatitude>4.000000</northBoundLatitude>\n        </EX_GeographicBoundingBox>\n        <BoundingBox CRS="EPSG:4326" minx="2.000000" miny="1.000000" maxx="4.000000" maxy="3.000000"/>\n        <Dimension name="time" units="ISO8601" nearestValue="0">2024-01-17T14:47:43Z/2024-01-17T14:47:43Z</Dimension>\n        <MetadataURL type="TC211">\n          <Format>text/xml</Format>\n          <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?request=GetMetadata&amp;layer=hr_overview"/>\n        </MetadataURL>\n    </Layer>\n  </Layer>\n</Capability>\n</WMS_Capabilities>'
    #expected_result = b'<?xml version="1.0" ?><WMS_Capabilities xmlns="http://www.opengis.net/wms" xmlns:sld="http://www.opengis.net/sld" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ms="http://mapserver.gis.umn.edu/mapserver" version="1.3.0" xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd  http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/sld_capabilities.xsd  http://mapserver.gis.umn.edu/mapserver http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?service=WMS&amp;version=1.3.0&amp;request=GetSchemaExtension">\n<Service>\n  <Name>WMS</Name>\n  <Title>WMS senda fastapi</Title>\n  <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/>\n  <ContactInformation>\n  </ContactInformation>\n  <MaxWidth>4096</MaxWidth>\n  <MaxHeight>4096</MaxHeight>\n</Service>\n\n<Capability>\n  <Request>\n    <GetCapabilities>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetCapabilities>\n    <GetMap>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <Format>application/x-pdf</Format>\n      <Format>image/svg+xml</Format>\n      <Format>image/tiff</Format>\n      <Format>application/vnd.mapbox-vector-tile</Format>\n      <Format>application/x-protobuf</Format>\n      <Format>application/json</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetMap>\n    <GetFeatureInfo>\n      <Format>text/plain</Format>\n      <Format>application/vnd.ogc.gml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </GetFeatureInfo>\n    <sld:DescribeLayer>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:DescribeLayer>\n    <sld:GetLegendGraphic>\n      <Format>image/png</Format>\n      <Format>image/jpeg</Format>\n      <Format>image/png; mode=8bit</Format>\n      <Format>image/vnd.jpeg-png</Format>\n      <Format>image/vnd.jpeg-png8</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </sld:GetLegendGraphic>\n    <ms:GetStyles>\n      <Format>text/xml</Format>\n      <DCPType>\n        <HTTP>\n          <Get><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Get>\n          <Post><OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?"/></Post>\n        </HTTP>\n      </DCPType>\n    </ms:GetStyles>\n  </Request>\n  <Exception>\n    <Format>XML</Format>\n    <Format>INIMAGE</Format>\n    <Format>BLANK</Format>\n  </Exception>\n  <sld:UserDefinedSymbolization SupportSLD="1" UserLayer="0" UserStyle="1" RemoteWFS="0" InlineFeature="0" RemoteWCS="0"/>\n  <Layer>\n    <Name>MS</Name>\n    <Title>WMS senda fastapi</Title>\n    <Abstract>MS</Abstract>\n    <CRS>EPSG:3857</CRS>\n    <CRS>EPSG:3978</CRS>\n    <CRS>EPSG:4269</CRS>\n    <CRS>EPSG:4326</CRS>\n    <CRS>EPSG:25832</CRS>\n    <CRS>EPSG:25833</CRS>\n    <CRS>EPSG:25835</CRS>\n    <CRS>EPSG:32632</CRS>\n    <CRS>EPSG:32633</CRS>\n    <CRS>EPSG:32635</CRS>\n    <CRS>EPSG:32661</CRS>\n    <EX_GeographicBoundingBox>\n        <westBoundLongitude>-90.000000</westBoundLongitude>\n        <eastBoundLongitude>90.000000</eastBoundLongitude>\n        <southBoundLatitude>-35.000000</southBoundLatitude>\n        <northBoundLatitude>145.000000</northBoundLatitude>\n    </EX_GeographicBoundingBox>\n    <Layer queryable="0" opaque="0" cascaded="0">\n        <Name>hr_overview</Name>\n        <Title>hr_overview</Title>\n                                      <EX_GeographicBoundingBox>\n            <westBoundLongitude>1.000000</westBoundLongitude>\n            <eastBoundLongitude>3.000000</eastBoundLongitude>\n            <southBoundLatitude>2.000000</southBoundLatitude>\n            <northBoundLatitude>4.000000</northBoundLatitude>\n        </EX_GeographicBoundingBox>\n                                                                                                                <Dimension name="time" units="ISO8601" nearestValue="0">2024-01-17T14:47:43Z/2024-01-17T14:47:43Z</Dimension>\n        <MetadataURL type="TC211">\n          <Format>text/xml</Format>\n          <OnlineResource xmlns:xlink="http://www.w3.org/1999/xlink" xlink:type="simple" xlink:href="http://localhost/api/get_quicklook/test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc?request=GetMetadata&amp;layer=hr_overview"/>\n        </MetadataURL>\n    </Layer>\n  </Layer>\n</Capability>\n</WMS_Capabilities>'
    assert result == expected_result
    assert content_type == "text/xml; charset=UTF-8"

    assert "Request with full path. Please fix your request. Depricated from version 2.0.0." in caplog.text 

@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_abs_path(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.return_value = True
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '200 OK'
    assert content_type == "text/xml; charset=UTF-8"

    assert "Request with full path. Please fix your request. Depricated from version 2.0.0." not in caplog.text 

@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_keyerror(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.return_value = True
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert "status_code=500, Missing base dir in server config." in caplog.text 

@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_false(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.return_value = False
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert "status_code=500, Some part of the generate failed." in caplog.text 

@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_keyerror(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.side_effect = KeyError('Unknown datasets')
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert "status_code=500, Layer can not be made for this dataset 'Unknown datasets'" in caplog.text 



@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_aqua(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.side_effect = KeyError('Unknown datasets')
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(aqua)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/aqua-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert "status_code=500, Layer can not be made for this dataset 'Unknown datasets'" in caplog.text 


@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_products(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.side_effect = KeyError('Unknown datasets')
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(aqua)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/aqua-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=['test-product'])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert "status_code=500, Layer can not be made for this dataset 'Unknown datasets'" in caplog.text 



@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_no_match(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.side_effect = KeyError('Unknown datasets')
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-nomatch-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert ("status_code=500, No file name match: /test/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-nomatch-20240117145323.nc, "
            "match string ^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$.") in caplog.text 


@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_no_match_mersi_qk(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.side_effect = KeyError('Unknown datasets')
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/mersi2-qk.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert ("status_code=500, No file name match: /test/satellite-thredds/polar-swath/2024/01/17/mersi2-qk.nc, "
            "match string ^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$.") in caplog.text 
@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_geotiff_no_match_mersi_1k(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.side_effect = KeyError('Unknown datasets')
    mock_raster = rasterio_open.return_value
    mock_raster.bounds = (1, 2, 3, 4)
    mock_raster.crs = rasterio.crs.CRS.from_epsg(4326)
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/mersi2-1k.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '500 Internal Server Error'
    assert content_type == "text/plain"

    assert ("status_code=500, No file name match: /test/satellite-thredds/polar-swath/2024/01/17/mersi2-1k.nc, "
            "match string ^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$.") in caplog.text 


@patch('mapgen.modules.satellite_satpy_quicklook._generate_satpy_geotiff')
@patch('mapgen.modules.satellite_satpy_quicklook.rasterio.open')
@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_get_quicklook_satpy_ordinary_generate_layer_rasterioerror(read_config, rasterio_open, generate_satpy_geotiff, caplog):
    """Test satpy ordinary netcdf file with abs path"""
    generate_satpy_geotiff.return_value = True
    rasterio_open.side_effect = rasterio.errors.RasterioIOError('RasterioIOError')
    read_config.return_value =  {'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(noaa21|noaa20|npp)-(viirs-iband)-(\d{14})-(\d{14})\.nc$',
                                 'base_netcdf_directory': '/test',
                                 'module': 'mapgen.modules.satellite_satpy_quicklook',
                                 'module_function': 'generate_satpy_quicklook',
                                 'mapfile_template': '/mapfile-templates/mapfile.map',
                                 'map_file_bucket': 's-enda-mapfiles',
                                 'geotiff_bucket': 'geotiff-products-for-senda-iband',
                                 'mapfiles_path': '/tmp',
                                 'geotiff_tmp': '/tmp',
                                 'default_dataset': 'hr_overview'}, None, None, None

    netcdf_path = "/satellite-thredds/polar-swath/2024/01/17/noaa20-viirs-iband-20240117144743-20240117145323.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
    assert response_code == '200 OK'
    assert content_type == "text/xml; charset=UTF-8"

    assert "Rasterio opened" not in caplog.text 

class TestUploadGeotiffToCeph(unittest.TestCase):
    def setUp(self):
        self.test_files = [
            {
                'satpy_product_filename': 'test1.tiff',
                'bucket': 'test-bucket'
            },
            {
                'satpy_product_filename': 'test2.tiff',
                'bucket': 'test-bucket'
            }
        ]
        self.product_config = {
            'geotiff_tmp': '/tmp/test'
        }
        self.start_time = datetime.datetime(2023, 1, 1, 0, 0, 0)
        os.environ['S3_ENDPOINT_URL'] = 'http://test-endpoint'
        os.environ['S3_ACCESS_KEY'] = 'test-key'
        os.environ['S3_SECRET_KEY'] = 'test-secret'
        # self.logger = logging.getLogger()
        # self.logger.level = logging.DEBUG
        # self.stream_handler = logging.StreamHandler(sys.stdout)
        # self.logger.addHandler(self.stream_handler)

    # def tearDown(self) -> None:
    #     self.logger.removeHandler(self.stream_handler)
    
    @patch('boto3.client')
    @patch('os.remove')
    def test_successful_upload(self, mock_remove, mock_boto_client):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {'ContentLength': 1000}

        result = _upload_geotiff_to_ceph(self.test_files, self.start_time, self.product_config)
        
        self.assertTrue(result)
        self.assertEqual(mock_s3.upload_file.call_count, 2)
        self.assertEqual(mock_s3.put_object_acl.call_count, 2)
        self.assertEqual(mock_remove.call_count, 2)

    @patch('boto3.client')
    @patch('os.remove')
    def test_zero_size_file_upload(self, mock_remove, mock_boto_client):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {'ContentLength': 0}
        mock_s3.delete_object.return_value = {'DeleteMarker': True}

        result = _upload_geotiff_to_ceph(self.test_files, self.start_time, self.product_config)
        
        self.assertTrue(result)
        self.assertEqual(mock_s3.delete_object.call_count, 2)
        self.assertEqual(mock_remove.call_count, 2)

    @patch('boto3.client')
    @patch('os.remove')
    def test_zero_size_file_upload_delete_false(self, mock_remove, mock_boto_client):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {'ContentLength': 0}
        mock_s3.delete_object.return_value = {'DeleteMarker': False}

        result = _upload_geotiff_to_ceph(self.test_files, self.start_time, self.product_config)
        
        self.assertTrue(result)
        self.assertEqual(mock_s3.delete_object.call_count, 2)
        self.assertEqual(mock_remove.call_count, 2)

    @patch('boto3.client')
    def test_upload_failure(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.upload_file.side_effect = Exception('Upload failed')

        with self.assertRaises(HTTPError) as context:
            _upload_geotiff_to_ceph(self.test_files, self.start_time, self.product_config)
        
        self.assertEqual(context.exception.response_code, '500 Internal Server Error')

    @patch('boto3.client')
    def test_empty_filenames(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        result = _upload_geotiff_to_ceph([], self.start_time, self.product_config)
        
        self.assertTrue(result)
        mock_s3.upload_file.assert_not_called()

    @patch('boto3.resource')
    def test_exists_on_ceph(self, mock_boto_resource):
        mock_s3 = MagicMock()
        mock_boto_resource.return_value = mock_s3

        result = _exists_on_ceph(self.test_files[0], self.start_time)
        
        self.assertTrue(result)
        #mock_s3.upload_file.assert_not_called()

    @patch('boto3.resource')
    def test_exists_on_ceph_exception(self, mock_boto_resource):
        mock_s3 = MagicMock()
        mock_boto_resource.return_value = mock_s3
        mock_s3.Object.side_effect = botocore.exceptions.ClientError({'Error': {'Code': '403'}}, 'HeadObject')

        result = _exists_on_ceph(self.test_files[0], self.start_time)
        
        self.assertFalse(result)

        mock_s3.Object.side_effect = botocore.exceptions.ClientError({'Error': {'Code': '404'}}, 'HeadObject')

        result = _exists_on_ceph(self.test_files[0], self.start_time)
        
        self.assertFalse(result)

        mock_s3.Object.side_effect = botocore.exceptions.ClientError({'Error': {'Code': '401'}}, 'HeadObject')

        result = _exists_on_ceph(self.test_files[0], self.start_time)
        
        self.assertFalse(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    def test_generate_satpy_geotiff_already_exists(self, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = True
        satpy_products_to_generate = [{'satpy_product': 'test_product'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        # def _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertTrue(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    def test_generate_satpy_geotiff(self, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        # def _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertFalse(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    def test_generate_satpy_geotiff_exception(self, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        mock_scene.side_effect = ValueError('Test Exception')
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        # def _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, start_time, product_config, resolution):
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertFalse(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    def test_generate_satpy_geotiff_bb_area_exception(self, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        mock_scene.return_value.coarsest_area.side_effect = ValueError
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        with self.assertLogs(level='ERROR') as cm:
            result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
            self.assertFalse(result)
            self.assertEqual(['ERROR:mapgen.modules.satellite_satpy_quicklook:Failed to compute optimal area. Several reasons could cause this. Please see previous log lines.'], cm.output)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    def test_generate_satpy_geotiff_bb_area_exception_keyerror(self, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        mock_scene.return_value.coarsest_area.side_effect = KeyError
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        with self.assertLogs(level='DEBUG') as cm:
            result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
            self.assertFalse(result)
            self.assertIn('DEBUG:mapgen.modules.satellite_satpy_quicklook:Can not compute bb area. Use euro4 as backup.', cm.output)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.path.exists', side_effect=[False, True, False, True])
    @patch('mapgen.modules.satellite_satpy_quicklook.os.remove')
    @patch('mapgen.modules.satellite_satpy_quicklook._upload_geotiff_to_ceph')
    def test_generate_satpy_geotiff_exists(self, mock_upload, mock_remove, mock_exists, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        # mock_exists.return_value = True
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertTrue(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.path.exists', side_effect=[False, True, True, True])
    @patch('mapgen.modules.satellite_satpy_quicklook.os.remove')
    @patch('mapgen.modules.satellite_satpy_quicklook._upload_geotiff_to_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.stat')
    def test_generate_satpy_geotiff_exists_after_gen(self, mock_stat, mock_upload, mock_remove, mock_exists, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        mock_stat.return_value.st_size = 0
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertTrue(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.path.exists', side_effect=[False, True, True, True])
    @patch('mapgen.modules.satellite_satpy_quicklook.os.remove')
    @patch('mapgen.modules.satellite_satpy_quicklook._upload_geotiff_to_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.stat')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.rename')
    def test_generate_satpy_geotiff_exists_after_gen_got_size(self, mock_rename, mock_stat, mock_upload, mock_remove, mock_exists, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        mock_stat.return_value.st_size = 1
        #mock_upload.return_value = False
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertTrue(result)

    @patch('mapgen.modules.satellite_satpy_quicklook._exists_on_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.Scene')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.path.exists', side_effect=[False, True, True, True])
    @patch('mapgen.modules.satellite_satpy_quicklook.os.remove')
    @patch('mapgen.modules.satellite_satpy_quicklook._upload_geotiff_to_ceph')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.stat')
    @patch('mapgen.modules.satellite_satpy_quicklook.os.rename')
    def test_generate_satpy_geotiff_exists_after_gen_fail_upload(self, mock_rename, mock_stat, mock_upload, mock_remove, mock_exists, mock_scene, mock_exists_on_ceph):
        mock_exists_on_ceph.return_value = False
        mock_stat.return_value.st_size = 1
        mock_upload.return_value = False
        satpy_products_to_generate = [{'satpy_product': 'test_product',
                                       'satpy_product_filename': 'test_product.tif'}]
        resolution = 1000
        netcdf_paths = ['/path/to/netcdf']
        result = _generate_satpy_geotiff(netcdf_paths, satpy_products_to_generate, self.start_time, self.product_config, resolution)
        self.assertFalse(result)

# if __name__ == '__main__':
#     unittest.main()
