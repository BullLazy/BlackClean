import re

from fastapi.testclient import TestClient
from blackclean.main import app
from PIL import Image, ExifTags
from io import BytesIO
from PIL.TiffImagePlugin import IFDRational

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code ==  200
    assert "Upload" in response.text
    assert 'type="file"' in response.text
    assert "<form" in response.text
    assert 'action="/inspect"' in response.text
    assert 'method="post"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert 'name="file"' in response.text
    assert "<button" in response.text
    assert "<script>" in response.text
    assert "fetch" in response.text
    assert 'id="file"' in response.text
    assert "fileInput" in response.text
    assert "files[0]" in response.text
    assert "FormData" in response.text
    assert "formData.append" in response.text
    assert 'method: "POST"' in response.text
    assert "body: formData" in response.text
    assert "response.json" in response.text
    assert "metadata" in response.text
    assert "Object.entries" in response.text
    assert "createElement" in response.text
    assert "row.textContent" in response.text
    assert "appendChild" in response.text
    assert "submit" in response.text
    assert "event.preventDefault" in response.text
    assert 'id="anonymizeFilename"' in response.text
    assert 'name="anonymize_filename"' in response.text
    assert 'id="anonymizeFilename" type="checkbox"' in response.text
    assert 'name="anonymize_filename" checked' in response.text
    assert "Dosya adını anonimleştir" in response.text
    assert 'formData.append("anonymize_filename"' in response.text


def test_root_uses_response_filename_for_download_and_success_message():
    response = client.get("/")

    assert response.status_code == 200
    assert 'const header = response.headers.get("Content-Disposition") || ""' in response.text
    assert 'const match = header.match(/filename="([^"]+)"/i)' in response.text
    assert 'const downloadName = responseFilename(response);' in response.text
    assert 'downloadLink.download = downloadName;' in response.text
    assert 'showStatus("success", "Dosyan temizlendi ✓", downloadLink.download);' in response.text
    assert 'selectedFile.name.slice(0, selectedFile.name.lastIndexOf("."))' not in response.text
    assert 'return `${baseName}_clean`' not in response.text
    assert 'return "clean_download";' in response.text


def test_root_includes_local_history_and_privacy_report_states():
    response = client.get("/")

    assert response.status_code == 200
    assert 'aria-label="Menüyü aç"' in response.text
    assert "Temizleme geçmişi" in response.text
    assert 'id="historyView"' in response.text
    assert 'id="reportView"' in response.text
    assert "X-BlackClean-Report" in response.text
    assert "localStorage.getItem" in response.text
    assert "localStorage.setItem" in response.text
    assert "MAX_HISTORY_ITEMS = 50" in response.text
    assert "Henüz temizleme geçmişi yok" in response.text
    assert "Geçmiş yüklenemedi" in response.text
    assert "Temizleme raporu" in response.text
    assert "GPS bilgisi kaldırıldı" in response.text
    assert "window.confirm" in response.text
    assert "orijinal filename" not in response.text.lower()


def test_root_includes_versioned_local_settings_with_safe_defaults():
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="settingsView"' in response.text
    assert 'id="settingsAnonymizeFilename"' in response.text
    assert 'id="settingsKeepHistory"' in response.text
    assert 'id="settingsCreateHistory"' in response.text
    assert 'id="settingsShowPrivacyReport"' in response.text
    assert 'id="settingsMaxHistoryItems"' in response.text
    assert 'id="settingsHistoryExpiryDays"' in response.text
    assert 'id="settingsTheme"' in response.text
    assert 'id="settingsDensity"' in response.text
    assert 'id="settingsMotion"' in response.text
    assert 'const SETTINGS_STORAGE_KEY = "blackclean.settings.v1"' in response.text
    assert 'anonymizeFilename: true' in response.text
    assert 'keepHistory: true' in response.text
    assert 'createHistoryRecord: true' in response.text
    assert 'showPrivacyReport: true' in response.text
    assert 'maxHistoryItems: 50' in response.text
    assert 'historyExpiryDays: 0' in response.text
    assert 'theme: "system"' in response.text
    assert 'density: "normal"' in response.text
    assert 'motion: "normal"' in response.text
    assert 'localStorage.setItem(SETTINGS_STORAGE_KEY' in response.text


def test_root_settings_explain_local_privacy_and_history_controls():
    response = client.get("/")

    assert response.status_code == 200
    assert "BlackClean temizlenen dosyaların kendisini temizleme geçmişinde saklamaz." in response.text
    assert "Geçmiş bilgileri cihazın yerel depolamasında tutulur." in response.text
    assert "GPS koordinatları ve ham metadata geçmişte saklanmaz." in response.text
    assert 'value="10"' in response.text
    assert 'value="25"' in response.text
    assert 'value="50"' in response.text
    assert 'value="100"' in response.text
    assert 'value="7"' in response.text
    assert 'value="30"' in response.text
    assert 'value="90"' in response.text
    assert 'if (!currentSettings.keepHistory || !currentSettings.createHistoryRecord) return false;' in response.text
    assert 'if (!currentSettings.keepHistory) return { records: [], error: false };' in response.text
    assert 'slice(0, currentSettings.maxHistoryItems)' in response.text


def test_root_uses_theme_tokens_for_light_and_dark_surfaces():
    response = client.get("/")
    style = response.text.split("<style>", 1)[1].split("</style>", 1)[0]

    assert response.status_code == 200
    assert "--brand-background" in style
    assert "--brand-foreground" in style
    assert "--card-background" in style
    assert "--dropzone-background" in style
    assert "--status-success-background" in style
    assert "--verification-background" in style
    assert 'body[data-theme="dark"]' in style
    assert '@media (prefers-color-scheme: dark)' in style
    assert '.brand-mark' in style and 'color: var(--brand-foreground);' in style
    assert 'background: var(--card-background);' in style
    assert 'background: var(--dropzone-background);' in style
    assert 'background: var(--preview-background);' in style
    assert 'color: white;' not in style


def test_root_theme_settings_apply_and_persist_without_backend_state():
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="settingsTheme"' in response.text
    assert 'function applySettings(settings)' in response.text
    assert 'document.body.dataset.theme = settings.theme;' in response.text
    assert 'localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(normalized));' in response.text
    assert 'settingsThemeInput,' in response.text
    assert 'settingsMotionInput' in response.text
    assert 'body.motion-reduced *' in response.text


def test_root_has_a_local_preview_for_supported_image_files():
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="filePreview"' in response.text
    assert 'id="filePreviewImage"' in response.text
    assert 'id="filePreviewFallback"' in response.text
    assert "URL.createObjectURL(file)" in response.text
    assert "URL.revokeObjectURL(previewUrl)" in response.text
    assert "Önizleme kullanılamıyor" in response.text
    assert "filePreviewImage.onerror" in response.text


def test_root_keeps_sidebar_interactive_without_inert_support():
    response = client.get("/")

    assert response.status_code == 200
    assert "function setOptionalInert(element, isInert)" in response.text
    assert 'if ("inert" in element)' in response.text
    assert "setOptionalInert(sidebar, !isOpen)" in response.text
    assert "setOptionalInert(mainContent, isOpen)" in response.text
    assert 'openSidebarButton.addEventListener("click", () => setSidebarOpen(true));' in response.text
    assert 'sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));' in response.text
    assert 'event.key === "Escape"' in response.text


def test_root_escapes_javascript_newlines_in_rendered_html():
    response = client.get("/")

    assert response.status_code == 200
    assert 'window.confirm("Temizleme geçmişi silinsin mi?\\n\\nBu işlem geçmiş kayıtlarını cihazdan kaldırır.")' in response.text
    assert 'window.confirm("Temizleme geçmişi silinsin mi?\n\nBu işlem geçmiş kayıtlarını cihazdan kaldırır.")' not in response.text


def test_root_inline_dom_references_match_rendered_html_elements():
    response = client.get("/")
    script = response.text.split("<script>", 1)[1].split("</script>", 1)[0]
    referenced_ids = set(re.findall(r'getElementById\("([^"]+)"\)', script))
    rendered_ids = set(re.findall(r'\bid="([^"]+)"', response.text))

    assert referenced_ids - rendered_ids <= {"downloadLink", "reportLink"}
    assert '<main class="page">' in response.text
    assert 'class="report-section verification-card"' in response.text


def test_root_constrains_long_file_names_inside_the_file_card():
    response = client.get("/")
    css = response.text

    assert response.status_code == 200
    assert re.search(
        r"\.file-details\s*\{[^}]*min-width:\s*0;[^}]*flex:\s*1 1 auto;",
        css,
        re.DOTALL,
    )
    assert re.search(
        r"\.file-name\s*\{[^}]*display:\s*block;[^}]*min-width:\s*0;[^}]*"
        r"max-width:\s*100%;[^}]*overflow:\s*hidden;[^}]*"
        r"text-overflow:\s*ellipsis;[^}]*white-space:\s*nowrap;",
        css,
        re.DOTALL,
    )


def test_root_shows_no_metadata_message():
    response = client.get("/")

    assert response.status_code == 200
    assert "No metadata found" in response.text


def test_root_hides_no_metadata_message_initially():
    response = client.get("/")

    assert 'id="noMetadata"' in response.text
    assert 'style="display: none"' in response.text


def test_root_handles_no_metadata():
    response = client.get("/")

    assert "noMetadata" in response.text
    assert "Object.keys(data).length === 0" in response.text

def test_inspect_file():
    files = {
        "file": ("test.txt", b"hello", "text/plain")
    }

    response = client.post("/inspect", files=files)
    assert response.status_code == 400

def test_inspect_exif():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()
    exif = im.getexif()
    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "Make":
            make_tag = tag_id
            exif[make_tag] =  "Canon"

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)
    assert response.json()["Make"] == "Canon"

def test_inspect_camera_metadata():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "Make":
            exif[tag_id] = "Canon"
        elif tag_name == "Model":
            exif[tag_id] = "EOS 90D"

    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response =  client.post("/inspect", files=files)

    assert response.status_code == 200

    assert response.json()["Make"] == "Canon"
    assert response.json()["Model"] == "EOS 90D"


def test_inspect_no_exif():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()
    im.save(buffer, format="JPEG")
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)
    assert response.status_code == 200
    assert response.json() == {}


def test_inspect_multiple_exif():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()
    exif= im.getexif()
    for tag_id, tag_name in  ExifTags.TAGS.items():
        if tag_name == "Model":
            model_tag = tag_id
            exif[model_tag] = "EOS 90D"
        if tag_name == "Make":
            make_tag = tag_id
            exif[make_tag] = "Canon"

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["Model"] == "EOS 90D"
    assert response.json()["Make"] == "Canon"


def test_root_clears_previous_metadata():
    response = client.get("/")
    assert "metadata.innerHTML = ''" in response.text


def test_inspect_ifdraional_exif():
    im = Image.new(mode="RGB", size=(200,200,))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "ExposureTime":
            exif[tag_id] = IFDRational(1,200)
            break

        im.save(buffer, format="JPEG", exif=exif.tobytes())
        files = {
            "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
        }
        response = client.post("/inspect", files=files)

        print(response.status_code)
        print(response.json())

        assert response.status_code == 200

def test_inspect_image_metadata():
    im = Image.new(mode="RGB", size=(200,200))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "ImageWidth":
            exif[tag_id] = 1920
        elif tag_name == "ImageLength":
            exif[tag_id] = 1080
        elif tag_name == "Orientation":
            exif[tag_id] = 1

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)

    assert response.status_code == 200

    assert response.json()["ImageWidth"] == 1920
    assert response.json()["ImageLength"] == 1080
    assert response.json()["Orientation"] == 1

def test_inspect_software_metadata():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "Software":
            exif[tag_id] = "BlackClean Test"

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)

    assert response.status_code == 200

    assert response.json()["Software"] == "BlackClean Test"


def test_inspect_datetime_original():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in  ExifTags.TAGS.items():
        if tag_name == "DateTimeOriginal":
            exif[tag_id] = "2026:10:15 15:00:00"

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)

    assert response.status_code == 200

    assert response.json()["DateTimeOriginal"] == "2026:10:15 15:00:00"


def test_inspect_exposure_time():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "ExposureTime":
            exif_ifd[tag_id] = (1,200)
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["ExposureTime"] == [1,200]


def test_inspect_fnumber():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "FNumber":
            exif_ifd[tag_id] = (18, 10)
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["FNumber"] == [18, 10]


def test_inspect_iso_speed_rating():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "ISOSpeedRatings":
            exif_ifd[tag_id] = 400
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd

    im.save(buffer, format="JPEG", exif=exif.tobytes())
    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }
    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["ISOSpeedRatings"] == 400


def test_inspect_focal_length():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "FocalLength":
            exif_ifd[tag_id] = (50, 1)
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["FocalLength"] == [50, 1]


def test_inspect_lens_model():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "LensModel":
            exif_ifd[tag_id] = "EF50mm f/1.8 STM"
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["LensModel"] == "EF50mm f/1.8 STM"


def test_inspect_exposure_bias_value():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "ExposureBiasValue":
            exif_ifd[tag_id] = (-1, 3)
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["ExposureBiasValue"] == [-1, 3]


def test_inspect_flash():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "Flash":
            exif_ifd[tag_id] = 1
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["Flash"] == 1


def test_inspect_datetime():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "DateTime":
            exif[tag_id] = "2026:10:05 12:00:00"
            break

    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["DateTime"] == "2026:10:05 12:00:00"


def test_inspect_datetime_digitized():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "DateTimeDigitized":
            exif_ifd[tag_id] = "2026:10:05 12:00:00"
            break

    exif[ExifTags.Base.ExifOffset] = exif_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["DateTimeDigitized"] == "2026:10:05 12:00:00"


def test_inspect_image_description():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()

    for tag_id, tag_name in ExifTags.TAGS.items():
        if tag_name == "ImageDescription":
            exif[tag_id] = "BlackClean test image"
            break

    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["ImageDescription"] == "BlackClean test image"


def test_inspect_gps_latitude():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)

    gps_ifd[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps_ifd[ExifTags.GPS.GPSLatitude] = [IFDRational(38, 1), IFDRational(25, 1), IFDRational(30, 1)]

    exif[ExifTags.Base.GPSInfo] = gps_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["GPSLatitudeRef"] == "N"
    assert response.json()["GPSLatitude"] == [[38, 1], [25, 1], [30, 1]]


def test_inspect_gps_longitude():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)

    gps_ifd[ExifTags.GPS.GPSLongitudeRef] = "E"
    gps_ifd[ExifTags.GPS.GPSLongitude] = [IFDRational(27, 1), IFDRational(8, 1), IFDRational(15, 1)]

    exif[ExifTags.Base.GPSInfo] = gps_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["GPSLongitudeRef"] == "E"
    assert response.json()["GPSLongitude"] == [[27, 1], [8, 1], [15, 1]]


def test_inspect_gps_altitude():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)

    gps_ifd[ExifTags.GPS.GPSAltitudeRef] = 0
    gps_ifd[ExifTags.GPS.GPSAltitude] = (100, 1)

    exif[ExifTags.Base.GPSInfo] = gps_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["GPSAltitudeRef"] == 0
    assert response.json()["GPSAltitude"] == [100, 1]


def test_inspect_gps_latitude_ref():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)

    gps_ifd[ExifTags.GPS.GPSLatitudeRef] = "S"

    exif[ExifTags.Base.GPSInfo] = gps_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["GPSLatitudeRef"] == "S"


def test_inspect_gps_longitude_ref():
    im = Image.new(mode="RGB", size=(200, 200))
    buffer = BytesIO()

    exif = im.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)

    gps_ifd[ExifTags.GPS.GPSLongitudeRef] = "W"

    exif[ExifTags.Base.GPSInfo] = gps_ifd
    im.save(buffer, format="JPEG", exif=exif.tobytes())

    files = {
        "file": ("test.jpeg", buffer.getvalue(), "image/jpeg")
    }

    response = client.post("/inspect", files=files)

    assert response.status_code == 200
    assert response.json()["GPSLongitudeRef"] == "W"
