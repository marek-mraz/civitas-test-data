# CIVITAS/CORE test data sources — Smart Meter energy use case

One Docker Compose project that provides the two external data sources used by the
CIVITAS/CORE ["Connect external Data"](https://docs.core.civitasconnect.digital) how-to
guide (the "TAF10" Smart Meter energy example):

| Service | Role in CIVITAS/CORE | What it provides |
|---|---|---|
| `postgres` | **Master data** Data source (PostgreSQL connector) | Things, Sensors, ObservedProperties, Datastreams — pre-provisioned on first start |
| `mosquitto` | **Measurement data** Data source (MQTT connector) | Broker with username/password auth |
| `simulator` | (test harness) | Publishes realistic smart-meter measurements to MQTT every 15 s, derived from the master data in postgres |

Data modeling follows the [FIWARE Smart Data Models](https://smartdatamodels.org):
master data uses `dataModel.Device` attribute names, measurements are
`dataModel.Energy/ACMeasurement` entities.

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
postgres/init/01_schema.sql   master data schema (SensorThings-style)
postgres/init/02_seed.sql     5 meters, 5 sensors, 4 properties, 20 datastreams
postgres/pg_hba.conf          client auth: remote = TLS + SCRAM only
mosquitto/mosquitto.conf      broker config (TLS on 8883, auth required)
simulator/                    python publisher (paho-mqtt + psycopg2)
INGEST.md                     step-by-step CIVITAS/CORE ingestion instructions
```
# civitas-test-data
