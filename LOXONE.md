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
> Loxone's native MQTT payload is *not* this shape by default — see step 4.

---

## 1. Connect to the Miniserver and back up its config

All programming happens in **Loxone Config** (Windows only — on a Mac run it
in a Windows VM). Download it from <https://www.loxone.com/downloads>; you
need a Miniserver user with admin rights.

**Version pairing matters.** Config must be the same or newer than the
Miniserver firmware, and a newer *major* version will prompt to upgrade the
Miniserver firmware on connect — decline that; never bundle a firmware
upgrade into another change. The ZŠ SNP 20 Miniserver runs firmware
**16.0.6.10**, so use the archived **Config 16.1.11.6** (downloads page →
Archive), not the current 17.x.

**Connect:**

- **Same LAN** (normal case): the Loxone Config start screen lists every
  Miniserver it finds on the network — double-click it and log in. If nothing
  shows up, use **Miniserver → Connect** and enter its IP directly.
- **Remote**: if Cloud DNS is enabled on the Miniserver, open
  `http://dns.loxonecloud.com/<miniserver-serial>` in a browser to learn its
  external address, then connect to that address from Loxone Config. If that
  is not set up, connect from a machine on the school's network (VPN or
  on-site).

**Back up before changing anything:**

1. **Miniserver → Load from Miniserver.** Always start from this, never from
   an old local file — the copy on the Miniserver is the source of truth, and
   saving a stale local project over it silently reverts someone else's work.
2. **File → Save As…** to a dated file, e.g.
   `ZS-SNP-20_2026-07-30_pre-mqtt.Loxone`, and copy it somewhere off that
   machine. This file *is* the full config backup; restoring = opening it and
   saving it back to the Miniserver.

Loxone Config also keeps an automatic local archive of every save (under
`Documents\Loxone`), but don't rely on it — it lives on whichever PC last
edited the config.

**Making changes:** everything you edit is local until you press **Save to
Miniserver**. Saving reloads the Miniserver program — expect a few seconds of
outage, so avoid saving while the building is in active use if relays/blinds
are wired in.

**Updating MQTT settings later** (broker password rotation, new broker
address): Load from Miniserver → select the MQTT Client in the periphery
tree → edit its properties → Save to Miniserver. The broker password is
stored only in the Loxone project, so a platform-side `MQTT_PASSWORD` change
always needs this round-trip.

## 2. Enable the MQTT Client in Loxone Config 16

The built-in MQTT Client needs a **Miniserver Gen 2** (or a Gen 1 plus the
Loxone MQTT Gateway running on a separate host).

1. Open Loxone Config 16 and connect to the Miniserver (section 1).
2. In the periphery tree, right-click **Miniserver → Add Extension → MQTT
   Client** (listed under *Network* / *Communication* depending on your
   Config build).
3. Select the MQTT Client. It shows **DEVICE NOT FULLY CONFIGURED** until the
   required fields are filled — that warning is normal. Set the properties:

   | Property | Value |
   | --- | --- |
   | Name | `MQTT dok` (free text, only the label in the tree) |
   | Broker address | `dok.marek-mraz.com` |
   | Broker port | `8883` (change from the default 1883) |
   | Protocol version | MQTT v5 (leave default) |
   | Client ID | `loxone-zs-snp-20` |
   | Username | `civitas` |
   | Password | `MQTT_PASSWORD` from Dokploy → civitas-test-data → Environment |
   | Use SSL/TLS | ✅ — required on port 8883 |
   | Monitor service | ✅ — enables connection diagnostics |
   | Display Diagnostic Inputs | ✅ — adds a "connected" status input to the tree |

   Give the client a **unique Client ID**. Two MQTT clients sharing an ID kick
   each other off the broker in an endless reconnect loop; this exact bug took
   the smart-meter dataset offline for a week.

   The broker serves a Let's Encrypt certificate (issued by the stack's
   `certbot` service via Route 53 DNS-01), which the Miniserver trusts out of
   the box — no client certificate, no CA import. If the broker still has its
   self-signed bootstrap cert, Loxone rejects it with `tlsv1 alert unknown ca`
   in the broker log; check that `PUBLIC_HOSTNAME` and the AWS credentials are
   set in Dokploy → civitas-test-data → Environment and that the `certbot`
   container logged a successful issuance.

4. Save to the Miniserver and check the diagnostic input goes to "connected".

   **Verified working 2026-08-03**: with the Let's Encrypt cert on the broker
   the ZŠ SNP 20 Miniserver connects with TLSv1.3, MQTT v5. Field notes:

   - Until the Config properties are saved to the Miniserver, it connects
     with its stored settings and a default client ID `LxMs-<timestamp>` —
     seeing that ID in the broker log means the box is fine but your local
     Config edits (client ID, protocol version) were never saved.
   - The school egresses over two WAN paths (`84.245.110.x` + `84.245.111.x`);
     both race the broker and the loser logs a harmless
     `unexpected eof while reading` next to the successful connect.
   - After days of failed TLS attempts the retry back-off grows to tens of
     minutes — a quiet 5-minute log window does not mean the client gave up.
     Wait, or force a reconnect by saving the config / rebooting.
   - Config version lock is real: Config 16.0.0 cannot save to firmware
     16.0.6.10, so broker-side fixes beat client-side workarounds when no
     matching Config is at hand.

   If it stays disconnected, try in order:

   1. Protocol version → MQTT 3.1.1, save again.
   2. Broker log shows `tlsv1 alert unknown ca` → the broker is still on its
      self-signed bootstrap cert; fix the `certbot` service (see
      [README → Let's Encrypt for MQTT](README.md#lets-encrypt-for-mqtt-required-for-loxone)),
      don't fight Loxone's TLS validation. Plain 1883 is *not* a fallback from
      the school: that port is firewalled to the platform's egress IP.

## 3. Publish the temperature value

In this Config build the MQTT client shows two branches in the periphery
tree: **Subscription (TI)** (incoming, ignore for this use case) and
**Publish (TO)** (outgoing).

1. Right-click **Publish (TO)** → **Add Publish**.
2. In its properties set the topic:

   ```
   loxone/sensors/LOX-2026-000201
   ```

3. Payload — **verified 2026-08-03 on the ZŠ SNP 20 box**: the Publish
   object is a plain *Text output* with **no payload/format field**; it
   stringifies whatever is wired into its input, so a directly connected
   temperature goes out as the bare value (`26.300`). To publish JSON,
   format the text *before* the Publish with a **Status block**:

   1. On the programming page, insert a **Status** block and connect the
      room temperature to its input **I1**.
   2. Double-click it, use a single row, leave every condition field
      empty (an unconditioned row is always true) and set the Status-text
      to exactly:

      ```
      {"temperature": <v1.1>}
      ```

      `<v1.1>` = value of I1 with one decimal (`<v1.2>` = two decimals).
      Red text in the dialog means a syntax error; black is OK.
   3. Connect the Status block's text output to the Publish input.

   No timestamp or id is needed in the payload, the pipeline adds those.
4. Publishing is **on value change**, not periodic — a stable room emits a
   couple of messages per hour and that is normal (the 15 s heartbeat you
   may remember from testing was the simulator). Set **Minimum Time
   Interval** on the Publish object (e.g. 15 s) to rate-limit flicker; a
   Mean value block is not needed. If a fixed cadence is ever required,
   re-publish from a bridge (Node-RED heartbeat) rather than fighting the
   trigger model in Config.
5. Save to the Miniserver.

### Scaling to many sensors

- The Miniserver MQTT client supports **max 16 publishes (and 16
  subscriptions) per broker connection** (Loxone KB). For more sensors add
  a second **MQTT Client extension** to the same broker — each with its own
  **unique Client ID** (see the warning in step 2; shared IDs cause the
  mutual kick-off loop). Community reports confirm multiple connections
  work; still, test publish #17 on the second client before wiring a whole
  building.
- One **Status block + Publish pair per sensor**, copy-pasted, changing
  only the topic serial and the input wire. Bundling several sensors into
  one payload is a dead end here: the Status block has only 4 inputs and
  the platform pipeline expects one message per sensor topic anyway.
- Platform side per added sensor: a row in
  `postgres/seed/03_temperature_seed.sql` + its Thing/Datastream (section 6).

## 4. Verify what is actually on the wire

Before touching the platform, look at the real payload:

```bash
mosquitto_sub -h dok.marek-mraz.com -p 1883 -u civitas -P '493f9f90f90fd90fds90dfs' \
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

## 5. Confirm it reached the platform

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

## 6. Adding more sensors later

1. Insert a row per sensor in `postgres/seed/03_temperature_seed.sql`
   (unique `id` and `serial_number`, its own coordinates) and redeploy — the
   `seed` service applies that directory on every deploy.
2. Publish that sensor to `loxone/sensors/<its serial>`.

The pipeline subscribes to `loxone/sensors/#`, so new serials are picked up
without any platform change — a new SensorThings `Thing` and a new WFS feature
appear automatically on the first message.
