# emretool

PyQt6 ile geliştirilen, hafif ve hızlı bir **developer toolbox** masaüstü uygulaması.
DBeaver + RedisInsight + Kibana'nın temel işlevlerini tek uygulamada birleştirmeyi hedefler.

## Modüller

- **Database** — MySQL bağlantısı (SSH tünel destekli), schema görüntüleme, read-only SQL, schema kopyalama
- **Redis** — key tarama, pattern arama, value görüntüleme/edit, TTL
- **Elasticsearch** — cluster bağlantısı, index/mapping görüntüleme, query DSL

> Mimari plugin tabanlıdır; ileride yeni modüller kolayca eklenebilir.

## Mimari

```
app/
  main.py              # giriş noktası
  config.py            # sabitler
  ui/                  # sunum katmanı (PyQt6)
    main_window.py
    sidebar.py
    theme.py           # dark/light tema (QSS)
    base_view.py
    widgets/
    views/             # db_view, redis_view, elastic_view
  core/                # iş mantığı / data access
    container.py       # dependency injection
    module_registry.py # plugin kaydı
    base_agent.py
    db_agent.py, redis_agent.py, elastic_agent.py
  services/            # storage (SQLite), secrets (keyring), connection_manager, worker
  models/              # connection_profile vb.
  utils/
```

Katmanlar ayrıktır: **UI ↔ core (agent) ↔ services**. UI donmaması için IO işleri
`services/worker.py` üzerinden arka plan thread'lerinde çalışır. Şifreler keyring'de
saklanır (asla plaintext değil); bağlantı profilleri lokal SQLite'ta tutulur.

## Geliştirme

```bash
# Sanal ortam + bağımlılıklar
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Çalıştır
python -m app.main
```

## Gereksinimler

- Python 3.10+ (geliştirme 3.12 ile)
- PyQt6
