# T02.08 – ThinkPad-Geschwindigkeit (18.10.2026)

**Nur Geschwindigkeit, kein i3-Nachweis, kein Beleg für das 3,3-GB-Gate** (Entscheidung Damiano, 18.10.2026).

- Gerät: DESKTOP-JTA4OIM (Lenovo ThinkPad T14 Gen 1), AMD Ryzen 5 PRO 4650U (6 Kerne / 12 Threads), 24938991616 B RAM, Windows, Python 3.12.10, llama-cpp-python 0.3.36 (CPU).
- Quelle: Code-Stand `f4cb380a` (nur zum Vergleich, die Messung nutzt llama-cpp-python direkt und nicht den App-Installer). Die App-Installation des Nutzers wurde nicht verändert.
- Modelle: `qwen3-8b-Q3_K_M.gguf` (aus der App-Installation, Katalog-SHA-256 `81894ed9…0e77`) und `Qwen3.5-4B-Q2_K_XL.gguf` (direkt von `ISTA-DASLab/Qwen3.5-4B-GGUF-GSQ` @ `3fd6825d…`, 1940825248 B, SHA-256 `b7d9ec51…cb5a` geprüft = Katalog).
- Ablauf `kk_speedbench.py`: n_ctx 2048, n_threads = physische Kerne (6), fester deutscher CV-Prompt, max_tokens 128, temperature 0, seed 1, 3 Läufe; Spitzen-RSS = `peak_wset` des Prozesses.
- Das Skript liegt hier byte-identisch so, wie es lief (SHA-256 in `SHA256SUMS`). ruff meldet darin 4 Stil-Funde (I001, 2× BLE001, SIM115); bewusst nicht korrigiert, damit der Hash zum Lauf passt.
