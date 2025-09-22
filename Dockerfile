 FROM python:3.9-alpine

 COPY requirements.txt /

 RUN pip install -r requirements.txt

 COPY root /

 ENV CF_API=https://api.cloudflare.com/client/v4 RRTYPE=A

 CMD ["python3", "/app/ddns.py", "run"]
