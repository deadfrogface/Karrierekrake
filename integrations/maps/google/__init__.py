"""Google Geocoding helpers (proxy-backed). Package marker for google/."""

from __future__ import annotations

# Implementation lives in integrations.maps.proxy.MapsProxyBackend.geocode
# and integrations.maps.client.MapsProxyClient.geocode — keep this module as
# the stable import surface for geocoding-specific constants.

GEOCODING_API = "Geocoding API"
DATA_SOURCE = "google_geocoding"
DATA_VERSION = "maps-geocoding-v1"
