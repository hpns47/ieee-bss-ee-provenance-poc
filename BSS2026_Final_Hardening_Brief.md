# Technical Brief: Final Hardening Pass Before Submission
## Для передачи разработчику — приоритет 0 (интеграция в текст) + приоритет 1 (новые метрики)

---

## 0. Контекст

Пакет `provenance_poc/` уже содержит: `attack_sweep.py` (64 комбинации, детекция/локализация по всем 9 стадиям), 5 готовых графиков (Fig. A-E), `HYPERLEDGER_FABRIC_MAPPING.md`, обновлённую `architecture.dot`. Всё это работает и проверено. **Но ничего из этого ещё не встроено в текст самой статьи** — текущий docx (`BSS2026_Provenance_Paper.docx`) написан ДО этого пакета. Задача этого прохода — закрыть разрыв между "у нас есть данные" и "у нас есть готовая к подаче статья".

Работает поверх существующего кода — почти вся инфраструктура (`merkle.py`, `ledger.py`, `pipeline.py`, `demo_tamper_detection.py`, `attack_sweep.py`) не требует переписывания, только расширения.

---

## ПРИОРИТЕТ 0 — без этого шага остальное не считается

### 0.1. Интеграция в текст статьи (главная задача)

В `BSS2026_Provenance_Paper.docx`:

1. **Section VII-C (Tamper detection and localization)** — заменить текущий текст (единичный пример на change_mask) на абзац с агрегированной статистикой из `attack_sweep_results.json`: "across 64 attack_type × target_stage × magnitude combinations (40 trials each, N=2560 episodes total), the proposed scheme achieved 100% detection and 100% localization accuracy across all 9 pipeline stages, versus the naive baseline's 0% detection rate for Type-2 (parameter-level) tampering and inability to localize even the Type-3 tampering it does catch." Указать Table/Fig ссылки на Fig. A, B, C.
2. **Вставить Fig. A–E** с подписями в Section VII, рядом с соответствующим текстом.
3. **Section VIII (Limitations)** — убрать пункт "a broader sweep over attack magnitudes... is needed" (закрыт), заменить на актуальные оставшиеся ограничения (single real GEE episode, no false-positive sweep — если не успеете п.1.1 ниже, оставить как честное ограничение; no real Fabric deployment — сослаться на `HYPERLEDGER_FABRIC_MAPPING.md`).
4. **Architecture/Implementation** — сослаться на `HYPERLEDGER_FABRIC_MAPPING.md` явно (можно вставить таблицу function-mapping как Table, сократив прозу).
5. **Заменить Fig. 1 (architecture)** на обновлённый рендер `architecture_rendered.png` (с Sensitivity Testing Harness блоком).
6. **Проверить лимит страниц** — с 5 новыми figures почти наверняка вылезет за 6 стр. План сокращения: уплотнить Related Work (Section II) и часть Discussion (Section VIII) — не трогать Evaluation, это теперь самая сильная часть.
7. Технический долг из старой версии — обязательно поправить при переписывании: дублирующаяся нумерация "Table II" (встречается дважды — ledger→Fabric mapping и scale sweep), порядок Fig.1/Fig.2 (сейчас Fig.2 упоминается в тексте раньше Fig.1).

---

## ПРИОРИТЕТ 1 — новые метрики (расширение существующего кода)

### 1.1. False Positive Rate sweep (самое ценное дополнение)

**Зачем:** весь текущий sweep измеряет только detection rate атак (true positive). Ни разу не измерено, не срабатывает ли система ложно на легитимные, санкционированные изменения. Рецензент спросит именно это.

**Что добавить** — новый скрипт `fp_sweep.py`, использующий инфраструктуру `attack_sweep.py`/`demo_tamper_detection.py`:

1. Сгенерировать N=40 "genuine" эпизодов (разные seed, без атаки).
2. Для части из них (например половина) выполнить **легитимное** изменение параметра — governance-транзакция, подписанная DID, точно как в `demo_tamper_detection.py` (τ 0.4→0.5), с последующим пересчётом episode под новым τ.
3. Прогнать verification (Merkle-proof check против anchored root + governance log cross-check) на каждом.
4. Ожидаемый результат: **0% false positive rate** — ни один легитимный эпизод не должен триггерить tamper alert, потому что governance log содержит подтверждённое изменение параметра.
5. Записать в `fp_sweep_results.json`, формат аналогичный `attack_sweep_results.json`, но с полем `false_positive_rate` вместо `detection_rate`.
6. Построить **Fig. F** — простой bar chart или таблицу: "False positive rate: 0/40 (0%) across legitimate parameter changes and 0/40 (0%) across genuine unmodified episodes" — можно объединить с Fig. A/B в одну комбинированную figure (detection + false positive rate side by side), чтобы не плодить лишние figures при ограничении по странице.

**Важно:** если результат окажется не 0% (например, найдётся edge case, где легитимное изменение ошибочно триггерит alert из-за бага в cross-check логике governance log) — это не проблема, а находка. Зафиксировать честно и либо исправить логику verification (сверка должна проверять "совпадает ли изменение с последней governance-записью", а не просто "совпадает ли текущее значение с исходным"), либо описать как известное ограничение.

### 1.2. End-to-end verification latency

**Зачем:** сейчас измерен только anchoring overhead (запись). Но в Threat Model ключевой сценарий — аудитор запрашивает proof и проверяет его. Это время нигде не измерено.

**Что добавить** — расширить `benchmark.py`:
1. Измерить время генерации Merkle-proof для случайной стадии (`MerkleTree.get_proof` или аналог, если такой метод уже есть в `merkle.py` — проверить, есть ли уже `find_mismatched_stage`, возможно можно переиспользовать её внутренности).
2. Измерить время верификации proof аудитором (`Verify(h_i, path_i, R)` — уравнение (5) из статьи).
3. Прогнать на тех же 5 масштабах (100/50/30/20/10м), что и текущий `benchmark.py`.
4. Добавить колонку в существующую Table (latency vs scale) или отдельную строку в `benchmark_results.json`: `proof_generation_ms`, `proof_verification_ms`.
5. Ожидание: эти числа должны быть на порядки меньше anchoring overhead (проверка одного пути в дереве из 9 листьев — это ~log2(9)≈4 хеш-операции), что даёт хороший аргумент "verification is cheap even though it happens externally, at audit time, potentially much later."

### 1.3. Интерпретирующая строка под Fig. A

В подписи к Fig. A (или в тексте Section VII-C) добавить одно предложение: "The flat 100%/0% curves are expected given hash-based verification is magnitude-invariant by construction (SHA-256's avalanche property guarantees any nonzero perturbation changes the hash); the informative result is that detection holds uniformly down to a 1% relative magnitude, not that it varies with attack size."

---

## ПРИОРИТЕТ 2 — опционально, если останется время

- **Combined-attack test**: один эпизод, одновременно Type-2 (на risk_index) + Type-3 (на change_mask) — проверить, что локализация правильно называет ОБЕ атакованные стадии, а не путается. Расширение `attack_sweep.py`, новая функция `apply_combined`.
- Увеличить `N_TRIALS` в `benchmark.py` для финальных чисел в статье (текущий разброс ±0.8мс на 100м заметен между запусками).

---

## Что НЕ трогать (сознательное решение, зафиксированное в CLAUDE.md)

- Реальный Hyperledger Fabric / Caliper деплой — решение не делать до 20 сентября уже принято, не пересматривать.
- Множественные реальные GEE-эпизоды на разных AOI — за пределами оставшегося времени, честно остаётся как Limitation.
- Полноценный W3C DID — упрощённый ECDSA уже задокументирован как осознанное упрощение.

---

## Чек-лист готовности к подаче

- [ ] Section VII-C переписан под агрегированную sweep-статистику
- [ ] Fig. A–E вставлены с подписями
- [ ] False positive rate добавлен (п. 1.1) — либо результат, либо честно как gap, если не успели
- [ ] End-to-end verification latency измерена (п. 1.2)
- [ ] Architecture figure заменена на обновлённый рендер
- [ ] HYPERLEDGER_FABRIC_MAPPING.md процитирован в Architecture/Implementation/Limitations
- [ ] Дублирующаяся нумерация Table II исправлена
- [ ] Порядок Fig.1/Fig.2 исправлен под порядок упоминания в тексте
- [ ] Объём проверен и уложен в 6 страниц
- [ ] Self-citation на SIST-статью — строго в третьем лице, без деанонимизации
