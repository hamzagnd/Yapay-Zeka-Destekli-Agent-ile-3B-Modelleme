# Yapay Zeka Destekli Agent ile 3B Modelleme

Blender sahnelerinde yapay zeka destekli iç mekân tasarımı oluşturan çok ajanlı bir sistemdir. Proje; doğal dilde verilen tasarım isteğini analiz eder, yerel asset kataloğundan uygun modelleri seçer, yerleşim planını hesaplar ve Blender eklentisi üzerinden sahneyi otomatik olarak oluşturur.

## Özellikler

- Gemini veya Claude ile çalışan çok ajanlı iç mimari ekibi
- Oda ölçüsü, kullanım amacı ve stil analizi
- Yerel `.blend` asset kataloğunda semantik arama
- Mobilya seçimi ve oda sınırlarına uygun otomatik yerleşim
- Blender ile HTTP tabanlı çift yönlü iletişim
- Tarayıcı tabanlı tasarım ve asset yönetim arayüzü
- Sketchfab üzerinde model arama ve indirilebilir modelleri kataloğa ekleme
- ZIP veya `.blend` dosyalarını otomatik kategorize ederek asset kütüphanesine alma
- MCP üzerinden katalog sorgulama ve Blender'a model aktarma

## Sistem Mimarisi

```text
Kullanıcı / Web Arayüzü
          |
          v
FastAPI + Agno Agent Ekibi (:8080)
          |
          +-- Space Analyst
          +-- Furniture Selector
          +-- Layout Designer
          +-- Blender Executor
          |
          v
Blender Asset Library Eklentisi (:8766)
          |
          v
Blender Sahnesi
```

Agent ekibi iki temel akışı destekler:

1. **Sıfırdan oda oluşturma:** Oda geometrisi oluşturulur, ardından seçilen mobilyalar yerleştirilir.
2. **Hazır ev modeli kullanma:** Katalogdaki ev modeli sahneye alınır ve mobilyalar seçilen odanın sınırları içine yerleştirilir.

## Gereksinimler

- Python 3.10 veya üzeri
- Blender 4.5 veya uyumlu daha yeni bir sürüm
- Gemini kullanımı için `GOOGLE_API_KEY`
- Claude kullanımı için `ANTHROPIC_API_KEY`
- Sketchfab indirmeleri için isteğe bağlı `SKETCHFAB_TOKEN`

## Kurulum

Depoyu klonlayın ve Python paketini kurun:

```powershell
git clone <repo-url>
cd Yapay-Zeka-Destekli-Agent-ile-3B-Modelleme

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".\asset-library-mcp"
```

### Ortam Değişkenleri

`asset-library-mcp` klasöründe `.env` dosyası oluşturun:

```env
GOOGLE_API_KEY=your_google_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
SKETCHFAB_TOKEN=your_sketchfab_token

# İsteğe bağlı: Catalog.json dosyasının bulunduğu klasör
ASSET_LIBRARY_DIR=C:\path\to\Yapay-Zeka-Destekli-Agent-ile-3B-Modelleme
```

Yalnızca kullanacağınız model sağlayıcısının API anahtarı zorunludur. `ASSET_LIBRARY_DIR` belirtilmezse proje kökü otomatik olarak kullanılır.

## Blender Eklentisi

Önce eklenti ZIP dosyasını üretin:

```powershell
cd asset-library-mcp
python make_addon_zip.py
```

Ardından Blender içinde:

1. `Edit > Preferences > Add-ons` bölümünü açın.
2. `Install from Disk` ile `asset_library_mcp_addon.zip` dosyasını seçin.
3. **Asset Library MCP Bridge** eklentisini etkinleştirin.
4. 3D görünümde `N` tuşuna basın.
5. **Asset Library** sekmesinden **Start Server** düğmesine tıklayın.

Eklenti varsayılan olarak `http://localhost:8766` adresinde çalışır.

## Web Arayüzünü Çalıştırma

Blender eklenti sunucusu çalışırken yeni bir terminal açın:

```powershell
cd asset-library-mcp
python run_team.py --serve
```

Kullanılabilir adresler:

- Web arayüzü: <http://localhost:8080>
- Asset yöneticisi: <http://localhost:8080/asset-manager>
- API dokümantasyonu: <http://localhost:8080/docs>
- Sağlık kontrolü: <http://localhost:8080/health>

## Komut Satırı Kullanımı

Gemini ile:

```powershell
cd asset-library-mcp
python run_team.py "5x4 metre endüstriyel bir çalışma odası oluştur"
```

Claude ile:

```powershell
python run_team.py "6x4 metre modern bir salon tasarla" --llm claude
```

Blender eklentisi çalışmıyorsa ajanlar sahneye model aktaramaz.

## Asset Kütüphanesi

Katalog verileri repo kökündeki `Catalog.json` dosyasında tutulur. Asset dosya yolları bu klasöre göre çözülür.

Bir ZIP veya `.blend` dosyasını kataloğa eklemek için:

```powershell
python add_asset.py .\zip\model.zip
```

Tam otomatik kullanım:

```powershell
python add_asset.py .\zip\model.zip --quick --name "Office Chair" --id "office_chair_01"
```

LLM tabanlı sınıflandırmayı kapatmak için:

```powershell
python add_asset.py .\model.blend --no-llm
```

Otomatik kategorilendirme; model ölçülerini, kategorisini, alt kategorisini, stilini, uygun oda türlerini ve modelin baktığı ekseni tahmin eder.

## MCP Sunucusu

MCP sunucusu standart giriş/çıkış üzerinden çalışır:

```powershell
cd asset-library-mcp
python -m mcp_server.server
```

Kurulumdan sonra `asset-library-mcp` komutu da aynı sunucuyu başlatır. MCP araçlarının Blender'a erişebilmesi için Blender eklentisinin `8766` portunda çalışıyor olması gerekir.

Örnek MCP istemci yapılandırması:

```json
{
  "mcpServers": {
    "asset-library": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:\\path\\to\\repo\\asset-library-mcp",
      "env": {
        "ASSET_LIBRARY_DIR": "C:\\path\\to\\repo"
      }
    }
  }
}
```

## Proje Yapısı

```text
.
|-- Catalog.json                 # Asset kataloğu
|-- taxonomy.json                # Kategori ve etiket taksonomisi
|-- add_asset.py                 # Kataloğa model ekleme aracı
|-- auto_categorize.py           # Otomatik model analizi
|-- recategorize_existing.py     # Mevcut assetleri yeniden sınıflandırma
|-- schema/
|   `-- catalog_schema.json
`-- asset-library-mcp/
    |-- agents/                  # Agno ajanları ve FastAPI uygulaması
    |-- blender_addon/           # Blender HTTP köprü eklentisi
    |-- mcp_server/              # MCP sunucusu ve araçları
    |-- ui/                      # Web arayüzü
    |-- run_team.py              # CLI ve API başlangıç noktası
    `-- pyproject.toml
```

## Sorun Giderme

### Blender bağlantısı kurulamıyor

- Blender eklentisinin etkin olduğundan emin olun.
- 3D görünümde `N > Asset Library > Start Server` adımını uygulayın.
- `8766` portunun başka bir uygulama tarafından kullanılmadığını kontrol edin.

### Web arayüzü açılmıyor

- `python run_team.py --serve` komutunun çalıştığını kontrol edin.
- <http://localhost:8080/health> adresini açın.
- `8080` portunun kullanılabilir olduğundan emin olun.

### Model sağlayıcısı görünmüyor

- `.env` dosyasının `asset-library-mcp` klasöründe olduğunu kontrol edin.
- Gemini için `GOOGLE_API_KEY`, Claude için `ANTHROPIC_API_KEY` tanımlayın.
- Sunucuyu ortam değişkenini değiştirdikten sonra yeniden başlatın.

### Katalog bulunamıyor

- Repo kökünde geçerli bir `Catalog.json` bulunduğunu kontrol edin.
- Kütüphane başka bir konumdaysa `ASSET_LIBRARY_DIR` değişkenini o klasöre ayarlayın.

## Geliştirme

Geliştirme bağımlılıklarını yüklemek için:

```powershell
python -m pip install -e ".\asset-library-mcp[dev]"
```

Temel kontroller:

```powershell
pytest
ruff check .
```

