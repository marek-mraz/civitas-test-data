"""Self-check for the enrichment logic: python test_bridge.py"""

from bridge import enrich

REF = "urn:ngsi-ld:Device:TemperatureSensor:001"
NOW = "2026-08-03T12:00:00Z"
FULL = {
    "id": "urn:ngsi-ld:TemperatureMeasurement:LOX-2026-000201",
    "type": "TemperatureMeasurement",
    "refDevice": REF,
    "dateObserved": NOW,
    "temperature": 27.3,
}

# bare numeric payload (Loxone default)
assert enrich("27.300", "LOX-2026-000201", REF, NOW) == FULL
# Status-block short JSON
assert enrich('{"temperature": 27.3}', "LOX-2026-000201", REF, NOW) == FULL
# already complete → untouched (this is also the republish-loop breaker)
assert enrich('{"refDevice": "x", "dateObserved": "y", "temperature": 1}', "s", REF, NOW) is None
# garbage → skipped
assert enrich("hello", "s", REF, NOW) is None
assert enrich('{"humidity": 40}', "s", REF, NOW) is None
assert enrich('{"temperature": true}', "s", REF, NOW) is None
assert enrich('{"temperature": "27.3"}', "s", REF, NOW) is None

print("test_bridge: all checks passed")
