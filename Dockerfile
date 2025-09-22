 FROM ghcr.io/wy15/docker-s6-alpine:master

 RUN apk add --no-cache python3 py3-pip bind-tools

 ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2 CF_API=https://api.cloudflare.com/client/v4 RRTYPE=A CRON="*/5 * * * *"

 COPY requirements.txt /

 RUN pip3 install -r requirements.txt

 COPY root /
