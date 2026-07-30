"""Self-check for the measurement logic: python3 test_simulator.py

Stubs paho/psycopg2 so it runs without the container's dependencies.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timezone

for name in ("paho", "paho.mqtt", "paho.mqtt.client", "psycopg2"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["paho.mqtt.client"].Client = object
sys.modules["paho.mqtt.client"].CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
sys.modules["psycopg2"].OperationalError = Exception
os.environ.update(PG_PASSWORD="x", MQTT_PASSWORD="x")

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sim", os.path.join(_here, "simulator.py"))
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)


def test_category_routing():
    temp = sim.build_device("urn:ngsi-ld:Device:TemperatureSensor:001", "LOX-2026-000201",
                            "temperatureSensor", "Loxone temperature sensor")
    meter = sim.build_device("urn:ngsi-ld:Device:SmartMeter:001", "SM-2024-000101",
                             "meter", "Residential smart meter")
    assert isinstance(temp, sim.TemperatureSensor)
    assert isinstance(meter, sim.Meter)
    # Each category publishes to its own topic tree.
    assert temp.topic_root == "loxone/sensors"
    assert meter.topic_root == "taf10/sensors"


def test_temperature_payload_shape():
    s = sim.build_device("urn:ngsi-ld:Device:TemperatureSensor:001", "LOX-2026-000201",
                         "temperatureSensor", "Loxone temperature sensor")
    p = s.measure(datetime.now(timezone.utc), 15 / 3600)
    assert set(p) == {"id", "type", "refDevice", "dateObserved", "temperature"}
    assert p["type"] == "TemperatureMeasurement"
    assert p["id"].endswith("LOX-2026-000201")
    assert p["dateObserved"].endswith("Z")
    assert isinstance(p["temperature"], float)


def test_temperature_follows_daily_curve():
    s = sim.build_device("urn:ngsi-ld:Device:TemperatureSensor:001", "LOX-2026-000201",
                         "temperatureSensor", "Loxone temperature sensor")
    readings = {}
    for hour in (3, 15):
        now = datetime(2026, 7, 30, hour, 0, 0, tzinfo=timezone.utc)
        for _ in range(20):  # let the easing settle on the hour's target
            p = s.measure(now, 15 / 3600)
        readings[hour] = p["temperature"]
    assert readings[15] > readings[3], readings
    assert all(10.0 < v < 35.0 for v in readings.values()), readings


def test_meter_energy_is_cumulative():
    m = sim.build_device("urn:ngsi-ld:Device:SmartMeter:001", "SM-2024-000101",
                         "meter", "Residential smart meter")
    now = datetime.now(timezone.utc)
    first = m.measure(now, 15 / 3600)["totalActiveEnergyImport"]
    second = m.measure(now, 15 / 3600)["totalActiveEnergyImport"]
    assert second >= first, (first, second)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all checks passed")
