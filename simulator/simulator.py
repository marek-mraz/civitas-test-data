"""Measurement simulator for CIVITAS/CORE testing.

Reads device master data from PostgreSQL and continuously publishes
measurement messages over MQTT. Two device categories are simulated,
each with its own Smart Data Models payload and topic tree.

Smart meters (category `meter`) — "ACMeasurement" (dataModel.Energy):

    topic:  <MQTT_BASE_TOPIC>/<meter serial number>       (retained: no)
    payload:
    {
      "id": "urn:ngsi-ld:ACMeasurement:SM-2024-000101",
      "type": "ACMeasurement",
      "refDevice": "urn:ngsi-ld:Device:SmartMeter:001",
      "dateObserved": "2026-07-14T09:30:00Z",
      "totalActiveEnergyImport": 18234.512,   # kWh, cumulative
      "activePower": 1.84,                    # kW
      "voltage": 230.7,                       # V
      "current": 7.98                         # A
    }

Loxone temperature sensors (category `temperatureSensor`) — a single
observed property, matching what a Loxone Miniserver publishes:

    topic:  <MQTT_TEMPERATURE_TOPIC>/<sensor serial number>
    payload:
    {
      "id": "urn:ngsi-ld:TemperatureMeasurement:LOX-2026-000201",
      "type": "TemperatureMeasurement",
      "refDevice": "urn:ngsi-ld:Device:TemperatureSensor:001",
      "dateObserved": "2026-07-30T09:30:00Z",
      "temperature": 21.4                     # degrees Celsius
    }

Values follow a simple daily load profile (morning/evening peaks for
residential meters, business hours for commercial/municipal; a diurnal
curve for temperature) plus noise, so time-series charts built on top of
the data look plausible.
"""

import json
import logging
import math
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("simulator")

PG = {
    "host": os.environ.get("PG_HOST", "postgres"),
    "port": int(os.environ.get("PG_PORT", "5432")),
    "dbname": os.environ.get("PG_DB", "smartmeter"),
    "user": os.environ.get("PG_USER", "civitas"),
    "password": os.environ["PG_PASSWORD"],
}
MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "civitas")
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]
BASE_TOPIC = os.environ.get("MQTT_BASE_TOPIC", "taf10/sensors").rstrip("/")
TEMPERATURE_TOPIC = os.environ.get("MQTT_TEMPERATURE_TOPIC", "loxone/sensors").rstrip("/")
INTERVAL = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "15"))


def load_devices():
    """Fetch device master data, retrying until postgres is ready."""
    for attempt in range(60):
        try:
            with psycopg2.connect(**PG) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id, serial_number, category, description "
                    "FROM smartmeter.thing ORDER BY id"
                )
                rows = cur.fetchall()
            if rows:
                return rows
            log.warning("no devices found yet, retrying...")
        except psycopg2.OperationalError as exc:
            log.warning("postgres not ready (%s), retrying...", exc)
        time.sleep(2)
    raise RuntimeError("could not load master data from postgres")


class Meter:
    def __init__(self, device_id, serial, description):
        self.device_id = device_id
        self.serial = serial
        self.topic_root = BASE_TOPIC
        # Commercial/municipal sites draw more and peak during the day
        self.residential = "residential" in (description or "").lower()
        self.base_kw = random.uniform(0.15, 0.4) if self.residential else random.uniform(0.8, 1.5)
        self.peak_kw = random.uniform(2.0, 4.0) if self.residential else random.uniform(6.0, 12.0)
        # Cumulative register starts at a realistic historic value
        self.energy_kwh = random.uniform(5_000, 40_000)

    def profile(self, hour):
        """Fraction of peak load for the current hour of day."""
        if self.residential:
            morning = math.exp(-((hour - 7.5) ** 2) / 3.0)
            evening = math.exp(-((hour - 19.0) ** 2) / 5.0)
            return min(1.0, 0.15 + 0.5 * morning + 0.9 * evening)
        workday = math.exp(-((hour - 13.0) ** 2) / 18.0)
        return min(1.0, 0.1 + 0.9 * workday)

    def measure(self, now, dt_hours):
        power = self.base_kw + self.peak_kw * self.profile(now.hour + now.minute / 60.0)
        power *= random.uniform(0.85, 1.15)
        self.energy_kwh += power * dt_hours
        voltage = random.gauss(230.0, 1.5)
        current = (power * 1000.0) / voltage
        return {
            "id": f"urn:ngsi-ld:ACMeasurement:{self.serial}",
            "type": "ACMeasurement",
            "refDevice": self.device_id,
            "dateObserved": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "totalActiveEnergyImport": round(self.energy_kwh, 3),
            "activePower": round(power, 3),
            "voltage": round(voltage, 1),
            "current": round(current, 2),
        }


class TemperatureSensor:
    """Loxone temperature probe: diurnal curve plus noise, slow drift."""

    def __init__(self, device_id, serial, description):
        self.device_id = device_id
        self.serial = serial
        self.topic_root = TEMPERATURE_TOPIC
        # Indoor probes sit in a narrow band; outdoor ones swing with the day.
        self.outdoor = "outdoor" in (description or "").lower()
        self.mean_c = random.uniform(8.0, 16.0) if self.outdoor else random.uniform(20.0, 23.0)
        self.swing_c = random.uniform(5.0, 9.0) if self.outdoor else random.uniform(0.5, 1.5)
        self.value_c = self.mean_c

    def measure(self, now, _dt_hours):
        # Warmest around 15:00, coldest around 03:00.
        hour = now.hour + now.minute / 60.0
        target = self.mean_c + self.swing_c * math.sin((hour - 9.0) * math.pi / 12.0)
        # Ease toward the target so consecutive readings stay realistic.
        self.value_c += (target - self.value_c) * 0.25 + random.gauss(0.0, 0.08)
        return {
            "id": f"urn:ngsi-ld:TemperatureMeasurement:{self.serial}",
            "type": "TemperatureMeasurement",
            "refDevice": self.device_id,
            "dateObserved": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "temperature": round(self.value_c, 2),
        }


def build_device(device_id, serial, category, description):
    if category == "temperatureSensor":
        return TemperatureSensor(device_id, serial, description)
    return Meter(device_id, serial, description)


def main():
    rows = load_devices()
    devices = [build_device(*row) for row in rows]
    log.info(
        "loaded %d devices from master data (%d meters, %d temperature sensors)",
        len(devices),
        sum(1 for d in devices if isinstance(d, Meter)),
        sum(1 for d in devices if isinstance(d, TemperatureSensor)),
    )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartmeter-simulator")
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    dt_hours = INTERVAL / 3600.0
    log.info(
        "publishing to %s/<serial> and %s/<serial> every %.0fs",
        BASE_TOPIC,
        TEMPERATURE_TOPIC,
        INTERVAL,
    )
    while running:
        now = datetime.now(timezone.utc)
        for device in devices:
            payload = device.measure(now, dt_hours)
            topic = f"{device.topic_root}/{device.serial}"
            client.publish(topic, json.dumps(payload), qos=1)
        log.info("published %d measurements at %s", len(devices), now.isoformat())
        time.sleep(INTERVAL)

    client.loop_stop()
    client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
