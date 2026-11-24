"""Constants for the Smart Garden integration."""
from datetime import timedelta

DOMAIN = "smart_garden"
CONF_KEY = "key"
CONF_SIDEBAR = "sidebar"          # show the Smart Garden dashboard in the sidebar
CONF_PANEL_URL = "panel_url"      # optional: also the full app as a web page in the sidebar
SCAN_INTERVAL = timedelta(seconds=10)
INFO_EVERY = 30               # re-read zones/sensors/schedules every 30 updates (~5 min)
PANEL_PATH = "smart-garden"
STATIC_URL = "/smart_garden_static"
