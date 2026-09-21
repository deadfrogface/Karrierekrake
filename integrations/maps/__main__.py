"""Run the minimal Karrierekrake Google Maps proxy.

  export KARRIEREKRAKE_GOOGLE_MAPS_API_KEY=...
  export KARRIEREKRAKE_MAPS_PROXY_TOKEN=...
  python -m integrations.maps.proxy
"""

from integrations.maps.proxy import run_proxy_main

if __name__ == "__main__":
    run_proxy_main()
