-- CIVITAS/CORE Smart Meter master data schema
--
-- Master data for the "Integrate Smart Meter energy usage data" use case.
-- Entities follow the SensorThings model referenced by the CIVITAS/CORE
-- how-to guides (Things, Sensors, ObservedProperties, Datastreams) and use
-- attribute names from the FIWARE Smart Data Models "Device" model
-- (https://github.com/smart-data-models/dataModel.Device).

CREATE SCHEMA IF NOT EXISTS smartmeter;
SET search_path TO smartmeter;

-- Things: the smart meter devices (Smart Data Models: Device)
CREATE TABLE thing (
    id                  TEXT PRIMARY KEY,          -- urn:ngsi-ld:Device:SmartMeter:NNN
    name                TEXT NOT NULL,
    description         TEXT,
    category            TEXT NOT NULL DEFAULT 'meter',
    controlled_property TEXT[] NOT NULL,           -- Smart Data Models controlledProperty
    serial_number       TEXT NOT NULL UNIQUE,
    manufacturer_name   TEXT,
    model_name          TEXT,
    firmware_version    TEXT,
    date_installed      DATE,
    street_address      TEXT,
    address_locality    TEXT,
    postal_code         TEXT,
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL
);

-- Sensors: the measuring instrument inside each meter
CREATE TABLE sensor (
    id           TEXT PRIMARY KEY,                 -- urn:ngsi-ld:Sensor:SmartMeter:NNN
    thing_id     TEXT NOT NULL REFERENCES thing (id),
    name         TEXT NOT NULL,
    description  TEXT,
    encoding_type TEXT NOT NULL DEFAULT 'application/json',
    metadata     TEXT
);

-- ObservedProperties: what is being measured
CREATE TABLE observed_property (
    id          TEXT PRIMARY KEY,                  -- urn:ngsi-ld:ObservedProperty:xxx
    name        TEXT NOT NULL UNIQUE,              -- payload attribute name
    definition  TEXT NOT NULL,
    description TEXT
);

-- Datastreams: one time series per (thing, observed property)
CREATE TABLE datastream (
    id                    TEXT PRIMARY KEY,        -- urn:ngsi-ld:Datastream:SmartMeter:NNN:prop
    thing_id              TEXT NOT NULL REFERENCES thing (id),
    sensor_id             TEXT NOT NULL REFERENCES sensor (id),
    observed_property_id  TEXT NOT NULL REFERENCES observed_property (id),
    name                  TEXT NOT NULL,
    description           TEXT,
    unit_of_measurement   TEXT NOT NULL,           -- unit name
    unit_symbol           TEXT NOT NULL,
    observation_type      TEXT NOT NULL DEFAULT
        'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement',
    mqtt_topic            TEXT NOT NULL,           -- where measurements arrive
    UNIQUE (thing_id, observed_property_id)
);
