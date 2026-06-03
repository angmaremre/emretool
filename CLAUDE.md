# CLAUDE.md — emretool

PyQt6 ile yazılmış "developer toolbox" masaüstü uygulaması. 3 modül: **Database (MySQL)**,
**Redis**, **Elasticsearch**. Plugin tabanlı, katmanlı mimari.

## Çalıştırma & test

```bash
# Çalıştır (proje kökünden)
.venv/bin/python -m app.main

# GUI açmadan hızlı doğrulama (smoke test / screenshot) — pencere açmadan render eder:
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "<kod>"     # widget.grab().save('/tmp/x.png')

# Bağımlılık ekleme (requirements.txt PostToolUse hook ile OTOMATİK güncellenir)
.venv/bin/python -m pip install <paket>
```

- Python: `.venv/` (3.12). Her zaman `.venv/bin/python` kullan, global python değil.
- Test için gerçek DB/Redis/ES gerekebilir; yoksa **stub agent** ile UI'ı offscreen render edip doğrula.
- **Testlerde gerçek uygulama DB'sine yazma** (`~/Library/Application Support/emretool/emretool.db`) —
  `ServiceContainer(storage=Storage(tempfile.mktemp(suffix='.db')))` ile geçici DB kullan.

## Mimari (katmanlar kesin ayrık)

```
app/
  main.py              # giriş: QApplication + ServiceContainer + ThemeManager + ModuleRegistry
  config.py            # sabitler
  core/                # İŞ MANTIĞI + DATA ACCESS (UI'dan bağımsız)
    container.py       # ServiceContainer (DI): storage, connections, threadpool, theme_manager
    module_registry.py # ModuleDescriptor + ModuleRegistry (plugin kaydı)
    base_agent.py
    db_agent.py        # MySQLAgent + SSHConfig/MySQLConfig + open_tunnel() + read-only doğrulama
    redis_agent.py     # RedisAgent + RedisConfig
    elastic_agent.py   # ElasticAgent + ElasticConfig
    schema_copy.py     # SchemaCopier (mysqldump|mysql; Python fallback)
  services/            # storage.py (SQLite), secrets.py (keyring), connection_manager.py, worker.py
  ui/
    main_window.py, sidebar.py, theme.py (dark/light QSS), base_view.py, widgets/
    views/
      db_view.py, redis_view.py, elastic_view.py     # modül ana görünümleri (panel + sekmeler)
      db/, redis/, elastic/                           # her modülün alt parçaları (aşağıdaki desen)
  models/connection_profile.py
  modules.py           # register_builtin_modules() — yeni modül burada kaydedilir
```

## Modül deseni (HER modül aynı yapıda)

`ui/views/<modül>/` altında 4 dosya:
- `profile_config.py` — `MODULE` sabiti + `build_<x>_config(profile)` (keyring'den şifre çeker)
- `connection_dialog.py` — bağlantı formu + SSH grubu + "Bağlantıyı test et"
- `connection_panel.py` — kayıtlı profil listesi (Yeni/Bağlan/Düzenle/Sil), `connectRequested` sinyali
- `connection_tab.py` — asıl çalışma alanı (çoklu sekme ana view'de açılır)

**Yeni modül eklemek:** agent'ı `core/`, UI parçalarını `ui/views/<modül>/`, ana view'i
`ui/views/<modül>_view.py` yaz; `app/modules.py`'de bir `ModuleDescriptor` ile kaydet. Sidebar otomatik gösterir.

## Konvansiyonlar / dikkat edilecekler

- **Thread-safety:** Agent'lar `threading.RLock` ile tüm bağlantı erişimini seri yapar.
  pymysql/redis bağlantısı thread-safe DEĞİL; eşzamanlı kullanım `(0,'')` benzeri hata verir. Kilidi koru.
- **IO daima arka planda:** UI donmaması için `services/worker.run_in_background(pool, fn, on_result=, on_error=, on_finished=)` kullan. Sonuç callback'leri UI thread'inde çalışır (sinyal).
- **Şifreler:** asla SQLite/log'a yazılmaz; `services/secrets.py` (keyring) üzerinden. Profiller SQLite'ta.
- **DB read-only:** `MySQLAgent.run_query` yalnızca SELECT/SHOW/DESCRIBE/EXPLAIN/WITH kabul eder
  (`is_read_only`). Yazma gereken tek yer schema kopyalama (ayrı yazılabilir bağlantı).
- **Tema:** açık (light) varsayılan. Seçim renkleri koyu accent + beyaz (açık temada okunabilirlik). QSS `ui/theme.py`.
- **Dil:** UI metinleri ve commit mesajları Türkçe.

## Git
- `main` → origin (github.com/angmaremre/emretool). Commit/push yalnızca kullanıcı isteyince.
