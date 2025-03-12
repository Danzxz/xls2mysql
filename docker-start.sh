#!/bin/bash

# Выводим информацию о запуске
echo "Запуск приложения Excel-to-MySQL на порту 80 с увеличенным таймаутом..."

# Запускаем docker-compose
docker-compose up -d

# Проверяем статус контейнеров
echo "Проверка статуса контейнеров:"
docker-compose ps

echo ""
echo "Приложение запущено на http://localhost:80"
echo "Для остановки приложения используйте команду: ./docker-stop.sh"