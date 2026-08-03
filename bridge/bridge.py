"""Loxone → CIVITAS/CORE MQTT enrichment bridge.

The platform's NiFi mapping only ingests messages that carry
``refDevice`` + ``dateObserved`` + ``temperature`` (verified 2026-08-03 by
probing the live pipeline; ``id``/``type`` are optional). A Loxone
Miniserver can publish the bare value ("27.300") or, with a Status block,
``{"temperature": 27.4}`` — but it cannot generate an ISO timestamp, so it
can never produce the full shape on its own.

This bridge subscribes to the same topic tree the pipeline consumes
(``loxone/sensors/<serial>``), and republishes any incomplete payload as the
full CIVITAS shape:

    {"id": "urn:ngsi-ld:TemperatureMeasurement:<serial>",
     "type": "TemperatureMeasurement",
     "refDevice": <thing.id for that serial, from master data>,
     "dateObserved": <receive time, UTC ISO>,
     "temperature": <value>}

Messages that already carry the three required keys (the bridge's own
output, or a source that formats correctly) are left alone — that is also
what breaks the republish loop.

refDevice comes from the ``smartmeter.thing`` master data (serial_number →
id), loaded at startup and re-queried once per unknown serial, so sensors
added via postgres/seed are picked up without a restart. Set REF_MAP to a
JSON object {"<serial>": "<thing id>", ...} to skip the database (testing).
"""

import json
import logging
import os
import sys
import time

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

REQUIRED_KEYS = {"refDevice", "dateObserved", "temperature"}


def enrich(raw, serial, ref_device, now_iso):
    """Return the full CIVITAS payload dict, or None if nothing to do.

    None means: already complete (leave it alone) or unparseable (skip).
    """
    temperature = None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict):
        if REQUIRED_KEYS <= obj.keys():
            return None  # already the full shape (incl. our own republish)
        temperature = obj.get("temperature")
    elif isinstance(obj, (int, float)):
        temperature = obj  # bare numeric payload, e.g. "27.300"
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        log.warning("skipping unparseable payload for %s: %.100r", serial, raw)
        return None
    return {
        "id": f"urn:ngsi-ld:TemperatureMeasurement:{serial}",
        "type": "TemperatureMeasurement",
        "refDevice": ref_device,
        "dateObserved": now_iso,
        "temperature": temperature,
    }


def load_ref_map():
    static = os.environ.get("REF_MAP")
    if static:
        return json.loads(static), None

    import psycopg2  # only needed without REF_MAP

    conn_args = dict(
        host=os.environ.get("PG_HOST", "postgres"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB", "smartmeter"),
        user=os.environ.get("PG_USER", "civitas"),
        password=os.environ["PG_PASSWORD"],
    )

    def query():
        with psycopg2.connect(**conn_args) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT serial_number, id FROM smartmeter.thing "
                "WHERE category = 'temperatureSensor'"
            )
            return dict(cur.fetchall())

    for attempt in range(30):
        try:
            return query(), query
        except psycopg2.OperationalError as exc:
            log.warning("postgres not ready (%s), retrying", exc)
            time.sleep(2)
    raise SystemExit("could not reach postgres")


def main():
    topic_root = os.environ.get("MQTT_TEMPERATURE_TOPIC", "loxone/sensors")
    ref_map, requery = load_ref_map()
    log.info("ref map: %s", ref_map)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=os.environ.get("MQTT_CLIENT_ID", "loxone-bridge"),
    )
    client.username_pw_set(os.environ.get("MQTT_USER", "civitas"), os.environ["MQTT_PASSWORD"])

    def on_message(_client, _userdata, msg):
        serial = msg.topic.rsplit("/", 1)[-1]
        if serial not in ref_map and requery:
            ref_map.update(requery())  # sensor seeded after startup
        ref_device = ref_map.get(serial)
        if not ref_device:
            log.warning("no thing for serial %s — seed it first", serial)
            return
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = enrich(msg.payload.decode(errors="replace"), serial, ref_device, now_iso)
        if payload is None:
            return
        client.publish(msg.topic, json.dumps(payload), qos=1)
        log.info("enriched %s -> %s", msg.topic, payload)

    # Subscribe in on_connect, not once after connect(): paho does NOT restore
    # subscriptions on auto-reconnect, so a broker restart would otherwise
    # leave the bridge connected but deaf (bit us on 2026-08-03).
    def on_connect(client_, _userdata, _flags, reason_code, _properties):
        client_.subscribe(f"{topic_root}/#", qos=1)
        log.info("connected (%s), bridging %s/#", reason_code, topic_root)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(os.environ.get("MQTT_HOST", "mosquitto"), int(os.environ.get("MQTT_PORT", "1883")), keepalive=30)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    sys.exit(main())
