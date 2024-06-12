"""
gridded data quicklook : module
====================

Copyright 2023 MET Norway

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

"""
Needed entries in the config:
---
  - 'pattern': '^(.*satellite-thredds/polar-swath/\d{4}/\d{2}/\d{2}/)(metopb|metopc)-(avhrr)-(\d{14})-(\d{14})\.nc$'
    'base_netcdf_directory': '/lustre/storeB/immutable/archive/projects/remotesensing'
    'module': 'mapgen.modules.gridded_data_quicklook_template'
    'module_function': 'gridded_data_quicklook_template'
    'default_dataset': 'air_temperature'

            #The following is not needed for gridded data, but is available
            'mapfile_template': '/mapfile-templates/mapfile.map'
            'map_file_bucket': 's-enda-mapfiles'
            'geotiff_bucket': 'geotiff-products-for-senda'
            'mapfiles_path': '.'
            'geotiff_tmp': '.'

"""
import os
import pandas
import datetime
import mapscript
from fastapi import Request, Query, HTTPException
import xarray as xr
from mapgen.modules.create_symbol_file import create_symbol_file
from mapgen.modules.helpers import handle_request, _fill_metadata_to_mapfile, _parse_filename, _get_mapfiles_path
from mapgen.modules.helpers import _generate_getcapabilities, _generate_getcapabilities_vector, _generate_layer

grid_mapping_cache = {}
summary_cache = {}
wind_rotation_cache = {}

# def _generate_layer(layer, ds, grid_mapping_cache, netcdf_file, qp, map_obj, product_config):
#     try:
#         variable = qp['layer']
#     except KeyError:
#         variable = qp['layers']
#     try:
#         style = qp['styles']
#     except KeyError:
#         style = qp['style']
#     if style == "":
#         print("Empty style. force raster.")
#         style = 'raster'
#     print(f"Selected style: {style}")

#     actual_variable = variable
#     #if style in 'contour': #variable.endswith('_contour'):
#     #    actual_variable = '_'.join(variable.split("_")[:-1])
#     if variable.endswith('_vector'):
#         actual_x_variable = '_'.join(['x'] + variable.split("_")[:-1])
#         actual_y_variable = '_'.join(['y'] + variable.split("_")[:-1])
#         vector_variable_name = variable
#         actual_variable = actual_x_variable
#         print("VECTOR", vector_variable_name, actual_x_variable, actual_y_variable)

#     dimension_search = _find_dimensions(ds, actual_variable, variable, qp)
#     band_number = _calc_band_number_from_dimensions(dimension_search)
#     if variable.endswith('_vector'):
#         layer.setProcessingKey('BANDS', f'1,2')
#     else:
#         layer.setProcessingKey('BANDS', f'{band_number}')

#     grid_mapping_name = _find_projection(ds, actual_variable, grid_mapping_cache)
#     layer.setProjection(grid_mapping_cache[grid_mapping_name])
#     layer.status = 1
#     if variable.endswith('_vector'):
#         x_vector_param = 'x_wind_10m'
#         y_vector_param = 'y_wind_10m'

#         timestep = 0
#         if timestep is not None:
#             ds = ds.isel(**{'time': timestep, 'height7': 0})
#         #ds = ds.sel(height7=1, method='nearest', drop=True)
#         print(ds.dims)
#         grid_mapping_name = ds['x_wind_10m'].attrs['grid_mapping']
#         grid_mapping = ds[grid_mapping_name]

#         standard_name_prefix = 'wind'
#         speed = _get_speed(
#             ds[x_vector_param],
#             ds[y_vector_param],
#             f'{standard_name_prefix}_speed'
#         )
#         from_direction = _get_from_direction(
#             ds[x_vector_param],
#             ds[y_vector_param],
#             f'{standard_name_prefix}_from_direction'
#         )

#         # Rotate wind direction, so it relates to the north pole, rather than to the grid's y direction.
#         north = _get_north(x_vector_param, ds)
#         _rotate_relative_to_north(from_direction, north)

#         print("from direction", from_direction)
#         new_x = np.sin(from_direction) * speed
#         new_y = np.cos(from_direction) * speed
#         print("Newx new y", new_x, new_y)

#         gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "xvar.vrt"),
#                     [f'NETCDF:{netcdf_file}:{actual_x_variable}'],
#                     **{'bandList': [band_number]})
#         gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), "yvar.vrt"),
#                     [f'NETCDF:{netcdf_file}:{actual_y_variable}'],
#                     **{'bandList': [band_number]})
#         variable_file_vrt = f'var-{actual_x_variable}-{actual_y_variable}-{band_number}.vrt'
#         gdal.BuildVRT(os.path.join(_get_mapfiles_path(product_config), variable_file_vrt),
#                     [os.path.join(_get_mapfiles_path(product_config), 'xvar.vrt'),
#                      os.path.join(_get_mapfiles_path(product_config), 'yvar.vrt')],
#                     **{'separate': True})
#         layer.data = os.path.join(_get_mapfiles_path(product_config), variable_file_vrt)
#     else:
#         layer.data = f'NETCDF:{netcdf_file}:{actual_variable}'

#     if style in 'contour': #variable.endswith('_contour'):
#         print("Style in contour for config")
#         print("Dataset attrs:", ds[actual_variable].attrs)
#         layer.type = mapscript.MS_LAYER_LINE
#         layer.setConnectionType(mapscript.MS_CONTOUR, "")
#         layer.setProcessingKey('CONTOUR_INTERVAL', f'{500}')
#         layer.setProcessingKey('CONTOUR_ITEM', 'contour')
#         layer.setGeomTransform('smoothsia(generalize([shape], 0.25*[data_cellsize]))')
#     elif variable.endswith('_vector'):
#         layer.setConnectionType(mapscript.MS_UVRASTER, "")
#         layer.type = mapscript.MS_LAYER_POINT
#     else:
#         layer.type = mapscript.MS_LAYER_RASTER
#     layer.name = variable
#     if variable.endswith('_vector'):
#         layer.metadata.set("wms_title", '_'.join(variable.split("_")[:-1]))
#     else:
#         layer.metadata.set("wms_title", variable)
#     ll_x, ur_x, ll_y, ur_y = _extract_extent(ds, actual_variable)
#     layer.metadata.set("wms_extent", f"{ll_x} {ll_y} {ur_x} {ur_y}")


#     if variable.endswith('_vector'):
#         s = mapscript.classObj(layer)
#         style = mapscript.styleObj(s)
#         # style.updateFromString('STYLE SYMBOL "horizline" ANGLE [uv_angle] SIZE [uv_length] WIDTH 3 COLOR 100 255 0 END')
#         # style.setSymbolByName(map_obj, "horizline")
#         style.updateFromString('STYLE SYMBOL "vector_arrow" ANGLE [uv_angle] SIZE [uv_length] WIDTH 3 COLOR 100 255 0 END')
#         style.setSymbolByName(map_obj, "vector_arrow")
#         #layer.setProcessingKey('UV_SIZE_SCALE', '2')

#         # #style.autoangle = "[uv_angle]"
#         # style.angle = 43
#         # #"[uv_angle]"
#         #style.size = style.size*2
#         # #"[uv_length]"
#         # style.width = 3
#         # style.color = mapscript.colorObj(red=100, green=255, blue=0)
#     else:
#         if len(dimension_search) == 1:
#             print("Len 1")
#             _ds = ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data
#             if '_FillValue' in ds[actual_variable].attrs:
#                 print("FillValue:", ds[actual_variable].attrs)
#                 _ds = np.where(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data == ds[actual_variable].attrs['_FillValue'],
#                                np.nan,
#                                ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
#             #min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
#             #max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],:,:].data)
#         elif len(dimension_search) == 2:
#             print("Len 2 of ", actual_variable)
#             _ds = ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data
#             if '_FillValue' in ds[actual_variable].attrs:
#                 _ds = np.where(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data == ds[actual_variable].attrs['_FillValue'],
#                                np.nan,
#                                ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
#             #min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
#             #max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],:,:].data)
#         # Find which band
#         elif len(dimension_search) == 3:
#             print("Len 3")
#             _ds = ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data
#             if '_FillValue' in ds[actual_variable].attrs:
#                 _ds = np.where(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data == ds[actual_variable].attrs['_FillValue'], 
#                                np.nan,
#                                ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
#             #min_val = np.nanmin(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
#             #max_val = np.nanmax(ds[actual_variable][dimension_search[0]['selected_band_number'],dimension_search[1]['selected_band_number'],dimension_search[2]['selected_band_number'],:,:].data)
#         else:
#             print("Undefined lenght of dimension search ", len(dimension_search))
#         min_val = np.nanmin(_ds)
#         max_val = np.nanmax(_ds)
#         print("MIN:MAX ", min_val, max_val)
#         # print(ds[actual_variable].attrs)
#         # if 'scale_factor' in ds[actual_variable].attrs:
#         #     print("Setting scale factor to the data.")
#         #     min_val *= ds[actual_variable].attrs['scale_factor']
#         #     max_val *= ds[actual_variable].attrs['scale_factor']
#         #     print("Scaled with scale_factor MIN:MAX ", min_val, max_val)
#         #     layer.setProcessingKey("SCALE",f'{min_val},{max_val}')
#         #     layer.setProcessingKey("SCALE_BUCKETS", "256")
#         #Grayscale
#         s = mapscript.classObj(layer)
#         if style in 'contour': #variable.endswith('_contour'):
#             print("Style in contour for style setup.")
#             layer.labelitem = 'contour'
#             s.name = "contour"
#             style = mapscript.styleObj(s)
#             style.width = 1
#             style.color = mapscript.colorObj(red=0, green=0, blue=255)
#             label = mapscript.labelObj()
#             label.setText('(tostring(([contour]/100),"%.0f"))')
#             #label.setText("(tostring(([contour]/100),'%.0f'))")
#             print(label.convertToString())
#             label.color = mapscript.colorObj(red=0, green=0, blue=255)
#             #label.font = 'sans'
#             # TYPE truetype
#             label.size = 10
#             label.position = mapscript.MS_CC
#             label.force = True
#             label.angle = 0 #mapscript.MS_AUTO
#             s.addLabel(label)
#         else:
#             print("Raster scaling")
#             s.name = "Linear grayscale using min and max not nan from data"
#             s.group = 'raster'
#             style = mapscript.styleObj(s)
#             style.rangeitem = 'pixel'
#             style.mincolor = mapscript.colorObj(red=0, green=0, blue=0)
#             style.maxcolor = mapscript.colorObj(red=255, green=255, blue=255)
#             style.minvalue = float(min_val)
#             style.maxvalue = float(max_val)

#     return True

def generic_quicklook(netcdf_path: str,
                      full_request: Request,
                      products: list = Query(default=[]),
                      product_config: dict = {}):
    netcdf_path = netcdf_path.replace("//", "/")
    orig_netcdf_path = netcdf_path
    try:
        if netcdf_path.startswith(product_config['base_netcdf_directory']):
            print("Request with full path. Please fix your request. Depricated from version 2.0.0.")
        elif os.path.isabs(netcdf_path):
            netcdf_path = netcdf_path[1:]
        netcdf_path = os.path.join(product_config['base_netcdf_directory'], netcdf_path)
    except KeyError:
        raise HTTPException(status_code=500, detail="Missing base dir in server config.")

    if not netcdf_path:
        raise HTTPException(status_code=404, detail="Missing netcdf path")

    # Read all variables names from the netcdf file.
    is_ncml = False
    try:
        ds_disk = xr.open_dataset(netcdf_path, mask_and_scale=False)
    except ValueError:
        try:
            import xncml
            ds_disk = xncml.open_ncml(netcdf_path)
            is_ncml = True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Can not open file. Either not existing or ncml file: {e}")

    # variables = list(ds_disk.keys())

    #get forecast reference time from dataset
    try:
        if is_ncml:
            if len(ds_disk['forecast_reference_time'].data) > 1:
                if ds_disk['forecast_reference_time'].attrs['units'] == 'seconds since 1970-01-01 00:00:00 +00:00':
                    forecast_time = datetime.timedelta(seconds=ds_disk['forecast_reference_time'].data[0]) + datetime.datetime(1970,1,1)
                else:
                    raise HTTPException(status_code=500, detail=f"This unit is not implemented: {ds_disk['forecast_reference_time'].attrs['units']}")
            try:
                print(ds_disk['time'].dt)
            except TypeError:
                if ds_disk['time'].attrs['units'] == 'seconds since 1970-01-01 00:00:00 +00:00':
                    ds_disk['time'] = pandas.TimedeltaIndex(ds_disk['time'], unit='s') + datetime.datetime(1970, 1, 1)
                    ds_disk['time'] = pandas.to_datetime(ds_disk['time'])
                else:
                    print(f"This unit is not implemented: {ds_disk['time'].attrs['units']}")
                    raise HTTPException(status_code=500, detail=f"This unit is not implemented: {ds_disk['time'].attrs['units']}")

        else:
            forecast_time = pandas.to_datetime(ds_disk['forecast_reference_time'].data).to_pydatetime()
    except KeyError:
        try:
            print("Could not find forecast time or analysis time from dataset. Try parse from filename.")
            # Parse the netcdf filename to get start time or reference time
            _, _forecast_time = _parse_filename(netcdf_path, product_config)
            forecast_time = datetime.datetime.strptime(_forecast_time, "%Y%m%dT%H")
            print(forecast_time)
        except ValueError:
            print("Could not find any forecast_reference_time. Try use time_coverage_start.")
            try:
                forecast_time = datetime.datetime.fromisoformat(ds_disk.time_coverage_start)
                print(forecast_time)
            except Exception as ex:
                print(f"Could not find any forecast_reference_time. Use now. Last unhandled exception: {str(ex)}")
                forecast_time = datetime.datetime.now()

    symbol_file = os.path.join(_get_mapfiles_path(product_config), "symbol.sym")
    create_symbol_file(symbol_file)
 
    # symbol = mapscript.symbolObj("horizline")
    # symbol.name = "horizline"
    # symbol.type = mapscript.MS_SYMBOL_VECTOR
    # po = mapscript.pointObj()
    # po.setXY(0, 0)
    # lo = mapscript.lineObj()
    # lo.add(po)
    # po.setXY(1, 0)
    # lo.add(po)
    # symbol.setPoints(lo)

    # symbol_obj = mapscript.symbolSetObj()
    # symbol_obj.appendSymbol(symbol)

    # # Create vector arrow
    # symbol_wa = mapscript.symbolObj("vector_arrow")
    # symbol_wa.name = "vector_arrow"
    # symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
    # #po = mapscript.pointObj()
    # #po.setXY(0, 0)
    # lo = mapscript.lineObj()
    # lo.add(mapscript.pointObj(0,0))
    # lo.add(mapscript.pointObj(-4,3))
    # lo.add(mapscript.pointObj(-3,0.75))
    # lo.add(mapscript.pointObj(-10,0.75))
    # lo.add(mapscript.pointObj(-10,-0.75))
    # lo.add(mapscript.pointObj(-3,-0.75))
    # lo.add(mapscript.pointObj(-4,-3))
    # lo.add(mapscript.pointObj(0,0))
    # #po.setXY(1, 0)
    # #lo.add(po)
    # #FILLED true
    # # Place the according to its center
    # #ANCHORPOINT 0.5 0.5
    # symbol_wa.setPoints(lo)
    # symbol_wa.anchorpoint_x = 0.
    # symbol_wa.anchorpoint_y = 0.
    # symbol_wa.filled = True
    # #symbol_obj = mapscript.symbolSetObj()
    # symbol_obj.appendSymbol(symbol_wa)


    # symbol_obj.save(os.path.join(_get_mapfiles_path(product_config), "symbol.sym"))
    # map_object.setSymbolSet(os.path.join(_get_mapfiles_path(product_config),"symbol.sym"))

    qp = {k.lower(): v for k, v in full_request.query_params.items()}
    print(qp)

    layer_no = 0
    map_object = None
    if 'request' in qp and qp['request'] != 'GetCapabilities':
        mapserver_map_file = os.path.join(_get_mapfiles_path(product_config), f'{os.path.basename(orig_netcdf_path)}.map')
        map_object = mapscript.mapObj()
        _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, full_request, ds_disk, summary_cache, "Generic netcdf WMS")
        map_object.setSymbolSet(symbol_file)
        layer = mapscript.layerObj()
        if _generate_layer(layer, ds_disk, grid_mapping_cache, netcdf_path, qp, map_object, product_config, wind_rotation_cache):
            layer_no = map_object.insertLayer(layer)
    else:
        # Assume getcapabilities
        mapserver_map_file = os.path.join(_get_mapfiles_path(product_config), f'{os.path.basename(orig_netcdf_path)}-getcapabilities.map')
        if os.path.exists(mapserver_map_file):
            print(f"Reuse existing getcapabilities map file {mapserver_map_file}")
            map_object = mapscript.mapObj(mapserver_map_file)
        else:
            map_object = mapscript.mapObj()
            _fill_metadata_to_mapfile(orig_netcdf_path, forecast_time, map_object, full_request, ds_disk, summary_cache, "Generic netcdf WMS")
            map_object.setSymbolSet(symbol_file)
            # Read all variables names from the netcdf file.
            variables = list(ds_disk.keys())
            for variable in variables:
                layer = mapscript.layerObj()
                if _generate_getcapabilities(layer, ds_disk, variable, grid_mapping_cache, netcdf_path):
                    layer_no = map_object.insertLayer(layer)
                if variable.startswith('x_wind') and variable.replace('x', 'y') in variables:
                    print(f"Add wind vector layer for {variable}.")
                    layer_contour = mapscript.layerObj()
                    if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path, direction_speed=False):
                        layer_no = map_object.insertLayer(layer_contour)
                if variable == 'wind_direction' and 'wind_speed' in variables:
                    print(f"Add wind vector layer based on wind direction and speed for {variable}.")
                    layer_contour = mapscript.layerObj()
                    if _generate_getcapabilities_vector(layer_contour, ds_disk, variable, grid_mapping_cache, netcdf_path, direction_speed=True):
                        layer_no = map_object.insertLayer(layer_contour)

    if layer_no == 0 and not map_object:
        print(f"No layers {layer_no} or no map_object {map_object}")
        raise HTTPException(status_code=500, detail=("Could not find any variables to turn into OGC WMS layers. One reason can be your data does "
                                                     "not have a valid grid_mapping (Please see CF grid_mapping), or internal resampling failed."))

    map_object.save(os.path.join(_get_mapfiles_path(product_config), f'generic-{forecast_time:%Y%m%d%H%M%S}.map'))

    # Handle the request and return results.
    return handle_request(map_object, full_request)
