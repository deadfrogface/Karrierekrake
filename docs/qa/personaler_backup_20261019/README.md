# Backup Personaler 2026-10-19 (DRAFT – nicht mergen)

Sicherung lokaler, bisher nur auf der Box liegender Stände auf Damianos Anweisung (Teamauftrag 19.10.2026).
**Dieser Stand darf nicht gemergt werden.** Nur synthetische Daten (SMOKE_DE_EN_10-Fixtures aus `tests/fixtures/cv_corpus/`,
Kontakte mit example.org/.net/.com bzw. Fixture-Telefonnummern, die bereits in `docs/qa/pr144_model_compare_2026-10-18/` im Repo stehen).

## Ausgangslage (geprüft 2026-10-19, ca. 13:55 MESZ)

- Worktree `/workspace/kk-144-personaler-gold`, Branch `personaler/pr144-gold-native` @ `cf0b1287`.
- `git fetch origin cursor/roadmap-execution-20261012-d85b` → #144-Head `7d5243d0`. `git log origin/…d85b..HEAD`: **leer** – alle lokalen Commits (bis `cf0b1287`) sind in #144 enthalten.
- `git status`: **sauber**, keine uncommitteten oder untracked Dateien.
- Zweiter Worktree `/workspace/km_main` (`personaler/pr144-gsq4b-vs-q4km-compare` @ `ffa483c3`): ebenfalls keine Commits außerhalb #144, sauber.
- Einziger lokal-only Bestand: `/workspace/thinkpad_extracts_2026-10-18/` (ThinkPad-Lauf Q4_K_M, Code-Stand `47e8f83b`).

## Inhalt

- `q4_k_m/` – Q4_K_M-Referenzextrakte der 10 SMOKE-CVs (`<CV>.json`, `<CV>.child_raw.json`), `logs/`, `RUN.log`, `run_meta.json`,
  `SYSINFO.txt` (UTF-16, Hardware-Infos ThinkPad), `pip_freeze_venv_llama0335.txt`, `HR_URTEIL_ENTWURF.md` (Entwurf HR-Urteil CV-Extrakt).
- `harness/` – Treiberskripte des Laufs (`kk_extract_run.py`, `kk_extract_child.py`, `setup_extract.ps1`, `stop_letters.ps1`).

## Redaktion (einzige Änderung gegenüber dem Original)

Lokale Windows-Benutzerpfade `C:\Users\<Konto>\` (auch JSON-escaped) → `%USERPROFILE%\`, Hostname des ThinkPads → `<ThinkPad-Host>`.
Sonst bytegleich. Die Harness-Skripte sind dadurch nicht unverändert lauffähig (Pfad-Literale), sie dienen als Beleg.
SHA256 der **unredigierten Originale** (zur Rückverfolgung auf die Box-Dateien):

```
dc657c23858b15521fb5fee0ff164bb77756ebb2210c8f5ea1b27e5544342e74  q4_k_m/DE_01_Klassisch.child_raw.json
df793f9dfa55b9e9ecbde9ff45f4e06e615495bb8582d3e87af1bdaadb50d9a2  q4_k_m/DE_01_Klassisch.json
bf14cea78d49c853a6e811906a4dfc7a8f8146d52206b8929e8fa8acdff377b9  q4_k_m/DE_02_Zweispaltig_Trap.child_raw.json
c41468c311afd7e0938e8923c577c4d679010384073de6d981cadd7f42cd4965  q4_k_m/DE_02_Zweispaltig_Trap.json
37962c175ffddc3a885fbef7c035c7781e76e95815991f26da5bf46f7ed6031a  q4_k_m/DE_03_C1_Kontextfalle.child_raw.json
1c498777dcfe4c716b81a520f4db1e0aa5c34899286b98bb0c3f6a181e546fa6  q4_k_m/DE_03_C1_Kontextfalle.json
89a6ff05309b0787a8fc69c7cb704e45f60b7dc9a76407e69837d0b163d71153  q4_k_m/DE_04_Unvollstaendige_Kontaktdaten.child_raw.json
6e209fa0cfa3d1797463d35d51d2b0ad62faaa74fb2d9933a37e6ba3e46fea40  q4_k_m/DE_04_Unvollstaendige_Kontaktdaten.json
cae2bc828d00126ee037428378c787bcb14429c705e8c50767aeb4f8a0f64987  q4_k_m/DE_05_Zweiseitig.child_raw.json
1e47082e14afaab3bf3119b7d5a58881e8e686afc6be30ba5ccf50fd93b13e04  q4_k_m/DE_05_Zweiseitig.json
3e454cad845284f730a36133c95dfc1223e7c6231972618c7607f21533ac6b8e  q4_k_m/EN_01_Classic_Resume.child_raw.json
14fa06a0ce64d08e8cda558bd57f8e8c6d5e95c54a5e62d92c44634e564908c6  q4_k_m/EN_01_Classic_Resume.json
61e96b74f73a4605bb3ce796b669c9b221acd0e2e717b13d2569d77141f5f384  q4_k_m/EN_02_Two_Column_Trap.child_raw.json
7041361e3e3ffbbde320113ccaa743448fdf1cca7720ccf82811b8b2d8236316  q4_k_m/EN_02_Two_Column_Trap.json
9b76fd07e498e6b5577d9cb535dffe96998cafb98c88b6e519bba25645d1d2ed  q4_k_m/EN_03_Missing_Address_Fields.child_raw.json
34eb890cc8a0cf2ca4c9f5f5e1d316b587709d94394851fc8e5fa7c5586a461f  q4_k_m/EN_03_Missing_Address_Fields.json
f61866731588dded21ffdc8e942a84aa1922f02d98d747189f345e59270f090d  q4_k_m/EN_04_German_Address_English_CV.child_raw.json
931cc2d0c1ace2d10a571af02e981789e497903d070fc0760ee9e73e5d9cccbf  q4_k_m/EN_04_German_Address_English_CV.json
a6af59f7091b60ac6da18e9338e0bf51cd8274f3ab03d46e8c84d08c4e1af770  q4_k_m/EN_05_Skills_Heavy.child_raw.json
94fec7a704b22e80e793eb1e965e78fb0233ddc7eefce658d82a2e825faa6744  q4_k_m/EN_05_Skills_Heavy.json
dc045caaddb04ac8645ad13c9413b29fc9da24f133b21c5f03bf2a5105c3670e  q4_k_m/HR_URTEIL_ENTWURF.md
9cbbc9612f95ff80a1db9d14e341f849f370f0156913ad6a6814199577644747  q4_k_m/RUN.log
a22f7e71bed197b9daa8809824293b969bb8c52afe27c17ff0476df32608ba57  q4_k_m/SYSINFO.txt
9a1a1e73809fcdf303aaa666c71386174fc088f833189d0967528596bc0ef6d3  q4_k_m/logs/DE_01_Klassisch.log
a8fedad6af6ef2abf34ef138bd7dab9880ee300d36b6e6d90e8dc19c47309cca  q4_k_m/logs/DE_02_Zweispaltig_Trap.log
fafd4cc188c6485c6951083de756ac629e00fd564e9003c98239422f3852e122  q4_k_m/logs/DE_03_C1_Kontextfalle.log
9a3848674cd006a332a35fd1047b25472b2dab46e3a4f0cd588c15bf7df9f64a  q4_k_m/logs/DE_04_Unvollstaendige_Kontaktdaten.log
feb98ff6fd93097c4473a89e294ed0be06f82e22da8d3b7caa7a2e206b3d2801  q4_k_m/logs/DE_05_Zweiseitig.log
f3f078f2912c4d730f316089d728db848879531f7499e529693085e4e8f1fbcc  q4_k_m/logs/EN_01_Classic_Resume.log
71e5fc70f6d7f6daa680787c35ea118b617cf933343a06ac437b9d43b0439162  q4_k_m/logs/EN_02_Two_Column_Trap.log
489e511a47f488855166d1b712e7a1c8a1e129bc56ac63dc192657fdb08c5aeb  q4_k_m/logs/EN_03_Missing_Address_Fields.log
1252e34e7ecd01170a3cd9f580f764f0bf7a7ca0b86bc8bd19e3979615cd9739  q4_k_m/logs/EN_04_German_Address_English_CV.log
848250e3a4cfd9b88bd372db46ba09d063a7401463b392c2084c754150b7073c  q4_k_m/logs/EN_05_Skills_Heavy.log
21aec68079ba5761758c002bad28a442c82a5af35f807e923dc748bccb19f19a  q4_k_m/pip_freeze_venv_llama0335.txt
3dfae23bfb26dba1c048ebeab87ada2ff0c4d84dc6c54353d521b5fe81012a1a  q4_k_m/run_meta.json
2bbba23ccfa65969093ffc75e60a7c664f2501530099ff68fb841524eb7b4a69  harness/kk_extract_child.py
318fffe1be00a8aaecc44c78ccb3ec070d538f6d4867ef459263f0eefaa15a9f  harness/kk_extract_run.py
427b4d436e98c8b820e8bf4a6ad4f7d12b2f33368108f810a573b3cde81d2aa4  harness/setup_extract.ps1
dc54ebaf2236db83fc44ec637533ce333e5b5e5b78bd4802b39a3a9331a8e357  harness/stop_letters.ps1
```

## Bewusst ausgeschlossen

- `q4_k_m_pack.zip` (Transport-Archiv, Duplikat von `q4_k_m/`), `thinkpad_extracts_2026-10-18/RUN.log` (identisch mit `q4_k_m/RUN.log`).
- `_harness/kk144_src_47e8f83b.zip` (24 MB, > 5 MB) und `_harness/src/` (git-archive von `47e8f83b`, bereits im Repo-Verlauf).
- Modelldateien (`.gguf`), venvs, Caches, heruntergeladene CI-Artefakte (`/workspace/kk144-art`).

## Privacy-Scan

`python3 scripts/privacy_scan.py --all-files` – vor Redaktion: FAILED (`HR_URTEIL_ENTWURF.md: windows_user_path`), nach Redaktion: OK.
