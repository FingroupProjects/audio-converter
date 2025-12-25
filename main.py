import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Audio Converter Service")

# Создаём директорию для выходных файлов
OUTPUT_DIR = Path("/app/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEMP_DIR = Path("/tmp/audio_converter")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_FORMATS = ["mp3", "ogg"]


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
    
    try:
        # Сохраняем загруженный файл во временную директорию
        with open(temp_input_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Выполняем конвертацию через ffmpeg
        command = [
            "ffmpeg",
            "-i", str(temp_input_path),
            "-y",  # перезаписать выходной файл если существует
            str(output_path)
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )
        
        # Проверяем результат выполнения
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"FFmpeg error: {result.stderr}"
            )
        
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
        temp_input_path.unlink(missing_ok=True)
        raise
    
    except Exception as e:
        # Очищаем временные файлы при ошибке
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
    return {"status": "healthy"}

