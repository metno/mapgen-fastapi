from bokeh.io import curdoc
from bokeh.models import Div
import bokeh

div = Div(text='Hello from bokeh {}'.format(bokeh.__version__))

curdoc().add_root(div)