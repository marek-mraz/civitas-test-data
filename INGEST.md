# Ingesting this stack into CIVITAS/CORE

Step-by-step instructions for the CIVITAS/CORE how-to guides *Connect external Data*
and *Persist, transform & provide Data*, filled in with this stack's actual values.

**Prerequisites**

- This stack is deployed and reachable from the platform: host + ports `5432`
  (PostgreSQL, TLS) and `8883` (MQTT, TLS), passwords from your env.
- Platform permissions: create/read Data structure + Data source; someone with
  **release** permission (Data Owner / Data Gatekeeper) for the release steps.

---

## Phase 1 — Master data (PostgreSQL)

### 1.1 Create the Data structure

*Data structures → Create Data structure*

- **Name:** `Smart Meter Energy master data`
- **Description:** Smart meter device and energy datastream structure

Create a version (e.g. `1.0`), then model these four classes in the
Structure Definition canvas.

**About types:** under the hood CIVITAS/CORE stores structure definitions as
JSON Schema 2020-12, so the primitives are `string`, `number`, `integer`,
`boolean` (dates/timestamps are strings with `format: date-time`), plus
geometry types. The tables below say `Double` — pick `number` (or whatever
your dropdown calls it); `Date`/`DateTime` — pick the date type if offered,
otherwise `string`.

**Class `Thing`** (table `smartmeter.thing`)

| Attribute | Type | Cardinality | Notes |
|---|---|---|---|
| id | String | 1 | **Primary Key** — `urn:ngsi-ld:Device:SmartMeter:NNN` |
| name | String | 1 | |
| description | String | 0..1 | |
| category | String | 1 | always `meter` (can set Default Value `meter`) |
| controlled_property | String | 1..* | array in postgres (`{energy,power,voltage,current}`) — multi-value cardinality |
| serial_number | String | 1 | unique, joins to MQTT topic |
| manufacturer_name | String | 0..1 | |
| model_name | String | 0..1 | |
| firmware_version | String | 0..1 | |
| date_installed | Date | 0..1 | `YYYY-MM-DD` |
| street_address | String | 0..1 | |
| address_locality | String | 0..1 | |
| postal_code | String | 0..1 | |
| latitude | Double | 1 | WGS84 |
| longitude | Double | 1 | WGS84 |

**Class `Sensor`** (table `smartmeter.sensor`)

| Attribute | Type | Cardinality | Notes |
|---|---|---|---|
| id | String | 1 | **Primary Key** — `urn:ngsi-ld:Sensor:SmartMeter:NNN` |
| thing_id | String | 1 | FK → Thing.id (or model as Relationship) |
| name | String | 1 | |
| description | String | 0..1 | |
| encoding_type | String | 1 | always `application/json` |
| metadata | String | 0..1 | |

**Class `ObservedProperty`** (table `smartmeter.observed_property`)

| Attribute | Type | Cardinality | Notes |
|---|---|---|---|
| id | String | 1 | **Primary Key** |
| name | String | 1 | payload attribute name (`activePower`, …) |
| definition | String | 1 | smartdatamodels.org URL |
| description | String | 0..1 | |

**Class `Datastream`** (table `smartmeter.datastream`)

| Attribute | Type | Cardinality | Notes |
|---|---|---|---|
| id | String | 1 | **Primary Key** |
| thing_id | String | 1 | FK → Thing.id |
| sensor_id | String | 1 | FK → Sensor.id |
| observed_property_id | String | 1 | FK → ObservedProperty.id |
| name | String | 1 | |
| description | String | 0..1 | |
| unit_of_measurement | String | 1 | `kilowatt hour`, `kilowatt`, `volt`, `ampere` |
| unit_symbol | String | 1 | `kWh`, `kW`, `V`, `A` |
| observation_type | String | 1 | constant OGC URL — set as Default Value + Static |
| mqtt_topic | String | 1 | `taf10/sensors/<serial_number>` |

**Relationships are mandatory:** every Class must be connected — unconnected
Classes are not included in the hierarchical structure and won't show up in
the Mapping Editor. Connect (Composition works for all four):
`Thing → Sensor`, `Thing → Datastream`, `Sensor → Datastream`,
`ObservedProperty → Datastream` — mirroring the FK columns.

### 1.2 Release the Data structure

Access Management: add your Group + Role. Then a Data Owner / Data Gatekeeper sets
the **Version** status → **Available**, then the **Data structure** status →
**Available**. Nothing below works until both are Available.

### 1.3 Create the Data source

*Data sources → Create Data source*

- **Name:** `Smart Meter PostgreSQL master data`
- **Connector type:** PostgreSQL

| Field | Value |
|---|---|
| Host | your deployment host |
| Port | `5432` |
| Database | `smartmeter` |
| Schema | `smartmeter` |
| User | `civitas` |
| Password | your `POSTGRES_PASSWORD` |
| SSL/TLS | enabled, `sslmode=require` — no certificate to import |

Tables: `thing`, `sensor`, `observed_property`, `datastream`.

In the **Data structure** tab: *Import → from Platform* → select
`Smart Meter Energy master data`. In **Datapools**: keep "Approve for all
Datapools" (or restrict). Release to **Available**.

---

## Phase 2 — Measurement data (MQTT)

### 2.1 Create the Data structure

- **Name:** `Smart Meter Energy measurement data`
- **Description:** Structure for incoming smart meter measurement data

**Class `ACMeasurement`** (one MQTT message)

| Attribute | Type | Cardinality | Notes |
|---|---|---|---|
| id | String | 1 | **Primary Key** — `urn:ngsi-ld:ACMeasurement:<serial>` |
| type | String | 1 | always `ACMeasurement` — Default Value + Static |
| refDevice | String | 1 | join key → master data `Thing.id` |
| dateObserved | Date/DateTime | 1 | ISO 8601 UTC, e.g. `2026-07-14T09:30:00Z` (String if no DateTime type) |
| totalActiveEnergyImport | Double | 1 | kWh, cumulative (monotonically increasing) |
| activePower | Double | 1 | kW |
| voltage | Double | 1 | V |
| current | Double | 1 | A |

Release to **Available** (same handover as 1.2).

### 2.2 Create the Data source

- **Name:** `Smart Meter MQTT measurement data`
- **Connector type:** MQTT

| Field | Value |
|---|---|
| Broker | your deployment host |
| Port | `8883` |
| TLS | enabled, server-certificate verification **off** ("allow self-signed") |
| Username | `civitas` |
| Password | your `MQTT_PASSWORD` |
| Topic | `taf10/sensors/#` |

Import the `Smart Meter Energy measurement data` structure, set Datapools,
release to **Available**.

---

## Phase 3 — Dataset, pipelines, API

### 3.1 Create the Dataset

*Datasets → Create Dataset* → **Name:** `Smart Meter energy usage`

### 3.2 Pipeline 1 — `Smart Meter Master Data`

Runs first: it provisions the SensorThings entities that observations attach to.

```
Flow start → Scheduled Trigger → Data source → Mapping → Sensor Data Storage → Flow end
```

- **Scheduled Trigger:** e.g. every 30 s: `*/30 * * * * *`
- **Data source node:** the PostgreSQL Data source
- **Mapping node:** input = master-data structure, output = SensorThings entities
  (Things / Sensors / ObservedProperties / Datastreams). The attribute names were
  chosen to map 1:1 in the mapping canvas.
- **Sensor Data Storage node:** stores into the SensorThings API backend

### 3.3 Pipeline 2 — `Smart Meter Measurement`

```
Flow start → Data source → Mapping → Sensor Data Storage → Flow end
```

- **Data source node:** the MQTT Data source (event-driven — no trigger node)
- **Mapping node:** `ACMeasurement` → `Observation`:
  - `dateObserved` → `phenomenonTime`
  - each value field (`activePower`, `voltage`, `current`,
    `totalActiveEnergyImport`) → `result` of its matching Datastream
  - join: `refDevice` → `Thing.id`, or topic serial number → `Datastream.mqtt_topic`
- **Sensor Data Storage node:** same SensorThings backend

**Validate** both pipelines, fix any issues, Save.

### 3.4 API

Dataset → Dataflow → APIs → *Add API* → type
**SensorThings API – Time-series Data**. The tile shows the consumer URL.

### 3.5 Release

Set the Dataset to **Ready**; a Data Owner / Data Gatekeeper releases it.
**Pipelines only start processing once the Dataset status is Available.**

---

## Verify

Within ~1 minute of release:

- Pipeline 1: 5 Things, 5 Sensors, 4 ObservedProperties, 20 Datastreams
- Pipeline 2: Observations arriving every 15 s (5 meters × 4 values)

Query the SensorThings API URL: `…/Things`, then
`…/Datastreams(<id>)/Observations` — the simulator's daily load-profile curve
should be visible in the values.
