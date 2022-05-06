import importlib
import os
from unittest.mock import patch
from xmlrpc.client import DateTime
import pytest
import shutil
from fastapi.testclient import TestClient
#import unittest.mock as mock
import base64
import datetime
from mapgen.main import app

client = TestClient(app)

# https://stackoverflow.com/questions/22627659/run-code-before-and-after-each-test-in-py-test
@pytest.fixture(autouse=True)
def run_before_and_after_tests():
    """Fixture to execute asserts before and after a test is run"""
    # Setup: fill with any logic you want
    if not os.path.exists('mapfiles'):
        os.mkdir('mapfiles')
    if not os.path.exists('lustre/storeA/project/metproduction/products/satdata_polar/senda-bb/'):
        os.makedirs('lustre/storeA/project/metproduction/products/satdata_polar/senda-bb/')
    quicklooks_stamps = ['20220427_122315.tif', '20220427_113327.tif', '20220427_124247.tif',
                         '20220427_115541.tif', '20220427_121037.tif']
    for quicklook_type in ['overview', 'natural_with_night_fog']:
        for stamp in quicklooks_stamps:
            open(os.path.join('lustre/storeA/project/metproduction/products/satdata_polar/senda-bb/', quicklook_type + '_' + stamp), 'w').close()

    # Need some envs
    os.environ['S3_ACCESS_KEY'] = "test s3 access key"
    os.environ['S3_SECRET_KEY'] = "test s3 secret key"
    os.environ['S3_ENDPOINT_URL'] = "test S3_ENDPOINT_URL"
    os.environ['S3_TENANT'] = "test S3_TENANT"
    yield # this is where the testing happens

    # Teardown : fill with any logic you want
    if os.path.exists('mapfiles'):
        shutil.rmtree('mapfiles')
    if os.path.exists('lustre'):
        shutil.rmtree('lustre')

def test_read_main():
    response = client.get("/api/get_mapserv", allow_redirects=False)
    print(response.text)
    print(dir(response))
    assert response.status_code == 307
    assert response.text == ""

def test_read_main_with_config_dict():
    """Need to add more here"""
    response = client.get("/api/get_mapserv?config_dict=test", allow_redirects=False)
    print(response.text)
    print(dir(response))
    assert response.status_code == 307
    assert response.text == ""

path = "/api/get_mapserv/satellite-thredds/polar-swath/2022/04/27/"
@patch('boto3.client')
@patch('mapgen.api.redirect.upload_mapfile_to_ceph')
@pytest.mark.parametrize("netcdf_path", ["metopb-avhrr-20220427124247-20220427125242.nc", "metopc-avhrr-20220427115541-20220427120710.nc", "noaa19-avhrr-20220427121037-20220427121853.nc",
                                         "noaa20-viirs-mband-20220427113327-20220427114740.nc", "noaa20-viirs-iband-20220427113327-20220427114740.nc", "noaa20-viirs-dnb-20220427113327-20220427114740.nc",
                                         "npp-viirs-mband-20220427122315-20220427123728.nc", "npp-viirs-iband-20220427122315-20220427123728.nc", "npp-viirs-dnb-20220427122315-20220427123728.nc"])
def test_get_netcdf(upload_patch, boto3_client, netcdf_path):
    upload_patch.return_value = True
    boto3_client().list_objects.return_value = {'Contents': [{'Key': '2022/04/27/overview_20220427_124247.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_115541.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_113327.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_122315.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_121037.tif'}]}
    response = client.get(path + netcdf_path, allow_redirects=False)
    print(response.text)
    assert response.status_code == 307
    assert response.text == ""

@patch('re.compile', side_effect=Exception("compile exception test"))
def test_get_netcdf_exception1(get_mapserv):
    netcdf_path = "metopb-avhrr-20220427124247-20220427125242.nc"
    response = client.get(path + netcdf_path, allow_redirects=False)
    print(response.text)
    print(response.json()['message'])
    assert response.status_code == 500
    assert response.json()['message'] == "Exception raised when regexp. Check the config."

def test_get_netcdf_bad_pattern():
    netcdf_path = "bad-satellite-name-avhrr-20220427124247-20220427125242.nc"
    response = client.get(path + netcdf_path, allow_redirects=False)
    print(response.text)
    print(response.json()['message'])
    assert response.status_code == 501
    assert response.json()['message'] == "Could not match against any pattern. Check the config."

@patch('importlib.import_module', side_effect=ModuleNotFoundError)
def test_fail_load_module(import_module):
    netcdf_path = "metopb-avhrr-20220427124247-20220427125242.nc"
    response = client.get(path + netcdf_path, allow_redirects=False)
    print(response.text)
    print(response.json()['message'])
    assert response.status_code == 500
    assert response.json()['message'] == "Failed to load module mapgen.modules.satellite_thredds_module"

# @patch('getattr', side_effect=False)
# def test_fail_call_module(call_module):
#     """This is not working yet but only covers one line of code"""
#     netcdf_path = "metopb-avhrr-20220427124247-20220427125242.nc"
#     response = client.get(path + netcdf_path, allow_redirects=False)
#     print(response.text)
#     print(response.json()['message'])
#     assert response.status_code == 500
#     assert response.json()['message'] == "Failed to load module mapgen.modules.satellite_thredds_module"

def test_get_dashboard():
    """This is not finished"""
    dd = base64.urlsafe_b64encode('teststring'.encode('ascii'))
    print(dd)
    dashboard_get = '/dashboard?data=' + str(dd)
    response = client.get(dashboard_get)
    print(response.text)
    print(response.status_code)
    assert response.status_code == 200

@patch('boto3.client')
def test_list_files_in_bucket(boto3_client):
    from mapgen.modules.satellite_thredds_module import list_files_in_bucket
    boto3_client().list_objects.return_value = {'Contents': [{'Key': '2022/04/27/overview_20220427_124247.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_115541.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_113327.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_122315.tif'},
                                                             {'Key': '2022/04/27/overview_20220427_121037.tif'}]}
    bucket = 'test bucket'
    start_time = datetime.datetime(2022, 4, 27, 12, 42, 47)
    files_in_bucket = list_files_in_bucket(bucket, start_time)
    expected_files = ['2022/04/27/overview_20220427_124247.tif', '2022/04/27/overview_20220427_115541.tif', '2022/04/27/overview_20220427_113327.tif', '2022/04/27/overview_20220427_122315.tif', '2022/04/27/overview_20220427_121037.tif']
    assert files_in_bucket == expected_files

@patch('boto3.client')
def test_list_files_in_bucket_exception(boto3_client):
    from mapgen.modules.satellite_thredds_module import list_files_in_bucket
    boto3_client().list_objects.side_effect = Exception("boto3 client list_bucket exception")
    bucket = 'test bucket'
    start_time = datetime.datetime(2022, 4, 27, 12, 42, 47)
    files_in_bucket = list_files_in_bucket(bucket, start_time)
    expected_files = []
    assert files_in_bucket == expected_files

@patch('mapgen.modules.satellite_thredds_module.list_files_in_bucket')
def test_get_previews(list_files_in_bucket):
    from mapgen.modules.satellite_thredds_module import get_previews
    files_in_bucket = ['2022/04/27/overview_20220427_124247.tif', '2022/04/27/overview_20220427_115541.tif', '2022/04/27/overview_20220427_113327.tif', '2022/04/27/overview_20220427_122315.tif', '2022/04/27/overview_20220427_121037.tif']
    list_files_in_bucket.return_value = files_in_bucket
    start_time = datetime.datetime(2022, 4, 27, 12, 42, 47)
    regexp_pattern_module = {'geotiff_bucket': 'test bucket'}
    previews = get_previews(start_time, regexp_pattern_module)
    assert previews == ['2022/04/27/overview_20220427_124247.tif']

def test_build_render_data():
    from mapgen.modules.satellite_thredds_module import build_render_data
    start_time = datetime.datetime(2022, 4, 27, 12, 42, 47)
    regexp_pattern_module = {'geotiff_bucket': 'test bucket'}
    previews = ['2022/04/27/overview_20220427_124247.tif']
    layers_render_data = build_render_data(regexp_pattern_module, start_time, previews)
    assert layers_render_data == [{'preview': '/vsicurl/test S3_ENDPOINT_URL/test S3_TENANT:test bucket/2022/04/27/overview_20220427_124247.tif',
                                   'preview_stamp': '2022-04-27T12:42:47Z',
                                   'layer_name': 'overview'}]


def test_get_mapfile_template():
    import jinja2
    from mapgen.modules.satellite_thredds_module import get_mapfile_template
    regexp_pattern_module = {'mapfile_template': 'does/not/exists'}
    with pytest.raises(jinja2.exceptions.TemplateNotFound):
        get_mapfile_template(regexp_pattern_module)

@patch('mapgen.modules.satellite_thredds_module.get_previews')
def test_generate_mapfile_found_no_prefix(get_previews):
    from mapgen.modules.satellite_thredds_module import generate_mapfile
    get_previews.return_value = []
    regexp_pattern_module = {'mapfile_template': 'mapgen/templates/mapfiles/mapfile.map'}
    netcdf_path = 'also-dummy'
    netcdf_file_name = 'metopb-avhrr-20220427124247-20220427125242.nc'
    map_file_name = 'dummy'
    ret = generate_mapfile(regexp_pattern_module, netcdf_path, netcdf_file_name, map_file_name)
    assert ret == False

@patch('boto3.client')
def test_upload_mapfile_to_ceph(boto3_client):
    from mapgen.api.redirect import upload_mapfile_to_ceph
    map_file_name = ''
    bucket = 'test bucket'
    ret = upload_mapfile_to_ceph(map_file_name, bucket)
    assert ret == True

@patch('boto3.client')
def test_upload_mapfile_to_ceph_except(boto3_client):
    from mapgen.api.redirect import upload_mapfile_to_ceph
    from botocore.exceptions import ClientError

    boto3_client().upload_file.side_effect = ClientError({'Error': {}}, 'test')
    map_file_name = ''
    bucket = 'test bucket'
    ret = upload_mapfile_to_ceph(map_file_name, bucket)
    assert ret == False
