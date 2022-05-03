import os
import re
import boto3
import datetime
from jinja2 import Environment, FileSystemLoader

def list_files_in_bucket(bucket, start_time):
    """Assume less than 1000 objects in bucket with this prefix"""
    files_in_bucket = []
    s3_client = boto3.client(service_name='s3',
                             endpoint_url=os.environ['S3_ENDPOINT_URL'],
                             aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                             aws_secret_access_key=os.environ['S3_SECRET_KEY'])
    try:
        bucket_objects = s3_client.list_objects(Bucket=bucket, Prefix=f'{start_time:%Y/%m/%d}')
        print(bucket_objects)
    except Exception as e:
        print("s3 client/list object failed with: ", str(e))
        return files_in_bucket

    if 'Contents' in bucket_objects:
        for content in bucket_objects['Contents']:
            files_in_bucket.append(content['Key'])
    print(files_in_bucket)
    return files_in_bucket

def get_previews(start_time, regexp_pattern_module):
    files_in_bucket = list_files_in_bucket(regexp_pattern_module['geotiff_bucket'], start_time)
    previews = []
    pattern = re.compile(f'{start_time:%Y/%m/%d/}.*{start_time:%Y%m%d_%H%M%S}.tif')
    for file_in_bucket in files_in_bucket:
        print ("Checking file in bucket", file_in_bucket)
        if pattern.match(file_in_bucket):
            previews.append(file_in_bucket)
    return previews

def build_render_data(regexp_pattern_module, start_time, previews):
    layers_render_data = []
    for preview in previews:
        base_preview, _ = os.path.splitext(os.path.basename(preview))
        layer_name = '_'.join(base_preview.split('_')[:-2])
        layer_render_data = {'preview': os.path.join('/vsicurl',
                                                     os.environ['S3_ENDPOINT_URL'],
                                                     os.environ['S3_TENANT'] + ':' + regexp_pattern_module['geotiff_bucket'],
                                                     preview),
                             'preview_stamp': datetime.datetime.strftime(start_time, '%Y-%m-%dT%H:%M:%SZ'),
                             'layer_name': layer_name}
        layers_render_data.append(layer_render_data)
    return layers_render_data

def get_mapfile_template(regexp_pattern_module):
    mapfile_template_dir = os.path.dirname(regexp_pattern_module['mapfile_template'])
    if not os.path.exists(mapfile_template_dir):
        mapfile_template_dir = os.path.join('app', mapfile_template_dir)
    print(mapfile_template_dir)
    env = Environment(loader=FileSystemLoader(mapfile_template_dir))
    return env.get_template(os.path.basename(regexp_pattern_module['mapfile_template']))

def generate_mapfile(regexp_pattern_module, netcdf_path, netcdf_file_name, map_file_name):
    print("Inside generate mapfile")
    mt = get_mapfile_template(regexp_pattern_module)

    start_time = datetime.datetime.strptime(netcdf_file_name.split("-")[-2], '%Y%m%d%H%M%S')
    previews = get_previews(start_time, regexp_pattern_module)
    if not len(previews):
        # No previews found. No need to generate map config file
        return False

    layers_render_data = build_render_data(regexp_pattern_module, start_time, previews)

    redered_map_template = mt.render(layers=layers_render_data,
                                     map_file_name=map_file_name,
                                     netcdf_path=netcdf_path,
                                     mapserver_url='fastapi-dev.s-enda.k8s.met.no/mapserver')
    print(redered_map_template)

    with open(map_file_name, "w") as map_file:
        map_file.write(redered_map_template)
        map_file.close()

    return True
