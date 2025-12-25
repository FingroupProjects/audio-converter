# 🎵 Audio Converter Service

Простой микросервис для конвертации аудиофайлов в форматы MP3 и OGG с использованием FastAPI и ffmpeg.

## 🚀 Быстрый старт

### Сборка Docker образа

```bash
docker build -t audio-converter .
```

### Запуск контейнера

```bash
docker run -d -p 8000:8000 --name audio-converter audio-converter
```

Или с монтированием директории output:

```bash
docker run -d -p 8000:8000 \
  -v $(pwd)/output:/app/output \
  --name audio-converter \
  audio-converter
```

## 📖 Использование API

### Проверка работоспособности

```bash
curl http://localhost:8000/
```

### Конвертация аудиофайла

#### Вариант A: Получить JSON с путём к файлу

```bash
curl -X POST http://localhost:8000/convert \
  -F "file=@input.wav" \
  -F "target_format=mp3"
```

Ответ:
```json
{
  "status": "ok",
  "output_path": "/app/output/input_abc123.mp3",
  "download_url": "http://localhost:8000/download/input_abc123.mp3"
}
```

Теперь можно скачать файл напрямую по ссылке:
```bash
curl -O http://localhost:8000/download/input_abc123.mp3
```

#### Вариант B: Скачать конвертированный файл

```bash
curl -X POST http://localhost:8000/convert \
  -F "file=@input.wav" \
  -F "target_format=ogg" \
  -F "download=true" \
  -o output.ogg
```

### Поддерживаемые форматы

- **mp3** — MPEG Audio Layer III
- **ogg** — Ogg Vorbis

## 🛠 API эндпоинты

### `POST /convert`

Конвертирует аудиофайл в указанный формат.

**Параметры (multipart/form-data):**
- `file` (обязательный) — загружаемый аудиофайл
- `target_format` (обязательный) — формат конвертации: `mp3` или `ogg`
- `download` (опциональный) — если `true`, вернёт файл для скачивания

**Ответы:**
- `200 OK` — успешная конвертация
- `400 Bad Request` — неподдерживаемый формат
- `500 Internal Server Error` — ошибка ffmpeg

### `GET /download/{filename}`

Скачивание сконвертированного файла по имени.

**Параметры:**
- `filename` (path) — имя файла из `download_url`

**Ответы:**
- `200 OK` — файл успешно найден и возвращён
- `404 Not Found` — файл не найден
- `403 Forbidden` — доступ запрещён

**Пример:**
```bash
curl -O http://localhost:8000/download/input_abc123.mp3
```

### `GET /`

Проверка работоспособности сервиса.

### `GET /health`

Health check для мониторинга.

## 📁 Структура проекта

```
/home/tursunboy/projects/python/
├── main.py              # FastAPI приложение
├── requirements.txt     # Python зависимости
├── Dockerfile          # Docker конфигурация
├── .dockerignore       # Исключения для Docker
└── README.md           # Документация
```

## 🧪 Примеры использования

### Python (requests)

```python
import requests

# Конвертация файла
with open('audio.wav', 'rb') as f:
    files = {'file': f}
    data = {'target_format': 'mp3'}
    response = requests.post('http://localhost:8000/convert', files=files, data=data)
    result = response.json()
    print(result)
    # {'status': 'ok', 'output_path': '...', 'download_url': 'http://localhost:8000/download/...'}
    
    # Скачивание по ссылке
    download_url = result['download_url']
    file_response = requests.get(download_url)
    with open('converted.mp3', 'wb') as output:
        output.write(file_response.content)
```

### JavaScript (fetch)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('target_format', 'mp3');

// Конвертация
fetch('http://localhost:8000/convert', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => {
  console.log(data);
  // {status: 'ok', output_path: '...', download_url: 'http://localhost:8000/download/...'}
  
  // Автоматическое скачивание файла
  const link = document.createElement('a');
  link.href = data.download_url;
  link.download = 'converted.mp3';
  link.click();
});
```

## 🔧 Управление контейнером

### Остановка

```bash
docker stop audio-converter
```

### Удаление

```bash
docker rm audio-converter
```

### Просмотр логов

```bash
docker logs audio-converter
```

### Перезапуск

```bash
docker restart audio-converter
```

## 📝 Технологии

- **Python 3.11**
- **FastAPI** — современный веб-фреймворк
- **Uvicorn** — ASGI сервер
- **ffmpeg** — конвертация аудио
- **Docker** — контейнеризация

## ⚙️ Требования

- Docker 20.10+
- 100 MB свободного места для образа

## 🐛 Устранение неполадок

### Контейнер не запускается

Проверьте логи:
```bash
docker logs audio-converter
```

### Порт 8000 уже занят

Используйте другой порт:
```bash
docker run -d -p 8080:8000 --name audio-converter audio-converter
```

### Ошибки ffmpeg

Убедитесь, что входной файл является валидным аудиофайлом. FFmpeg поддерживает большинство популярных форматов: WAV, MP3, FLAC, AAC, OGG и др.

## 📄 Лицензия

MIT License

