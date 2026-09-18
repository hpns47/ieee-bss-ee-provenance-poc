# Project Brief: Blockchain-Anchored Provenance для Multi-Level Geospatial Change Detection
## Для подачи на BSS 2026 (5th International Workshop on Blockchain Security and Scalability)

---

## 0. Контекст проекта — зачем это всё

Есть опубликованная статья (SIST 2026, Astana): **"Multi-Level Optical-Radar Correlation Decoupling Framework for Hidden Land Surface Change Detection"**. Она предлагает статистический пайплайн для детекции скрытых изменений земной поверхности (Almaty, Sentinel-1/2 данные 2023–2024) через распад корреляции между оптическими (NDVI) и радарными (SAR VV/VH) индексами. Пайплайн многоуровневый: Pearson correlation → Δr (seasonal disruption) → r_t (sliding window temporal correlation) → Moran's I (spatial autocorrelation) → Z-score → composite risk index → CSI/SCR/CPI.

Сейчас делаем **вторую, отдельную статью** — не переписываем старую, а строим поверх неё security/provenance-слой и подаём как самостоятельную работу на BSS 2026 (тематика: blockchain security, scalability, trustworthy AI, zero trust). Старая статья в новой цитируется как prior work (метод), а не переписывается заново.

**Важно про анонимность:** BSS 2026 — double-blind review. В тексте статьи ссылку на старую работу нужно давать строго в третьем лице ("the framework proposed in [X] computes..."), никогда "our earlier work"/"we previously showed" — иначе рецензент легко деанонимизирует авторов.

---

## 1. Ключевые даты (BSS 2026, https://inbss.com/call-for-papers.html)

| Этап | Дата |
|---|---|
| Подача статьи | **20 сентября 2026** |
| Уведомление авторов | 15 октября 2026 |
| Camera-ready | 22 октября 2026 |
| Воркшоп | 30 ноября – 4 декабря 2026 |

Формат: IEEE Computer Society, double-anonymous review, EDAS-система. Подача: https://edas.info/newPaper.php?c=35179&track=139226

⚠️ **Дедлайн подачи очень близко.** Реалистично успеть полноценную реализацию + эксперименты почти невозможно за оставшееся время — см. раздел 6 (что можно урезать без потери проходимости).

---

## 2. Тема и название

**Основное название:**
> *Verifiable Multi-Level Statistical Provenance: A Blockchain-Anchored Audit Framework for Trustworthy Optical–Radar Decoupling in Hidden Land-Surface Change Detection*

**Короткий вариант (если нужен под лимит символов):**
> *Chain-of-Evidence: Blockchain-Anchored Provenance for Multi-Level Statistical Change Detection Pipelines*

**В какие темы BSS попадает (используйте формулировки прямо из CFP в Introduction):**
- Blockchain for AI, IoT, CPS, edge and cloud computing
- Blockchain and LLMs, including provenance, validation, access control and auditability (у нас не LLM, а geospatial statistical pipeline — но логика provenance/validation та же)
- Applications in ... e-government
- Zero Trust and Blockchain, including continuous verification, decentralised identity and policy enforcement

---

## 3. Научная новизна (novelty statement — ядро статьи)

**Одной фразой:** ни одна из найденных работ не якорит **каждую стадию статистического вывода** (а не только вход/выход) и не защищает от манипуляции **параметрами анализа** (α, β, τ, λ), а не только данными.

Подробный разбор пробела в литературе — см. отдельный файл `BSS2026_Related_Work_Bibliography.md`. Коротко: похожие работы делятся на три кластера —
1. Blockchain для целостности сырых/продуктовых RS-снимков (якорят изображение целиком);
2. Blockchain для земельного кадастра (якорят транзакции владения, не автоматический мониторинг);
3. Blockchain для provenance ML/AI-пайплайнов (близко методологически, но не geospatial multi-sensor и без модели атаки на параметры).

Наш вклад — на пересечении: **multi-level Merkle-anchoring, повторяющий структуру самого статистического алгоритма**, плюс явный threat model с тремя векторами атаки (data-level / parameter-level / output-level), где parameter-level — то, чего в литературе нет вообще.

---

## 4. Архитектура — что строить технически

### 4.1. Схема 1 — Multi-Level Provenance Architecture

Слои снизу вверх:

1. **Data Acquisition Layer** (off-chain): Sentinel-1 SAR + Sentinel-2 optical, 15-дневная temporal synchronization (как в оригинальном пайплайне, `ee.Join.saveFirst`).
2. **Statistical Computation Layer** (off-chain, Google Earth Engine): каждая стадия пайплайна (Pearson r → Δr → σ_Δr → r_t → Moran's I → Z-score → risk_index → CSI/SCR/CPI) на выходе формирует **leaf-хеш**:
   ```
   H_i = SHA256(input_ref, params_i, output_i, operator_DID, timestamp)
   ```
3. **Merkle Aggregation Layer**: leaf-хеши одного эпизода мониторинга (дата/тайл) собираются в Merkle-дерево → один корень на эпизод.
4. **On-chain Layer** (рекомендуется Hyperledger Fabric — permissioned, подходит под академический прототип, есть готовые инструменты бенчмаркинга типа Hyperledger Caliper): смарт-контракт хранит только Merkle root + метаданные; **отдельная governance-транзакция**, подписанная DID уполномоченного оператора, требуется для изменения любого из параметров α/β/τ/λ — сама история изменений параметров тоже неизменяема.
5. **Verification/Audit Layer** (off-chain, для регулятора/аудитора): запрос конкретной стадии → пайплайн отдаёт Merkle-proof → аудитор пересчитывает хеш локально и сверяет с on-chain root — без раскрытия всего массива сырых данных (selective disclosure).

### 4.2. Схема 2 — Threat Model & Verification Flow

Три вектора атаки и контрмеры:

| Атака | Что происходит | Контрмера |
|---|---|---|
| **Type 1 — Data-level** | Подмена/повтор старого снимка Sentinel | Хеш сырых снимков как leaf level 0 |
| **Type 2 — Parameter-level** ⭐ ключевой вклад | Задним числом меняется τ (напр. 0.4→0.6), чтобы скрыть реальную аномалию | Governance-транзакции параметров подписаны DID и неизменяемы; расхождение детектируется мгновенно |
| **Type 3 — Output-level** | Прямая правка risk_index/change_mask в отчёте без пересчёта | Merkle root верхнего уровня не совпадёт при пересчёте |

Verification workflow: Verifier → запрос стадии → smart contract возвращает {root, Merkle-path} → Verifier пересчитывает хеш локально → сравнение → PASS/FAIL **с указанием конкретного уровня пайплайна**, на котором произошло расхождение (не просто бинарный ответ — это отличает от большинства систем в литературе).

### 4.3. Технологический стек (рекомендация)

- **Ledger:** Hyperledger Fabric (permissioned) — стандарт в найденной литературе, есть Hyperledger Caliper для бенчмарков latency/throughput.
- **Off-chain storage** (если нужно хранить что-то кроме хешей): IPFS — используется в нескольких referenced-работах для снимков/perceptual hash.
- **Merkle tree:** обычная бинарная Merkle-структура, SHA-256.
- **DID/identity:** можно упростить до PKI-подписей (ECDSA) вместо полноценного DID-стандарта, если времени мало — это нормально описать как "simplified DID scheme" с явным ограничением (limitation) в тексте.
- **Geospatial pipeline:** переиспользовать существующий Google Earth Engine код из старой статьи как есть — не переписывать.

---

## 5. Evaluation Plan — что нужно измерить и показать

Обязательно (без этого раздел "Adequacy of evaluation" рецензент BSS зарежет):

1. **Overhead записи в блокчейн** относительно времени выполнения geospatial-пайплайна — на 10m/30m/100m масштабах (эти масштабы уже есть в оригинальной статье, просто добавить туда метрику времени).
2. **Storage cost** — сколько хешей/блоков на регион за период мониторинга.
3. **Demonstration of tamper-detection** — искусственно подменить τ или risk_index задним числом и показать, что верификация проваливается (это буквально центральный эксперимент статьи, без него никакой "security paper" не проходит).
4. **Сравнение с naive baseline** — обычная цифровая подпись/timestamping authority без блокчейна — иначе рецензент спросит "зачем вам вообще блокчейн".
5. Опционально, если хватит времени — latency/throughput на batch операциях (ориентир для сравнения: аналогичные работы показывают overhead порядка десятых долей процента при батчевой записи — см. библиографию, документ ChainGuards).

---

## 6. Что можно урезать при нехватке времени (реалистичный minimum viable paper)

Если полноценная реализация Hyperledger Fabric не успевается до 20 сентября:

- **Minimum:** реализовать Merkle-дерево + SHA-256 хеширование стадий в Python как proof-of-concept (без реального distributed ledger), симулировать "on-chain" запись как append-only локальный лог с подписями. Честно указать в Limitations, что full permissioned-ledger deployment — future work.
- **Обязательно оставить:** demonstration of tamper-detection (эксперимент №3 из раздела 5) — это единственное, без чего статья не будет выглядеть как security-контрибуция, даже в сокращённом виде его можно сделать за несколько часов.
- Threat model (раздел 4.2) — это чисто концептуальная часть, не требует кода, можно сделать полностью и качественно независимо от того, что успеет команда.

---

## 7. Структура статьи (6 страниц, IEEE two-column, стандартный BSS workshop формат)

1. **Abstract** — 150–200 слов, сразу formulировка gap + вклад.
2. **Introduction** — мотивация (юридическая admissibility результатов ДЗЗ, insider-манипуляция оператором платформы), явная ссылка на прежнюю статью как prior work (третье лицо!).
3. **Related Work** — три кластера (см. библиографию), явный gap statement в конце раздела.
4. **Threat Model** — три типа атак (раздел 4.2).
5. **Architecture** — Схема 1 + Схема 2, детальное описание Merkle-структуры и governance-транзакций.
6. **Implementation** — стек, детали (раздел 4.3).
7. **Evaluation** — метрики из раздела 5.
8. **Discussion / Limitations** — честно указать упрощения (см. раздел 6).
9. **Conclusion.**

---

## 8. Чек-лист перед подачей

- [ ] Self-citation на SIST-статью — только в третьем лице
- [ ] Явный threat model присутствует (требование review criteria BSS)
- [ ] Есть демонстрация tamper-detection (не только архитектура на бумаге)
- [ ] Есть baseline-сравнение (не просто "у нас блокчейн")
- [ ] Limitations прописаны явно, отдельным разделом или подразделом
- [ ] Все 11 источников из библиографии процитированы там, где релевантно (особенно в Related Work и Evaluation)
- [ ] Проверить дублирование разделов / опечатки, перенесённые из старой статьи, не повторять их
