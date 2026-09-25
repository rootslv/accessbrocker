FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends openssh-server python3 python3-pip && \
    python3 -m pip install --no-cache-dir pydantic==2.10.4 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /run/sshd

RUN useradd -m -s /bin/bash deploy_user && \
    useradd -m -s /bin/bash readonly_user && \
    usermod -p '*' deploy_user && usermod -p '*' readonly_user

RUN echo '#!/bin/bash\necho "[demo] restarting nutricio-api... done."' \
    > /usr/local/bin/restart_app.sh && \
    chmod +x /usr/local/bin/restart_app.sh

COPY broker/intents.py /opt/access-broker/broker/intents.py
COPY server/intent_runner.py /opt/access-broker/intent_runner.py
COPY server/start-demo.sh /opt/access-broker/start-demo.sh
RUN chmod 755 /opt/access-broker/start-demo.sh

COPY server/ca_key.pub /etc/ssh/ca_key.pub
RUN chmod 644 /etc/ssh/ca_key.pub

RUN echo "TrustedUserCAKeys /etc/ssh/ca_key.pub" >> /etc/ssh/sshd_config && \
    echo "LogLevel VERBOSE" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config && \
    echo "KbdInteractiveAuthentication no" >> /etc/ssh/sshd_config

EXPOSE 22
CMD ["/opt/access-broker/start-demo.sh"]
