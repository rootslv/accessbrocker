FROM ubuntu:22.04

RUN apt-get update && apt-get install -y openssh-server sudo && \
    mkdir -p /var/run/sshd

# Юзер, под которым будет заходить агент (не root!)
RUN useradd -m -s /bin/bash deploy_user && \
    useradd -m -s /bin/bash readonly_user

# Пример "деплой"-скрипта, который агенту разрешено вызывать
RUN echo '#!/bin/bash\necho "[demo] restarting nutricio-api... done."' \
    > /usr/local/bin/restart_app.sh && \
    chmod +x /usr/local/bin/restart_app.sh

RUN echo '#!/bin/bash\necho "[demo] recent logs:"; echo "2026-09-24 12:00:01 INFO service healthy"' \
    > /usr/local/bin/show_logs.sh && \
    chmod +x /usr/local/bin/show_logs.sh

COPY ca_key.pub /etc/ssh/ca_key.pub
RUN chmod 644 /etc/ssh/ca_key.pub

RUN echo "TrustedUserCAKeys /etc/ssh/ca_key.pub" >> /etc/ssh/sshd_config && \
    echo "LogLevel VERBOSE" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
