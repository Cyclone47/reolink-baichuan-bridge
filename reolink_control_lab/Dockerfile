FROM python:3.13-slim-bookworm
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app/ /app/
ENTRYPOINT ["python", "-u", "/app/main.py"]
