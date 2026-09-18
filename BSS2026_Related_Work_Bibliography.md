# Аннотированная библиография — Related Work для BSS 2026 статьи

Полных PDF здесь нет по авторско-правовым причинам — скачайте по ссылкам через институтский доступ / arXiv / ResearchGate / DOI. Для каждой статьи: точная ссылка, что в ней есть, чего не хватает, что взять для нашей статьи.

---

## Кластер A — Blockchain для целостности сырых/продуктовых RS-данных

### 1. Blockchain Integration for Secure and Transparent Satellite Remote Sensing Data Systems
**Источник:** Springer Nature Link
**Ссылка:** https://link.springer.com/chapter/10.1007/978-3-032-14935-0_34

Распределённое хранилище и система транзакций для спутниковых данных на immutable ledger, протестировано на ~100 000 блоков / 200 000 транзакций.
**Недостаток:** якорит сырое изображение целиком, не производные статистические метрики.
**Взять:** масштаб тестирования (количество блоков/транзакций) как ориентир для собственных экспериментов.

### 2. A Blockchain Solution for Remote Sensing Data Management Model
**Источник:** Applied Sciences (MDPI), 2023
**Ссылка:** https://doi.org/10.3390/app13179609

Мотивация — недоверие между "data islands" разных операторов ДЗЗ; DLT для отслеживания источника и целостности.
**Недостаток:** фокус на data sharing между организациями, не на single-operator / external-auditor сценарии.
**Взять:** формулировку проблемы "data islands" для Introduction — хороший контраст с нашим single-pipeline сценарием.

### 3. A Blockchain-Based Approach to Enable Remote Sensing Trusted Data
**Источник:** ISPRS (researchgate)
**Ссылка:** https://www.researchgate.net/publication/346558191_A_BLOCKCHAIN-BASED_APPROACH_TO_ENABLE_REMOTE_SENSING_TRUSTED_DATA

Two-tier запись (full history vs sliding 48-часовое окно), смарт-контракты для автоматизации действий. Авторы сами признают: система не использует потенциал доверия/стимулирования блокчейна, так как все участники уже известны друг другу.
**Недостаток:** нет decentralized identity / модели неизвестного/недоверенного актора.
**Взять:** прямая цитата про отсутствие identity-слоя — хороший gap statement, который мы закрываем.

### 4. Blockchain-Based Method for Spatial Retrieval and Verification of Remote Sensing Images
**Источник:** PMC
**Ссылка:** https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11014153/

Geohash + LSM-дерево + Hyperledger Fabric + IPFS. Сильная эмпирика: снижение задержки доступа и рост throughput при работе с пространственными данными в Fabric.
**Недостаток:** unit верификации — изображение целиком (через geohash), не иерархия статистических метрик.
**Взять:** методологию оценки latency/throughput на Hyperledger Fabric как шаблон для нашей Evaluation-секции.

### 5. Integrity Authentication Based on Blockchain and Perceptual Hash for Remote-Sensing Imagery
**Источник:** Remote Sensing (MDPI), 2023
**Ссылка:** https://doi.org/10.3390/rs15194860

Perceptual hash + приватный IPFS + Hyperledger Fabric, детальная оценка latency по размеру файлов (1–50 MB).
**Недостаток:** защищает только целостность снимка, не производные вычисления над ним.
**Взять:** идею комбинировать их perceptual-hash слой (raw image integrity) с нашим Merkle-деревом стадий (derived-metric integrity) — двухуровневая защита, упомянуть как future extension.

---

## Кластер B — Blockchain для земельного кадастра / geospatial governance

### 6. Design and Implementation of a Geospatially Enabled Blockchain Application for Land Record Management
**Источник:** ISPRS Annals, 2025
**Ссылка:** https://isprs-annals.copernicus.org/articles/X-5-W2-2025/491/2025/index.html

GIS + смарт-контракты для земельного кадастра; ledger обеспечивал синхронизацию в реальном времени, минимизировал мошенничество/подделку/дублирование записей.
**Недостаток:** про транзакции владения (человек инициирует запись), не про автоматический непрерывный мониторинг изменений.
**Взять:** контраст в Related Work — показать переход "human-initiated record" → "pipeline-triggered record" как наш вклад.

---

## Кластер C — Blockchain для верифицируемости AI/ML-пайплайнов (самый близкий кластер)

### 7. Trustworthy AI for secure and robust machine learning through blockchain enabled data integrity
**Источник:** Discover Artificial Intelligence (Springer), 2026
**Ссылка:** https://link.springer.com/article/10.1007/s44163-026-01443-5

Permissioned blockchain (Hyperledger Fabric) + TensorFlow Federated, Merkle-хеширование per-sample/per-update provenance, смарт-контракт для anomaly-scoring.
**Недостаток:** применяется к federated learning (веса модели), не к geospatial статистическому пайплайну с физическими метриками.
**Взять:** их Merkle-tree + on-chain metadata layout как техническую основу для нашей Схемы 1 — самый близкий технический шаблон из всех 11.

### 8. Immutable AI: A blockchain-based MLOps framework for auditable solar forecasting and anomaly logging
**Источник:** ScienceDirect, 2026
**Ссылка:** https://www.sciencedirect.com/science/article/pii/S1474034626006671

Методологический близнец нашей задачи: система доказывает существование конкретного артефакта/снимка данных до определённого момента через consensus-verified timestamp, детектирует ретроспективную замену весов модели и изменение записей аудита.
**Недостаток:** один источник данных (солнечная генерация), не мультисенсорное слияние SAR+optical с temporal synchronization.
**Взять:** формулировку "what the system can prove / what the system can detect" — прямой шаблон для нашей Evaluation-секции.

### 9. AI-Enhanced Blockchain Networks for Climate Change Monitoring and Carbon Credit Verification
**Источник:** ACM (Proceedings of ICFAIML 2025)
**Ссылка:** https://dl.acm.org/doi/10.1145/3748382.3748389

Самый близкий по домену: спутниковые снимки + IoT-данные + immutable ledger для защищённого от подделки экологического мониторинга.
**Недостаток:** описательная/высокоуровневая, нет строгой статистической модели детекции, нет sensitivity-анализа, нет explicit threat model.
**Взять:** позиционировать нашу статью как методологически более строгую реализацию той же идеи — явно указать в Related Work.

### 10. Blockchain-enabled Audit Trails for AI Models
**Источник:** SAMRIDDHI Journal / ResearchGate, 2025
**Ссылка:** https://www.researchgate.net/publication/395415248_Blockchain-enabled_Audit_Trails_for_AI_Models

Комбинация симуляционных экспериментов, threat modeling и performance analysis для immutable-записи training-данных.
**Недостаток:** generic AI training data, нет geospatial-специфичных угроз (например, geo-spoofing метаданных тайла).
**Взять:** структуру "threat modeling + performance analysis" как шаблон для нашего раздела Sensitivity/Evaluation.

### 11. ChainGuards: Verification of Sensed Data using Permissioned Blockchain Technology
**Источник:** arXiv, 2026
**Ссылка:** https://arxiv.org/pdf/2603.20769

Сильная эмпирика: оверхед записи в Hyperledger Fabric на batch из 1000 событий — около 0.03% по сравнению с прямым хранением без блокчейна.
**Недостаток:** generic "sensed data" (логистика/IoT), не geospatial multi-level статистический вывод.
**Взять:** цифру overhead ~0.03% как бенчмарк для сравнения с собственными результатами.

---

## Итоговый gap statement (для конца Related Work)

Ни одна из 11 работ не решает одновременно три задачи: (1) многоуровневое иерархическое якорение каждой статистической стадии пайплайна, а не только входа/выхода; (2) явную модель угрозы манипуляции параметрами анализа (не только данными); (3) демонстрацию tamper-detection для geospatial multi-sensor fusion с temporal synchronization. Кластер A защищает данные, но не процесс анализа. Кластер B защищает транзакции владения, но не автоматический мониторинг. Кластер C (ближе всего методологически) решает provenance для ML-пайплайнов общего назначения, но не для многоуровневого статистического geospatial-фреймворка с настраиваемыми порогами принятия решений.
