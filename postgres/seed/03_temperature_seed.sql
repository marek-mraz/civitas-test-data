-- Seed: Loxone temperature sensor
--
-- Second use case on the same master-data schema: a temperature sensor read
-- from a Loxone Miniserver. One observed property (temperature), so one
-- datastream.
--
-- Installation site: ZŠ SNP 20, Banská Bystrica (48.7367419 N, 19.1593550 E).
--
-- IDEMPOTENT ON PURPOSE. Everything in postgres/seed/ is applied by the `seed`
-- compose service on EVERY deploy, not just on a fresh volume:
-- /docker-entrypoint-initdb.d only runs when the data directory is empty, so
-- devices added here would otherwise never reach an existing deployment.
SET search_path TO smartmeter;

INSERT INTO thing (id, name, description, category, controlled_property, serial_number,
                   manufacturer_name, model_name, firmware_version, date_installed,
                   street_address, address_locality, postal_code, latitude, longitude) VALUES
('urn:ngsi-ld:Device:TemperatureSensor:001', 'ZŠ SNP 20 temperature sensor',
 'Loxone temperature sensor at ZŠ SNP 20, Banská Bystrica', 'temperatureSensor',
 ARRAY['temperature'], 'LOX-2026-000201',
 'Loxone Electronics GmbH', 'Loxone Tree Temp', '14.2.3', '2026-02-10',
 'SNP 20', 'Banská Bystrica', '97401', 48.7367419, 19.1593550)
ON CONFLICT (id) DO NOTHING;

INSERT INTO sensor (id, thing_id, name, description, metadata)
SELECT replace(t.id, 'Device', 'Sensor'),
       t.id,
       t.name || ' probe',
       'Loxone Tree temperature probe of ' || t.name,
       t.manufacturer_name || ' ' || t.model_name || ' datasheet'
FROM thing t
WHERE t.category = 'temperatureSensor'
ON CONFLICT (id) DO NOTHING;

INSERT INTO observed_property (id, name, definition, description) VALUES
('urn:ngsi-ld:ObservedProperty:temperature', 'temperature',
 'https://smartdatamodels.org/dataModel.Environment/temperature',
 'Air temperature (degrees Celsius)')
ON CONFLICT (id) DO NOTHING;

-- One datastream per temperature sensor.
-- mqtt_topic matches what the Loxone Miniserver (and the simulator) publishes:
--   loxone/sensors/<serial>
INSERT INTO datastream (id, thing_id, sensor_id, observed_property_id, name, description,
                        unit_of_measurement, unit_symbol, mqtt_topic)
SELECT
    replace(t.id, 'Device', 'Datastream') || ':temperature',
    t.id,
    replace(t.id, 'Device', 'Sensor'),
    'urn:ngsi-ld:ObservedProperty:temperature',
    t.name || ' temperature',
    'Air temperature measured by ' || t.name,
    'degree Celsius',
    'Cel',
    'loxone/sensors/' || t.serial_number
FROM thing t
WHERE t.category = 'temperatureSensor'
ON CONFLICT (id) DO NOTHING;
