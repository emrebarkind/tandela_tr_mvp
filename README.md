# Klinia

Klinia, Türkçe diş hekimliği görüşmelerini ve periodontal dikteyi incelemeye
hazır klinik dokümantasyon taslaklarına dönüştüren, güvenlik öncelikli bir web
uygulamasıdır. Yapay zeka yalnızca kanıtlı taslak üretir; klinik karar, düzeltme,
onay ve export her zaman hekimde kalır.

## Temel özellikler

- **Voice-to-documentation:** Ses veya konuşmacı etiketli transkriptten kaynak
  alıntıları korunmuş klinik not taslağı üretir.
- **Dental chart:** Hekimin belirttiği FDI diş numarası, yüzey ve kondisyonları
  görsel diş şemasına taşır.
- **TDB kod eşleştirme:** İşlemleri versiyonlanmış TDB kod veritabanındaki
  adaylarla eşleştirir ve eksik dokümantasyonu checklist olarak gösterir.
- **Periodontal charting:** Cep derinliği, kanama, plak, gingival margin,
  attachment level, mobilite ve furkasyonu diş/site bazlı yapılandırır.
- **Human-in-the-loop review:** Konuşmacı belirsizliğini, provenance bilgisini
  ve kontrol edilmesi gereken maddeleri görünür tutar; onaysız export yapmaz.

## Güvenlik yaklaşımı

Klinia'nın pipeline'ı belirsiz bilgiyi tamamlamaz, hasta ifadesini hekim bulgusu
olarak kullanmaz ve epistemik belirsizliği kesinleştirmez. Kod adayları LLM
tarafından üretilmez; kapalı TDB veri kaynağından gelir. Tüm çıktılar hekim
onayına kadar **taslak** durumundadır. Ayrıntılı kurallar için [AGENTS.md](AGENTS.md)
ve ürün kapsamı için [docs/product-lines.md](docs/product-lines.md) dosyalarına
bakın.

## Teknik yapı

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, shadcn/ui
- **Backend:** FastAPI, Pydantic, SQLAlchemy
- **Veri:** PostgreSQL; lokal geliştirmede SQLite fallback
- **AI ve ses:** Gemini tabanlı klinik pipeline, provider adapter'ı arkasında
  Deepgram/Gemini Audio desteği

```text
Ses / transkript -> konuşmacı rolleri -> klinik facts -> not + dental chart
-> TDB kod eşleştirme -> hekim inceleme/onay -> export
```

## Lokal kurulum

Gereksinimler: Python 3.10+, Node.js 20+ ve pnpm.

```bash
git clone https://github.com/emrebarkind/klinia_mvp.git
cd klinia_mvp

python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
pnpm install
cd ..

cp backend/.env.example backend/.env
```

`backend/.env` içinde en az `GEMINI_API_KEY` değerini ve kullanacağınız ses
provider'ını yapılandırın. Gerçek anahtarları repoya eklemeyin.

Uygulamayı tek komutla başlatın:

```bash
./scripts/demo.sh
```

Ardından [http://127.0.0.1:3000](http://127.0.0.1:3000) adresini açın.

İki servisi ayrı çalıştırmak için:

```bash
# Terminal 1
cd backend
python3 -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend
pnpm dev
```

## Doğrulama

```bash
cd backend && python3 -m pytest tests/ -q
cd frontend && pnpm run typecheck
```

Golden-set eval'leri gerçek model çağrısı yapar ve geçerli provider anahtarları
gerektirir. Senaryolar [docs/golden-set.md](docs/golden-set.md) içinde tutulur.

## Durum

Klinia aktif geliştirme aşamasındaki bir demo/MVP'dir; klinik kullanım öncesi
kurumsal güvenlik, uyum ve klinik doğrulama adımları tamamlanmalıdır.
