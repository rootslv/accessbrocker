# Access Broker (MVP) — временный SSH-доступ для AI-агентов

Идея: агент не получает постоянный root-ключ и даже временный SSH
сертификат. Вместо этого он передаёт broker'у структурированное намерение
под конкретную задачу. Broker проверяет identity и policy, сам выпускает
одноразовый ephemeral credential, выполняет строго разрешённую команду и
возвращает агенту только результат.

## Проблема

AI-агенты (Devin, Claude Code, Cursor) всё чаще получают прямой доступ
к продакшн-инфраструктуре. Стандартная практика сегодня — выдать агенту
постоянный SSH-ключ, часто с root-правами, потому что нормальный
scoping доступа требует ручной настройки (отдельный юзер, sudoers,
ротация) — а на это никогда нет времени.

Последствия:
- **Доступ не истекает.** Ключ работает бессрочно, пока кто-то не
  вспомнит его вручную отозвать.
- **Нет границ на действия.** Галлюцинация, неверная интерпретация
  задачи или prompt injection — и у агента хватит прав сделать что
  угодно, не только то, что нужно для задачи.
- **Нет разделения в логах.** Невозможно отличить, что сделал человек,
  а что — агент во время конкретной задачи.

Это не гипотетический риск:

> **53%** организаций сообщили, что AI-агенты хотя бы раз превысили
> заданные им права (Cloud Security Alliance, апрель 2026).
> **47%** столкнулись с security-инцидентом с участием AI-агента
> за последний год.

## Решение

Access Broker выдаёт не ключ, а **временное, узко ограниченное право**:
- **Time-boxed** — сертификат живёт минуты (в демо — секунды), потом
  сам перестаёт работать. Ничего не нужно отзывать вручную.
- **Intent-scoped** — агент может запросить только заранее описанное
  действие (`restart_nutricio` или `show_vpn_logs`), а не shell-команду.
  Broker сам компилирует intent в команду. Даже если агент попросит что-то
  другое, сервер физически выполнит только разрешённое —
  `force-command` работает на уровне SSH-протокола, а не полагается
  на то, что агент "послушается" инструкции в промпте.
- **Authenticated** — agent identity выводится из bearer token, а не из
  подставляемого клиентом `agent_name`.
- **Audit by default** — каждый allow/deny и результат исполнения попадает
  в hash-chained receipt с task ID и serial сертификата.

Это не альтернатива системным промптам/`AGENTS.md` — это вторая, жёсткая
линия защиты поверх них: если инструкция в промпте не сработала (её
переписали инъекцией, модель её проигнорировала), граница на уровне
инфраструктуры всё равно держит.

## Что это даёт

| | Сейчас (статичный root-ключ) | С Access Broker |
|---|---|---|
| Срок действия доступа | Бессрочно | Секунды-минуты, сам истекает |
| Что можно сделать | Что угодно | Одна разрешённая команда |
| Отзыв при увольнении/смене задачи | Вручную, легко забыть | Не требуется — доступ и так истёк |
| Видимость (кто что делал) | Общий root-лог, не разделить агента и человека | Отдельная запись на каждый запрос доступа |

**Питч-фраза:**
> Agents get root keys because scoping access takes too long.
> We make scoped, expiring access as fast as handing over a static key.

## Подготовка (сделать заранее, до демо)

```bash
# 1. Создать CA
chmod +x setup_ca.sh
./setup_ca.sh

# 2. Скопировать публичный ключ CA туда, откуда его подхватит Docker build
cp ca/ca_key.pub server/ca_key.pub

# 3. Поднять тестовый сервер
docker compose up -d --build

# 4. Установить зависимости broker'а и клиента
pip install fastapi uvicorn requests --break-system-packages

# 5. Запустить broker (отдельный терминал, из корня проекта)
uvicorn broker.main:app --port 8000
```

## Демо-сценарий (3 шага, ~2 минуты)

**Терминал 1** — broker уже работает (см. выше).

**Терминал 2** — агент запрашивает действие и получает только его результат:
```bash
cd client
python agent_ssh.py restart_nutricio --task-id INC-1842
```
Ожидаемый результат: `[demo] restarting nutricio-api... done.` Агент не
получает private key или certificate.

**Терминал 2** — подмена identity или target не помогает:
```bash
python agent_ssh.py restart_nutricio --target root-vpn-node-1 --task-id INC-1843
```
Ожидаемый результат: `403`. Policy привязывает identity, action и target.
Сам broker намеренно просит SSH выполнить `rm -rf /tmp/not-run`; в итоге
`sshd` выполняет только зашитый `restart_app.sh`.

**Терминал 2** — проверка целостности журнала:
```bash
curl localhost:8000/audit/verify | jq
```

## Audit log

```bash
cat logs/audit_receipts.log
# или через broker:
curl localhost:8000/audit | jq
```
Каждая строка — одно решение или исполнение: verified agent, task ID, action,
target, serial сертификата, exit code и hash результата. `GET /audit/verify`
проверяет hash-chain.

## Питч-фраза

> AI agents get permanent root SSH keys because scoping access takes too
> long. We built a broker that issues short-lived, task-scoped SSH
> certificates in seconds — the agent can only run the allowed command,
> for a limited time, and every request is logged.

## Что сознательно упрощено ради 3 часов

- Identity использует demo bearer tokens. В production это OIDC/mTLS, а не
  токены из environment variables.
- Policy — обычный Python dict, не YAML/DB (для демо этого достаточно)
- Нет ротации host-сертификата (не нужна для короткого демо)
- CA-ключ лежит на диске broker'а без доп. изоляции. В production signer
  должен быть отдельным сервисом/HSM, а audit head — отправляться во внешнее
  неизменяемое хранилище.
