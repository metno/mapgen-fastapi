"""Test arome arctic"""
import os
import json
import logging
import xml.etree.ElementTree as ET
import xarray as xr
from unittest.mock import patch
from mapgen.modules.get_quicklook import get_quicklook


def _local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_child(node, local_name):
    for child in list(node):
        if _local_name(child.tag) == local_name:
            return child
    return None


def _find_children(node, local_name):
    return [child for child in list(node) if _local_name(child.tag) == local_name]


def _text(node, default=""):
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _extract_getcapabilities_contract(xml_bytes):
    root = ET.fromstring(xml_bytes)

    service = _find_child(root, "Service")
    capability = _find_child(root, "Capability")
    request = _find_child(capability, "Request")
    exception = _find_child(capability, "Exception")
    root_layer = _find_child(capability, "Layer")

    request_formats = {}
    for operation in list(request):
        op_name = _local_name(operation.tag)
        formats = [_text(fmt) for fmt in _find_children(operation, "Format")]
        request_formats[op_name] = formats

    contract = {
        "service": {
            "name": _text(_find_child(service, "Name")),
            "title": _text(_find_child(service, "Title")),
            "online_resource": _find_child(service, "OnlineResource").attrib.get(
                "{http://www.w3.org/1999/xlink}href", ""
            ),
        },
        "request_formats": request_formats,
        "exception_formats": [_text(fmt) for fmt in _find_children(exception, "Format")],
        "root_layer": {
            "name": _text(_find_child(root_layer, "Name")),
            "title": _text(_find_child(root_layer, "Title")),
            "abstract": _text(_find_child(root_layer, "Abstract")),
            "crs": [_text(crs) for crs in _find_children(root_layer, "CRS")],
            "bbox": {
                "west": _text(_find_child(_find_child(root_layer, "EX_GeographicBoundingBox"), "westBoundLongitude")),
                "east": _text(_find_child(_find_child(root_layer, "EX_GeographicBoundingBox"), "eastBoundLongitude")),
                "south": _text(_find_child(_find_child(root_layer, "EX_GeographicBoundingBox"), "southBoundLatitude")),
                "north": _text(_find_child(_find_child(root_layer, "EX_GeographicBoundingBox"), "northBoundLatitude")),
            },
        },
        "layers": [],
    }

    for layer in _find_children(root_layer, "Layer"):
        layer_bbox = _find_child(layer, "EX_GeographicBoundingBox")
        layer_dimensions = []
        for dim in _find_children(layer, "Dimension"):
            layer_dimensions.append(
                {
                    "name": dim.attrib.get("name", ""),
                    "units": dim.attrib.get("units", ""),
                    "default": dim.attrib.get("default", ""),
                    "values": _text(dim),
                }
            )

        contract["layers"].append(
            {
                "name": _text(_find_child(layer, "Name")),
                "title": _text(_find_child(layer, "Title")),
                "queryable": layer.attrib.get("queryable", ""),
                "styles": [_text(_find_child(style, "Name")) for style in _find_children(layer, "Style")],
                "dimensions": sorted(layer_dimensions, key=lambda x: x["name"]),
                "bbox": {
                    "west": _text(_find_child(layer_bbox, "westBoundLongitude")),
                    "east": _text(_find_child(layer_bbox, "eastBoundLongitude")),
                    "south": _text(_find_child(layer_bbox, "southBoundLatitude")),
                    "north": _text(_find_child(layer_bbox, "northBoundLatitude")),
                },
            }
        )

    contract["layers"] = sorted(contract["layers"], key=lambda x: x["name"])
    return contract

def _create_arome_arctic_dataset_from_orig_data():
    """Create a simple dataset for testing"""
    ds = xr.open_dataset("/lustre/storeB/project/metproduction/products/arome_arctic/arome_arctic_det_vdiv_2_5km_20241111T06Z.nc")
    ds = ds.isel(time=[0,1], x=[0,1,2,3,4,5,6,7,8,9], y=[0,1,2,3,4,5,6,7,8,9,10,11,12], pressure=[0,1], height5=[0,1])
    print(list(ds.keys()))
    remove_variables = ['land_area_fraction', 'surface_aerosol_sea', 'surface_aerosol_land', 'surface_aerosol_soot', 'surface_aerosol_desert', 'ozone_profile_a', 'ozone_profile_b', 'ozone_profile_c', 'graupelfall_amount', 'toa_net_downward_shortwave_flux', 'surface_downwelling_shortwave_flux_in_air', 'toa_outgoing_longwave_flux', 'surface_downwelling_longwave_flux_in_air', 'convective_cloud_area_fraction', 'hail_diagnostic', 'cloud_binary_mask', 'atmosphere_level_of_max_icing', 'atmosphere_level_of_max_icing_growth', 'atmosphere_level_of_icing_bottom', 'atmosphere_level_of_icing_top', 'atmosphere_level_of_max_wind_speed', 'x_wind_at_maximum_wind_speed_level', 'y_wind_at_maximum_wind_speed_level',
                        'cloud_base_altitude', 'cloud_top_altitude', 'cloud_base_altitude_z', 'lightning_index', 'level_of_max_CAT_index', 'max_cat_index', 'bottom_level_of_CAT', 'top_level_of_CAT', 'visibility_in_air', 'precipitation_type', 'brunt_vaisala_frequency_in_air', 'integral_of_surface_downward_latent_heat_flux_wrt_time', 'integral_of_surface_net_downward_longwave_flux_wrt_time_assuming_clear_sky', 'integral_of_surface_net_downward_shortwave_flux_wrt_time_assuming_clear_sky', 'integral_of_surface_parallel_solar_flux_wrt_time', 'integral_of_toa_net_downward_longwave_flux_wrt_time_assuming_clear_sky', 'integral_of_toa_net_downward_shortwave_flux_wrt_time_assuming_clear_sky',
                        'integral_of_toa_downwelling_shortwave_flux_wrt_time', 'integral_of_surface_direct_normal_irradiance_wrt_time', 'icing_index', 'liquid_water_content_of_surface_snow', 'altitude_of_0_degree_isotherm', 'integral_of_surface_net_downward_shortwave_flux_wrt_time', 'integral_of_surface_net_downward_longwave_flux_wrt_time', 'integral_of_surface_downward_latent_heat_evaporation_flux_wrt_time', 'integral_of_surface_downward_latent_heat_sublimation_flux_wrt_time', 'integral_of_surface_downward_sensible_heat_flux_wrt_time', 'downward_eastward_momentum_flux_in_air', 'specific_humidity_pl', 'downward_northward_momentum_flux_in_air', 'integral_of_toa_net_downward_shortwave_flux_wrt_time',
                        'mass_fraction_of_cloud_condensed_water_in_air_pl', 'integral_of_toa_outgoing_longwave_flux_wrt_time', 'water_evaporation_amount', 'surface_snow_sublimation_amount_acc', 'mass_fraction_of_cloud_ice_in_air_pl', 'relative_humidity_z', 'integral_of_surface_downwelling_shortwave_flux_in_air_wrt_time', 'integral_of_surface_downwelling_longwave_flux_in_air_wrt_time', 'cloud_area_fraction_pl', 'integral_of_rainfall_amount_wrt_time', 'integral_of_snowfall_amount_wrt_time', 'mass_fraction_of_snow_in_air_pl', 'integral_of_graupelfall_amount_wrt_time', 'mass_fraction_of_rain_in_air_pl', 'tropopause_air_temperature', 'altitude_of_0_degree_isotherm_from_above', 'specific_humidity_2m',
                        'mass_fraction_of_graupel_in_air_pl', 'tropopause_air_pressure', 'cloud_area_fraction', 'turbulent_kinetic_energy_pl', 'altitude_of_isoTprimW_equal_0', 'high_type_cloud_area_fraction', 'medium_type_cloud_area_fraction', 'geopotential_pl', 'low_type_cloud_area_fraction', 'x_wind_gust_10m', 'relative_humidity_pl', 'y_wind_gust_10m', 'air_temperature_max', 'upward_air_velocity_pl', 'lifting_condensation_level', 'air_temperature_min', 'atmosphere_boundary_layer_thickness', 'ertel_potential_vorticity_pl', 'atmosphere_level_of_free_convection', 'rainfall_amount', 'snowfall_amount', 'lwe_thickness_of_atmosphere_mass_content_of_water_vapor', 'atmosphere_level_of_neutral_buoyancy',
                        'precipitation_amount_acc', 'snowfall_amount_acc', 'wind_speed_of_gust', 'fog_area_fraction', 'SFX_TICE_01', 'SFX_TICE_02', 'SFX_TICE_03', 'SFX_TICE_04', 'SFX_ICE_THK', 'SFX_SIC', 'SFX_SST', 'SFX_TS_WATER', 'SFX_T_SNOW', 'SFX_T_ICE', 'SFX_T_MNW', 'SFX_T_WML', 'SFX_T_BOT', 'SFX_H_SNOW', 'SFX_H_ICE', 'SFX_H_ML', 'SFX_X001TG1', 'SFX_X002TG1', 'SFX_X001TG2', 'SFX_X002TG2', 'SFX_X001WG1', 'SFX_X002WG1', 'SFX_X001WG2', 'SFX_X002WG2', 'SFX_X001WGI1', 'SFX_X002WGI1', 'SFX_X001WGI2', 'SFX_X002WGI2', 'SFX_X001WSN_VEG1', 'SFX_X002WSN_VEG1', 'SFX_X001RSN_VEG1', 'SFX_X002RSN_VEG1', 'SFX_X001ASN_VEG', 'SFX_X002ASN_VEG', 'SFX_WS_ROAD', 'SFX_T2M_SEA', 'SFX_Q2M_SEA', 'SFX_HU2M_SEA',
                        'SFX_ZON10M_SEA', 'SFX_MER10M_SEA', 'SFX_DSN_T_ICE', 'SFX_T2M_WAT', 'SFX_Q2M_WAT', 'SFX_HU2M_WAT', 'SFX_ZON10M_WAT', 'SFX_MER10M_WAT', 'SFX_TALB_ISBA', 'SFX_T2M_ISBA', 'SFX_Q2M_ISBA', 'SFX_HU2M_ISBA', 'SFX_ZON10M_ISBA', 'SFX_MER10M_ISBA', 'SFX_X001T2M_P', 'SFX_X002T2M_P', 'SFX_X001Q2M_P', 'SFX_X002Q2M_P', 'SFX_X001HU2M_P', 'SFX_X002HU2M_P', 'SFX_X001ZON10M_P', 'SFX_X001MER10M_P', 'SFX_X002ZON10M_P', 'SFX_X002MER10M_P', 'SFX_RNC_ISBA', 'SFX_HC_ISBA', 'SFX_LEC_ISBA', 'SFX_FMUC_ISBA', 'SFX_FMVC_ISBA', 'SFX_PSNG_ISBA', 'SFX_PSNV_ISBA', 'SFX_PSN_ISBA', 'SFX_WSN_T_ISBA', 'SFX_DSN_T_ISBA', 'SFX_X001LAI', 'SFX_X002LAI', 'SFX_X001VEG', 'SFX_X002VEG', 'SFX_T2M_TEB', 'SFX_Q2M_TEB',
                        'SFX_HU2M_TEB', 'SFX_ZON10M_TEB', 'SFX_MER10M_TEB', 'SFX_RI', 'SFX_TS', 'SFX_EMIS', 'SFX_T2M', 'SFX_Q2M', 'SFX_HU2M', 'SFX_ZON10M', 'SFX_MER10M', 'SFX_RN', 'SFX_H', 'SFX_LE', 'SFX_GFLUX', 'SFX_FMU', 'SFX_FMV', 'SFX_CD', 'SFX_CH', 'SFX_CE', 'SFX_Z0', 'SFX_Z0H']
    ds_trimmed = ds.drop_vars(remove_variables)    
    ds_trimmed.to_netcdf("test_arome_arctic.nc")

def _create_arome_arctic_dataset_from_orig_data_without_reference_time():
    """Create a simple dataset for testing"""
    ds = xr.open_dataset("tests/data/test_arome_arctic.nc")  # arome_arctic_det_vdiv_2_5km_20241111T06Z.nc
    ds_trimmed = ds.drop_vars(['forecast_reference_time'])    
    ds_trimmed.to_netcdf("test_arome_arctic_without_forecast_time_20241111T06Z.nc")

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
@patch('mapgen.modules.helpers._find_summary_from_csw')
def test_read_dataset(mock_csw, mock_read_config, tmpdir, caplog):
    """Test reading the dataset"""
    netcdf_path = "tests/data/test_arome_arctic.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_csw.return_value = "TEST_CSW"
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
                                 'base_netcdf_directory': '.',
                                 'module': 'mapgen.modules.arome_arctic_quicklook',
                                 'module_function': 'arome_arctic_quicklook',
                                 'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                 'map_file_bucket': 'test-map-bucket',
                                 'geotiff_bucket': 'test_bucket',
                                 'mapfiles_path': tmpdir,
                                 'geotiff_tmp': tmpdir,
                                 'default_dataset': 'presure'}, None, None, None

    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    assert response_code == '200 OK'
    contract = _extract_getcapabilities_contract(result)
    fixture_file = os.path.join(
        os.path.dirname(__file__),
        "data",
        "expected_getcapabilities_arome_arctic_contract.json",
    )
    with open(fixture_file) as fh:
        expected_contract = json.load(fh)
    assert contract == expected_contract
    assert content_type == "text/xml; charset=UTF-8"

    # Retest the same test to check for existing getcapabilities map file
    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    if response_code == '500 Internal Server Error':
        assert 'msProcessProjection()' in caplog.text
    else:
        assert response_code == '200 OK'
    assert "Reuse existing getcapabilities map file" in caplog.text 
    assert content_type == "text/xml; charset=UTF-8"
    tmpdir.remove()

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
@patch('mapgen.modules.helpers._find_summary_from_csw')
def test_get_quicklook_arome_arctic_no_reference_time(mock_csw, mock_read_config, tmpdir, caplog):
    """Test for a none existing netcdf file"""
    netcdf_path = "tests/data/test_arome_arctic_without_forecast_time_20241111T06Z.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_csw.return_value = "TEST CSW"
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic_without_forecast_time_(\d{8}T\d{2})Z.nc)$',
                                      'base_netcdf_directory': '.',
                                      'module': 'mapgen.modules.arome_arctic_quicklook',
                                      'module_function': 'arome_arctic_quicklook',
                                      'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                      'map_file_bucket': 'test-map-bucket',
                                      'geotiff_bucket': 'test_bucket',
                                      'mapfiles_path': tmpdir,
                                      'geotiff_tmp': tmpdir,
                                      'default_dataset': 'presure'}, None, None, None

    caplog.set_level(logging.DEBUG)
    response_code, _, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    assert response_code == '200 OK'
    assert content_type == "text/xml; charset=UTF-8"
    assert 'Could not find forecast time or analysis time from dataset. Try parse from filename.' in caplog.text
    assert 'Forecast time: 2024-11-11 06:00:00' in caplog.text
    tmpdir.remove()

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_read_dataset_base_path(mock_read_config, tmpdir):
    """Test reading the dataset"""
    netcdf_path = "/tests/data/test_arome_arctic.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
                                 'base_netcdf_directory': '/tests',
                                 'module': 'mapgen.modules.arome_arctic_quicklook',
                                 'module_function': 'arome_arctic_quicklook',
                                 'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                 'map_file_bucket': 'test-map-bucket',
                                 'geotiff_bucket': 'test_bucket',
                                 'mapfiles_path': tmpdir,
                                 'geotiff_tmp': tmpdir,
                                 'default_dataset': 'presure'}, None, None, None

    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    assert response_code == '404 Not Found'
    tmpdir.remove()

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
def test_read_dataset_base_path_missing_base(mock_read_config, tmpdir):
    """Test reading the dataset"""
    netcdf_path = "/tests/data/test_arome_arctic.nc"
    query_string = ""
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
                                 #'base_netcdf_directory': '/tests',
                                 'module': 'mapgen.modules.arome_arctic_quicklook',
                                 'module_function': 'arome_arctic_quicklook',
                                 'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                 'map_file_bucket': 'test-map-bucket',
                                 'geotiff_bucket': 'test_bucket',
                                 'mapfiles_path': tmpdir,
                                 'geotiff_tmp': tmpdir,
                                 'default_dataset': 'presure'}, None, None, None

    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    assert response_code == '500 Internal Server Error'
    tmpdir.remove()

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
@patch('mapgen.modules.helpers._find_summary_from_csw')
def test_read_dataset_request_getmap(mock_csw, mock_read_config, tmpdir, caplog):
    """Test reading the dataset"""
    netcdf_path = "tests/data/test_arome_arctic.nc"
    query_string = ("?&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=air_temperature_2m&WIDTH=767&HEIGHT=880&CRS=EPSG%3A3857&"
                    "BBOX=-4822584.097826986,7566329.44660393,10215292.880334288,24819695.471091438&STYLES=raster&FORMAT=image/png&"
                    "TRANSPARENT=TRUE&&TIME=2024-11-11T07%3A00%3A00Z")
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_csw.return_value = "TEST CSW"
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
                                 'base_netcdf_directory': os.getcwd(),
                                 'module': 'mapgen.modules.arome_arctic_quicklook',
                                 'module_function': 'arome_arctic_quicklook',
                                 'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                 'map_file_bucket': 'test-map-bucket',
                                 'geotiff_bucket': 'test_bucket',
                                 'mapfiles_path': tmpdir,
                                 'geotiff_tmp': tmpdir,
                                 'default_dataset': 'presure'}, None, None, None

    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    if response_code == '500 Internal Server Error':
        assert 'msProcessProjection()' in caplog.text
    else:
        assert response_code == '200 OK'
    assert ("QP after flatten lists {'service': 'WMS', 'version': '1.3.0', 'request': 'GetMap', 'layers': 'air_temperature_2m', "
            "'width': '767', 'height': '880', 'crs': 'EPSG:3857', 'bbox': '-4822584.097826986,7566329.44660393,10215292.880334288,24819695.471091438', "
            "'styles': 'raster', 'format': 'image/png', 'transparent': 'TRUE', 'time': '2024-11-11T07:00:00Z'}") in caplog.text
    assert ("Calculate band number from dimension: [{'dim_name': 'time', 'ds_size': 2, 'selected_band_number': 1}, "
            "{'dim_name': 'height1', 'ds_size': 1, 'selected_band_number': 0}]") in caplog.text
    assert "MIN:MAX 274.2896728515625 274.8013916015625" in caplog.text
    assert "REQUEST is: GetMap" in caplog.text
    assert "STYLES: raster" in caplog.text
    assert "STYLE: None" in caplog.text

    tmpdir.remove()

# @patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
# @patch('mapgen.modules.helpers._find_summary_from_csw')
# def test_read_dataset_request_getmap_contour_style(mock_csw, mock_read_config, tmpdir, caplog):
#     """Test reading the dataset"""
#     netcdf_path = "tests/data/test_arome_arctic.nc"
#     query_string = ("?&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=air_temperature_2m&WIDTH=767&HEIGHT=880&CRS=EPSG%3A3857&"
#                     "BBOX=-4822584.097826986,7566329.44660393,10215292.880334288,24819695.471091438&STYLES=contour&FORMAT=image/png&"
#                     "TRANSPARENT=TRUE&&TIME=2024-11-11T07%3A00%3A00Z")
#     http_host = "localhost"
#     url_scheme = "http"
#     mock_csw.return_value = "TEST CSW"
#     mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
#                                  'base_netcdf_directory': '.',
#                                  'module': 'mapgen.modules.arome_arctic_quicklook',
#                                  'module_function': 'arome_arctic_quicklook',
#                                  'mapfile_template': os.path.join(tmpdir, 'test.map'),
#                                  'map_file_bucket': 'test-map-bucket',
#                                  'geotiff_bucket': 'test_bucket',
#                                  'mapfiles_path': tmpdir,
#                                  'geotiff_tmp': tmpdir,
#                                  'default_dataset': 'presure'}, None, None, None

#     caplog.set_level(logging.DEBUG)
#     response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, products=[])
#     assert response_code == '200 OK'
#     assert "Selected style: contour" in caplog.text
#     assert "Style in contour for style setup." in caplog.text
#     assert "Selected label scale 1 and offset -273.15" in caplog.text
#     assert "STYLES: contour" in caplog.text

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
@patch('mapgen.modules.helpers._find_summary_from_csw')
def test_read_dataset_request_getmap_vector_barbs(mock_csw, mock_read_config, tmpdir, caplog):
    """Test reading the dataset"""
    netcdf_path = "tests/data/test_arome_arctic.nc"
    query_string = ("?&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=wind_10m_vector&WIDTH=767&HEIGHT=880&CRS=EPSG%3A3857&"
                    "BBOX=-4891698.287598623,6944679.416003374,10026224.553483257,24060418.79038676&STYLES=Wind_Barbs&"
                    "FORMAT=image/png&TRANSPARENT=TRUE&&TIME=2024-11-11T07%3A00%3A00Z&DIM_SPACING=32&DIM_COLOUR=light-green")
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_csw.return_value = "TEST CSW"
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
                                 'base_netcdf_directory': '.',
                                 'module': 'mapgen.modules.arome_arctic_quicklook',
                                 'module_function': 'arome_arctic_quicklook',
                                 'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                 'map_file_bucket': 'test-map-bucket',
                                 'geotiff_bucket': 'test_bucket',
                                 'mapfiles_path': tmpdir,
                                 'geotiff_tmp': tmpdir,
                                 'default_dataset': 'presure'}, None, None, None

    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    if response_code == '500 Internal Server Error':
        assert 'msProcessProjection()' in caplog.text
    else:
        assert response_code == '200 OK'
    assert 'Selected style: Wind_Barbs' in caplog.text
    assert 'VECTOR wind_10m_vector x_wind_10m y_wind_10m' in caplog.text

@patch('mapgen.modules.get_quicklook.find_config_for_this_netcdf')
@patch('mapgen.modules.helpers._find_summary_from_csw')
def test_read_dataset_request_getmap_vector_vector(mock_csw, mock_read_config, tmpdir, caplog):
    """Test reading the dataset"""
    netcdf_path = "tests/data/test_arome_arctic.nc"
    query_string = ("?&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=wind_10m_vector&WIDTH=767&HEIGHT=880&CRS=EPSG%3A3857&"
                    "BBOX=-4891698.287598623,6944679.416003374,10026224.553483257,24060418.79038676&STYLES=vector&"
                    "FORMAT=image/png&TRANSPARENT=TRUE&&TIME=2024-11-11T07%3A00%3A00Z&DIM_SPACING=32&DIM_COLOUR=light-green")
    http_host = "localhost"
    url_scheme = "http"
    shared_cache = {}
    mock_csw.return_value = "TEST CSW"
    mock_read_config.return_value =  {'pattern': r'^(.*data/test_arome_arctic.nc)$',
                                 'base_netcdf_directory': '.',
                                 'module': 'mapgen.modules.arome_arctic_quicklook',
                                 'module_function': 'arome_arctic_quicklook',
                                 'mapfile_template': os.path.join(tmpdir, 'test.map'),
                                 'map_file_bucket': 'test-map-bucket',
                                 'geotiff_bucket': 'test_bucket',
                                 'mapfiles_path': tmpdir,
                                 'geotiff_tmp': tmpdir,
                                 'default_dataset': 'presure'}, None, None, None

    caplog.set_level(logging.DEBUG)
    response_code, result, content_type = get_quicklook(netcdf_path, query_string, http_host, url_scheme, shared_cache, products=[])
    if response_code == '500 Internal Server Error':
        assert 'msProcessProjection()' in caplog.text
    else:
        assert response_code == '200 OK'
    assert 'Selected style: vector' in caplog.text
    assert 'VECTOR wind_10m_vector x_wind_10m y_wind_10m' in caplog.text

if __name__ == '__main__':
    #_create_arome_arctic_dataset_from_orig_data()
    _create_arome_arctic_dataset_from_orig_data_without_reference_time()
