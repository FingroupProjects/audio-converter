# ⚡ Быстрый запуск Audio Converter

## 🚀 Запуск сервиса

```bash
cd /home/tursunboy/projects/python
docker-compose up -d
```

## 🔄 Пересборка после изменений кода

```bash
docker-compose down
docker-compose build
docker-compose up -d
```

## 📝 Проверка работы

```bash
# Проверка статуса
curl http://localhost:8000/

# Конвертация файла
curl -X POST http://localhost:8000/convert \
  -F "file=@your_audio.wav" \
  -F "target_format=mp3"
```

**Ожидаемый ответ:**
```json
{
  "status": "ok",
  "output_path": "/app/output/your_audio_xxxxx.mp3",
  "download_url": "http://localhost:8000/download/your_audio_xxxxx.mp3"
}
```

## 📥 Скачивание файла

```bash
# Просто откройте URL в браузере или используйте curl:
curl -O http://localhost:8000/download/your_audio_xxxxx.mp3
```

## 🛠 Управление

```bash
# Остановка
docker-compose down

# Просмотр логов
docker logs audio-converter

# Просмотр логов в реальном времени
docker logs -f audio-converter

# Перезапуск
docker-compose restart
```

## 🎯 Полный пример

```bash
# 1. Конвертируем файл
response=$(curl -s -X POST http://localhost:8000/convert \
  -F "file=@input.wav" \
  -F "target_format=mp3")

# 2. Получаем ссылку для скачивания
download_url=$(echo $response | grep -o '"download_url":"[^"]*"' | cut -d'"' -f4)

# 3. Скачиваем файл
curl -O "$download_url"
```

## 🌐 Доступ с других компьютеров

Если нужен доступ извне (не только с localhost), используйте IP адрес сервера:

```bash
curl -X POST http://YOUR_SERVER_IP:8000/convert \
  -F "file=@audio.wav" \
  -F "target_format=mp3"
```

Ответ будет содержать правильный URL с вашим IP:
```json
{
  "download_url": "http://YOUR_SERVER_IP:8000/download/audio_xxxxx.mp3"
}
```

