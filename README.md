[![pytest](https://github.com/metno/mapgen-fastapi/actions/workflows/pytest.yml/badge.svg)](https://github.com/metno/mapgen-fastapi/actions/workflows/pytest.yml)
[![codecov](https://codecov.io/gh/metno/mapgen-fastapi/branch/main/graph/badge.svg?token=d6fc1817-897f-483a-8474-17086bd669fb)](https://codecov.io/gh/metno/mapgen-fastapi)
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
