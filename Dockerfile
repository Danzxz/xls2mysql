FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY pyproject.toml uv.lock ./

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev pkg-config && \
    pip install --no-cache-dir flask flask-sqlalchemy gunicorn mysql-connector-python openpyxl pandas werkzeug psycopg2-binary xlrd email-validator && \
    apt-get purge -y --auto-remove gcc && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Копируем файлы приложения
COPY .src .

# Указываем порт
EXPOSE 80

# Запускаем приложение с увеличенным timeout
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--timeout", "6000", "main:app"]