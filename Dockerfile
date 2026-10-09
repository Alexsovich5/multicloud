FROM python:3.6.7-stretch

WORKDIR /app

COPY requirements.txt requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . /app

ENV PYTHONPATH=/app/src:/app \
    AWS_ACCESS_KEY_ID=testing \
    AWS_SECRET_ACCESS_KEY=testing \
    AWS_DEFAULT_REGION=us-east-1

EXPOSE 8000
