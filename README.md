# CIVITAS/CORE test data sources — Smart Meter energy + Loxone temperature

One Docker Compose project that provides the two external data sources used by the
CIVITAS/CORE ["Connect external Data"](https://docs.core.civitasconnect.digital) how-to
guide (the "TAF10" Smart Meter energy example):

| Service | Role in CIVITAS/CORE | What it provides |
|---|---|---|
| `postgres` | **Master data** Data source (PostgreSQL connector) | Things, Sensors, ObservedProperties, Datastreams — pre-provisioned on first start |
| `mosquitto` | **Measurement data** Data source (MQTT connector) | Broker with username/password auth |
| `simulator` | (test harness) | Publishes realistic measurements to MQTT every 15 s, derived from the master data in postgres |

Two use cases share the stack:

| Use case | Devices | MQTT topic | Payload |
|---|---|---|---|
| Smart meter energy | 5 meters (`meter`) | `taf10/sensors/<serial>` | `ACMeasurement` |
| Loxone temperature | 1 sensor (`temperatureSensor`), ZŠ SNP 20 | `loxone/sensors/<serial>` | `TemperatureMeasurement` |

Wiring a real Loxone Miniserver into the temperature pipeline: see
[LOXONE.md](LOXONE.md).

Data modeling follows the [FIWARE Smart Data Models](https://smartdatamodels.org):
master data uses `dataModel.Device` attribute names, energy measurements are
`dataModel.Energy/ACMeasurement` entities, temperature uses
`dataModel.Environment/temperature`.

## Quick start

```bash
cp .env.example .env       # then fill in the passwords (required)
docker compose up -d --build
```

Verify:

```bash
# master data seeded?
docker compose exec postgres psql -U civitas -d smartmeter \
  -c "SELECT id, serial_number, street_address FROM smartmeter.thing;"

# measurements flowing?
docker compose exec mosquitto mosquitto_sub -u civitas -P <password> -t 'taf10/#' -C 3 -v
```

## Deploy in Dokploy

1. Create a **Compose** service, point it at this repository (compose path `docker-compose.yml`).
2. Set the environment variables from `.env.example` in the Dokploy *Environment* tab
   (at minimum `POSTGRES_PASSWORD` and `MQTT_PASSWORD`).
3. Deploy. Ports `5432` (PostgreSQL, TLS-enforced) and `8883` (MQTT over TLS) are
   published on the host so the CIVITAS/CORE platform can reach them; change
   `POSTGRES_PORT` / `MQTT_TLS_PORT` if those ports are already taken on the Dokploy
   host. If CIVITAS/CORE runs on the **same** Dokploy/Docker network you can instead
   connect via the service names `postgres:5432` / `mosquitto:8883` and remove the
   `ports:` mappings.

The `simulator` builds from `./simulator` — Dokploy builds it automatically as part of
the compose deployment. Postgres provisioning (`postgres/init/*.sql`) runs only on the
first start of an empty volume; to re-provision from scratch, delete the
`postgres-data` volume and redeploy.

### Two provisioning directories

|  | When it runs | Use it for |
|---|---|---|
| `postgres/init/` | **First start of an empty volume only** (Docker's `docker-entrypoint-initdb.d`) | schema, one-time bootstrap |
| `postgres/seed/` | **Every deploy**, applied by the `seed` service | master data that must also reach an already-running deployment |

This split exists because Docker silently skips `init/` once the data
directory is non-empty. Adding a device there would never show up on a live
stack: the redeploy would ship the new simulator code, the simulator would find
no such device, and the topic would stay empty with no error anywhere.

Anything in `postgres/seed/` must be **idempotent** (`ON CONFLICT DO NOTHING`) —
it is re-applied on every single deploy. The `simulator` waits for the `seed`
service to finish, because it reads the device list once at startup and never
re-queries.

So adding a sensor is just: add an idempotent `INSERT` to `postgres/seed/`,
redeploy. Verify afterwards:

```bash
docker compose exec postgres psql -U civitas -d smartmeter \
  -c "SELECT id, serial_number, category FROM smartmeter.thing WHERE category='temperatureSensor';"
docker compose exec mosquitto \
  mosquitto_sub -u civitas -P "$MQTT_PASSWORD" -t 'loxone/sensors/#' -C 1 -v
```

Once a real Loxone Miniserver publishes to `loxone/sensors/<serial>`, stop
simulating that sensor: delete its row from `smartmeter.thing` (or leave it —
the Miniserver and the simulator would both publish to the same topic and the
readings would interleave).

## Security

Both data sources are TLS-encrypted and password-protected, with **zero manual
certificate handling** — nothing to create, copy or import:

- **TLS, hands-free.** The one-shot `cert-gen` service auto-generates a certificate
  into the `certs` volume on first start. Clients simply connect with encryption on
  and server-cert verification off (`sslmode=require` for PostgreSQL — its default
  verification level anyway; "allow self-signed"/"insecure" for MQTT). All traffic
  — credentials and payloads — is encrypted in transit.
- **Plaintext is not an option.** PostgreSQL rejects non-TLS remote connections
  outright (`postgres/pg_hba.conf`, mounted and enforced on every boot);
  Mosquitto only publishes the TLS listener `8883` — plaintext `1883` never
  leaves the internal docker network.
- **No default passwords.** `POSTGRES_PASSWORD` and `MQTT_PASSWORD` have no fallback —
  the stack refuses to start until you set them. Generate strong ones:
  `openssl rand -base64 24`.
- **PostgreSQL auth is SCRAM-SHA-256** (challenge-response, salted hashes at rest).
- **Mosquitto** rejects anonymous connections.

If a client insists on verifying the server certificate, set `PUBLIC_HOSTNAME` to
your host's DNS name, grab the CA with
`docker compose cp mosquitto:/mosquitto/certs/ca.crt .` and import it — optional,
not required. Verification off still encrypts everything; it only skips proof of
the server's identity, which is a fair trade-off for test data.

## Let's Encrypt for MQTT (required for Loxone)

Some MQTT clients **always** verify the server certificate and cannot import a
custom CA — the Loxone Miniserver is one (it drops the handshake with
`tlsv1 alert unknown ca` in the broker log). For those, the `certbot` service
replaces the self-signed cert on port `8883` with a real Let's Encrypt one,
issued and renewed automatically via a Route 53 DNS-01 challenge. Nothing else
in the stack changes; postgres keeps the self-signed cert.

One-time setup:

1. **DNS**: `PUBLIC_HOSTNAME` (e.g. `dok.marek-mraz.com`) must be an A record
   in a Route 53 hosted zone of your AWS account, pointing at the Dokploy host.
2. **IAM**: in the AWS console create an IAM user (e.g. `certbot-dok`) with an
   access key and this policy (the zone ID below is the `marek-mraz.com`
   hosted zone — swap it if you deploy against a different zone):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow",
         "Action": ["route53:ListHostedZones", "route53:GetChange"],
         "Resource": "*" },
       { "Effect": "Allow",
         "Action": ["route53:ChangeResourceRecordSets", "route53:ListResourceRecordSets"],
         "Resource": "arn:aws:route53:::hostedzone/Z05021702HRYE5DV4ALT6" }
     ]
   }
   ```

3. **Environment** (Dokploy → this service → *Environment*, or `.env`):

   ```bash
   PUBLIC_HOSTNAME=dok.marek-mraz.com   # must match the DNS record
   AWS_ACCESS_KEY_ID=...                # the IAM user's key
   AWS_SECRET_ACCESS_KEY=...
   LETSENCRYPT_EMAIL=you@example.com    # expiry warnings from Let's Encrypt
   ```

4. **Redeploy** and check the `certbot` container log for
   `published Let's Encrypt certificate`. Verify what the broker serves:

   ```bash
   openssl s_client -connect dok.marek-mraz.com:8883 </dev/null 2>/dev/null \
     | openssl x509 -noout -issuer -enddate
   # issuer should be Let's Encrypt, not "civitas-test-data CA"
   ```

Renewal is automatic: `certs/renew-loop.sh` runs `certbot renew` twice a day
and copies the new cert into the `certs` volume; the mosquitto entrypoint
notices the change (checked hourly) and reloads the broker via SIGHUP — no
downtime, connected clients stay connected.

If `AWS_ACCESS_KEY_ID` is unset (or `PUBLIC_HOSTNAME` is `localhost`) the
certbot service idles and the broker keeps the self-signed certificate — the
stack works as before, minus Loxone.

## Wiring it up in CIVITAS/CORE

Follow the *Connect external Data* guide with these values:

**Data source 1 — master data (PostgreSQL connector)**
- Host: your Dokploy host (or `postgres` on a shared network), port `5432`
- SSL/TLS: enabled, `sslmode=require` (no certificate to import)
- Database `smartmeter`, user `civitas`, password from your `.env`
- Schema `smartmeter`, tables: `thing`, `sensor`, `observed_property`, `datastream`
- Data structure: Classes `Thing`, `Sensor`, `ObservedProperty`, `Datastream`
  matching the columns in `postgres/init/01_schema.sql`

**Data source 2 — measurement data (MQTT connector)**
- Broker: your Dokploy host (or `mosquitto`), port `8883`
- TLS: enabled, server-certificate verification **off** ("allow self-signed" /
  "insecure" — no certificate to import)
- Username `civitas`, password from your `.env`
- Topic: `taf10/sensors/#` (one subtopic per meter serial number)
- Message format (Smart Data Models `ACMeasurement`):

```json
{
  "id": "urn:ngsi-ld:ACMeasurement:SM-2024-000101",
  "type": "ACMeasurement",
  "refDevice": "urn:ngsi-ld:Device:SmartMeter:001",
  "dateObserved": "2026-07-14T09:30:00Z",
  "totalActiveEnergyImport": 18234.512,
  "activePower": 1.84,
  "voltage": 230.7,
  "current": 7.98
}
```

`refDevice` joins a measurement to its meter in the master data (`thing.id`); the MQTT
topic equals `datastream.mqtt_topic` / `thing.serial_number`.

## What's in the master data

5 smart meters (2 residential, 1 commercial, 2 municipal) in Münster, each with one
sensor and 4 datastreams (energy, power, voltage, current) — 20 datastreams total.
The simulator generates a daily load profile (residential: morning/evening peaks;
commercial/municipal: business hours) with noise, and a monotonically increasing
cumulative energy register, so charts on top of the data look plausible.

## Layout

```
docker-compose.yml            the whole stack (Dokploy-ready)
.env.example                  credentials / ports / simulator settings
certs/gen-certs.sh            auto-generates the TLS certificate (one-shot service)
certs/renew-loop.sh           Let's Encrypt issue/renew loop for MQTT (certbot service)
postgres/init/01_schema.sql   master data schema (SensorThings-style)
postgres/init/02_seed.sql     5 meters, 5 sensors, 4 properties, 20 datastreams
postgres/pg_hba.conf          client auth: remote = TLS + SCRAM only
mosquitto/mosquitto.conf      broker config (TLS on 8883, auth required)
simulator/                    python publisher (paho-mqtt + psycopg2)
INGEST.md                     step-by-step CIVITAS/CORE ingestion instructions
```
# civitas-test-data
