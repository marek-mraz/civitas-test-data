# Publishing Loxone temperature to CIVITAS/CORE

How to get a temperature reading out of a Loxone Miniserver, into this stack's
MQTT broker, and from there into the CIVITAS/CORE SensorThings API and the
GeoServer WFS/WMS layer.

Reference deployment: sensor at **ZŠ SNP 20, Banská Bystrica**
(48.7367419 N, 19.1593550 E), serial `LOX-2026-000201`, dataset
`31bffb18-8940-4068-a940-9182337de111`.

---

## 0. What the platform expects

The CIVITAS data structure `Loxone Temperature measurement data` is defined as
one JSON message per reading:

```json
{
  "id":           "urn:ngsi-ld:TemperatureMeasurement:LOX-2026-000201",
  "type":         "TemperatureMeasurement",
  "refDevice":    "urn:ngsi-ld:Device:TemperatureSensor:001",
  "dateObserved": "2026-07-30T09:30:00Z",
  "temperature":  21.4
}
```

published to:

```
topic:  loxone/sensors/LOX-2026-000201
broker: dok.marek-mraz.com:1883   (plain)  /  :8883 (TLS)
user:   civitas
```

`refDevice` is the join key — it becomes the SensorThings `Thing`, and the
primary key of the WFS layer. `dateObserved` becomes `phenomenonTime`.
Everything else about the device (name, address, coordinates) lives in the
platform, not in the message.

> **Check what your Miniserver actually sends before wiring anything up.**
> Loxone's native MQTT payload is *not* this shape by default — see step 3.

---

## 1. Enable the MQTT Client in Loxone Config 16

The built-in MQTT Client needs a **Miniserver Gen 2** (or a Gen 1 plus the
Loxone MQTT Gateway running on a separate host).

1. Open Loxone Config 16 and connect to the Miniserver.
2. In the periphery tree, right-click **Miniserver → Add Extension → MQTT
   Client** (listed under *Network* / *Communication* depending on your
   Config build).
3. Select the MQTT Client and fill in its properties:

   | Property | Value |
   | --- | --- |
   | Broker address | `dok.marek-mraz.com` |
   | Port | `1883` (plain) or `8883` (TLS) |
   | User | `civitas` |
   | Password | your `MQTT_PASSWORD` |
   | Client ID | `loxone-zs-snp-20` (must be unique on the broker) |
   | Topic prefix | leave empty — full topics are set per output |

   Give the client a **unique Client ID**. Two MQTT clients sharing an ID kick
   each other off the broker in an endless reconnect loop; this exact bug took
   the smart-meter dataset offline for a week.

4. If you use port 8883, enable TLS and turn **off** certificate verification
   ("allow self-signed") — the broker's certificate is auto-generated.
5. Save to the Miniserver.

## 2. Publish the temperature value

1. Drag your temperature sensor (Tree/1-Wire/Modbus input, or the analog value
   you want to send) into the programming page.
2. Add an **MQTT Publish** block (or connect the value to an input of the MQTT
   Client block, depending on your Config build).
3. Set the publish topic to:

   ```
   loxone/sensors/LOX-2026-000201
   ```

4. Set the send interval to **15 s**, or publish on change with a minimum
   interval. Do not publish faster than every few seconds; each message becomes
   a stored observation.
5. Save to the Miniserver.

## 3. Verify what is actually on the wire

Before touching the platform, look at the real payload:

```bash
mosquitto_sub -h dok.marek-mraz.com -p 1883 -u civitas -P '<MQTT_PASSWORD>' \
  -t 'loxone/sensors/#' -v
```

You will see one of two things.

**A. Loxone sends the CIVITAS shape** (because you templated the payload):
nothing more to do — the pipeline already ingests it.

**B. Loxone sends its native format** — typically the bare value (`21.4`) or a
small Loxone-specific JSON object. This is the normal case. Pick one fix:

- **Adjust the platform to match Loxone** (preferred, no extra moving parts).
  Edit the `Loxone Temperature measurement data` structure in the portal so its
  attributes match the keys Loxone actually publishes, then update the mapping
  nodes in both pipelines to read those keys. Nothing else changes.
- **Reshape in a bridge.** Run Node-RED (or the `simulator` in this repo) next
  to the Miniserver, subscribe to Loxone's raw topic, and republish the CIVITAS
  JSON to `loxone/sensors/<serial>`. Use this when the Miniserver cannot format
  a payload at all.

Send the output of the `mosquitto_sub` command above when you get to this
point and the structure/mapping can be adapted to it in a few minutes.

## 4. Confirm it reached the platform

Within about a minute of the first message:

```bash
BASE=https://api.city.marek-mraz.com/v1/datasets/31bffb18-8940-4068-a940-9182337de111

# SensorThings: the Thing, its Datastream and the latest observations
curl "$BASE/frost-server/Things"
curl "$BASE/frost-server/Things(7)/Datastreams(6)/Observations?\$top=5&\$orderby=phenomenonTime%20desc"

# WFS: latest value per sensor, as GeoJSON
curl "$BASE/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=temperature_latest&outputFormat=application/json"
```

In QGIS, add a WFS connection with URL `$BASE/ows` and add the
`temperature_latest` layer. The geometry column is named `geom`, so the layer
works over WFS 2.0.0 with default settings.

## 5. Adding more sensors later

1. Insert a row per sensor in `postgres/seed/03_temperature_seed.sql`
   (unique `id` and `serial_number`, its own coordinates) and redeploy — the
   `seed` service applies that directory on every deploy.
2. Publish that sensor to `loxone/sensors/<its serial>`.

The pipeline subscribes to `loxone/sensors/#`, so new serials are picked up
without any platform change — a new SensorThings `Thing` and a new WFS feature
appear automatically on the first message.
