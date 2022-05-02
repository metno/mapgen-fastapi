import os
import glob
import datetime
from jinja2 import Environment, FileSystemLoader

def generate_mapfile(regexp_pattern_module, netcdf_path, netcdf_file_name, map_file_name):
    print("Inside generate mapfile")
    mapfile_template_dir = os.path.dirname(regexp_pattern_module['mapfile_template'])
    if not os.path.exists(mapfile_template_dir):
        mapfile_template_dir = os.path.join('app', mapfile_template_dir)
    print(mapfile_template_dir)
    env = Environment(loader=FileSystemLoader(mapfile_template_dir))
    mt = env.get_template(os.path.basename(regexp_pattern_module['mapfile_template']))

    start_time = datetime.datetime.strptime(netcdf_file_name.split("-")[-2], '%Y%m%d%H%M%S')
    print(start_time)
    base_dir = '/lustre/storeA/project/metproduction/products/satdata_polar/senda/'
    base_dir = '/lustre/storeA/project/metproduction/products/satdata_polar/senda-bb/'
    previews = glob.glob(f'{base_dir}*{start_time:%Y%m%d_%H%M%S}.tif')
    print(previews)
    if not len(previews):
        # No previews found. No need to generate map config file
        return False

    layers_render_data = []
    for preview in previews:
        base_preview, _ = os.path.splitext(os.path.basename(preview))
        layer_name = '_'.join(base_preview.split('_')[:-2])
        layer_render_data = {'preview': preview,
                             'preview_stamp': datetime.datetime.strftime(start_time, '%Y-%m-%dT%H:%M:%SZ'),
                             'layer_name': layer_name}
        layers_render_data.append(layer_render_data)

    redered_map_template = mt.render(layers=layers_render_data,
                                     map_file_name=map_file_name,
                                     netcdf_path=netcdf_path,
                                     mapserver_url='fastapi-dev.s-enda.k8s.met.no/mapserver')
    print(redered_map_template)

    with open(map_file_name, "w") as map_file:
        map_file.write(redered_map_template)
        map_file.close()

    return True