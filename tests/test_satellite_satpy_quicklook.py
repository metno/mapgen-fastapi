"""Test arome arctic"""
import os
import logging
import datetime
import xarray as xr
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
from mapgen.modules.get_quicklook import get_quicklook

def test_get_satpy_products_is_list():
    from mapgen.modules.satellite_satpy_quicklook import _get_satpy_products
    assert isinstance(_get_satpy_products(None,{'layers': 'overview'}, 'overview'), list)
    assert isinstance(_get_satpy_products(None,{'layers': ['overview']}, 'overview'), list)
    assert isinstance(_get_satpy_products(None,{'LAYERS': 'overview'}, 'overview'), list)
    assert isinstance(_get_satpy_products(None,{'LAYERS': ['overview']}, 'overview'), list)

    assert isinstance(_get_satpy_products(None,{'layer': 'overview'}, 'overview'), list)
    assert isinstance(_get_satpy_products(None,{'layer': ['overview']}, 'overview'), list)
    assert isinstance(_get_satpy_products(None,{'LAYER': 'overview'}, 'overview'), list)
    assert isinstance(_get_satpy_products(None,{'LAYER': ['overview']}, 'overview'), list)

    assert isinstance(_get_satpy_products(None,{'NA': 'overview'}, 'overview'), list)

    assert isinstance(_get_satpy_products('overview',{'NA': 'overview'}, 'overview'), list)
