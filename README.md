[![pytest](https://github.com/metno/mapgen-fastapi/actions/workflows/pytest.yml/badge.svg)](https://github.com/metno/mapgen-fastapi/actions/workflows/pytest.yml)
[![codecov](https://codecov.io/gh/metno/mapgen-fastapi/branch/main/graph/badge.svg?token=51f2899b-a546-4fc5-b7cf-10043dbff212)](https://codecov.io/gh/metno/mapgen-fastapi)
[![flake8](https://github.com/metno/mapgen-fastapi/actions/workflows/syntax.yml/badge.svg?branch=main)](https://github.com/metno/mapgen-fastapi/actions/workflows/syntax.yml)
# mapgen-fastapi

FastAPI application to generate mapserver mapfiles and redirect to OGC WMS/WCS/WFS getcapabilities

## Getting started

```
git clone https://gitlab.met.no/s-enda/data-visualization-services/mapgen-fastapi
cd mapgen-fastapi
docker-compose up
```

Access the API swaggler UI at `http://localhost/docs`

* Test the [redirect API](mapgen/api/redirect.py#L8):

```
curl -L -X 'GET' \
  'http://localhost/api/get_mapserv' \
  -H 'accept: */*'
```

* Test embedding a [response into a template](mapgen/views/dashboard.py#L14):

Send a json string as input parameter `data`:

```json
{
  "data": {
    "id1": {
      "title": "Title",
      "feature_type": "NA",
      "resources": {
        "OGC:WMS": [
          "http://nbswms.met.no/thredds/wms_ql/NBS/S1A/2021/05/18/EW/S1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc?SERVICE=WMS&REQUEST=GetCapabilities"
        ]
      }
    }
  },
  "email": "epiesasha@me.com",
  "project": "Mapserver"
}
```
execute: 

```
curl -L -X 'GET' \
  'http://localhost/dashboard?data=%7B%20%20%20%22data%22%3A%20%7B%20%20%20%20%20%22id1%22%3A%20%7B%20%20%20%20%20%20%20%22title%22%3A%20%22Title%22%2C%20%20%20%20%20%20%20%22feature_type%22%3A%20%22NA%22%2C%20%20%20%20%20%20%20%22resources%22%3A%20%7B%20%20%20%20%20%20%20%20%20%22OGC%3AWMS%22%3A%20%5B%20%20%20%20%20%20%20%20%20%20%20%22http%3A%2F%2Fnbswms.met.no%2Fthredds%2Fwms_ql%2FNBS%2FS1A%2F2021%2F05%2F18%2FEW%2FS1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc%3FSERVICE%3DWMS%26REQUEST%3DGetCapabilities%22%20%20%20%20%20%20%20%20%20%5D%20%20%20%20%20%20%20%7D%20%20%20%20%20%7D%20%20%20%7D%2C%20%20%20%22email%22%3A%20%22epiesasha%40me.com%22%2C%20%20%20%22project%22%3A%20%22Mapserver%22%20%7D' \
  -H 'accept: application/json'
```

or access the [corresponding URL](http://localhost/dashboard?data=%7B%20%20%20%22data%22%3A%20%7B%20%20%20%20%20%22id1%22%3A%20%7B%20%20%20%20%20%20%20%22title%22%3A%20%22Title%22%2C%20%20%20%20%20%20%20%22feature_type%22%3A%20%22NA%22%2C%20%20%20%20%20%20%20%22resources%22%3A%20%7B%20%20%20%20%20%20%20%20%20%22OGC%3AWMS%22%3A%20%5B%20%20%20%20%20%20%20%20%20%20%20%22http%3A%2F%2Fnbswms.met.no%2Fthredds%2Fwms_ql%2FNBS%2FS1A%2F2021%2F05%2F18%2FEW%2FS1A_EW_GRDM_1SDH_20210518T070428_20210518T070534_037939_047A42_65CD.nc%3FSERVICE%3DWMS%26REQUEST%3DGetCapabilities%22%20%20%20%20%20%20%20%20%20%5D%20%20%20%20%20%20%20%7D%20%20%20%20%20%7D%20%20%20%7D%2C%20%20%20%22email%22%3A%20%22epiesasha%40me.com%22%2C%20%20%20%22project%22%3A%20%22Mapserver%22%20%7D
) 


## Create module for new type of netcdf data

First of all, netcdf come in infinite number of variations. So most likely you need a module to be able to handle your netcdf data.

There are two main differences:
1. gridded data
2. not gridded data

The first means the data is gridded with equal distance between each grid point. An example is NWP data. Second is data with unequal distance between each grid point. An example is satellite data in swath; the further away from the sub satellite point the greater the distance between each grid/data point/value. These data will require a resampling before it can be used as the first. From there the handeling is the same.

### Add not gridded data
An example is the existing module `satellite_satpy_quicklook.py`. Here satellite data is resampled before it can be served which adds some complexity to the processing. For the resampling the `satpy` package is used. The `satpy` can read many types of data. Check https://satpy.readthedocs.io/en/stable/index.html#reader-table for supported data.


### Add gridded data
Please have a look at `gridded_data_quicklook_template.py`. Here you would need to implement your own handler and add configuration accordingly.

## Config format

The config is a yaml file with a list of entries. Valid elements are:
```yaml
---
- pattern: regexp pattern for the input file. Uses the python re module. see eg https://docs.python.org/3/library/re.html how this can be done. Mandatory.
  module: which module to handle the request. Mandatory.
  module_function: which function in the module to handle the request. Mandatory
  base_netcdf_directory: basename to be added to the request path. Not Mandatory, recommended due to security.
  mapfiles_path: where internal cached map (internal to mapserver) files are stored. Must be writable. Not Mandatory, defaults to ./ relative to the server home.
  styles: List of styles to add to all layers/variables for this dataset in the request. Not mandatory, if not given greyscale raster and blue contour is added
    - name: Name of the style. Used in the request and in the legend. Case sensitive.
      colors: list of hex color codes
      intervals: Interval of data values to be given the color in colors. First and last value are used as min max.
  geotiff_tmp: Where to store generated geotiffs. Only used in special satpy netcdf swath satellite data handling. Directory must be writable. Not mandatory.
  geotiff_bucket: Bucket to store generate geotiff. Only used in special satpy netcdf swath satellite data handling for cache. Not mandatory.
  default_dataset: Default dataset to generate as geotiff. Only used in special satpy netcdf swath satellite data handling for cache. Not mandatory.
  mapfile_template: Mapserver map file template to use. Deprecated.
  map_file_bucket: Bucket to store cached map files. Deprecated.
```

### Valid modules and module functions:
Normally to first should be used
- module: mapgen.modules.generic_quicklook
  - module_function: generic_quicklook
- module: mapgen.modules.arome_arctic_quicklook
  - module_function: arome_arctic_quicklook
- module: mapgen.modules.satellite_satpy_quicklook
  - module_function: satellite_satpy_quicklook


### Details on style:
The style.intervals uses greater or equal to (>=) and less than (<) for the intervals until the last where this is included using less than or equal to (<=)

eg. a style like this:
```yaml
styles:
  - name: 'Temperature'
    colors: ["#dd5f4d", "#b2182a", "#67001f", "#420114"]
    intervals: [0, 3, 4, 5, 10]
```

```
0 <= data value < 3      gets color #dd5f4d
3 <= data value < 4      gets color #b2182a
4 <= data value < 5      gets color #67001f
5 <= data value <= 10    gets color #420114
```

A legend will look like this, where the text is the unit of the variable viewed:

![alt text](legend_test.png)
