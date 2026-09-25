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

## Решение

Access Broker выдаёт не ключ, а **временное, узко ограниченное право**:
- **Time-boxed** — сертификат живёт минуты (в демо — секунды), потом
  сам перестаёт работать. Ничего не нужно отзывать вручную.
- **Intent-scoped** — агент отправляет типизированное действие и параметры,
  например `read_service_logs(unit=nutricio-api, since_minutes=30, lines=20)`.
  Broker проверяет policy и параметры, а затем подписывает SSH-сертификат,
  содержащий *проверенный intent* в `force-command`. Сервер повторно
  проверяет intent и исполняет только заранее разрешённую операцию.
- **Authenticated** — agent identity выводится из bearer token, а не из
  подставляемого клиентом `agent_name`.
- **Audit by default** — каждый allow/deny и результат исполнения попадает
  в hash-chained receipt с task ID, параметрами и serial сертификата.

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
./setup_ca.sh
cp ca/ca_key.pub server/ca_key.pub

# 2. Поднять тестовый сервер (нужен Docker)
docker compose up -d --build

# 3. Pin публичный host key тестового сервера в доверенный known_hosts
printf '[localhost]:2222 %s\n' "$(docker exec access-broker-demo-server cat /etc/ssh/ssh_host_ed25519_key.pub)" > known_hosts

# 4. Запустить broker (отдельный терминал, из корня проекта)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn broker.main:app --host 127.0.0.1 --port 8000
```

Сервер генерирует свежие строки лога при запуске контейнера. При пересборке
образа повторите шаг pin для нового host key. Никогда не получайте host key
по недоверенному соединению без проверки отпечатка.

## Демо-сценарий: Devin запрашивает ограниченный доступ

Откройте Devin-сессию с этим репозиторием и попросите: «Для задачи INC-1842
проверь ошибки nutricio-api за последние 30 минут через Access Broker.
Затем попробуй получить логи vpn на том же сервере. Покажи receipts».
Devin может исполнить клиент из корня репозитория:

```bash
.venv/bin/python client/agent_ssh.py read_service_logs --task-id INC-1842 \
  --params '{"unit":"nutricio-api","since_minutes":30,"lines":20,"contains":"ERROR"}'
```
Ожидаемый результат: строка `ERROR nutricio-api timeout connecting to database`.
В выводе также есть ID audit receipt. Агент не получает SSH credential.

Проверка policy: тот же агент не может выбрать чужой target или unit:
```bash
.venv/bin/python client/agent_ssh.py read_service_logs --target root-vpn-node-1 \
  --params '{"unit":"vpn"}' --task-id INC-1843
.venv/bin/python client/agent_ssh.py read_service_logs \
  --params '{"unit":"vpn"}' --task-id INC-1844
```
Ожидаемый результат: `403` и отдельный receipt для каждого отказа.

Фильтр трактует спецсимволы буквально (нет shell):
```bash
.venv/bin/python client/agent_ssh.py read_service_logs \
  --params '{"unit":"nutricio-api","contains":"; touch /tmp/owned"}'
docker exec access-broker-demo-server test ! -e /tmp/owned
```
Команда не создаёт файл, даже если фильтр содержит синтаксис shell. Старые
действия также работают: `restart_nutricio` и `show_vpn_logs` (для второго
используйте `--agent vpn-support-agent`).

Проверка цепочки receipts:

```bash
curl -s http://127.0.0.1:8000/audit/verify
curl -s http://127.0.0.1:8000/audit
```

Чтобы Devin запускался на **другой** машине, разместите broker за HTTPS с
аутентификацией и доступом только из доверенной сети; укажите `BROKER_URL` и
`BROKER_DEVIN_TOKEN` в секретах сессии. По умолчанию клиент и broker работают
локально с публично известными demo-токенами; такой запуск подходит только для
демо на одной машине. Для удалённого Devin можно также поднять всю демо-среду
внутри его сессии по шагам выше.

## Почему CA нужен даже с двумя скриптами

CA подписывает *точные параметры* операции, срок действия и Unix principal.
Подмена исходной SSH-команды через `SSH_ORIGINAL_COMMAND` не меняет операцию
из `force-command` сертификата. Payload кодируется в URL-safe base64, чтобы
динамические данные не попадали в shell как синтаксис; на сервере schema
проверяется снова. Чтение логов использует фиксированный mapping unit → файл
и буквальный поиск подстроки, ограниченный числом строк и объёмом вывода.
Ни один параметр агента не передаётся в командный интерпретатор.

## Питч-фраза

> AI agents get permanent root SSH keys because scoping access takes too
> long. We built a broker that issues short-lived, task-scoped SSH
> certificates in seconds — the agent can only run the allowed command,
> for a limited time, and every request is logged.

## Что сознательно упрощено ради 3 часов

- Identity использует известные demo bearer tokens; в production нужен OIDC
  или mTLS и отдельные полномочия агента. HTTP audit API пока без auth.
- Restart — только demo-скрипт. Логи — файлы внутри контейнера, а не
  настоящий `journalctl` хоста: контейнер не запускает systemd. Для
  настоящих хостов можно сохранить те же схемы и whitelist unit, но
  заменить фиксированный file reader на `subprocess.run` с постоянным argv
  вроде `["journalctl", "-u", unit, "-n", str(lines), "--no-pager"]`,
  `shell=False`, timeout и лимитом вывода.
- Policy — Python dict, без внешнего approval workflow; cert действует 30s,
  но операция после запуска не прерывается истечением срока сертификата.
- CA-ключ лежит на диске broker'а. Для production нужны защищённый signer,
  pinning host key вне локального Docker и внешнее неизменяемое хранение
  audit head: локальную цепочку можно переписать полностью.
