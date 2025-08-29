FROM ghcr.io/wy15/docker-s6-alpine:master

RUN apk add --no-cache jq curl bind-tools

ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2 CF_API=https://api.cloudflare.com/client/v4 RRTYPE=A CRON="*/5	*	*	*	*"

COPY root /

RUN find /app -maxdepth 1 -type f -exec chmod 0755 {} \;
RUN find /etc/cont-finish.d -maxdepth 1 -type f -exec chmod 0755 {} \;
RUN find /etc/cont-init.d -maxdepth 1 -type f -exec chmod 0755 {} \;
RUN find /etc/services.d/crond -maxdepth 1 -type f -exec chmod 0755 {} \;
