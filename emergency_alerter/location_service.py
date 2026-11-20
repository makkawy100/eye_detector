"""
Real-time Location Service
Provides real live GPS / geographic coordinates for emergency alerts.
Supports:
  1. Automated Real-Time Network Geolocation (Zero hardware required).
  2. Hardware Serial GPS Module (e.g. u-blox NEO-6M / NEO-8M via UART/USB).
  3. Seamless in-memory caching and offline fallback.
"""

import logging
import threading
import time
from typing import Tuple, Optional
import requests

logger = logging.getLogger("LocationService")


class LocationService:
    def __init__(
        self,
        default_lat: float = 31.209093,
        default_lon: float = 29.923094,
        default_location_name: str = "Specialized Scientific Programs, Faculty of Engineering",
        maps_url: Optional[str] = "https://maps.app.goo.gl/BcYvS5KqdEdAYyi4A",
        use_fixed_location: bool = True,
        gps_serial_port: Optional[str] = None,
        gps_baudrate: int = 9600,
        cache_ttl_seconds: int = 300,
    ):
        """
        :param default_lat: Latitude (e.g. 31.206157)
        :param default_lon: Longitude (e.g. 29.924451)
        :param default_location_name: Location label
        :param maps_url: Direct Google Maps URL
        :param use_fixed_location: If True, always uses fixed location specified by user
        :param gps_serial_port: Optional serial port for physical GPS module
        :param gps_baudrate: Baudrate for GPS module
        :param cache_ttl_seconds: Cache duration for network geolocation
        """
        self.default_lat = default_lat
        self.default_lon = default_lon
        self.default_location_name = default_location_name
        self.maps_url = maps_url or f"https://maps.google.com/?q={default_lat:.6f},{default_lon:.6f}"
        self.use_fixed_location = use_fixed_location
        self.gps_serial_port = gps_serial_port
        self.gps_baudrate = gps_baudrate
        self.cache_ttl_seconds = cache_ttl_seconds

        self._cached_lat: float = default_lat
        self._cached_lon: float = default_lon
        self._cached_name: str = default_location_name
        self._cached_maps_url: str = self.maps_url
        self._last_fetch_time: float = 0.0
        self._lock = threading.Lock()

        # If not fixed, fetch live location in background
        if not self.use_fixed_location:
            threading.Thread(target=self.refresh_location, daemon=True).start()

    def refresh_location(self) -> Tuple[float, float, str, str]:
        """Queries live network geolocation or hardware GPS to update coordinates."""
        if self.use_fixed_location:
            logger.info(f"📍 Using Fixed User Location: {self.default_location_name} ({self.default_lat:.6f}, {self.default_lon:.6f})")
            return self.default_lat, self.default_lon, self.default_location_name, self.maps_url

        # 1. Attempt Hardware GPS if configured
        if self.gps_serial_port:
            gps_result = self._read_hardware_gps()
            if gps_result:
                lat, lon = gps_result
                url = f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
                with self._lock:
                    self._cached_lat = lat
                    self._cached_lon = lon
                    self._cached_name = f"Live GPS Satellites ({lat:.4f}, {lon:.4f})"
                    self._cached_maps_url = url
                    self._last_fetch_time = time.time()
                logger.info(f"📍 Acquired Real Hardware GPS Location: {lat:.6f}, {lon:.6f}")
                return lat, lon, self._cached_name, url

        # 2. Attempt Live Network / IP Geolocation
        try:
            resp = requests.get("http://ip-api.com/json", timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    lat = float(data.get("lat", self._cached_lat))
                    lon = float(data.get("lon", self._cached_lon))
                    city = data.get("city", "")
                    region = data.get("regionName", "")
                    country = data.get("country", "")
                    loc_name = f"{city}, {region}, {country}".strip(", ")
                    url = f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"

                    with self._lock:
                        self._cached_lat = lat
                        self._cached_lon = lon
                        self._cached_name = loc_name or "Live Real Location"
                        self._cached_maps_url = url
                        self._last_fetch_time = time.time()

                    logger.info(f"📍 Acquired Live Real Location: {loc_name} ({lat:.4f}, {lon:.4f})")
                    return lat, lon, self._cached_name, url
        except Exception as e:
            logger.debug(f"Network location lookup info: {e}")

        # Return cached / fallback
        with self._lock:
            return self._cached_lat, self._cached_lon, self._cached_name, self._cached_maps_url

    def get_location(self) -> Tuple[float, float, str, str]:
        """Returns (latitude, longitude, location_name, maps_url)."""
        if self.use_fixed_location:
            return self.default_lat, self.default_lon, self.default_location_name, self.maps_url

        now = time.time()
        with self._lock:
            needs_refresh = (now - self._last_fetch_time) > self.cache_ttl_seconds
            lat, lon, name, url = self._cached_lat, self._cached_lon, self._cached_name, self._cached_maps_url

        if needs_refresh:
            threading.Thread(target=self.refresh_location, daemon=True).start()

        return lat, lon, name, url

    def _read_hardware_gps(self) -> Optional[Tuple[float, float]]:
        """Reads one valid fix from a hardware NMEA serial GPS module if connected."""
        try:
            import serial
            with serial.Serial(self.gps_serial_port, self.gps_baudrate, timeout=1.5) as ser:
                start = time.time()
                while time.time() - start < 2.0:
                    line = ser.readline().decode("ascii", errors="replace").strip()
                    if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                        parts = line.split(",")
                        if len(parts) > 6 and parts[2] == "A":  # 'A' = Valid fix
                            lat = self._nmea_to_decimal(parts[3], parts[4])
                            lon = self._nmea_to_decimal(parts[5], parts[6])
                            if lat is not None and lon is not None:
                                return lat, lon
        except Exception as e:
            logger.debug(f"Hardware GPS read skipped: {e}")
        return None

    @staticmethod
    def _nmea_to_decimal(nmea_val: str, direction: str) -> Optional[float]:
        try:
            if not nmea_val:
                return None
            dot = nmea_val.find(".")
            deg_digits = dot - 2
            degrees = float(nmea_val[:deg_digits])
            minutes = float(nmea_val[deg_digits:])
            decimal = degrees + (minutes / 60.0)
            if direction in ["S", "W"]:
                decimal = -decimal
            return decimal
        except Exception:
            return None
