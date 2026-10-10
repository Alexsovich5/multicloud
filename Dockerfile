FROM python:3.6.7-stretch

WORKDIR /app

COPY requirements.txt requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . /app

# The API key is generated into this directory on first start (see src/auth.py).
RUN mkdir -p /run/multicloud && chmod 700 /run/multicloud

ENV PYTHONPATH=/app/src:/app \
    AWS_ACCESS_KEY_ID=testing \
    AWS_SECRET_ACCESS_KEY=testing \
    AWS_DEFAULT_REGION=us-east-1 \
    MC_API_KEY_FILE=/run/multicloud/api_key

EXPOSE 8000
