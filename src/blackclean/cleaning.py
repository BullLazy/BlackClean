from dataclasses import dataclass
from io import BytesIO
import secrets
import warnings

from mutagen import MutagenError
from mutagen.apev2 import APEv2, APENoHeaderError
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from PIL import Image, ImageSequence, UnidentifiedImageError


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_SAFE_FILENAME_STEM_LENGTH = 120


class InvalidImageError(Exception):
    pass


class UnsupportedFormatError(Exception):
    pass


class VerificationError(Exception):
    pass


@dataclass(frozen=True)
class CleanedFile:
    content: bytes
    image_format: str
    media_type: str
    extension: str
    metadata_categories: tuple[str, ...] = ()


_FORMAT_DETAILS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
    "TIFF": ("image/tiff", ".tif"),
    "AVIF": ("image/avif", ".avif"),
    "GIF": ("image/gif", ".gif"),
    "BMP": ("image/bmp", ".bmp"),
    "TGA": ("image/x-tga", ".tga"),
    "ICO": ("image/x-icon", ".ico"),
    "ICNS": ("image/icns", ".icns"),
    "MP3": ("audio/mpeg", ".mp3"),
}

_TIFF_STRUCTURAL_TAGS = {
    254,
    255,
    256,
    257,
    258,
    259,
    262,
    273,
    277,
    278,
    279,
    284,
    292,
    293,
    296,
    317,
    320,
    322,
    323,
    324,
    325,
    338,
    339,
    347,
    530,
    531,
    532,
}

_METADATA_CATEGORY_ORDER = (
    "gps",
    "camera",
    "date",
    "exif",
    "xmp",
    "iptc",
    "icc",
    "comment",
    "text",
    "description",
    "application",
    "other",
)

_TIFF_METADATA_TAG_CATEGORIES = {
    270: "description",
    271: "camera",
    272: "camera",
    305: "application",
    306: "date",
    33723: "iptc",
    34675: "icc",
    34853: "gps",
    700: "xmp",
}


def _is_known_unsupported_format(contents: bytes) -> bool:
    if contents.startswith(b"%PDF-"):
        return True
    if len(contents) >= 12 and contents[4:8] == b"ftyp":
        file_type_data = contents[8:64]
        if b"avif" in file_type_data or b"avis" in file_type_data:
            return False
        return any(
            brand in file_type_data
            for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")
        )
    return False


def _is_mp3(contents: bytes) -> bool:
    try:
        MP3(BytesIO(contents))
        return True
    except (MutagenError, OSError, ValueError):
        return False


def _icon_frames(contents: bytes, image_format: str) -> list[Image.Image]:
    try:
        with Image.open(BytesIO(contents)) as image:
            if image_format == "ICO":
                sizes = sorted(
                    image.ico.sizes(),
                    key=lambda size: (size[0] * size[1], size[0]),
                    reverse=True,
                )
                frames = [image.ico.getimage(size) for size in sizes]
            else:
                seen_sizes = set()
                frames = []
                for size in image.icns.itersizes():
                    frame = image.icns.getimage(size)
                    if frame.size in seen_sizes:
                        continue
                    seen_sizes.add(frame.size)
                    frames.append(frame)
                frames.sort(
                    key=lambda frame: (frame.width * frame.height, frame.width),
                    reverse=True,
                )

            if not frames:
                raise InvalidImageError
            cleaned_frames = []
            for frame in frames:
                frame.load()
                frame = frame.convert("RGBA")
                cleaned_frames.append(frame)
            return cleaned_frames
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError):
        raise InvalidImageError from None


def _open_and_validate(contents: bytes) -> str:
    if not contents:
        raise InvalidImageError
    if _is_known_unsupported_format(contents):
        raise UnsupportedFormatError
    if _is_mp3(contents):
        return "MP3"

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents)) as image:
                image.load()
                image_format = image.format
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        raise InvalidImageError from None

    if image_format not in _FORMAT_DETAILS:
        raise UnsupportedFormatError
    if image_format in {"PNG", "TIFF"} and getattr(image, "n_frames", 1) > 1:
        raise UnsupportedFormatError
    if image_format in {"ICO", "ICNS"}:
        _icon_frames(contents, image_format)

    return image_format


def _add_metadata_category(categories: set[str], category: str) -> None:
    categories.add(category)


def _add_exif_metadata_categories(image: Image.Image, categories: set[str]) -> None:
    exif = image.getexif()
    if not exif:
        return

    _add_metadata_category(categories, "exif")
    if 34853 in exif:
        _add_metadata_category(categories, "gps")
    if any(tag in exif for tag in (271, 272)):
        _add_metadata_category(categories, "camera")
    if any(tag in exif for tag in (306, 36867, 36868)):
        _add_metadata_category(categories, "date")
    if 33723 in exif:
        _add_metadata_category(categories, "iptc")
    if 34675 in exif:
        _add_metadata_category(categories, "icc")
    if 700 in exif:
        _add_metadata_category(categories, "xmp")


def _jpeg_metadata_categories(contents: bytes, categories: set[str]) -> None:
    if not contents.startswith(b"\xff\xd8"):
        return

    position = 2
    while position < len(contents):
        if contents[position] != 0xFF:
            return
        while position < len(contents) and contents[position] == 0xFF:
            position += 1
        if position >= len(contents):
            return

        marker = contents[position]
        position += 1
        if marker in {0xDA, 0xD9}:
            return
        if marker in {0x01, *range(0xD0, 0xD8)}:
            continue
        if position + 2 > len(contents):
            return

        segment_length = int.from_bytes(contents[position : position + 2], "big")
        if segment_length < 2:
            return
        segment_end = position + segment_length
        if segment_end > len(contents):
            return
        payload = contents[position + 2 : segment_end]

        if marker == 0xFE:
            _add_metadata_category(categories, "comment")
        elif 0xE0 <= marker <= 0xEF:
            if payload.startswith(b"Exif\x00\x00"):
                _add_metadata_category(categories, "exif")
            elif b"XMP" in payload or b"xmp" in payload:
                _add_metadata_category(categories, "xmp")
            elif marker == 0xE2 and payload.startswith(b"ICC_PROFILE"):
                _add_metadata_category(categories, "icc")
            elif marker == 0xED or b"Photoshop 3.0" in payload or b"8BIM" in payload:
                _add_metadata_category(categories, "iptc")
            elif marker != 0xE0:
                _add_metadata_category(categories, "other")

        position = segment_end


def _png_metadata_categories(contents: bytes, categories: set[str]) -> None:
    signature = b"\x89PNG\r\n\x1a\n"
    if not contents.startswith(signature):
        return

    allowed_chunks = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
    category_by_chunk = {
        b"eXIf": "exif",
        b"iCCP": "icc",
        b"tEXt": "text",
        b"zTXt": "text",
        b"iTXt": "text",
        b"pHYs": "other",
        b"sCAL": "other",
        b"gAMA": "other",
        b"cHRM": "other",
        b"sRGB": "other",
    }
    position = len(signature)
    while position + 12 <= len(contents):
        chunk_length = int.from_bytes(contents[position : position + 4], "big")
        chunk_type = contents[position + 4 : position + 8]
        chunk_end = position + 12 + chunk_length
        if chunk_end > len(contents):
            return
        if chunk_type not in allowed_chunks:
            _add_metadata_category(categories, category_by_chunk.get(chunk_type, "other"))
        if chunk_type == b"IEND":
            return
        position = chunk_end


def _webp_metadata_categories(contents: bytes, categories: set[str]) -> None:
    try:
        chunks = _webp_chunks(contents)
    except InvalidImageError:
        return

    category_by_chunk = {b"EXIF": "exif", b"XMP ": "xmp", b"ICCP": "icc"}
    for chunk_type, _ in chunks:
        category = category_by_chunk.get(chunk_type)
        if category:
            _add_metadata_category(categories, category)


def _tiff_metadata_categories(image: Image.Image, categories: set[str]) -> None:
    for tag in image.tag_v2:
        if tag in _TIFF_STRUCTURAL_TAGS:
            continue
        _add_metadata_category(categories, _TIFF_METADATA_TAG_CATEGORIES.get(tag, "other"))


def _generic_image_metadata_categories(
    image: Image.Image,
    image_format: str,
    categories: set[str],
) -> None:
    if image_format != "TIFF":
        _add_exif_metadata_categories(image, categories)

    info_keys = {str(key).lower() for key in image.info}
    if "exif" in info_keys:
        _add_metadata_category(categories, "exif")
    if "xmp" in info_keys or "xml:com.adobe.xmp" in info_keys:
        _add_metadata_category(categories, "xmp")
    if "icc_profile" in info_keys:
        _add_metadata_category(categories, "icc")
    if "comment" in info_keys:
        _add_metadata_category(categories, "comment")
    if image_format == "PNG" and any(key in info_keys for key in ("comment", "text")):
        _add_metadata_category(categories, "text")


def _icon_frame_has_metadata(image: Image.Image, categories: set[str]) -> None:
    try:
        if image.getexif():
            _add_metadata_category(categories, "exif")
    except (AttributeError, OSError, ValueError):
        _add_metadata_category(categories, "other")

    info_keys = {str(key).lower() for key in image.info}
    if "exif" in info_keys:
        _add_metadata_category(categories, "exif")
    if "xmp" in info_keys or "xml:com.adobe.xmp" in info_keys:
        _add_metadata_category(categories, "xmp")
    if "icc_profile" in info_keys:
        _add_metadata_category(categories, "icc")
    if "comment" in info_keys:
        _add_metadata_category(categories, "comment")
    recognized_keys = {
        "exif",
        "xmp",
        "xml:com.adobe.xmp",
        "icc_profile",
        "comment",
        "transparency",
    }
    if info_keys - recognized_keys:
        _add_metadata_category(categories, "other")


def _icon_metadata_categories(
    contents: bytes, image_format: str, categories: set[str]
) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            if image_format == "ICO":
                sizes = image.ico.sizes()
                frames = [image.ico.getimage(size) for size in sizes]
            else:
                frames = [
                    image.icns.getimage(size) for size in image.icns.itersizes()
                ]
            for frame in frames:
                frame.load()
                _icon_frame_has_metadata(frame, categories)
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError):
        return


def _mp3_has_metadata(contents: bytes) -> bool:
    if _lyrics3_bounds(contents) is not None:
        return True
    for tag_loader, missing_error in (
        (ID3, ID3NoHeaderError),
        (APEv2, APENoHeaderError),
    ):
        try:
            if tag_loader(BytesIO(contents)):
                return True
        except missing_error:
            continue
        except (MutagenError, OSError, ValueError):
            return True
    return False


def _lyrics3_bounds(contents: bytes) -> tuple[int, int] | None:
    if contents.endswith(b"LYRICS200") and len(contents) >= 15:
        size_start = len(contents) - 15
        try:
            body_size = int(contents[size_start : size_start + 6])
        except ValueError:
            return None
        for start in (
            size_start - body_size,
            size_start - body_size - len(b"LYRICSBEGIN"),
        ):
            if start >= 0 and contents[start : start + 11] == b"LYRICSBEGIN":
                return start, len(contents)

    if contents.endswith(b"LYRICSEND"):
        start = contents.rfind(b"LYRICSBEGIN", 0, len(contents) - 9)
        if start >= 0:
            return start, len(contents)
    return None


def _detect_metadata_categories(contents: bytes, image_format: str) -> tuple[str, ...]:
    categories: set[str] = set()
    if image_format == "MP3":
        if _mp3_has_metadata(contents):
            _add_metadata_category(categories, "other")
        return tuple(
            category for category in _METADATA_CATEGORY_ORDER if category in categories
        )
    if image_format in {"ICO", "ICNS"}:
        _icon_metadata_categories(contents, image_format, categories)
        return tuple(
            category for category in _METADATA_CATEGORY_ORDER if category in categories
        )

    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            _generic_image_metadata_categories(image, image_format, categories)
            if image_format == "TIFF":
                _tiff_metadata_categories(image, categories)
            elif image_format == "JPEG":
                _jpeg_metadata_categories(contents, categories)
            elif image_format == "PNG":
                _png_metadata_categories(contents, categories)
            elif image_format == "WEBP":
                _webp_metadata_categories(contents, categories)
            elif image_format == "AVIF":
                if b"Exif\x00\x00" in contents:
                    _add_metadata_category(categories, "exif")
                if any(marker in contents for marker in (b"xml ", b"XMP")):
                    _add_metadata_category(categories, "xmp")
                if any(marker in contents for marker in (b"prof", b"rICC")):
                    _add_metadata_category(categories, "icc")
            elif image_format == "GIF":
                if b"\x21\xfe" in contents or "comment" in {
                    str(key).lower() for key in image.info
                }:
                    _add_metadata_category(categories, "comment")
                if _gif_has_metadata(contents) and "comment" not in categories:
                    _add_metadata_category(categories, "application")
            elif image_format == "BMP":
                if set(image.info) - {"dpi", "compression"}:
                    _add_metadata_category(categories, "other")
            elif image_format == "TGA":
                if set(image.info) - {"orientation"}:
                    _add_metadata_category(categories, "other")
    except (UnidentifiedImageError, OSError, ValueError, KeyError):
        return ()

    return tuple(category for category in _METADATA_CATEGORY_ORDER if category in categories)


def _jpeg_has_metadata_blocks(contents: bytes) -> bool:
    if not contents.startswith(b"\xff\xd8"):
        return True

    position = 2
    while position < len(contents):
        if contents[position] != 0xFF:
            return False

        marker_start = position
        while position < len(contents) and contents[position] == 0xFF:
            position += 1
        if position >= len(contents):
            return True

        marker = contents[position]
        position += 1

        if marker == 0xDA:
            return False
        if marker == 0xD9:
            return False

        if marker in {0x01, *range(0xD0, 0xD8)}:
            segment_end = position
        else:
            if position + 2 > len(contents):
                return True
            segment_length = int.from_bytes(contents[position : position + 2], "big")
            if segment_length < 2:
                return True
            segment_end = position + segment_length
            if segment_end > len(contents):
                return True

        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            return True

        position = segment_end
        if position == marker_start:
            return True

    return True


def _strip_jpeg_metadata(contents: bytes) -> bytes:
    if not contents.startswith(b"\xff\xd8"):
        raise InvalidImageError

    cleaned = bytearray(contents[:2])
    position = 2

    while position < len(contents):
        segment_start = position
        if contents[position] != 0xFF:
            raise InvalidImageError

        while position < len(contents) and contents[position] == 0xFF:
            position += 1
        if position >= len(contents):
            raise InvalidImageError

        marker = contents[position]
        position += 1

        if marker == 0xDA:
            cleaned.extend(contents[segment_start:])
            return bytes(cleaned)
        if marker == 0xD9:
            cleaned.extend(contents[segment_start:position])
            return bytes(cleaned)

        if marker in {0x01, *range(0xD0, 0xD8)}:
            segment_end = position
        else:
            if position + 2 > len(contents):
                raise InvalidImageError
            segment_length = int.from_bytes(contents[position : position + 2], "big")
            if segment_length < 2:
                raise InvalidImageError
            segment_end = position + segment_length
            if segment_end > len(contents):
                raise InvalidImageError

        if not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            cleaned.extend(contents[segment_start:segment_end])
        position = segment_end

    raise InvalidImageError


def _verify_clean_jpeg(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            if image.getexif():
                raise VerificationError
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None

    if _jpeg_has_metadata_blocks(contents):
        raise VerificationError


def _png_has_metadata_chunks(contents: bytes) -> bool:
    signature = b"\x89PNG\r\n\x1a\n"
    if not contents.startswith(signature):
        return True

    allowed_chunks = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
    position = len(signature)
    while position + 12 <= len(contents):
        chunk_length = int.from_bytes(contents[position : position + 4], "big")
        chunk_type_start = position + 4
        chunk_type_end = chunk_type_start + 4
        chunk_end = chunk_type_end + chunk_length + 4
        if chunk_end > len(contents):
            return True
        if contents[chunk_type_start:chunk_type_end] not in allowed_chunks:
            return True
        if contents[chunk_type_start:chunk_type_end] == b"IEND":
            return False
        position = chunk_end

    return True


def _strip_png_metadata(contents: bytes) -> bytes:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            clean_image = image.copy()
            clean_image.info = {}
            output = BytesIO()
            clean_image.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise InvalidImageError from None


def _verify_clean_png(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            if image.getexif():
                raise VerificationError
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None

    if _png_has_metadata_chunks(contents):
        raise VerificationError


def _webp_chunks(contents: bytes) -> list[tuple[bytes, bytes]]:
    if len(contents) < 12 or contents[:4] != b"RIFF" or contents[8:12] != b"WEBP":
        raise InvalidImageError

    chunks = []
    position = 12
    while position + 8 <= len(contents):
        chunk_type = contents[position : position + 4]
        chunk_length = int.from_bytes(contents[position + 4 : position + 8], "little")
        data_start = position + 8
        data_end = data_start + chunk_length
        padded_end = data_end + (chunk_length & 1)
        if padded_end > len(contents):
            raise InvalidImageError
        chunks.append((chunk_type, contents[data_start:data_end]))
        position = padded_end

    if position != len(contents) or not chunks:
        raise InvalidImageError
    return chunks


def _webp_has_metadata_chunks(contents: bytes) -> bool:
    try:
        chunks = _webp_chunks(contents)
    except InvalidImageError:
        return True
    return any(chunk_type in {b"EXIF", b"XMP ", b"ICCP"} for chunk_type, _ in chunks)


def _webp_bytes(chunks: list[tuple[bytes, bytes]]) -> bytes:
    body = bytearray(b"WEBP")
    for chunk_type, chunk_data in chunks:
        body.extend(chunk_type)
        body.extend(len(chunk_data).to_bytes(4, "little"))
        body.extend(chunk_data)
        if len(chunk_data) & 1:
            body.append(0)
    return b"RIFF" + len(body).to_bytes(4, "little") + bytes(body)


def _strip_webp_metadata(contents: bytes) -> bytes:
    chunks = _webp_chunks(contents)
    cleaned_chunks = []
    metadata_flags = 0x20 | 0x08 | 0x04

    for chunk_type, chunk_data in chunks:
        if chunk_type in {b"EXIF", b"XMP ", b"ICCP"}:
            continue
        if chunk_type == b"VP8X":
            if len(chunk_data) < 10:
                raise InvalidImageError
            chunk_data = bytes([chunk_data[0] & ~metadata_flags]) + chunk_data[1:]
        cleaned_chunks.append((chunk_type, chunk_data))

    return _webp_bytes(cleaned_chunks)


def _verify_clean_webp(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            if image.getexif():
                raise VerificationError
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None

    if _webp_has_metadata_chunks(contents):
        raise VerificationError


def _strip_tiff_metadata(contents: bytes) -> bytes:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            clean_image = image.copy()
            clean_image.info = {}
            output = BytesIO()
            clean_image.save(output, format="TIFF", tiffinfo={})
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise InvalidImageError from None


def _tiff_has_metadata(contents: bytes) -> bool:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            return any(tag not in _TIFF_STRUCTURAL_TAGS for tag in image.tag_v2)
    except (UnidentifiedImageError, OSError, ValueError):
        return True


def _verify_clean_tiff(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None

    if _tiff_has_metadata(contents):
        raise VerificationError


def _strip_avif_metadata(contents: bytes) -> bytes:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            clean_image = image.copy()
            clean_image.info = {}
            output = BytesIO()
            clean_image.save(output, format="AVIF", lossless=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise InvalidImageError from None


def _avif_has_metadata(contents: bytes) -> bool:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            if image.getexif() or any(
                key in image.info for key in ("exif", "xmp", "icc_profile")
            ):
                return True
    except (UnidentifiedImageError, OSError, ValueError):
        return True

    return any(
        marker in contents
        for marker in (b"Exif\x00\x00", b"xml ", b"XMP", b"prof", b"rICC")
    )


def _verify_clean_avif(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None

    if _avif_has_metadata(contents):
        raise VerificationError


def _gif_sub_blocks_end(contents: bytes, position: int) -> int:
    while True:
        if position >= len(contents):
            raise InvalidImageError
        block_length = contents[position]
        position += 1
        if block_length == 0:
            return position
        position += block_length
        if position > len(contents):
            raise InvalidImageError


def _gif_has_metadata(contents: bytes) -> bool:
    if len(contents) < 13 or contents[:6] not in {b"GIF87a", b"GIF89a"}:
        return True

    position = 6
    packed = contents[position + 4]
    position += 7
    if packed & 0x80:
        position += 3 * (2 ** ((packed & 0x07) + 1))

    try:
        while position < len(contents):
            block_type = contents[position]
            position += 1

            if block_type == 0x3B:
                return False
            if block_type == 0x2C:
                if position + 9 > len(contents):
                    return True
                packed = contents[position + 8]
                position += 9
                if packed & 0x80:
                    position += 3 * (2 ** ((packed & 0x07) + 1))
                if position >= len(contents):
                    return True
                position += 1
                position = _gif_sub_blocks_end(contents, position)
                continue
            if block_type != 0x21 or position >= len(contents):
                return True

            extension_label = contents[position]
            position += 1
            if extension_label == 0xF9:
                if position + 6 > len(contents):
                    return True
                position += 6
                continue
            if extension_label == 0xFE:
                return True
            if extension_label == 0xFF:
                if position >= len(contents):
                    return True
                application_length = contents[position]
                position += 1
                if position + application_length > len(contents):
                    return True
                application = contents[position : position + application_length]
                position += application_length
                if application != b"NETSCAPE2.0":
                    return True
                position = _gif_sub_blocks_end(contents, position)
                continue
            if extension_label == 0x01:
                return True
            position = _gif_sub_blocks_end(contents, position)
    except InvalidImageError:
        return True

    return True


def _strip_gif_metadata(contents: bytes) -> tuple[bytes, int]:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            frame_count = getattr(image, "n_frames", 1)
            frames = []
            durations = []
            disposals = []
            for frame_number in range(frame_count):
                image.seek(frame_number)
                frame = image.copy()
                frame.info = {}
                frames.append(frame)
                durations.append(image.info.get("duration", 0))
                disposals.append(image.info.get("disposal", 0))

            save_kwargs = {
                "format": "GIF",
                "save_all": frame_count > 1,
            }
            if frame_count > 1:
                save_kwargs["append_images"] = frames[1:]
                save_kwargs["duration"] = durations
                save_kwargs["loop"] = image.info.get("loop", 0)
                if any(disposals):
                    save_kwargs["disposal"] = disposals
            elif durations[0]:
                save_kwargs["duration"] = durations[0]

            transparency = image.info.get("transparency")
            if transparency is not None:
                save_kwargs["transparency"] = transparency

            output = BytesIO()
            frames[0].save(output, **save_kwargs)
            return output.getvalue(), frame_count
    except (UnidentifiedImageError, OSError, ValueError, IndexError):
        raise InvalidImageError from None


def _verify_clean_gif(contents: bytes, expected_frame_count: int) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            if getattr(image, "n_frames", 1) != expected_frame_count:
                raise VerificationError
            for frame_number in range(expected_frame_count):
                image.seek(frame_number)
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, IndexError):
        raise VerificationError from None

    if _gif_has_metadata(contents):
        raise VerificationError


def _strip_bmp_metadata(contents: bytes) -> bytes:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            clean_image = image.copy()
            clean_image.info = {}
            output = BytesIO()
            clean_image.save(output, format="BMP")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise InvalidImageError from None


def _verify_clean_bmp(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            structural_info = {"dpi", "compression"}
            if set(image.info) - structural_info:
                raise VerificationError
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None


def _strip_tga_metadata(contents: bytes) -> bytes:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            clean_image = image.copy()
            clean_image.info = {}
            output = BytesIO()
            clean_image.save(output, format="TGA")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise InvalidImageError from None


def _verify_clean_tga(contents: bytes) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            image.load()
            if set(image.info) - {"orientation"}:
                raise VerificationError
    except (UnidentifiedImageError, OSError, ValueError):
        raise VerificationError from None


def _strip_mp3_metadata(contents: bytes) -> bytes:
    lyrics3_bounds = _lyrics3_bounds(contents)
    if lyrics3_bounds is not None:
        start, end = lyrics3_bounds
        contents = contents[:start] + contents[end:]

    output = BytesIO(contents)
    try:
        APEv2(output).delete(output)
    except APENoHeaderError:
        pass
    except (MutagenError, OSError, ValueError):
        raise InvalidImageError from None

    output.seek(0)
    try:
        ID3(output).delete(output)
    except ID3NoHeaderError:
        pass
    except (MutagenError, OSError, ValueError):
        raise InvalidImageError from None
    return output.getvalue()


def _verify_clean_mp3(contents: bytes) -> None:
    try:
        MP3(BytesIO(contents))
    except (MutagenError, OSError, ValueError):
        raise VerificationError from None
    if _mp3_has_metadata(contents):
        raise VerificationError


def _strip_icon_metadata(contents: bytes, image_format: str) -> bytes:
    frames = _icon_frames(contents, image_format)
    for frame in frames:
        frame.info = {}
    output = BytesIO()
    if image_format == "ICO":
        sizes = [frame.size for frame in frames]
        frames[0].save(
            output,
            format="ICO",
            sizes=sizes,
            append_images=frames[1:],
        )
    else:
        frames[0].save(output, format="ICNS", append_images=frames[1:])
    return output.getvalue()


def _verify_clean_icon(contents: bytes, image_format: str) -> None:
    try:
        frames = _icon_frames(contents, image_format)
    except InvalidImageError:
        raise VerificationError from None

    categories: set[str] = set()
    for frame in frames:
        _icon_frame_has_metadata(frame, categories)
    if categories:
        raise VerificationError


def clean_image(contents: bytes) -> CleanedFile:
    image_format = _open_and_validate(contents)
    metadata_categories = _detect_metadata_categories(contents, image_format)

    if image_format == "JPEG":
        cleaned_contents = _strip_jpeg_metadata(contents)
        _verify_clean_jpeg(cleaned_contents)
    elif image_format == "PNG":
        cleaned_contents = _strip_png_metadata(contents)
        _verify_clean_png(cleaned_contents)
    elif image_format == "WEBP":
        cleaned_contents = _strip_webp_metadata(contents)
        _verify_clean_webp(cleaned_contents)
    elif image_format == "TIFF":
        cleaned_contents = _strip_tiff_metadata(contents)
        _verify_clean_tiff(cleaned_contents)
    elif image_format == "AVIF":
        cleaned_contents = _strip_avif_metadata(contents)
        _verify_clean_avif(cleaned_contents)
    elif image_format == "GIF":
        cleaned_contents, frame_count = _strip_gif_metadata(contents)
        _verify_clean_gif(cleaned_contents, frame_count)
    elif image_format == "BMP":
        cleaned_contents = _strip_bmp_metadata(contents)
        _verify_clean_bmp(cleaned_contents)
    elif image_format == "TGA":
        cleaned_contents = _strip_tga_metadata(contents)
        _verify_clean_tga(cleaned_contents)
    elif image_format == "ICO":
        cleaned_contents = _strip_icon_metadata(contents, image_format)
        _verify_clean_icon(cleaned_contents, image_format)
    elif image_format == "ICNS":
        cleaned_contents = _strip_icon_metadata(contents, image_format)
        _verify_clean_icon(cleaned_contents, image_format)
    elif image_format == "MP3":
        cleaned_contents = _strip_mp3_metadata(contents)
        _verify_clean_mp3(cleaned_contents)
    else:
        raise UnsupportedFormatError

    media_type, extension = _FORMAT_DETAILS[image_format]
    return CleanedFile(
        cleaned_contents,
        image_format,
        media_type,
        extension,
        metadata_categories,
    )


def safe_download_name(filename: str | None, extension: str) -> str:
    original_name = (filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
    stem = original_name.rsplit(".", 1)[0] if "." in original_name else original_name
    safe_stem = "".join(
        character
        if character.isascii() and (character.isalnum() or character in "._-")
        else "_"
        for character in stem
    ).strip("._-")
    safe_stem = safe_stem[:MAX_SAFE_FILENAME_STEM_LENGTH].strip("._-")
    if not safe_stem:
        safe_stem = "file"
    return f"{safe_stem}_clean{extension}"


def anonymized_download_name(extension: str) -> str:
    return f"clean_{secrets.token_hex(4)}{extension}"
