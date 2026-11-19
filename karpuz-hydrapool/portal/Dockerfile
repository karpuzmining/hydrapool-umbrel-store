# Official Umbrel apps ship their UI in a versioned image. Umbrel replaces
# docker-compose.yml on update and pulls this image, so the dashboard is not
# stuck on the copy from the first install.
FROM python:3.12-alpine

WORKDIR /opt/portal
COPY addresses.py configgen.py metrics.py bitcoin_status.py server.py /opt/portal/
COPY static /opt/portal/static

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
USER root
CMD ["python3", "-u", "/opt/portal/server.py"]
