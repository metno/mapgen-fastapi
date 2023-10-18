"""
Helpers
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

import os
import re
import sys
import yaml
import traceback
from fastapi import HTTPException

def _read_config_file(regexp_config_file):
    regexp_config = None
    try:
        if os.path.exists(regexp_config_file):
            with open(regexp_config_file) as f:
                regexp_config = yaml.load(f, Loader=yaml.loader.SafeLoader)
    except Exception as e:
        print(f"Failed to read yaml config: {regexp_config_file} with {str(e)}")
        pass
    return regexp_config

def find_config_for_this_netcdf(netcdf_path):
    default_regexp_config_filename = 'url-path-regexp-patterns.yaml'
    default_regexp_config_dir = '/config'
    if os.path.exists(os.path.join('./', default_regexp_config_filename)):
        regexp_config_file = os.path.join('./', default_regexp_config_filename)
    else:
        regexp_config_file = os.path.join(default_regexp_config_dir,
                                          default_regexp_config_filename)
    regexp_config = _read_config_file(regexp_config_file)
    regexp_pattern_module = None
    if regexp_config:
        try:
            for url_path_regexp_pattern in regexp_config:
                print(url_path_regexp_pattern)
                pattern = re.compile(url_path_regexp_pattern['pattern'])
                if pattern.match(netcdf_path):
                    print("Got match. Need to load module:", url_path_regexp_pattern['module'])
                    regexp_pattern_module = url_path_regexp_pattern
                    break
                else:
                    print(f"Could not find any match for the path {netcdf_path} in the configuration file {regexp_config_file}.")
                    print("Please review your config if you expect this path to be handled.")
            
        except Exception as e:
            print(f"Exception in the netcdf_path match part with {str(e)}")
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            raise HTTPException(status_code=500, detail=f"Exception raised when regexp. Check the config.")
    if not regexp_pattern_module:
        raise HTTPException(status_code=501, detail=f"Could not match against any pattern. Check the config.")

    return regexp_pattern_module