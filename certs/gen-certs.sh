#!/bin/sh
# Auto-generates a private CA + one server certificate into the shared certs
# volume — no manual cert handling anywhere. Runs as a one-shot service
# before postgres/mosquitto start.
# Idempotent: regenerates only when certs are missing or PUBLIC_HOSTNAME changed.
set -eu

DIR=/certs
HOST="${PUBLIC_HOSTNAME:-localhost}"
SAN="DNS:${HOST},DNS:postgres,DNS:mosquitto,DNS:localhost,IP:127.0.0.1"

if [ -f "$DIR/.san" ] && [ "$(cat "$DIR/.san")" = "$SAN" ] && [ -f "$DIR/ca.crt" ]; then
    echo "certificates up to date for $SAN"
    exit 0
fi

echo "generating certificates for $SAN"
rm -rf "$DIR/postgres" "$DIR/mosquitto"
mkdir -p "$DIR/postgres" "$DIR/mosquitto"

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -subj "/CN=civitas-test-data CA" \
    -keyout "$DIR/ca.key" -out "$DIR/ca.crt"

openssl req -newkey rsa:2048 -nodes \
    -subj "/CN=${HOST}" -addext "subjectAltName=${SAN}" \
    -keyout "$DIR/server.key" -out "$DIR/server.csr"

openssl x509 -req -in "$DIR/server.csr" -days 3650 \
    -CA "$DIR/ca.crt" -CAkey "$DIR/ca.key" -CAcreateserial \
    -copy_extensions copyall \
    -out "$DIR/server.crt"

# Each service gets its own copy, owned by the uid it runs as
# (postgres:16-alpine -> 70, eclipse-mosquitto -> 1883); postgres refuses
# to start if the key is readable by anyone else.
for svc in postgres mosquitto; do
    cp "$DIR/ca.crt" "$DIR/server.crt" "$DIR/server.key" "$DIR/$svc/"
done
chown -R 70:70 "$DIR/postgres"
chown -R 1883:1883 "$DIR/mosquitto"
chmod 600 "$DIR/postgres/server.key" "$DIR/mosquitto/server.key" "$DIR/ca.key"

printf '%s' "$SAN" > "$DIR/.san"
echo "certificates generated"
