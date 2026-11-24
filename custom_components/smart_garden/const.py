"""Constants for the Smart Garden integration."""
from datetime import timedelta

DOMAIN = "smart_garden"
CONF_KEY = "key"
CONF_SIDEBAR = "sidebar"
CONF_PANEL_URL = "panel_url"
SCAN_INTERVAL = timedelta(seconds=10)
INFO_EVERY = 30               # re-read zones/sensors/schedules every 30 updates (~5 min)
PANEL_PATH = "smart-garden"
