-- Seed: 5 smart meters with sensors and datastreams
SET search_path TO smartmeter;

INSERT INTO thing (id, name, description, category, controlled_property, serial_number,
                   manufacturer_name, model_name, firmware_version, date_installed,
                   street_address, address_locality, postal_code, latitude, longitude) VALUES
('urn:ngsi-ld:Device:SmartMeter:001', 'Smart Meter 001',
 'Residential smart meter, apartment block A', 'meter',
 ARRAY['energy','power','voltage','current'], 'SM-2024-000101',
 'MeterWorks GmbH', 'MW-E350', '2.4.1', '2024-03-12',
 'Hauptstraße 12', 'Münster', '48143', 51.9607, 7.6261),
('urn:ngsi-ld:Device:SmartMeter:002', 'Smart Meter 002',
 'Residential smart meter, apartment block B', 'meter',
 ARRAY['energy','power','voltage','current'], 'SM-2024-000102',
 'MeterWorks GmbH', 'MW-E350', '2.4.1', '2024-03-12',
 'Hauptstraße 14', 'Münster', '48143', 51.9611, 7.6268),
('urn:ngsi-ld:Device:SmartMeter:003', 'Smart Meter 003',
 'Commercial smart meter, retail unit', 'meter',
 ARRAY['energy','power','voltage','current'], 'SM-2024-000103',
 'MeterWorks GmbH', 'MW-C500', '3.1.0', '2024-05-02',
 'Marktplatz 3', 'Münster', '48143', 51.9625, 7.6280),
('urn:ngsi-ld:Device:SmartMeter:004', 'Smart Meter 004',
 'Municipal smart meter, school building', 'meter',
 ARRAY['energy','power','voltage','current'], 'SM-2024-000104',
 'GridSense AG', 'GS-M120', '1.9.7', '2024-06-18',
 'Schulweg 8', 'Münster', '48145', 51.9580, 7.6395),
('urn:ngsi-ld:Device:SmartMeter:005', 'Smart Meter 005',
 'Municipal smart meter, sports hall', 'meter',
 ARRAY['energy','power','voltage','current'], 'SM-2024-000105',
 'GridSense AG', 'GS-M120', '1.9.7', '2024-06-18',
 'Sportallee 21', 'Münster', '48147', 51.9702, 7.6120);

INSERT INTO sensor (id, thing_id, name, description, metadata)
SELECT replace(t.id, 'Device', 'Sensor'),
       t.id,
       t.name || ' metering unit',
       'Integrated electricity metering unit of ' || t.name,
       t.manufacturer_name || ' ' || t.model_name || ' datasheet'
FROM thing t;

INSERT INTO observed_property (id, name, definition, description) VALUES
('urn:ngsi-ld:ObservedProperty:totalActiveEnergyImport', 'totalActiveEnergyImport',
 'https://smartdatamodels.org/dataModel.Energy/totalActiveEnergyImport',
 'Cumulative active energy imported (kWh)'),
('urn:ngsi-ld:ObservedProperty:activePower', 'activePower',
 'https://smartdatamodels.org/dataModel.Energy/activePower',
 'Instantaneous active power (kW)'),
('urn:ngsi-ld:ObservedProperty:voltage', 'voltage',
 'https://smartdatamodels.org/dataModel.Energy/voltage',
 'Phase voltage (V)'),
('urn:ngsi-ld:ObservedProperty:current', 'current',
 'https://smartdatamodels.org/dataModel.Energy/current',
 'Phase current (A)');

-- One datastream per meter x observed property (5 x 4 = 20 rows).
-- mqtt_topic matches what the simulator publishes:  taf10/sensors/<serial>
INSERT INTO datastream (id, thing_id, sensor_id, observed_property_id, name, description,
                        unit_of_measurement, unit_symbol, mqtt_topic)
SELECT
    replace(t.id, 'Device', 'Datastream') || ':' || op.name,
    t.id,
    replace(t.id, 'Device', 'Sensor'),
    op.id,
    t.name || ' ' || op.name,
    op.description || ' of ' || t.name,
    CASE op.name
        WHEN 'totalActiveEnergyImport' THEN 'kilowatt hour'
        WHEN 'activePower'             THEN 'kilowatt'
        WHEN 'voltage'                 THEN 'volt'
        WHEN 'current'                 THEN 'ampere'
    END,
    CASE op.name
        WHEN 'totalActiveEnergyImport' THEN 'kWh'
        WHEN 'activePower'             THEN 'kW'
        WHEN 'voltage'                 THEN 'V'
        WHEN 'current'                 THEN 'A'
    END,
    'taf10/sensors/' || t.serial_number
FROM thing t
CROSS JOIN observed_property op;
