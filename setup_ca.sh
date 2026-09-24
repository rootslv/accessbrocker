#!/bin/bash
# Запустить один раз перед демо — создаёт CA-ключ, который будет подписывать
# все временные SSH-сертификаты.
set -e

mkdir -p ca
if [ -f ca/ca_key ]; then
  echo "CA уже существует в ./ca/ca_key — пропускаю."
else
  ssh-keygen -t ed25519 -f ca/ca_key -N "" -C "access-broker-ca"
  echo "CA создан: ca/ca_key (приватный), ca/ca_key.pub (публичный)"
fi

echo ""
echo "Публичный ключ CA (нужно положить на тестовый сервер):"
cat ca/ca_key.pub
