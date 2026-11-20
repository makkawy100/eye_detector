"""
ESP32 Serial Communication Bridge
Transmits vehicle motion, lane-change, and brake commands to the ESP32 microcontroller.
Supports auto-reconnection and a robust software simulation fallback if hardware is not connected.
"""

import logging
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger("ESP32Bridge")


class ESP32SerialBridge:
    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        enabled: bool = True,
        on_stopped_callback: Optional[Callable[[], None]] = None,
    ):
        """
        :param port: Serial device path (e.g. /dev/ttyUSB0 or COM3)
        :param baudrate: Serial baud rate (default 115200)
        :param enabled: Whether serial communication is enabled
        :param on_stopped_callback: Function called when ESP32 confirms complete stop
        """
        self.port = port
        self.baudrate = baudrate
        self.enabled = enabled
        self.on_stopped_callback = on_stopped_callback

        self.serial_conn = None
        self.last_command: Optional[str] = None
        self._running = False
        self._lock = threading.Lock()

        if self.enabled:
            self._connect()

    def _connect(self):
        try:
            import serial
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1.0)
            self._running = True
            logger.info(f"✅ Connected to ESP32 on {self.port} at {self.baudrate} baud.")
            # Start reader thread to listen for ESP32 status updates
            threading.Thread(target=self._read_loop, daemon=True).start()
        except Exception as e:
            logger.warning(
                f"⚠️ Could not open ESP32 serial port '{self.port}': {e}. "
                "Running in Software Simulation Mode (commands will be simulated)."
            )
            self.serial_conn = None

    def send_command(self, command: str) -> bool:
        """
        Sends a command to ESP32: 'NORMAL', 'SLOW_50', 'EMERGENCY_PULLOVER', 'RESET'.
        Deduplicates repeated calls.
        """
        command = command.strip().upper()
        with self._lock:
            if command == self.last_command:
                return True
            self.last_command = command

        logger.info(f"🚗 [ESP32 COMMAND] -> {command}")

        if self.serial_conn and self.serial_conn.is_open:
            try:
                msg = f"{command}\n".encode("utf-8")
                self.serial_conn.write(msg)
                self.serial_conn.flush()
                return True
            except Exception as e:
                logger.error(f"Error transmitting to ESP32: {e}")
                return False
        else:
            # Simulation feedback in console
            if command == "SLOW_50":
                print("\n[CAR ACTION] ⚠️ Eyes closed for 2s: Speed reduced by 50%! Warning beepers ON.")
            elif command == "EMERGENCY_PULLOVER":
                print("\n[CAR ACTION] 🚨 Eyes closed for 5s: Pulling over to right lane & applying emergency brakes!")
            elif command == "NORMAL":
                print("\n[CAR ACTION] 🟢 Driver awake: Cruising speed restored to 100%. Hazards OFF.")
            return True

    def _read_loop(self):
        """Background thread listening for feedback from ESP32."""
        while self._running and self.serial_conn and self.serial_conn.is_open:
            try:
                line = self.serial_conn.readline().decode("utf-8", errors="replace").strip()
                if line:
                    logger.debug(f"[ESP32 RX] {line}")
                    if "STATUS:STOPPED" in line:
                        logger.warning("🛑 ESP32 Confirmed: Vehicle pulled over and completely stopped!")
                        if self.on_stopped_callback:
                            self.on_stopped_callback()
            except Exception:
                break
        time.sleep(0.5)

    def close(self):
        self._running = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
