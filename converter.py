"""Починка и конвертация голосовых, которые браузер отдаёт без заголовка контейнера."""

import base64
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# WebM/Opus: заголовок с неизвестным размером Segment.
# Его хватает, чтобы ffmpeg прочитал кластеры, если EBML-заголовок потерялся.
OPUS_WEBM_HEADER = base64.b64decode(
    "GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQRChYECGFOAZwH/////////EU2bdKtNu4tTq4QVSalmU6yBoU27i1OrhBZUrmtTrIHLTbuMU6uEElTDZ1OsggE17AEAAAAAAABoAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVSalmpSrXsYMPQkBNgIxMYXZmNjEuMS4xMDBXQYxMYXZmNjEuMS4xMDAWVK5r5a4BAAAAAAAAXNeBAXPFiGfEn4eIz59qnIEAIrWcg3VuZIiBAIaGQV9PUFVTVqqDYy6gVruEBMS0AIOBAuGRn4EBtYhA53AAAAAAAGJkgSBjopNPcHVzSGVhZAEBOAGAuwAAAAAAElTDZ9dzc59jwIBnyJlFo4dFTkNPREVSRIeMTGF2ZjYxLjEuMTAwc3OyY8CLY8WIZ8Sfh4jPn2pnyKFFo4dFTkNPREVSRIeUTGF2YzYxLjMuMTAwIGxpYm9wdXM="
)

# fMP4/AAC: init-сегмент (ftyp + moov). Safari иногда присылает только moof+mdat.
AAC_INIT_SEGMENT = base64.b64decode(
    "AAAAHGZ0eXBpc281AAACAGlzbzVpc282bXA0MQAAArxtb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAAAAAABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAABv3RyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAQEAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAVttZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAAKxEAAAAAFXEAAAAAAAtaGRscgAAAAAAAAAAc291bgAAAAAAAAAAAAAAAFNvdW5kSGFuZGxlcgAAAAEGbWluZgAAABBzbWhkAAAAAAAAAAAAAAAkZGluZgAAABxkcmVmAAAAAAAAAAEAAAAMdXJsIAAAAAEAAADKc3RibAAAAH5zdHNkAAAAAAAAAAEAAABubXA0YQAAAAAAAAABAAAAAAAAAAAAAQAQAAAAAKxEAAAAAAA2ZXNkcwAAAAADgICAJQABAASAgIAXQBUAAAAAAPoAAAD6AAWAgIAFEghW5QAGgICAAQIAAAAUYnRydAAAAAAAAPoAAAD6AAAAABBzdHRzAAAAAAAAAAAAAAAQc3RzYwAAAAAAAAAAAAAAFHN0c3oAAAAAAAAAAAAAAAAAAAAQc3RjbwAAAAAAAAAAAAAAKG12ZXgAAAAgdHJleAAAAAAAAAABAAAAAQAAAAAAAAAAAAAAAAAAAGF1ZHRhAAAAWW1ldGEAAAAAAAAAIWhkbHIAAAAAAAAAAG1kaXJhcHBsAAAAAAAAAAAAAAAALGlsc3QAAAAkqXRvbwAAABxkYXRhAAAAAQAAAABMYXZmNjEuMS4xMDA="
)

EBML = bytes.fromhex("1a45dfa3")
CLUSTER = bytes.fromhex("1f43b675")


class ConversionError(Exception):
    """ffmpeg не смог открыть файл ни одним способом."""


def convert_file(input_path: Path, output_path: Path, target_format: str) -> None:
    """Конвертирует файл. Сначала как есть, потом после починки заголовка."""
    data = input_path.read_bytes()
    last_error = "unknown error"

    for name, payload in _candidates(data):
        source = input_path
        repaired = None
        if payload is not None:
            repaired = input_path.with_name(f"{input_path.name}.{name}")
            repaired.write_bytes(payload)
            source = repaired

        try:
            code, stderr = _run_ffmpeg(source, output_path, target_format)
        finally:
            if repaired is not None:
                repaired.unlink(missing_ok=True)

        if _output_ok(output_path):
            if name != "original" or code != 0:
                logger.warning(
                    "Converted with repair strategy=%s code=%s size=%s magic=%s stderr=%s",
                    name,
                    code,
                    len(data),
                    data[:8].hex(),
                    _short(stderr),
                )
            return

        last_error = stderr or last_error
        output_path.unlink(missing_ok=True)
        logger.warning(
            "Convert attempt failed strategy=%s size=%s magic=%s stderr=%s",
            name,
            len(data),
            data[:8].hex(),
            _short(stderr),
        )

    raise ConversionError(
        "The uploaded file is corrupted or not a valid audio file. "
        f"size={len(data)} magic={data[:8].hex()} ffmpeg={_short(last_error)}"
    )


def _candidates(data: bytes) -> list[tuple[str, bytes | None]]:
    # None значит «читать исходный файл как есть».
    items: list[tuple[str, bytes | None]] = [("original", None)]

    stripped = _strip_leading_junk(data)
    if stripped != data:
        items.append(("stripped", stripped))

    cluster_at = _headerless_cluster_offset(data)
    if cluster_at is not None:
        items.append(("opus-header", OPUS_WEBM_HEADER + data[cluster_at:]))

    moof_at = _moof_only_offset(data)
    if moof_at is not None:
        items.append(("aac-init", AAC_INIT_SEGMENT + data[moof_at:]))

    trimmed = _drop_last_cluster(data if stripped == data else stripped)
    if trimmed is not None:
        items.append(("trim-last-cluster", trimmed))

    return items


def _strip_leading_junk(data: bytes) -> bytes:
    """Иногда перед контейнером прилипает мусор multipart."""
    window = data[:4096]
    ebml = window.find(EBML)
    if ebml > 0:
        return data[ebml:]
    ogg = window.find(b"OggS")
    if ogg > 0:
        return data[ogg:]
    ftyp = window.find(b"ftyp")
    if ftyp >= 4:
        return data[ftyp - 4 :]
    return data


def _headerless_cluster_offset(data: bytes) -> int | None:
    # Chrome MediaRecorder с timeslice иногда теряет первый кусок с EBML.
    if data.startswith(EBML):
        return None
    index = data.find(CLUSTER, 0, 65536)
    if index < 0:
        return None
    return index


def _moof_only_offset(data: bytes) -> int | None:
    # Safari пишет fMP4. Если init-сегмент (moov) не попал в файл, остаётся moof.
    if b"moov" in data[:8192]:
        return None
    index = data.find(b"moof", 0, 65536)
    if index < 4:
        return None
    return index - 4


def _drop_last_cluster(data: bytes) -> bytes | None:
    # Последний кластер часто оборван в момент stop(). Без него файл открывается.
    if not data.startswith(EBML):
        return None
    positions = []
    start = 0
    while True:
        found = data.find(CLUSTER, start)
        if found < 0:
            break
        positions.append(found)
        start = found + 4
    if len(positions) < 2:
        return None
    trimmed = data[: positions[-1]]
    if len(trimmed) < 64:
        return None
    return trimmed


def _run_ffmpeg(source: Path, output_path: Path, target_format: str) -> tuple[int, str]:
    output_path.unlink(missing_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        # Битый хвост кадра не должен ронять всю конвертацию.
        "-fflags",
        "+genpts+discardcorrupt+igndts",
        "-err_detect",
        "ignore_err",
        "-probesize",
        "50M",
        "-analyzeduration",
        "50M",
        "-i",
        str(source),
        "-vn",
        *_codec_args(target_format),
        str(output_path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("Conversion timeout: file is too large or processing took too long") from exc

    return result.returncode, (result.stderr or "").strip()


def _codec_args(target_format: str) -> list[str]:
    # Без -c:a ffmpeg кладёт в .ogg Vorbis. WhatsApp и Telegram показывают
    # голосовое с волной только для OGG/Opus, поэтому кодек задаём явно.
    if target_format == "ogg":
        return [
            "-c:a", "libopus",
            "-b:a", "32k",
            "-ac", "1",
            "-ar", "48000",
            "-application", "voip",
        ]
    return []


def _output_ok(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 128:
        return False
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        return False
    try:
        return float((probe.stdout or "").strip() or "0") > 0.05
    except ValueError:
        return False


def _short(text: str) -> str:
    line = " | ".join(part.strip() for part in text.splitlines() if part.strip())
    return line[:400]
