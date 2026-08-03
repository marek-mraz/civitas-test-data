#!/bin/sh
# Obtains + renews a Let's Encrypt certificate for $DOMAIN via Route 53 DNS-01
# and copies it over the mosquitto server cert in the shared certs volume.
# The mosquitto entrypoint watches that file and SIGHUPs the broker on change.
# Idles (leaving the cert-gen self-signed fallback in place) when AWS
# credentials or a real hostname are missing, so the stack still starts.
set -u

D="${DOMAIN:-localhost}"
LIVE="/etc/letsencrypt/live/$D"

if [ "$D" = "localhost" ] || [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
    echo "certbot idle: set PUBLIC_HOSTNAME + AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY to enable Let's Encrypt"
    exec sleep infinity
fi

publish() {
    if ! cmp -s "$LIVE/fullchain.pem" /certs/mosquitto/server.crt 2>/dev/null; then
        cp "$LIVE/fullchain.pem" /certs/mosquitto/server.crt
        cp "$LIVE/privkey.pem" /certs/mosquitto/server.key
        chown 1883:1883 /certs/mosquitto/server.crt /certs/mosquitto/server.key
        chmod 600 /certs/mosquitto/server.key
        echo "published Let's Encrypt certificate for $D to mosquitto"
    fi
}

while :; do
    if [ -f "$LIVE/fullchain.pem" ]; then
        certbot renew --dns-route53 -n -q
    else
        certbot certonly --dns-route53 -d "$D" -n --agree-tos -m "$LETSENCRYPT_EMAIL"
    fi
    if [ -f "$LIVE/fullchain.pem" ]; then
        publish
        sleep 43200
    else
        echo "issuance failed, retrying in 5 minutes"
        sleep 300
    fi
done
