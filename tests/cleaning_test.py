from io import BytesIO
import importlib
import json
import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from PIL import ExifTags, Image, ImageSequence
from PIL.PngImagePlugin import PngInfo
from PIL.TiffImagePlugin import IFDRational

from blackclean.cleaning import MAX_UPLOAD_SIZE, VerificationError, safe_download_name
from blackclean.main import app


client = TestClient(app)


def download_filename(response) -> str:
    match = re.search(r'filename="([^"]+)"', response.headers["content-disposition"])
    assert match
    return match.group(1)


def cleaning_report(response) -> dict:
    return json.loads(unquote(response.headers["x-blackclean-report"]))


def assert_anonymous_filename(response, extension: str) -> str:
    filename = download_filename(response)
    assert re.fullmatch(rf"clean_[0-9a-f]{{8}}{re.escape(extension)}", filename)
    assert filename.isascii()
    assert all(character.isalnum() or character in "._-" for character in filename)
    assert "/" not in filename
    assert "\\" not in filename
    assert ".." not in filename
    return filename


def make_jpeg_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    exif = image.getexif()
    exif[ExifTags.Base.Make] = "BlackClean Test Camera"
    exif[ExifTags.Base.Model] = "Test Model"

    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps_ifd[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps_ifd[ExifTags.GPS.GPSLatitude] = [
        IFDRational(38, 1),
        IFDRational(25, 1),
        IFDRational(30, 1),
    ]
    exif[ExifTags.Base.GPSInfo] = gps_ifd

    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes(), quality=95)
    return buffer.getvalue()


def make_png_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    exif = image.getexif()
    exif[ExifTags.Base.Make] = "BlackClean PNG Camera"
    pnginfo = PngInfo()
    pnginfo.add_text("Comment", "private PNG metadata")

    buffer = BytesIO()
    image.save(buffer, format="PNG", pnginfo=pnginfo, exif=exif.tobytes())
    return buffer.getvalue()


def make_webp_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    exif = image.getexif()
    exif[ExifTags.Base.Make] = "BlackClean WebP Camera"

    buffer = BytesIO()
    image.save(
        buffer,
        format="WEBP",
        exif=exif.tobytes(),
        xmp=b"<x:xmpmeta>private WebP metadata</x:xmpmeta>",
        lossless=True,
    )
    return buffer.getvalue()


def make_avif_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    exif = image.getexif()
    exif[ExifTags.Base.Make] = "BlackClean AVIF Camera"

    buffer = BytesIO()
    image.save(
        buffer,
        format="AVIF",
        exif=exif.tobytes(),
        xmp=b"<x:xmpmeta>private AVIF metadata</x:xmpmeta>",
        lossless=True,
    )
    return buffer.getvalue()


def make_static_gif_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    buffer = BytesIO()
    image.save(buffer, format="GIF", comment=b"private GIF comment")
    return buffer.getvalue()


def make_animated_gif_with_metadata() -> bytes:
    frames = [
        Image.new("RGB", (8, 6), (20, 40, 60)),
        Image.new("RGB", (8, 6), (60, 40, 20)),
        Image.new("RGB", (8, 6), (40, 60, 20)),
    ]
    buffer = BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[80, 100, 120],
        loop=0,
        comment=b"private animated GIF comment",
    )
    return buffer.getvalue()


def make_tiff_with_metadata() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    buffer = BytesIO()
    image.save(
        buffer,
        format="TIFF",
        tiffinfo={
            270: "private TIFF description",
            271: "BlackClean TIFF Camera",
            305: "private TIFF software",
        },
    )
    return buffer.getvalue()


def make_bmp() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    buffer = BytesIO()
    image.save(buffer, format="BMP")
    return buffer.getvalue()


def make_tga() -> bytes:
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    buffer = BytesIO()
    image.save(buffer, format="TGA")
    return buffer.getvalue()


def _synchsafe(value: int) -> bytes:
    return bytes(
        (
            (value >> 21) & 0x7F,
            (value >> 14) & 0x7F,
            (value >> 7) & 0x7F,
            value & 0x7F,
        )
    )


def make_mp3_with_metadata() -> bytes:
    title = b"\x03private MP3 title"
    id3_frame = b"TIT2" + _synchsafe(len(title)) + b"\x00\x00" + title
    id3_body = id3_frame
    id3 = b"ID3\x04\x00\x00" + _synchsafe(len(id3_body)) + id3_body

    # MPEG-1 Layer III, 128 kbps, 44.1 kHz. Mutagen only needs valid frames
    # for this fixture; decoding audio is outside BlackClean's scope.
    frame_length = 417
    audio_frame = b"\xff\xfb\x90\x64" + b"\x00" * (frame_length - 4)
    id3v1 = (
        b"TAG"
        + b"private MP3 title".ljust(30, b"\x00")
        + b"BlackClean".ljust(30, b"\x00")
        + b"2026".ljust(4, b"\x00")
        + b"\x00" * 60
    )
    contents = id3 + audio_frame * 3 + id3v1
    from mutagen.apev2 import APEv2

    ape = APEv2()
    ape["Title"] = "private APE title"
    buffer = BytesIO(contents)
    ape.save(buffer)
    contents = buffer.getvalue()
    lyrics_body = b"LYRICSBEGINprivate Lyrics3 title"
    lyrics_size = f"{len(lyrics_body):06d}".encode("ascii")
    return contents + lyrics_body + lyrics_size + b"LYRICS200"


def make_ico() -> bytes:
    image = Image.new("RGBA", (32, 32), (20, 40, 60, 255))
    buffer = BytesIO()
    image.save(buffer, format="ICO", sizes=[(16, 16), (32, 32)])
    return buffer.getvalue()


def make_ico_with_metadata() -> bytes:
    image = Image.new("RGBA", (32, 32), (20, 40, 60, 255))
    exif = image.getexif()
    exif[ExifTags.Base.Make] = "Private icon metadata"
    buffer = BytesIO()
    image.save(
        buffer,
        format="ICO",
        sizes=[(16, 16), (32, 32)],
        exif=exif.tobytes(),
    )
    return buffer.getvalue()


def make_icns() -> bytes:
    image = Image.new("RGBA", (128, 128), (20, 40, 60, 255))
    buffer = BytesIO()
    image.save(buffer, format="ICNS")
    return buffer.getvalue()


def test_clean_jpeg_returns_valid_metadata_free_download():
    original_bytes = make_jpeg_with_metadata()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", original_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert "attachment" in response.headers["content-disposition"]
    assert_anonymous_filename(response, ".jpg")

    cleaned_bytes = response.content
    cleaned = Image.open(BytesIO(cleaned_bytes)).convert("RGB")

    assert cleaned.size == original.size
    assert list(cleaned.getdata()) == list(original.getdata())
    assert cleaned.getexif() == {}
    assert cleaned_bytes != original_bytes


def test_clean_mp3_removes_id3_metadata_without_reencoding():
    original_bytes = make_mp3_with_metadata()

    response = client.post(
        "/clean",
        files={"file": ("recording.wav", original_bytes, "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert_anonymous_filename(response, ".mp3")
    assert b"private MP3 title" not in response.content
    assert b"private APE title" not in response.content
    assert b"private Lyrics3 title" not in response.content

    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.mp3 import MP3

    MP3(BytesIO(response.content))
    with pytest.raises(ID3NoHeaderError):
        ID3(BytesIO(response.content))

    report = cleaning_report(response)
    assert report["format"] == "MP3"
    assert report["metadata_categories"] == ["other"]
    assert "metadata_cleaned" in report["operations"]


def test_clean_ico_preserves_icon_sizes_and_uses_canonical_extension():
    response = client.post(
        "/clean",
        files={"file": ("icon.png", make_ico(), "image/png")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/x-icon")
    assert_anonymous_filename(response, ".ico")

    with Image.open(BytesIO(response.content)) as icon:
        assert icon.format == "ICO"
        assert icon.ico.sizes() == {(16, 16), (32, 32)}
        for size in icon.ico.sizes():
            icon.ico.getimage(size).load()

    assert cleaning_report(response)["format"] == "ICO"


def test_clean_ico_removes_embedded_exif_metadata():
    response = client.post(
        "/clean",
        files={"file": ("icon.png", make_ico_with_metadata(), "image/png")},
    )

    assert response.status_code == 200
    assert b"Private icon metadata" not in response.content
    with Image.open(BytesIO(response.content)) as icon:
        assert icon.ico.getimage((32, 32)).getexif() == {}
    assert cleaning_report(response)["metadata_categories"] == ["exif"]


def test_clean_icns_preserves_readable_icon_resources_and_uses_canonical_extension():
    response = client.post(
        "/clean",
        files={"file": ("icon.jpg", make_icns(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/icns")
    assert_anonymous_filename(response, ".icns")

    with Image.open(BytesIO(response.content)) as icon:
        assert icon.format == "ICNS"
        sizes = list(icon.icns.itersizes())
        assert sizes
        for size in sizes:
            icon.icns.getimage(size).load()

    assert cleaning_report(response)["format"] == "ICNS"


def test_clean_jpeg_removes_non_exif_metadata_blocks():
    original_bytes = make_jpeg_with_metadata()
    app13_payload = b"Photoshop IPTC metadata"
    com_payload = b"private JPEG comment"
    app13 = b"\xff\xed" + (len(app13_payload) + 2).to_bytes(2, "big") + app13_payload
    comment = b"\xff\xfe" + (len(com_payload) + 2).to_bytes(2, "big") + com_payload
    original_bytes = original_bytes[:2] + app13 + comment + original_bytes[2:]

    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", original_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    assert app13_payload not in response.content
    assert com_payload not in response.content
    Image.open(BytesIO(response.content)).load()


def test_clean_rejects_empty_upload():
    response = client.post(
        "/clean",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )

    assert response.status_code == 400


def test_clean_requires_file_field():
    response = client.post("/clean")

    assert response.status_code == 422


def test_clean_rejects_invalid_upload():
    response = client.post(
        "/clean",
        files={"file": ("random.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400


def test_clean_rejects_truncated_jpeg():
    truncated = make_jpeg_with_metadata()[:24]

    response = client.post(
        "/clean",
        files={"file": ("truncated.jpg", truncated, "image/jpeg")},
    )

    assert response.status_code == 400


def test_clean_enforces_upload_size_limit():
    response = client.post(
        "/clean",
        files={"file": ("large.jpg", b"x" * (MAX_UPLOAD_SIZE + 1), "image/jpeg")},
    )

    assert response.status_code == 413


def test_clean_detects_format_from_content_and_sanitizes_filename():
    response = client.post(
        "/clean",
        files={
            "file": (
                "../../private.exe",
                make_jpeg_with_metadata(),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 200
    content_disposition = response.headers["content-disposition"]
    assert_anonymous_filename(response, ".jpg")
    assert "private" not in content_disposition
    assert ".." not in content_disposition
    assert "/" not in content_disposition


def test_clean_anonymizes_sensitive_filename_by_default():
    response = client.post(
        "/clean",
        files={
            "file": (
                "Ahmet_Karapinar_Izmir_Ev_2026.jpg",
                make_jpeg_with_metadata(),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 200
    filename = assert_anonymous_filename(response, ".jpg")
    assert all(value not in filename for value in ("Ahmet", "Karapinar", "Izmir", "2026"))


def test_clean_explicit_anonymization_on_uses_anonymous_filename():
    response = client.post(
        "/clean",
        data={"anonymize_filename": "true"},
        files={"file": ("IMG-20260930-WA0015.jpg", make_jpeg_with_metadata(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert_anonymous_filename(response, ".jpg")


def test_clean_response_contains_privacy_report_without_raw_metadata():
    original_bytes = make_jpeg_with_metadata()
    response = client.post(
        "/clean",
        files={"file": ("private-photo.jpg", original_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    report = cleaning_report(response)
    assert report["format"] == "JPEG"
    assert report["input_size"] == len(original_bytes)
    assert {"exif", "gps", "camera"}.issubset(report["metadata_categories"])
    assert "metadata_detected" in report["operations"]
    assert "metadata_cleaned" in report["operations"]
    assert "gps_found" in report["operations"]
    assert "gps_removed" in report["operations"]
    assert "filename_anonymized" in report["operations"]
    assert report["filename_anonymized"] is True
    assert report["verification"] == "passed"
    assert "private-photo" not in json.dumps(report)
    assert "38" not in json.dumps(report)


def test_clean_privacy_report_does_not_invent_metadata_operations():
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    response = client.post(
        "/clean",
        files={"file": ("plain.jpg", buffer.getvalue(), "image/jpeg")},
    )

    assert response.status_code == 200
    report = cleaning_report(response)
    assert report["metadata_categories"] == []
    assert "metadata_detected" not in report["operations"]
    assert "metadata_cleaned" not in report["operations"]
    assert "gps_removed" not in report["operations"]
    assert report["verification"] == "passed"


def test_clean_privacy_report_marks_filename_sanitization_when_anonymization_is_off():
    response = client.post(
        "/clean",
        data={"anonymize_filename": "false"},
        files={"file": ("../../private-photo.jpg", make_jpeg_with_metadata(), "image/jpeg")},
    )

    assert response.status_code == 200
    report = cleaning_report(response)
    assert report["filename_anonymized"] is False
    assert "filename_sanitized" in report["operations"]
    assert "filename_anonymized" not in report["operations"]


def test_clean_uses_content_based_extension_with_anonymization():
    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", make_png_with_metadata(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert_anonymous_filename(response, ".png")


def test_clean_anonymized_filenames_are_random():
    original_bytes = make_jpeg_with_metadata()
    first = client.post(
        "/clean", files={"file": ("same.jpg", original_bytes, "image/jpeg")}
    )
    second = client.post(
        "/clean", files={"file": ("same.jpg", original_bytes, "image/jpeg")}
    )

    assert first.status_code == second.status_code == 200
    first_name = assert_anonymous_filename(first, ".jpg")
    second_name = assert_anonymous_filename(second, ".jpg")
    assert first_name != second_name


def test_clean_can_disable_anonymization_without_disabling_safety():
    response = client.post(
        "/clean",
        data={"anonymize_filename": "false"},
        files={
            "file": (
                "Ahmet_Karapinar_Izmir_2026.jpg",
                make_jpeg_with_metadata(),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 200
    assert download_filename(response) == "Ahmet_Karapinar_Izmir_2026_clean.jpg"


@pytest.mark.parametrize(
    "filename",
    [
        "normal.jpg",
        "with spaces.jpg",
        "Ahmet_İzmir_📸_2026.jpg",
        "../../secret.jpg",
        r"..\..\secret.jpg",
        "/etc/passwd",
        r"C:\Users\Ahmet\secret.jpg",
        "bad\r\nContent-Disposition: injected.jpg",
        "bad\x00name.jpg",
        "a" * 1000 + ".jpg",
        "photo.jpg.exe",
        "photo.tar.jpg",
        "..",
        ".",
        "trailing. ",
    ],
)
def test_anonymization_off_sanitizes_untrusted_filename(filename):
    response = client.post(
        "/clean",
        data={"anonymize_filename": "false"},
        files={"file": (filename, make_jpeg_with_metadata(), "image/jpeg")},
    )

    assert response.status_code == 200
    output_filename = download_filename(response)
    assert output_filename.endswith("_clean.jpg")
    assert output_filename.isascii()
    assert len(output_filename) < 255
    assert all(
        character.isalnum() or character in "._-" for character in output_filename
    )
    assert "/" not in output_filename
    assert "\\" not in output_filename
    assert ".." not in output_filename
    assert "\r" not in output_filename
    assert "\n" not in output_filename
    assert "\x00" not in output_filename


@pytest.mark.parametrize("filename", [None, "", "..", "."])
def test_safe_download_name_handles_empty_and_dot_names(filename):
    output_filename = safe_download_name(filename, ".jpg")

    assert output_filename == "file_clean.jpg"


def test_clean_png_returns_valid_metadata_free_download():
    original_bytes = make_png_with_metadata()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.png", original_bytes, "image/png")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert_anonymous_filename(response, ".png")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.size == original.size
    assert list(cleaned.convert("RGB").getdata()) == list(original.getdata())
    assert cleaned.getexif() == {}
    assert "Comment" not in cleaned.info


def test_clean_webp_returns_valid_metadata_free_download():
    original_bytes = make_webp_with_metadata()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.webp", original_bytes, "image/webp")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
    assert_anonymous_filename(response, ".webp")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.size == original.size
    assert list(cleaned.convert("RGB").getdata()) == list(original.getdata())
    assert cleaned.getexif() == {}
    assert "xmp" not in cleaned.info


def test_clean_avif_returns_valid_metadata_free_download():
    original_bytes = make_avif_with_metadata()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.avif", original_bytes, "image/avif")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/avif")
    assert_anonymous_filename(response, ".avif")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.size == original.size
    cleaned_pixels = list(cleaned.convert("RGB").getdata())
    original_pixels = list(original.getdata())
    assert len(cleaned_pixels) == len(original_pixels)
    assert max(
        max(abs(cleaned_value - original_value) for cleaned_value, original_value in zip(cleaned_pixel, original_pixel))
        for cleaned_pixel, original_pixel in zip(cleaned_pixels, original_pixels)
    ) <= 3
    assert cleaned.getexif() == {}
    assert "xmp" not in cleaned.info


def test_clean_rejects_truncated_avif():
    response = client.post(
        "/clean",
        files={"file": ("truncated.avif", make_avif_with_metadata()[:32], "image/avif")},
    )

    assert response.status_code == 400


def test_clean_detects_avif_from_content_not_filename_or_mime():
    response = client.post(
        "/clean",
        files={
            "file": (
                "photo.jpg",
                make_avif_with_metadata(),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/avif")
    assert_anonymous_filename(response, ".avif")


def test_clean_static_gif_returns_metadata_free_download():
    original_bytes = make_static_gif_with_metadata()

    response = client.post(
        "/clean",
        files={"file": ("photo.gif", original_bytes, "image/gif")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/gif")
    assert_anonymous_filename(response, ".gif")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.n_frames == 1
    assert "comment" not in cleaned.info
    assert list(cleaned.convert("RGB").getdata()) == list(
        Image.open(BytesIO(original_bytes)).convert("RGB").getdata()
    )


def test_clean_animated_gif_preserves_frames():
    original_bytes = make_animated_gif_with_metadata()
    original = Image.open(BytesIO(original_bytes))

    response = client.post(
        "/clean",
        files={"file": ("animation.gif", original_bytes, "image/gif")},
    )

    assert response.status_code == 200
    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.n_frames == original.n_frames == 3
    assert "comment" not in cleaned.info
    assert [frame.size for frame in ImageSequence.Iterator(cleaned)] == [
        (8, 6),
        (8, 6),
        (8, 6),
    ]


def test_clean_rejects_truncated_gif():
    response = client.post(
        "/clean",
        files={"file": ("truncated.gif", make_animated_gif_with_metadata()[:20], "image/gif")},
    )

    assert response.status_code == 400


def test_clean_detects_gif_from_content_not_filename():
    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", make_static_gif_with_metadata(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/gif")


def test_clean_bmp_returns_valid_metadata_free_download():
    original_bytes = make_bmp()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.bmp", original_bytes, "image/bmp")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/bmp")
    assert_anonymous_filename(response, ".bmp")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.format == "BMP"
    assert cleaned.size == original.size
    assert set(cleaned.info) <= {"dpi", "compression"}
    assert list(cleaned.convert("RGB").getdata()) == list(original.getdata())


def test_clean_rejects_truncated_bmp():
    response = client.post(
        "/clean",
        files={"file": ("truncated.bmp", make_bmp()[:54], "image/bmp")},
    )

    assert response.status_code == 400


def test_clean_detects_bmp_from_content_not_filename():
    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", make_bmp(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/bmp")


def test_clean_tga_returns_valid_metadata_free_download():
    original_bytes = make_tga()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.tga", original_bytes, "image/x-tga")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/x-tga")
    assert_anonymous_filename(response, ".tga")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.format == "TGA"
    assert cleaned.size == original.size
    assert set(cleaned.info) <= {"orientation"}
    assert list(cleaned.convert("RGB").getdata()) == list(original.getdata())


def test_clean_rejects_truncated_tga():
    response = client.post(
        "/clean",
        files={"file": ("truncated.tga", make_tga()[:18], "image/x-tga")},
    )

    assert response.status_code == 400


def test_clean_detects_tga_from_content_not_filename():
    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", make_tga(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/x-tga")


def test_clean_tiff_returns_valid_metadata_free_download():
    original_bytes = make_tiff_with_metadata()
    original = Image.open(BytesIO(original_bytes)).convert("RGB")

    response = client.post(
        "/clean",
        files={"file": ("photo.tiff", original_bytes, "image/tiff")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/tiff")
    assert_anonymous_filename(response, ".tif")

    cleaned = Image.open(BytesIO(response.content))
    assert cleaned.size == original.size
    assert list(cleaned.convert("RGB").getdata()) == list(original.getdata())
    assert 270 not in cleaned.tag_v2
    assert 271 not in cleaned.tag_v2
    assert 305 not in cleaned.tag_v2


def test_clean_rejects_unsupported_image_format():
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    unsupported = BytesIO()
    image.save(unsupported, format="PPM")

    response = client.post(
        "/clean",
        files={"file": ("photo.ppm", unsupported.getvalue(), "image/x-portable-pixmap")},
    )

    assert response.status_code == 415


def test_clean_rejects_pdf_signature():
    response = client.post(
        "/clean",
        files={"file": ("document.pdf", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 415


def test_clean_rejects_heif_signature():
    heif_header = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic"
    response = client.post(
        "/clean",
        files={"file": ("photo.heic", heif_header, "image/heic")},
    )

    assert response.status_code == 415


def test_clean_does_not_download_when_verification_fails(monkeypatch):
    main_module = importlib.import_module("blackclean.main")

    def fail_verification(_contents):
        raise VerificationError

    monkeypatch.setattr(main_module, "clean_image", fail_verification)
    original_bytes = make_jpeg_with_metadata()
    response = client.post(
        "/clean",
        files={"file": ("photo.jpg", original_bytes, "image/jpeg")},
    )

    assert response.status_code == 500
    assert response.content != original_bytes
