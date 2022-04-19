
# methods to perform some processing
# the worker can be used on the main machine
# or we can, later on. send them to celery + rabbitmq

from starlette.templating import Jinja2Templates


templates = Jinja2Templates(directory='/app/templates')

def make_mapfile(mapfile_dict):
    response = parse_spec(mapfile_dict)
    return response

def parse_spec(mapfile_dict):
    # this should: 
    # - parse the config
    # - chose the appropriate routine to generate a mapfile
    # - save it in the sharfed volume
    return False



