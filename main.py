import os
import subprocess
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Audio Converter Service")

# Создаём директорию для выходных файлов
OUTPUT_DIR = Path("/app/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEMP_DIR = Path("/tmp/audio_converter")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_FORMATS = ["mp3", "ogg"]
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB максимум


@app.get("/")
async def root():
    """Проверка работоспособности сервиса"""
    return {"status": "ok", "service": "Audio Converter"}


@app.post("/convert")
async def convert_audio(
    request: Request,
    file: UploadFile = File(...),
    target_format: str = Form(...),
    download: Optional[bool] = Form(False)
):
    """
    Конвертация аудиофайла в указанный формат
    
    Args:
        request: Request объект для получения base URL
        file: Загружаемый аудиофайл
        target_format: Формат конвертации (mp3 или ogg)
        download: Если True, вернёт файл для скачивания
    
    Returns:
        JSON с информацией о файле или сам файл
    """
    
    # Проверка формата
    if target_format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {target_format}. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )
    
    # Генерируем уникальное имя для файлов
    unique_id = str(uuid.uuid4())
    original_filename = Path(file.filename).stem if file.filename else "audio"
    
    # Пути для временного и выходного файлов
    temp_input_path = TEMP_DIR / f"{unique_id}_input{Path(file.filename).suffix if file.filename else ''}"
    output_filename = f"{original_filename}_{unique_id}.{target_format}"
    output_path = OUTPUT_DIR / output_filename
    
    logger.info(f"Starting conversion: {file.filename} -> {target_format} (ID: {unique_id})")
    
    try:
        # Сохраняем загруженный файл во временную директорию чанками
        # Это предотвращает проблемы с большими файлами
        chunk_size = 1024 * 1024  # 1MB чанки
        total_size = 0
        
        with open(temp_input_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                
                total_size += len(chunk)
                
                # Проверяем размер файла во время загрузки
                if total_size > MAX_FILE_SIZE:
                    temp_input_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.0f}MB"
                    )
                
                buffer.write(chunk)
        
        # Проверяем, что файл действительно сохранён
        if not temp_input_path.exists() or temp_input_path.stat().st_size == 0:
            logger.error(f"Uploaded file is empty: {temp_input_path}")
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty or corrupted"
            )
        
        file_size = temp_input_path.stat().st_size
        logger.info(f"File saved successfully: {file_size} bytes")
        
        # Выполняем конвертацию через ffmpeg
        command = [
            "ffmpeg",
            "-i", str(temp_input_path),
            "-y",  # перезаписать выходной файл если существует
            "-loglevel", "error",  # показывать только ошибки
            str(output_path)
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300  # таймаут 5 минут для больших файлов
        )
        
        # Проверяем результат выполнения
        if result.returncode != 0:
            # Очищаем stderr от лишней информации для пользователя
            error_msg = result.stderr.strip()
            
            # Определяем тип ошибки для более понятного сообщения
            if "moov atom not found" in error_msg or "Invalid data" in error_msg:
                user_error = "The uploaded file is corrupted or not a valid audio file. Please check the file and try again."
            elif "No such file or directory" in error_msg:
                user_error = "Input file not found. Please try uploading again."
            else:
                # Берём только последние строки с реальной ошибкой
                error_lines = [line for line in error_msg.split('\n') if line.strip()]
                user_error = '\n'.join(error_lines[-5:]) if error_lines else error_msg
            
            raise HTTPException(
                status_code=400,
                detail=user_error
            )
        
        # Проверяем, что выходной файл создан
        if not output_path.exists() or output_path.stat().st_size == 0:
            logger.error(f"Output file not created or empty: {output_path}")
            raise HTTPException(
                status_code=500,
                detail="Conversion failed: output file not created"
            )
        
        output_size = output_path.stat().st_size
        logger.info(f"Conversion successful: {output_size} bytes, file: {output_filename}")
        
        # Удаляем временный файл
        temp_input_path.unlink(missing_ok=True)
        
        # Возвращаем результат
        if download:
            return FileResponse(
                path=str(output_path),
                media_type=f"audio/{target_format}",
                filename=output_filename
            )
        else:
            # Формируем полный URL для скачивания
            base_url = str(request.base_url).rstrip('/')
            download_url = f"{base_url}/download/{output_filename}"
            
            return JSONResponse({
                "status": "ok",
                "output_path": str(output_path),
                "download_url": download_url
            })
    
    except HTTPException:
        # Пробрасываем HTTP исключения дальше
        logger.warning(f"Conversion failed for {file.filename}: HTTP exception")
        temp_input_path.unlink(missing_ok=True)
        raise
    
    except subprocess.TimeoutExpired:
        logger.error(f"Conversion timeout for {file.filename}")
        temp_input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Conversion timeout: file is too large or processing took too long"
        )
    
    except Exception as e:
        # Очищаем временные файлы при ошибке
        logger.error(f"Unexpected error during conversion of {file.filename}: {str(e)}")
        temp_input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"Conversion error: {str(e)}"
        )


@app.get("/download/{filename}")
async def download_file(filename: str):
    """
    Скачивание сконвертированного файла по имени
    
    Args:
        filename: Имя файла для скачивания
    
    Returns:
        Файл для скачивания
    """
    file_path = OUTPUT_DIR / filename
    
    # Проверяем существование файла
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {filename}"
        )
    
    # Проверяем, что файл находится в разрешённой директории (безопасность)
    if not str(file_path.resolve()).startswith(str(OUTPUT_DIR.resolve())):
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )
    
    # Определяем media type по расширению
    extension = file_path.suffix.lstrip('.')
    media_type = f"audio/{extension}" if extension in SUPPORTED_FORMATS else "application/octet-stream"
    
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename
    )


@app.get("/health")
async def health_check():
    """Health check эндпоинт для мониторинга"""
    # Проверяем доступность ffmpeg
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        ffmpeg_available = result.returncode == 0
        ffmpeg_version = result.stdout.split('\n')[0] if ffmpeg_available else "Not available"
    except Exception as e:
        ffmpeg_available = False
        ffmpeg_version = f"Error: {str(e)}"
    
    return {
        "status": "healthy" if ffmpeg_available else "degraded",
        "ffmpeg": {
            "available": ffmpeg_available,
            "version": ffmpeg_version
        },
        "supported_formats": SUPPORTED_FORMATS,
        "max_file_size_mb": MAX_FILE_SIZE / (1024 * 1024)
    }

