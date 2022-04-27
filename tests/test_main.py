import os
import pytest
import shutil
from fastapi.testclient import TestClient

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

path = "/api/get_mapserv/satellite-thredds/polar-swath/2022/04/27/"
@pytest.mark.parametrize("netcdf_path", ["metopb-avhrr-20220427124247-20220427125242.nc", "metopc-avhrr-20220427115541-20220427120710.nc", "noaa19-avhrr-20220427121037-20220427121853.nc",
                                         "noaa20-viirs-mband-20220427113327-20220427114740.nc", "noaa20-viirs-iband-20220427113327-20220427114740.nc", "noaa20-viirs-dnb-20220427113327-20220427114740.nc",
                                         "npp-viirs-mband-20220427122315-20220427123728.nc", "npp-viirs-iband-20220427122315-20220427123728.nc", "npp-viirs-dnb-20220427122315-20220427123728.nc"])
def test_get_netcdf(netcdf_path):
    response = client.get(path + netcdf_path, allow_redirects=False)
    print(response.text)
    assert response.status_code == 307
    assert response.text == ""