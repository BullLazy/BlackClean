# BlackClean

BlackClean, yüklenen görsellerin metadata bilgisini temizleyip doğrulanmış temiz dosyayı indirme olarak döndüren privacy-first bir FastAPI uygulamasıdır.

## API

### `POST /clean`

İstek `multipart/form-data` içinde `file` alanını içermelidir. İsteğe bağlı
`anonymize_filename` alanı filename anonimleştirmesini kontrol eder ve
varsayılan değeri `true`'dur.

Başarılı yanıt:

- Temizlenmiş gerçek dosya gövdesi döner; metadata JSON’u dönmez.
- Uygun `Content-Type` kullanılır.
- Varsayılan olarak `clean_<random-id>.<extension>` biçiminde anonim bir download adı ve `Content-Disposition: attachment` gönderilir.
- `anonymize_filename=false` verilirse orijinal filename'in güvenli ASCII sanitize edilmiş gövdesi korunur; path traversal ve kontrol karakterleri yine korunmaz.
- Dosya, yanıt verilmeden önce yeniden açılır ve metadata temizliği doğrulanır.

Hata durumları:

- `400`: boş, bozuk veya geçersiz görsel
- `413`: 10 MiB üzerindeki upload
- `415`: desteklenmeyen format
- `500`: temizlenmiş dosya doğrulanamazsa

Dosya adı ve MIME type kararın kaynağı değildir; format dosyanın gerçek içeriğinden tespit edilir.

### `POST /inspect`

Mevcut metadata görüntüleme endpoint’idir. Development, debugging ve regression testleri için korunmuştur; ürünün ana workflow’u değildir.

### `GET /`

Dosya temizleme arayüzünü, yerel Cleaning History listesini ve Privacy Report detaylarını döndürür.

## Desteklenen formatlar

- **JPEG**: EXIF, GPS, XMP/IPTC/ICC içeren APP blokları ve JPEG comment blokları kaldırılır. JPEG scan verisi yeniden encode edilmez.
- **PNG**: EXIF, text, XMP, ICC, resolution ve diğer ancillary metadata chunk’ları kaldırılır. PNG kayıpsız olarak yeniden oluşturulur.
- **WebP**: EXIF, XMP ve ICCP RIFF chunk’ları ile VP8X metadata bayrakları kaldırılır. Görüntü payload’ı yeniden encode edilmez.
- **TIFF**: görüntü yeniden açılıp metadata tag’leri taşınmadan TIFF olarak kaydedilir; yapısal görüntü tag’leri korunur.
- **AVIF**: EXIF, XMP ve ICC metadata’sı kaldırılır; lossless olarak yeniden yazılır.
- **GIF**: yorum ve desteklenmeyen extension metadata’sı kaldırılır; animasyon kareleri korunur.
- **BMP**: metadata temizlenerek BMP olarak yeniden yazılır.
- **TGA**: metadata temizlenerek TGA olarak yeniden yazılır.
- **ICO**: icon kaynakları korunarak gömülü EXIF ve benzeri metadata kaldırılır.
- **ICNS**: okunabilir icon kaynakları korunarak gömülü metadata kaldırılır.
- **MP3**: ID3v1/ID3v2, APEv2 ve tanınan Lyrics3 etiketleri kaldırılır; ses frame'leri yeniden encode edilmez.

HEIC/HEIF ve PDF için güvenilir cleaning yöntemi mevcut dependency setinde bulunmadığından desteklenmez ve `415` döndürülür.

PNG ve TIFF çok sayfalı/animasyonlu içerikleri desteklenmez; bu içerikler metadata temizlenmeden reddedilir.

## Privacy ve dosya lifecycle’ı

Pipeline:

```text
upload → validate → detect → clean → reopen → verify → download
```

- Upload boyutu 10 MiB ile sınırlıdır.
- Filename anonymization varsayılan olarak açıktır; random ID içerik veya orijinal filename'den türetilmez.
- Kullanıcı dosyaları persistent storage’a yazılmaz; işlem bellekte gerçekleştirilir.
- `UploadFile`, okuma tamamlandıktan sonra kapatılır.
- Orijinal metadata içeren dosya hiçbir başarılı response’ta döndürülmez.
- Filename hiçbir zaman filesystem path’i olarak kullanılmaz; anonim download adı canonical, content-based extension kullanır ve OFF modunda da sanitize edilir.
- Dosya içeriği ve metadata loglanmaz.
- Temizleme doğrulaması başarısız olursa dosya download edilmez.

## Cleaning History ve Privacy Report

- Geçmiş yalnızca kullanılan tarayıcı cihazının local storage alanında tutulur; sunucuya history kaydı yazılmaz.
- History kaydı dosya içeriği, thumbnail, original filename, GPS koordinatı veya ham metadata değeri içermez.
- Her başarılı temizleme için anonim filename, format, boyut, zaman, tespit edilen metadata kategorileri, gerçek cleaning operasyonları ve verification sonucu tutulur.
- History en fazla son 50 kaydı saklar ve kullanıcı tarafından onayla silinebilir.
- Privacy Report yalnızca “ne bulundu → ne temizlendi → ne doğrulandı” akışını gösterir; ham metadata viewer değildir.

## Bilinen sınırlamalar

- Uygulama görsel formatları ile MP3 ses formatını destekler; video, diğer ses container'ları ve PDF temizleme desteği yoktur.
- TIFF yeniden yazıldığı için compression/byte-level dosya düzeni korunmaz; görüntü boyutu, mode ve piksel içeriği korunması test edilir.
- PNG/TIFF çok sayfalı içerikleri bilinçli olarak reddedilir.
- `/inspect` yalnızca development/debugging uyumluluğu için korunur; ana UI cleaning workflow’u ve Privacy Report ile bağlıdır.

## Testler

Bağımlılıkları uv ortamında kurduktan sonra:

```bash
uv run pytest -q
```

## Render deployment

Repository kökünde bulunan `render.yaml`, BlackClean'i Frankfurt bölgesinde
tek bir Render Web Service olarak tanımlar. Render, `uv.lock` dosyasını
kullanarak bağımlılıkları şu komutla kurar:

```bash
uv sync --locked --no-dev
```

Production start command:

```bash
uv run uvicorn blackclean.main:app --host 0.0.0.0 --port $PORT
```

Render'ın Python runtime'ı `.python-version` içindeki Python 3.14 sürümünü
kullanır. Sağlık kontrolü mevcut `GET /` endpoint'ine yapılır; uygulamada
ayrı bir `/healthz` endpoint'i bulunmadığı için yeni bir endpoint eklenmemiştir.

Uygulama dosyaları işlem sırasında bellekte tutar ve kalıcı dosya depolaması
kullanmaz. Upload sınırı 10 MiB'dir. Cleaning History tarayıcının yerel
depolamasında tutulur; Render'a dosya içeriği, ham metadata veya history
kaydı gönderilmez.
