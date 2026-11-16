# Scalping Gold V1 — คู่มือภาษาไทย

Scalping Gold คือ Expert Advisor (EA) สำหรับวิจัยการเทรดทองบน MetaTrader 5 (MT5)
โดยใช้กฎกลยุทธ์สร้างสัญญาณ และให้ Machine Learning (ML) ช่วยกรองก่อนส่งคำสั่ง
รองรับ **บัญชี DEMO เท่านั้น** ปฏิเสธบัญชี REAL และ CONTEST และตั้ง
`AUTO_TRADING=false` เป็นค่าเริ่มต้น

**สถานะปัจจุบัน:** มีซอร์สโค้ด EA และระบบ Python แล้ว แต่ยังไม่มีหลักฐานว่า
คอมไพล์ MQL5 ผ่าน ทดสอบ MT5 Strategy Tester ผ่าน หรือทำกำไรจากข้อมูลตลาดจริง
ยังไม่มีโมเดลที่อนุมัติให้ซื้อขายรวมอยู่ในโปรเจกต์ การผ่าน Python tests ไม่เท่ากับ EA
ผ่านการทดสอบกับโบรกเกอร์ อ่าน [สถานะการตรวจสอบ](docs/VALIDATION.md) ประกอบด้วย

โค้ดอยู่บน branch `feature/scalping-gold-v1` ใน
[Draft PR #2](https://github.com/Knerubon/scalping-gold/pull/2)
ตาม [ข้อกำหนด Issue #1](https://github.com/Knerubon/scalping-gold/issues/1)
โปรเจกต์นี้แยกจาก NEXORA และไม่ได้ใช้โค้ดของ NEXORA

ลำดับสำหรับผู้เริ่มต้นคือ **ติดตั้ง → คอมไพล์ → ตรวจสัญญาณแบบ Shadow → ตรวจข้อมูลและโมเดล
→ Backtest ด้วย Replay → พิจารณาทดลอง Demo หลังตรวจหลักฐานครบ**
คู่มือนี้ไม่ได้อนุมัติโมเดล เปิดสิทธิ์ซื้อขาย หรือติดตั้งลงบัญชีให้โดยอัตโนมัติ

## 1. ภาพรวมระบบ Scalping Gold

### EA ทำงานอย่างไร

EA ตรวจเงื่อนไขบนแท่งราคาที่ปิดแล้ว โดยแบ่งหน้าที่ตามกรอบเวลา:

| กรอบเวลา | หน้าที่ |
|---|---|
| `M5` | สร้างสัญญาณเข้า ใช้ ATR/RSI/EMA และรูปแบบแท่งราคา |
| `M15` | ตรวจสภาพตลาดด้วย ADX, DI, EMA และกรอบราคา |
| `H1` | ให้ข้อมูลบริบทเป็น feature ของ ML ไม่ใช่เงื่อนไขบังคับทิศทางแยกต่างหาก |

เมื่อมีแท่ง M5 ใหม่ EA อ่านข้อมูลแท่งที่ปิดแล้ว ตรวจสภาพตลาด และสร้าง candidate
หรือแผนซื้อขายที่มี `signal_id`, เวลา, กลยุทธ์, ทิศทาง, entry, SL, TP และ features
เลือกได้ไม่เกินหนึ่ง candidate ต่อรอบ สัญญาณขัดแย้งกันจะไม่เข้าเทรด
และให้ Breakout มีลำดับความสำคัญเมื่อเข้าเงื่อนไข

สถานะภายใน ได้แก่ `IDLE`, `CANDIDATE_READY`, `ML_WAIT`, `APPROVED`, `SUBMITTING`,
`OPEN` และ `LOCKED` ตัวตรวจ regime รอการยืนยันจาก M15 ที่ปิดแล้วสองแท่งต่างเวลากัน
เงื่อนไขไม่ปลอดภัยจะกลับเป็น `WAIT` ทันที ADX ตั้งแต่ 20 แต่น้อยกว่า 25 หรือ
ทิศทาง EMA/DI ขัดแย้งกันจะไม่สร้างสัญญาณเข้า

### กลยุทธ์ที่มีในโค้ด

| กลยุทธ์ | หลักการเข้า | SL และ TP เริ่มต้น |
|---|---|---|
| Trend Pullback | ตามแนวโน้ม M15; ADX ≥25, EMA20/EMA50 และ DI ไปทางเดียวกัน; M5 ย่อแตะ EMA20 แล้วปิดกลับยืนตามทิศทาง | SL ระยะ 1.5 × ATR(M5), TP เป้าหมาย 2R |
| Range Reversal | ADX(M15) <20 และกรอบก่อนหน้ากว้าง ≥3 × ATR(M15); M5 ใกล้ขอบกรอบ พร้อม RSI และแท่งกลับตัว | SL อยู่นอกขอบกรอบอีก 0.5 × ATR(M5); TP กลางกรอบเมื่อ RR ≥1.5 |
| Breakout | ตลาด ADX <20 ที่ ATR(M15) ≤0.8 เท่าของค่าเฉลี่ย ATR ก่อนหน้า 50 แท่ง; M5 ปิดพ้นกรอบ ≥0.1 ATR และ body ≥60% ของช่วงแท่ง | SL ระยะ 1.5 × ATR(M5), TP เป้าหมาย 2.5R; จำกัดการไล่ราคาเข้าไม่เกิน 0.5 ATR(M5) จากขอบกรอบ |

BUY และ SELL ใช้เงื่อนไขกลับด้านกัน ตัวอย่าง Trend BUY ต้องปิดเหนือ EMA20,
ปิดสูงกว่าราคาเปิดและราคาปิดแท่งก่อนหน้า ส่วน Range BUY ต้อง RSI <35 และแท่งขาขึ้น
Range SELL ต้อง RSI >65 และแท่งขาลง
กรอบราคาใช้ 20 แท่ง M15 ที่ปิดแล้วและทราบข้อมูลได้ก่อนแท่ง M5 สัญญาณเปิด
SL/TP ถูกปรับให้ตรง tick size และข้อกำหนดโบรกเกอร์ก่อนส่งคำสั่ง

`ATR` คือค่าความผันผวนของราคา ส่วน `R` คือระยะจากราคาเข้า actual fill ถึง initial SL
ของสถานะนั้น ตัวอย่าง entry 3000 และ initial SL 2997 หมายถึง 1R = ระยะราคา 3
ไม่ใช่กำไรเงินสดคงที่ initial R ต้องคงเดิมแม้ SL ถูกเลื่อนภายหลัง

### EA ทำงานร่วมกับ ML อย่างไร

```text
แท่ง M5/M15/H1 ที่ปิดแล้ว
  → ตรวจ regime และกฎกลยุทธ์
  → candidate พร้อม features
  → ML Service หรือ Offline Decision Replay
  → APPROVE / REJECT / ABSTAIN
  → ตรวจ Demo และ execution guards
  → ส่ง BUY/SELL พร้อม broker-side SL/TP
```

ML ไม่สร้างการเทรดขึ้นเองและเปลี่ยน BUY เป็น SELL ไม่ได้ ใช้ Logistic Regression
เป็น baseline และ LightGBM เป็น challenger จากโมเดลที่ฝึกไว้ล่วงหน้าและตรึงเวอร์ชันแล้ว
ผลทำนายประกอบด้วยความน่าจะเป็น `WIN`, `LOSS`, `TIMEOUT` และ estimated net R
ซึ่งคำนวณจากความน่าจะเป็นกับค่าเฉลี่ย net R ของแต่ละคลาสในชุดฝึก
ยังไม่มีโมเดล regression สำหรับ expected R แยกต่างหาก

โมเดลที่โหลดได้แต่ยังไม่อนุมัติจะตอบ `ABSTAIN` แม้คำนวณคะแนนได้
เมื่อ ML หายไป, timeout, ข้อมูลผิดรูปแบบ, หมดอายุ หรือเวอร์ชันไม่ตรงกัน จะไม่เปิดสถานะใหม่
การจัดการสถานะเดิมไม่ต้องขอ ML แต่ยังต้องมี MT5 ทำงาน เชื่อมต่อ และมีสิทธิ์ส่งคำสั่ง
ไม่มีการฝึกโมเดลออนไลน์หรือใช้ AI สั่งปิดสถานะใน V1

## 2. สิ่งที่ต้องติดตั้ง

### โปรแกรมและ dependencies

| สิ่งที่ต้องมี | ใช้ทำอะไร |
|---|---|
| MetaTrader 5 Desktop | เปิดกราฟ อ่านประวัติ ใช้งาน EA และ Strategy Tester; เวอร์ชันเว็บ/มือถือใช้รัน EA นี้ไม่ได้ |
| MetaEditor | เปิดไฟล์ `.mq5` และคอมไพล์เป็น `.ex5`; ปกติเข้าจาก MT5 ด้วย F4 |
| บัญชี Demo ของโบรกเกอร์ | ต้องมี symbol ที่ชื่อเริ่มด้วย `XAUUSD` เช่น `XAUUSD` หรือ `XAUUSDm` |
| Git หรือไฟล์ซอร์สจาก feature branch | ดาวน์โหลดโค้ดตามเวอร์ชันของ PR |
| Python | `pyproject.toml` กำหนด ≥3.11; CI ที่มีหลักฐานผ่านใช้ 3.11 และ 3.12 จึงแนะนำสองเวอร์ชันนี้ |
| Python dependencies | `numpy`, `pandas`, `scikit-learn`, `lightgbm`, `fastapi`, `uvicorn`, `pydantic`, `joblib` |
| เครื่องมือทดสอบ | ติดตั้งเพิ่มด้วย `.[test]`: `pytest`, `httpx`, `ruff` |

LightGBM ติดตั้งพร้อม dependencies ของโปรเจกต์ ไม่ต้องติดตั้ง ML Service เป็นโปรแกรมแยก
Service เป็น Python process ที่เปิดด้วย `scripts/serve.py`
หาก LightGBM import ไม่ผ่าน ให้ตรวจว่า Python/ระบบปฏิบัติการ/สถาปัตยกรรม CPU และ native runtime
รองรับ wheel ที่ติดตั้ง ไม่มีสคริปต์ติดตั้งระบบปฏิบัติการหรือ runtime เหล่านี้ให้ใน repository

ต้องมีพื้นที่เก็บประวัติราคา ไฟล์โมเดล และรายงาน รวมทั้งอินเทอร์เน็ตตอนติดตั้ง dependencies
หรือดาวน์โหลดข้อมูลโบรกเกอร์ ยังไม่ได้วัด minimum RAM/CPU/disk จึงไม่มีตัวเลขขั้นต่ำที่ยืนยันแล้ว
ไม่จำเป็นต้องใช้ GPU ตามโค้ดที่มี

### ใช้เครื่อง Mac ได้ไหม

**ใช้ส่วน Python บน Mac ได้ตามรูปแบบคำสั่งด้านล่าง** แต่ยังไม่มีผลทดสอบ macOS หรือ Apple Silicon
บันทึกไว้ในโปรเจกต์ หลักฐานปัจจุบันเป็น Linux และ CI บน Ubuntu

| รูปแบบใช้งาน | สิ่งที่ต้องทราบ |
|---|---|
| Python บน macOS | เตรียมข้อมูล ฝึกโมเดล และใช้เครื่องมือประเมินผลได้หากติดตั้ง dependencies สำเร็จ; ยังไม่ผ่านการยืนยันบน Mac |
| MT5 สำหรับ macOS ที่ใช้ Wine/ตัวห่อของผู้ให้บริการ | ต้องตรวจว่ามี MetaEditor, รองรับ EA/WebRequest และคอมไพล์ได้จริง; โปรเจกต์ยังไม่ได้ทดสอบรูปแบบนี้ |
| Windows VM บน Mac | ให้ติดตั้ง MT5, MetaEditor, Python และเปิด ML Service **ภายใน Windows VM เดียวกัน** เพื่อให้ตรงกับการใช้ loopback ของโค้ด; ความเข้ากันได้ของ VM/Windows ARM/dependencies ยังต้องตรวจตามเครื่อง |

EA ปัจจุบันยอมรับ `InferenceURL` ที่ขึ้นต้นด้วย `http://127.0.0.1:` เท่านั้น
`127.0.0.1` ของ Windows VM คือ VM ไม่ใช่ macOS host ดังนั้นเปิด Service บน Mac แล้ว
ให้ MT5 ใน Windows VM เรียกที่อยู่นี้จะไม่ได้ชี้ไปยัง Service บน Mac
การเชื่อม Service ข้ามเครื่องหรือข้าม VM ผ่าน IP อื่น **ยังไม่ได้รองรับใน EA นี้**

หากใช้ Windows VM ให้ทำขั้นตอน PowerShell ใน VM ส่วนคำสั่ง macOS ด้านล่างเหมาะกับส่วน Python
อย่าถือว่าผลทดสอบ Python บน Mac เป็นหลักฐานว่า MT5/Wine ทำงานถูกต้อง

## 3. วิธีติดตั้ง EA บน MT5

### 3.1 ดาวน์โหลดโค้ด

ใน PowerShell บน Windows หรือ Terminal บน macOS ที่มี Git:

```sh
git clone -b feature/scalping-gold-v1 https://github.com/Knerubon/scalping-gold.git
cd scalping-gold
```

หากมี checkout อยู่แล้ว ให้ตรวจ `git status` และเก็บงานที่แก้ไว้ก่อนเปลี่ยน branch
ขั้นตอนต่อจากนี้ถือว่าอยู่ในโฟลเดอร์ `scalping-gold`

### 3.2 วางไฟล์และคอมไพล์

1. เปิด MT5 Desktop ด้วยบัญชี Demo และคงปุ่ม Algo Trading เป็น OFF ขณะติดตั้ง
2. เลือก **File → Open Data Folder** ใช้โฟลเดอร์ที่ MT5 เปิดให้จริง ไม่เดาตำแหน่งจากโฟลเดอร์ติดตั้งโปรแกรม
3. สร้าง `MQL5/Experts/ScalpingGold/` แล้วคัดลอกไฟล์จาก `mql5/` ดังนี้:

   ```text
   MQL5/Experts/ScalpingGold/
   ├── ScalpingGold.mq5
   ├── GoldCore.mqh
   └── GoldJson.mqh
   ```

4. กด **F4** เปิด MetaEditor แล้วเปิดไฟล์ `ScalpingGold.mq5` ที่เพิ่งคัดลอก
5. กด **F7** แล้วดูแท็บ Errors ต้องแก้ errors ให้หมดและตรวจ warnings ก่อนใช้งาน
   หากสำเร็จ MetaEditor จะสร้าง `ScalpingGold.ex5` ไม่มีไฟล์ `.ex5` ที่คอมไพล์ไว้ให้ใน repository
6. บันทึก compiler log, build ของ MT5/MetaEditor และเวอร์ชันโค้ดที่ใช้
   คู่มือนี้ไม่ได้ยืนยันว่าขั้นตอนคอมไพล์ผ่านแล้ว

ไฟล์ `.mq5` คือซอร์สหลัก ส่วน `.mqh` คือไฟล์ include ที่ซอร์สเรียกใช้
ห้ามลืม `.mqh` ทั้งสองไฟล์หรือเปิดคอมไพล์จากโฟลเดอร์คนละชุด

### 3.3 เปิดกราฟและใส่ EA

1. เปิด Market Watch ด้วย **Ctrl+M** หา symbol ทองของโบรกเกอร์ หากไม่พบให้เปิดรายการ Symbols
2. เปิดกราฟ symbol นั้นและเลือก **M5**
3. เปิด Navigator ด้วย **Ctrl+N** → Expert Advisors → ScalpingGold หากยังไม่เห็นให้ Refresh
4. ลาก EA ใส่กราฟ ใน Inputs เลือก Load แล้วเลือก `config/demo-shadow.set` จาก checkout
5. ตั้ง `TradeSymbol` ให้ตรงชื่อกราฟทุกตัวอักษร เช่น `XAUUSDm` และตรวจ UTC offset
   หากชื่อทองเป็น `GOLD` โค้ดปัจจุบันจะปฏิเสธ เพราะกำหนดให้ชื่อเริ่มด้วย `XAUUSD`
6. คง `AUTO_TRADING=false` สำหรับ Shadow โดยยังไม่เปิดซื้อขายอัตโนมัติ

EA ตรวจว่าชื่อกราฟตรง `TradeSymbol` และ timeframe เป็น M5 หากไม่ตรงจะเริ่มต้นไม่สำเร็จ
ค่า `AUTO_TRADING=false` ไม่ปิดการอ่านข้อมูลหรือส่ง candidate ไปขอคะแนน ML

### 3.4 ตรวจว่าเริ่มทำงานแล้ว

เปิด Toolbox ด้วย **Ctrl+T** แล้วดู **Experts / Journal** ควรมี structured log เช่น:

```json
{"event":"startup","reason":"shadow_disabled"}
```

ตัวอย่างด้านบนย่อเฉพาะ fields สำคัญ log จริงมีเวลาและ state เพิ่มเติม
ถ้ามี `data` / `not_ready` ให้รอหรือโหลดประวัติ M5/M15/H1 เพิ่ม
EA ต้องมีข้อมูลอย่างน้อย 250 แท่งที่ปิดแล้วในแต่ละ timeframe และข้อมูล indicator พร้อมใช้งาน
การเห็นชื่อ EA บนกราฟอย่างเดียวไม่ได้พิสูจน์ว่าโหลดข้อมูล เชื่อม ML หรือส่งคำสั่งได้

### 3.5 ทดสอบ fixture ของ MQL5 ก่อน

สร้าง `MQL5/Scripts/ScalpingGoldTests/` แล้วคัดลอก `GoldCoreTests.mq5`,
`GoldCore.mqh`, `GoldJson.mqh` และ `ExportBars.mq5` ไปไว้ด้วยกัน
เปิด `.mq5` ทั้งสองไฟล์ใน MetaEditor และคอมไพล์ด้วย F7

รัน `GoldCoreTests` จาก Scripts บนกราฟ Demo สคริปต์นี้ไม่ส่งออร์เดอร์
ต้องตรวจผล `GoldCoreTests failures=0` ใน Experts จากนั้นคัดลอก
`MQL5/Files/GoldCoreTests.csv` ไปไว้ในโฟลเดอร์ repository แล้วใช้ Python ที่ติดตั้งในหัวข้อถัดไป:

```sh
python scripts/verify_parity.py GoldCoreTests.csv
```

นี่เป็นการตรวจ fixture ของกลยุทธ์และ features หกกรณี ยังไม่ครอบคลุม indicator
จากข้อมูลโบรกเกอร์หรือพฤติกรรมส่งคำสั่งจริง และยังไม่มีหลักฐานว่า native script นี้ผ่านแล้ว

## 4. วิธีติดตั้งและใช้งาน Machine Learning

### 4.1 ติดตั้ง Python dependencies

**Windows PowerShell** — ใช้ executable ใน virtual environment โดยตรง
จึงไม่ต้องเปลี่ยน PowerShell execution policy เพื่อ Activate:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
```

ถ้า `python` ไม่พบ ให้ติดตั้ง Python และตรวจ PATH ก่อน ไม่จำเป็นต้องเปลี่ยนชื่อคำสั่งของโปรเจกต์

**macOS Terminal** — ใช้สำหรับส่วน Python; ยังไม่ได้ยืนยันการรันบน macOS:

```sh
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pip check
python -m pytest -q
python -m ruff check src tests scripts
```

ตัวอย่างหลังจากนี้ใช้ PowerShell เป็นหลัก หากใช้ macOS ที่ Activate แล้ว ให้แทน
`.\.venv\Scripts\python.exe` ด้วย `python` และใช้คำสั่งบรรทัดเดียวเดิม
ไม่ต้องติดตั้ง LightGBM แยกจากคำสั่ง `pip install -e ".[test]"`

### 4.2 เตรียม Historical Data

ใช้ `ExportBars` ที่คอมไพล์ไว้ในหัวข้อ 3 รันจาก Navigator → Scripts ของ MT5
สคริปต์อ่านประวัติ ไม่เปิดออร์เดอร์ มี Inputs จริงสี่ตัว:

| Input | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `ExportSymbol` | `XAUUSD` | symbol ที่ต้องการส่งออก ต้องตรงกับข้อมูลที่จะทดสอบ |
| `FromServer` | `2024.01.01 00:00` | เวลาเริ่มต้นตามเซิร์ฟเวอร์โบรกเกอร์ |
| `ToServer` | `2025.01.01 00:00` | เวลาสิ้นสุดตามเซิร์ฟเวอร์โบรกเกอร์ |
| `BrokerUtcOffsetMinutes` | `0` | ส่วนต่างเวลาเซิร์ฟเวอร์จาก UTC หน่วยนาที ใช้แปลง timestamp เป็น UTC |

เลือกช่วงข้อมูลที่โบรกเกอร์มีจริง ต้องมีช่วง warmup อย่างน้อย 250 แท่ง H1 ก่อนช่วงประเมิน
หาก UTC offset เปลี่ยนเพราะ DST ให้ส่งออกแยกช่วง ตรวจเวลาและเรียงรวมอย่างระมัดระวัง
`ExportBars` ใช้ชื่อ `gold-m5.csv` เดิมทุกครั้ง คัดลอกหรือเปลี่ยนชื่อไฟล์เก็บไว้ก่อนส่งออกครั้งถัดไป
ค่าเริ่มต้นของช่วงวันที่เป็นเพียงตัวอย่าง ไม่ใช่ข้อมูลที่รวมมาให้

ผลลัพธ์อยู่ที่ `MQL5/Files/gold-m5.csv` ให้คัดลอกมาไว้ใน `data/gold-m5.csv` ของ repository
สร้างโฟลเดอร์ปลายทางใน PowerShell ได้ด้วย:

```powershell
New-Item -ItemType Directory -Force data
```

รูปแบบ CSV ที่ pipeline อ่านคือ:

```csv
time,open,high,low,close,spread
2025-01-01T00:00:00Z,2600.00,2601.00,2599.00,2600.50,0.20
```

บรรทัดข้างต้นเป็นตัวอย่างรูปแบบ ไม่ใช่ข้อมูลตลาดสำหรับฝึกโมเดล
`time` คือเวลา **เปิดแท่ง M5 ใน UTC** ต้องตรงช่วงห้านาที เรียงเพิ่มและไม่ซ้ำ
OHLC เป็นราคา Bid และ `spread` เป็นส่วนต่างราคา ไม่ใช่จำนวน points
`ExportBars` แปลง spread จาก points เป็นหน่วยราคาให้แล้ว
ข้อมูล NaN, spread ติดลบ หรือ OHLC ผิดรูปแบบจะถูกปฏิเสธ
Python รวม M5 เป็น M15/H1 เฉพาะช่วงที่มีแท่งครบ จึงต้องตรวจความตรงกับข้อมูล MT5 จริงอีกครั้ง

### 4.3 สร้าง candidate, features และ labels

ตัวอย่างนี้ใช้ `XAUUSD` และเซิร์ฟเวอร์ UTC+0 ต้องแก้ symbol/offset/tick size/ต้นทุนให้ตรงโบรกเกอร์
ก่อนใช้ผลวิจัย โดยเฉพาะ `BrokerUtcOffsetMinutes` คือเวลาของโบรกเกอร์ ไม่ใช่เวลาเครื่องหรือเวลาประเทศไทย
เช่นเซิร์ฟเวอร์ UTC+2 ใช้ `120` ไม่ใช่ `420` เพียงเพราะผู้ใช้อยู่ประเทศไทย

```powershell
.\.venv\Scripts\python.exe -m scalping_gold.cli prepare data/gold-m5.csv --output artifacts/data --symbol XAUUSD --server-utc-offset-minutes 0 --tick-size 0.01 --slippage 0.05 --commission 0.10 --be-allowance 0.20
```

| Argument | หน่วย/หน้าที่ |
|---|---|
| `--symbol` | ชื่อ symbol สำหรับ `signal_id`; ต้องตรง EA และ Replay |
| `--server-utc-offset-minutes` | ใช้กำหนดวันเซิร์ฟเวอร์สำหรับการประเมินพอร์ต; CSV ต้องเป็น UTC มาแล้ว ไม่ได้ใช้แปลง CSV ซ้ำ |
| `--tick-size` | ระยะ tick ของราคา |
| `--slippage` | ระยะราคาเสียเปรียบที่ใช้จำลอง |
| `--commission` | ต้นทุน commission ไป-กลับที่แปลงเป็นระยะราคาต่อหน่วยสถานะแล้ว ไม่ใช่ใส่จำนวนเงินต่อ lot โดยตรง |
| `--be-allowance` | ระยะราคาเผื่อต้นทุนสำหรับ BE ในตัวจำลอง ควรสอดคล้องกับ `CostAllowancePrice` |

ตัวเลขต้นทุนในตัวอย่างยังไม่ได้ calibrate กับโบรกเกอร์ ไม่รับประกันว่าใช้ได้กับบัญชีของคุณ
spread ถูกคิดผ่านราคาฝั่งซื้อ/ขายแล้ว และ model นี้ยังไม่ใช่การจำลอง swap/ค่าธรรมเนียมจริงครบทุกกรณี
DST หลาย offset ในข้อมูลชุดเดียวต้องตรวจข้อจำกัดการแบ่งวันของ pipeline ซึ่งรับ offset คงที่ต่อการรัน

ไฟล์ที่สร้างใน `artifacts/data/` ได้แก่:

- `candidates.jsonl` — แผนซื้อขายและ features จากกฎกลยุทธ์
- `labels-fixed.csv`, `labels-be.csv`, `labels-trailing.csv`, `labels-hybrid.csv` — ผลจำลองแต่ละ exit mode
- `exit-comparison.json` — ต้นทุน hash ของข้อมูล จำนวน candidate และสถิติของแต่ละ mode

การ label ใช้ net R หลังต้นทุน หาก SL และ TP ถูกแตะใน OHLC แท่งเดียวกัน จะสมมติ SL ก่อน
SL ที่เลื่อนใหม่มีผลตั้งแต่แท่งถัดไป gap ผ่าน SL ใช้ราคาเปิดฝั่งที่เสียเปรียบกว่า
และข้อมูลไม่ครบถึง horizon จะไม่ถูกสร้างเป็น timeout อย่างเดาสุ่ม
ผล `TIMEOUT` แยกเป็นอีกคลาส แม้ net R อาจเป็นบวก

### 4.4 Train Model และดูรายงาน

```powershell
.\.venv\Scripts\python.exe -m scalping_gold.train artifacts/data/labels-hybrid.csv --output artifacts/models --version gold-v1-research
.\.venv\Scripts\python.exe scripts/evaluate_matrix.py artifacts/data artifacts/models --output artifacts/comparison.json
```

คำสั่ง train ฝึก **ทั้ง Logistic Regression และ LightGBM** ไม่ต้องใส่ option เลือกชนิดโมเดล
ข้อมูลต้องเพียงพอหลัง purge/embargo และมีทั้ง `LOSS`, `TIMEOUT`, `WIN` ในช่วง fit และ calibration
ถ้าฝึกข้อมูลสังเคราะห์เพื่อทดสอบ ให้เพิ่ม `--synthetic` เพื่อระบุว่าใช้อนุมัติโมเดลไม่ได้

ข้อมูลถูกแบ่งตามเวลาเป็น fit, calibration, threshold validation และ test
โดยจุดแบ่งเริ่มต้นประมาณ 50% / 65% / 80% ของเวลาสัญญาณที่ไม่ซ้ำ
ตัด labels ที่ข้ามขอบชุดและเว้น embargo 300 วินาที ทำ sigmoid calibration บนช่วงแยก
เลือก threshold จาก validation และรายงาน expanding walk-forward อีกสามช่วง
หากไม่มี threshold ที่มีจำนวนเทรด validation เพียงพอตามกฎในโค้ด จะใช้ threshold 1.0
จึงอาจไม่อนุมัติสัญญาณใดเลย ไม่ใช่เหตุให้ปรับ threshold จากผล test ย้อนหลัง

ผลลัพธ์หลัก:

```text
artifacts/models/
├── evaluation.json
├── logistic/
│   ├── model.joblib
│   ├── manifest.json
│   └── test-scores.csv
└── lightgbm/
    ├── model.joblib
    ├── manifest.json
    └── test-scores.csv
```

อ่าน `evaluation.json` เพื่อดู baseline, expectancy, profit factor, drawdown ใน R,
rejection rate, calibration และ walk-forward ส่วน `artifacts/comparison.json`
เปรียบเทียบ EA-only/LR/LightGBM กับ exit ทั้งสี่แบบบน candidate OOS ที่ตรงกัน
OOS คือข้อมูลที่ไม่ใช้ fit/calibrate/เลือก threshold ของโมเดลนั้น
ช่วง test ของ walk-forward บาง fold อาจทับกัน ห้ามนำมาบวกเป็นเทรดอิสระทั้งหมด

อย่าโหลด `model.joblib` จากแหล่งที่ไม่เชื่อถือ เพราะ joblib สามารถรันโค้ดขณะ deserialize ได้
การตรวจ hash ช่วยตรวจความตรงของ artifact แต่ไม่ได้ทำให้ไฟล์อันตรายปลอดภัย

### 4.5 เปิด ML Inference Service

เปิด PowerShell อีกหน้าต่าง เข้าโฟลเดอร์ repository แล้วเลือก artifact ที่ต้องการ:

```powershell
$env:SG_ARTIFACT="artifacts/models/logistic"
.\.venv\Scripts\python.exe scripts/serve.py
```

บน macOS ที่ Activate virtual environment แล้ว คำสั่งส่วน Python คือ:

```sh
export SG_ARTIFACT=artifacts/models/logistic
python scripts/serve.py
```

Service ฟังที่ `127.0.0.1:8000` และเปิด INFO logs ที่มีคะแนน ความน่าจะเป็น estimated net R
เหตุผลการตัดสินใจ และ latency หากเลือก LightGBM ให้เปลี่ยน path เป็น
`artifacts/models/lightgbm` และใช้ manifest ของ LightGBM ให้ตรงกันทั้งหมด

`config/service.env.example` เป็นตัวอย่าง environment variables เท่านั้น
โค้ดไม่ได้โหลดไฟล์ `.env` ให้อัตโนมัติ ต้องตั้ง `$env:...` หรือ `export` เอง
หลังเปลี่ยน artifact หรือ approval ให้หยุด Service ด้วย Ctrl+C แล้วเปิดใหม่

ตรวจ health จาก PowerShell อีกหน้าต่าง:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" | ConvertTo-Json
```

หรือบน macOS:

```sh
curl http://127.0.0.1:8000/health
```

`model_loaded=true` แปลว่าโหลดโมเดลสำเร็จ ส่วน `approved=false` เป็นสถานะปกติก่อนมีการอนุมัติ
`status=shadow_or_unavailable` จึงอาจหมายถึงโมเดลโหลดแล้วแต่ยังไม่อนุมัติ หรือโมเดลไม่พร้อม
`status=ready` หมายถึงโหลดและผ่านเงื่อนไข approval ของ Service แล้ว ไม่ได้ยืนยันว่า EA ต่อสำเร็จ
ดู schema ของ API ได้ที่ `http://127.0.0.1:8000/docs`

### 4.6 ให้ EA เชื่อม ML แบบ Shadow และตรวจการเชื่อมต่อ

1. ใน MT5 เลือก **Tools → Options → Expert Advisors → Allow WebRequest for listed URL**
   แล้วเพิ่ม `http://127.0.0.1:8000`
2. เปิด `artifacts/models/logistic/manifest.json` ตรวจ `model_version` และ `model_hash`
   บน PowerShell ใช้คำสั่งนี้เพื่อดูได้:

   ```powershell
   Get-Content artifacts/models/logistic/manifest.json
   ```

3. ใส่ค่าทั้งสองตรงตามไฟล์ลง `ApprovedModelVersion` และ `ApprovedModelHash` ใน EA
   และคง `AUTO_TRADING=false` ชื่อ parameter มีคำว่า Approved แต่การกรอกเพียงเท่านี้
   **ไม่ได้อนุมัติโมเดล** หากปล่อยว่าง EA จะไม่เรียก HTTP scoring
4. ตรวจ `InferenceURL=http://127.0.0.1:8000/score` และให้ `ReplayFile` ว่างสำหรับกราฟปกติ
5. รอ candidate จากแท่ง M5 ที่ปิดแล้ว ตรวจ Service log ว่ามี `event=score`
   และ `signal_id` ตรงกับ `MQL5/Files/scalping-gold-candidates.jsonl` ของ EA

ยังไม่อนุมัติโมเดลควรเห็น `decision=ABSTAIN`, `reason=model_unapproved`
เมื่อโมเดล/เวอร์ชัน/เวลาอื่น ๆ ถูกต้อง นี่เป็นหลักฐานการเดินทางของ request ถึง Service
แม้ EA จะบันทึกเหตุผลรวมเป็น `abstain_or_reject`
หากยังไม่มี candidate, มี exposure บน symbol หรือไม่กรอก model version/hash อาจไม่มี HTTP request
ไม่ควรสรุปว่า connection เสียจากการไม่เห็นออร์เดอร์

ไฟล์ export ที่เขียนแบบ append อาจมีข้อมูลรอบก่อน ต้องเลือกช่วงเวลาเดียวกับข้อมูล Python
ก่อนเปรียบเทียบ parity เช่นหลังคัดลอกไฟล์ request ของ EA มาไว้ใน `artifacts/` แล้ว:

```powershell
.\.venv\Scripts\python.exe scripts/compare_exports.py artifacts/ea-candidates.jsonl artifacts/data/candidates.jsonl
```

`artifacts/ea-candidates.jsonl` ในคำสั่งคือสำเนาที่ผู้ใช้คัดลอกจาก
`MQL5/Files/scalping-gold-candidates.jsonl` ไม่ใช่ไฟล์ที่สร้างให้อัตโนมัติ
เครื่องมือต้องพบ candidate IDs ตรงกันทั้งชุดและ features ใกล้เคียงตาม tolerance ในสคริปต์
การมี feature hash เท่ากันอย่างเดียวไม่ได้ยืนยันค่า indicator เท่ากัน

### 4.7 การอนุมัติโมเดลหลังมีหลักฐานจริง

การฝึกเสร็จไม่ทำให้เทรดได้อัตโนมัติ ต้องมีผู้ตรวจ native parity, ผล OOS, ต้นทุนและ
acceptance checklist ใน [docs/VALIDATION.md](docs/VALIDATION.md) ก่อน
ขั้นตอนนี้เป็นสิ่งที่มนุษย์ต้องพิจารณาหลังทดสอบ ไม่ใช่ขั้นตอนให้ทำเครื่องหมายผ่านทันทีเพียงเพื่อเปิดออร์เดอร์

หลังตรวจหลักฐานครบแล้ว จึงเตรียมไฟล์อนุมัติส่วนตัว:

```powershell
Copy-Item config/approval.example.json config/local-approval.json
(Get-FileHash artifacts/models/logistic/model.joblib -Algorithm SHA256).Hash.ToLowerInvariant()
(Get-FileHash artifacts/models/evaluation.json -Algorithm SHA256).Hash.ToLowerInvariant()
```

แก้ `config/local-approval.json` ด้วย editor ให้มี `model_hash` และ `evaluation_sha256`
ตามผลข้างต้น ชื่อ `reviewer` และ `approved=true` เฉพาะหลังผู้ตรวจยอมรับหลักฐานจริง
ไฟล์ตัวอย่างเริ่มด้วย `approved=false`; ห้ามใช้ข้อมูลสังเคราะห์หรือแก้รายงานให้ดูเหมือนข้อมูลจริง
ไม่ต้องแก้ `approved` ใน `manifest.json` เพื่อข้ามขั้นตอน เพราะ Service ใช้ไฟล์อนุมัติแยก

จากนั้นเปิด Service ใหม่โดยตั้ง environment ทั้งสองตัวใน PowerShell เดียวกัน:

```powershell
$env:SG_ARTIFACT="artifacts/models/logistic"
$env:SG_APPROVAL="config/local-approval.json"
.\.venv\Scripts\python.exe scripts/serve.py
```

Service ตรวจ hash, ชื่อผู้ตรวจ, `synthetic=false` และลำดับเวลา test หลัง threshold validation
แต่พิสูจน์แทนมนุษย์ไม่ได้ว่าข้อมูลจริงหรือมีผู้ตรวจอย่างรอบคอบแล้ว
ไฟล์ `config/local-approval.json` ถูก ignore โดย Git โมเดลที่อนุมัติยังเป็น frozen model
หากเปลี่ยนโมเดลหรือรายงาน ต้องตรวจและอนุมัติ artifact/hash ชุดใหม่

## 5. วิธีตั้งค่า EA

### 5.1 Input Parameters ทั้งหมด

เปิด Properties ของ EA → Inputs หรือกด F7 ที่กราฟเมื่อ EA ถูกติดตั้งอยู่
F7 ในกราฟใช้เปิด Properties แต่ F7 ใน MetaEditor ใช้คอมไพล์
การเปลี่ยน Inputs ทำให้ EA เริ่มต้นใหม่ ควรอ่าน log และตรวจสถานะเดิมทุกครั้ง

| Parameter | ชนิด / ค่าเริ่มต้น | ความหมายและข้อกำหนดจริง |
|---|---|---|
| `AUTO_TRADING` | `bool` / `false` | อนุญาตการเปิดสถานะใหม่เมื่อเป็น `true` และผ่าน guards อื่นทั้งหมด; `false` ยังอ่านสัญญาณและจัดการสถานะเดิมได้หาก MT5 มีสิทธิ์ซื้อขาย |
| `EmergencyStop` | `bool` / `false` | `true` หยุดเปิดสถานะใหม่ แต่ไม่สั่งปิดทุกสถานะทันทีและไม่ถอด broker-side SL/TP |
| `TradeSymbol` | `string` / `XAUUSD` | ต้องตรงชื่อกราฟและชื่อเริ่มด้วย `XAUUSD`; ใช้กราฟ M5 เท่านั้น |
| `Magic` | `ulong` / `16012026` | ระบุสถานะของ EA ที่จะจัดการ; ไม่ควรเปลี่ยนขณะมีสถานะเดิม เพราะ EA จะไม่ถือว่าเป็นสถานะของ Magic ใหม่ |
| `BrokerUtcOffsetMinutes` | `int` / `0` | เวลาเซิร์ฟเวอร์ลบ UTC หน่วยนาที; ยอมรับช่วง −840 ถึง 840 ต้องตรวจ DST เอง |
| `MaxSpreadPoints` | `int` / `50` | spread สูงสุดก่อนเปิดออร์เดอร์ หน่วย broker points ต้องมากกว่า 0; ค่าเริ่มต้นยังไม่ผ่านการ calibrate |
| `MaxDeviationPoints` | `int` / `10` | ค่า deviation ที่ส่งในคำสั่งซื้อขาย หน่วย points ต้องไม่ติดลบ; ไม่รับประกันขีดจำกัด slippage ทุก execution mode |
| `CostAllowancePrice` | `double` / `0.20` | ระยะราคาเผื่อต้นทุนเมื่อเลื่อน BE ต้องไม่ติดลบ ไม่ใช่เงินต่อ lot หรือจำนวน points |
| `InferenceURL` | `string` / `http://127.0.0.1:8000/score` | endpoint สำหรับกราฟปกติ; EA ยอมรับ prefix `http://127.0.0.1:` เท่านั้น ต้องตรง port และ route ของ Service |
| `InferenceTimeoutMs` | `int` / `2000` | เวลารอ HTTP หน่วยมิลลิวินาที ช่วง 1–2000; ช้าหรือผิดพลาดให้ abstain |
| `ApprovedModelVersion` | `string` / ว่าง | ต้องตรง `model_version` ใน manifest ของโมเดลที่ Service โหลด; ว่างแล้วไม่เรียก scoring |
| `ApprovedModelHash` | `string` / ว่าง | SHA256 ของ `model.joblib` ต้องตรง manifest เป็นเลขฐานสิบหกตัวพิมพ์เล็ก 64 ตัวอักษรสำหรับ scoring |
| `ExportCandidates` | `bool` / `true` | เขียน candidate requests และแผน entry/SL/TP ลงไฟล์ JSONL ใน `MQL5/Files/`; event logs แยกต่างหากและไม่ได้ปิดตาม parameter นี้ |
| `ReplayFile` | `string` / ว่าง | ชื่อไฟล์ JSONL ภายใน file sandbox ของ Tester; ใช้เฉพาะ Strategy Tester ไม่ได้ทำให้กราฟปกติใช้ Replay |

`ApprovedModelVersion` ยอมรับตัวอักษรอังกฤษ ตัวเลข `_`, `-`, `.`
และ API จำกัดความยาวไม่เกิน 80 ตัวอักษร ใช้ชื่อเวอร์ชันที่เรียบง่ายและตรงกันทุกจุด
ห้ามแก้ชื่อหรือ hash เพียงเพื่อให้ error หายโดยไม่ตรวจว่าเป็น artifact ชุดเดียวกัน

### 5.2 Risk per Trade และ execution guards ที่กำหนดตายตัว

**ยังไม่มี Input `RiskPercent`, lot คงที่, ค่า multiplier ของ SL/TP, เกณฑ์ BE/Trailing,
Time Exit หรือปุ่มเปิด/ปิดแต่ละกลยุทธ์** ตัวเลขต่อไปนี้อยู่ในโค้ด
หากเปลี่ยนต้องแก้ซอร์ส ทดสอบใหม่ และคอมไพล์ใหม่ ไม่ใช่เพิ่มชื่อ option ลง `.set` เอง

| กฎ | ค่าที่มีจริง |
|---|---|
| งบความเสี่ยงเข้าเทรด | 0.5% ของ equity ปัจจุบัน คำนวณ volume จาก `OrderCalcProfit` ที่ SL |
| จำนวน exposure | ไม่เปิดใหม่หากมี position หรือ order ของ `TradeSymbol` อยู่แล้ว รวมของผู้ใช้/EA อื่นใน terminal นี้ |
| จำนวนเทรดสูงสุด | 5 สถานะที่เปิดต่อวันเซิร์ฟเวอร์สำหรับ symbol ที่กำหนด |
| Daily equity lock | หยุดเปิดใหม่เมื่อ equity ≤98% ของ daily baseline รวมผล floating ผ่าน equity |
| ขาดทุนต่อเนื่อง | ล็อกเมื่อพบสถานะที่ปิดครบขาดทุนต่อเนื่อง 3 ครั้งในวันนั้น รวมต้นทุนจาก deal history |
| Margin | ต้องคำนวณได้ และใช้ไม่เกิน 90% ของ free margin ตามการตรวจในโค้ด |
| Quote | ต้องอ่านได้และไม่เก่าเกิน 5 วินาทีสำหรับการเข้า |
| ราคาไล่จาก candidate | ไม่เกิน 0.5 × ATR(M5) หลังรอ ML; Breakout ตรวจระยะจากขอบกรอบซ้ำด้วย |

ตัวอย่าง equity 10,000 หน่วยเงินบัญชี มีงบ SL ประมาณ 50 หน่วยก่อนค่าใช้จ่ายที่ยังไม่ทราบ
EA ไม่ได้กำหนดว่าเงินจำนวนนี้ต้องเท่ากับกี่ lot ของทองทุกโบรกเกอร์
volume ต้องปัดลงตาม step และอยู่ระหว่าง min/max หากต่ำกว่า min จะข้าม ไม่ปัดขึ้นให้เสี่ยงเกินงบ
commission และ gap/slippage จริงอาจทำให้ขาดทุนเกิน 0.5% ได้

daily locks ถูกบันทึกไว้และไม่ปลดเพียงเพราะ equity ฟื้นขึ้นหรือมีเทรดกำไรตามมา
หากเริ่ม EA กลางวันโดยมี exposure ในบัญชีและไม่มี baseline เดิม ระบบจะล็อกวันนั้นอย่างระมัดระวัง
ไม่ควรลบ Global Variables เพื่อบังคับให้เปิดออร์เดอร์ต่อ

### 5.3 Stop Loss / Take Profit และ Hybrid Exit

| กลยุทธ์ | SL ในแผนสัญญาณ | TP เป้าหมาย | เริ่ม BE | เริ่ม Trailing / ระยะ | Time Exit |
|---|---|---|---|---|---|
| Trend Pullback | 1.5 × ATR(M5) | 2R | กำไรถึง 1R | 1.5R / 1 × ATR(M5) | 60 นาที |
| Range Reversal | นอกกรอบอีก 0.5 × ATR(M5) | กลางกรอบ เมื่อ RR ≥1.5 | 0.8R | ปิดการใช้ Trailing | 60 นาที |
| Breakout | 1.5 × ATR(M5) | 2.5R | 1R | 1.5R / 1.2 × ATR(M5) | 90 นาที |

ระยะ SL ของ candidate อิงราคาขณะสร้างสัญญาณ ระยะจาก actual fill อาจต่างออกไปเมื่อราคาเคลื่อน
EA เก็บ initial R จาก actual entry กับ initial SL หลังตรวจการ finalize ของ entry order
และปรับเป้าหมาย TP ของ Trend/Breakout ให้สอดคล้อง actual R ตามข้อกำหนดโบรกเกอร์
การ reconcile นี้และ partial fills ยังต้องทดสอบ native

BUY ใช้ Bid ประเมินกำไรเพื่อออก SELL ใช้ Ask
BE จะเสนอ SL ที่ actual entry บวก `CostAllowancePrice` สำหรับ BUY หรือหักสำหรับ SELL
ใช้เผื่อต้นทุนเท่านั้น ไม่รับประกันว่าผลสุทธิจะไม่ขาดทุน
Trailing ใช้ ATR ของ M5 ที่ปิดแล้ว ขยับ SL เฉพาะทิศที่ดีขึ้น
โดยแต่ละขั้นไม่น้อยกว่า 0.2 ATR และหนึ่ง tick พร้อมตรวจ stop/freeze levels

Time Exit เป็นคำสั่งจาก EA ไม่ใช่คำสั่งตั้งเวลาที่ฝากไว้บนเซิร์ฟเวอร์
เมื่อไม่มี state ที่เชื่อถือได้ โค้ดยังรักษา broker protection และพยายามใช้ time exit
แบบระมัดระวังที่ 60 นาที แต่ไม่สร้าง initial R ใหม่จาก SL ที่เลื่อนแล้ว
หากพบสถานะของ EA ไม่มี SL หรือ TP จะพยายามปิดฉุกเฉินเมื่อส่งคำสั่งได้
ทั้งหมดนี้ยังไม่ใช่หลักฐานว่าพฤติกรรมโบรกเกอร์ผ่านการทดสอบแล้ว

### 5.4 Spread Filter และหน่วยราคา

spread ตอนเข้า = `(Ask − Bid) / SYMBOL_POINT` แล้วเปรียบเทียบกับ `MaxSpreadPoints`
เช่นถ้า point = `0.01` ค่า 50 points คือส่วนต่างราคา `0.50`
แต่ถ้า point = `0.001` ค่า 50 points คือส่วนต่างราคา `0.050`
จึงไม่ควรนำเลข 50 ไปใช้กับทุกโบรกเกอร์โดยไม่ตรวจ digits, point และ tick size

EA ใช้ spread จากแท่งที่ปิดใน feature snapshot แต่ตรวจ quote spread ปัจจุบันอีกครั้งก่อนเข้า
Python ใช้ spread ที่อยู่ในข้อมูล historical ซึ่งอาจไม่ตรง spread ที่ซื้อขายได้จริงขณะนั้น

## 6. วิธีทดสอบ Backtest

### 6.1 เข้าใจสองรูปแบบการทดสอบ

- **Python replay/evaluation** ใช้ historical OHLC จำลอง outcome และเปรียบเทียบโมเดล/exit modes
  ไม่ใช่ MT5 Strategy Tester และไม่ยืนยันการส่งคำสั่งจริง
- **MT5 Strategy Tester** รัน EA ที่คอมไพล์แล้วกับข้อมูล tick/โบรกเกอร์
  โค้ดจะอ่าน ML decision จากไฟล์ Replay แทน HTTP เมื่ออยู่ใน Tester

ตอนนี้ยังไม่มีรายงาน MT5 Backtest ที่ยืนยันว่าผ่าน
การเลือก `AUTO_TRADING=true` ใน Tester เป็นเพียงการอนุญาตคำสั่งจำลองใน Tester
ไม่ทำให้กราฟบัญชีปกติได้รับอนุญาต และบัญชีที่ EA มองว่าไม่ใช่ DEMO ยังถูกปฏิเสธ

### 6.2 สร้าง Offline ML Decision Replay

ใช้ candidate และ `test-scores.csv` ของโมเดลชุดเดียวกัน เฉพาะ OOS หลัง
`threshold_through` ห้ามใช้โมเดลที่เรียนรู้ข้อมูลอนาคตของช่วงกำลังทดสอบ
ตัวสร้าง Replay จะใช้โมเดลคำนวณคะแนนใหม่สำหรับ IDs ที่มีใน test-scores
ไม่ได้อนุมัติตามการแก้ค่า CSV ด้วยมือ

จาก PowerShell ใน repository หลังเตรียมข้อมูล/โมเดลแล้ว:

```powershell
.\.venv\Scripts\python.exe -m scalping_gold.cli replay artifacts/models/logistic/test-scores.csv artifacts/data/candidates.jsonl artifacts/models/logistic/manifest.json artifacts/logistic-replay.jsonl --symbol XAUUSD
```

หากยังไม่มี approval ที่ถูกต้อง ไฟล์จะมีผล `ABSTAIN` และไม่ควรมีออร์เดอร์จาก Replay นั้น
ถ้าเป็นโมเดลที่ผู้ตรวจอนุมัติแล้วตามหัวข้อ 4.7 ให้ตั้ง `SG_APPROVAL` ใน PowerShell
ที่รันคำสั่ง Replay ด้วย เพราะตัว export อ่าน environment ของ process ตัวเอง:

```powershell
$env:SG_APPROVAL="config/local-approval.json"
```

ใช้ `--symbol XAUUSDm` แทนเมื่อข้อมูลและ EA ใช้ชื่อนั้น โมเดลอีกชนิดต้องใช้ path ของ
`lightgbm` ให้ครบทั้ง scores และ manifest การมีไฟล์ไม่เท่ากับ Replay ใช้งานได้
ต้องตรวจ `signal_id`, strategy, direction, เวลา UTC, schema/feature/model versions และ expiry
ตามที่ EA ตรวจจริง

### 6.3 นำ Replay เข้า Tester

1. คัดลอก `artifacts/logistic-replay.jsonl` ไปที่ `MQL5/Files/logistic-replay.jsonl`
   ของ terminal ที่ใช้ทดสอบ
2. เพื่อให้ MT5 ส่งไฟล์ไป local test agent ให้เพิ่มบรรทัดต่อไปนี้ใน **สำเนา EA ที่ใช้ทดสอบ**
   แล้วคอมไพล์ใหม่หลังไฟล์ Replay มีอยู่แล้ว:

   ```mql5
   #property tester_file "logistic-replay.jsonl"
   ```

3. ตั้ง Input `ReplayFile=logistic-replay.jsonl` และ pin
   `ApprovedModelVersion`/`ApprovedModelHash` ตาม manifest ที่สร้าง Replay
4. ตรวจว่า agent มองเห็นไฟล์ใน sandbox `MQL5/Files/` ของตัวเอง
   การกำหนดชื่อไฟล์ผ่าน Input อย่างเดียวไม่ได้รับประกันว่าจะถูกส่งไป agent อัตโนมัติ
5. ใช้ local agent สำหรับเริ่มตรวจสอบ ไม่ถือว่าการส่งไฟล์ให้ cloud/remote agent ผ่านแล้ว

ยังไม่มีระบบส่ง Replay ไป agent แบบอัตโนมัติใน repository
Replay มีเวลาอนุมัติสั้นเพื่อปฏิเสธคำตอบเก่า หาก tick มาถึงช้าอาจไม่เข้าแม้มีสัญญาณ
ห้ามขยายเวลาหรือแก้ไฟล์ย้อนหลังเพื่อทำให้รายงานดูดีขึ้น

### 6.4 ตั้งค่า Strategy Tester

1. กด **Ctrl+R** ใน MT5 เลือก EA `ScalpingGold/ScalpingGold.ex5`
2. เลือก symbol ตรงกับข้อมูลและ `TradeSymbol` และ timeframe **M5**
3. เลือก **Every tick based on real ticks** เมื่อโบรกเกอร์มีข้อมูลจริง
   จดแหล่งข้อมูลและช่วงที่ tick ไม่ครบไว้ด้วย
4. เลือกช่วงวันที่ประเมินหลัง `threshold_through` ของ manifest
   และมีประวัติ M5/M15/H1 ก่อนหน้านั้นเพียงพอสำหรับ warmup
   หลังเริ่ม EA ยังต้องรอ regime ยืนยันสอง M15 closes จึงอาจไม่ตรงกับการเริ่ม Python
   ที่มีประวัติ detector ต่อเนื่องทันที ต้องเทียบช่วงเริ่มนับผลให้ตรงกัน
5. ตั้ง deposit, currency และ leverage ให้เป็นสมมติฐาน Demo ที่จะทดสอบ
   อย่าใช้ค่าทุนต่างกันแล้วเปรียบเทียบกำไรเงินสดโดยไม่ปรับความเสี่ยง
6. เริ่มด้วย `AUTO_TRADING=false` เพื่อตรวจโหลดข้อมูล candidate และ parity
   แล้วจึงทดสอบคำสั่งจำลองด้วย `AUTO_TRADING=true` ใน **Tester Inputs เท่านั้น**
   เมื่อผ่านเงื่อนไขโมเดลและการตรวจ native ก่อนหน้า
7. กด Start แล้วตรวจ Journal ของ Tester ทั้งตอนเริ่มต้นและเวลาที่ควรมีสัญญาณ

`config/tester.example.ini` เป็น template ที่มีค่าตัวอย่าง `Model=4` สำหรับ real ticks,
M5, deposit 10000, USD, leverage 100 และช่วงปี 2025
ไม่ได้เป็นการตั้งค่าที่ผ่านการทดสอบหรือช่วง OOS ที่รับรองแล้ว
หากใช้ template ต้องคัดลอก `.set` ไปตำแหน่งที่ Tester หาได้จริง เช่น
`MQL5/Profiles/Tester/demo-shadow.set` สำหรับ `ExpertParameters=demo-shadow.set`
และปรับวันที่/ชื่อ EA/ข้อมูลตามการติดตั้ง ห้ามคัดลอกช่วงวันที่เดิมโดยไม่ตรวจ manifest

### 6.5 ดูและเก็บผล Backtest

ตรวจแท็บผลลัพธ์ รายงาน Backtest, Graph และ Journal
ชื่อแท็บอาจต่างกันตาม build ให้ดูจำนวนเทรด BUY/SELL, SL/TP, net result,
profit factor, drawdown, ระยะเวลาถือ และสาเหตุ rejection/timeout
บันทึก report พร้อม `.set`, compiler log, EA build/commit, model/data hashes และต้นทุน

ศูนย์ออร์เดอร์อาจเกิดจาก `AUTO_TRADING=false`, โมเดลยังไม่อนุมัติ,
regime ไม่มีสัญญาณ, replay ไม่ตรง หรือ guard ปฏิเสธ ไม่ใช่ผล backtest ว่าไม่มีความเสี่ยง
Python matrix รายงาน drawdown หน่วย R และจำกัดพอร์ตจาก completed trades
ยังไม่จำลอง floating-loss lock ระหว่างแท่งเหมือนการทดสอบ real ticks ของ EA
โหมด `fixed`/`be`/`trailing` มีการ censor ที่ horizon เพื่อสร้างชุดเปรียบเทียบ
จึงไม่ใช่หลักฐานว่า EA มี Input ให้เลือก exit modes เหล่านั้น

## 7. วิธีเปิด Auto Trading บน Demo

### 7.1 เงื่อนไขก่อนเริ่มทดลอง

ทำหลังคอมไพล์ native, parity, real-tick tests, ตรวจข้อกำหนดโบรกเกอร์ และอนุมัติ frozen model
ตามหลักฐานจริงแล้วเท่านั้น ปัจจุบันยังไม่มีหลักฐาน native ชุดดังกล่าวใน repository
ขั้นตอนต่อไปเป็นคู่มือสำหรับการทดลองในอนาคต ไม่ใช่รายงานว่าได้เปิดเทรดแล้ว

1. เปิดบัญชี **Demo โดยเฉพาะ** จากผู้ให้บริการ ตรวจ account type และ demo server
   กับโบรกเกอร์ อย่าอาศัยชื่อบัญชีหรือชื่อเซิร์ฟเวอร์อย่างเดียว
2. EA ใช้ `AccountInfoInteger(ACCOUNT_TRADE_MODE)` และต้องเท่ากับ
   `ACCOUNT_TRADE_MODE_DEMO` ที่เริ่มต้นและก่อนส่งคำสั่ง ไม่ใช่ดูคำว่า Demo ในชื่อ
   หากพบ `DEMO account required; REAL and CONTEST are rejected` ใน log ให้ตรวจบัญชี
   ไม่แก้ guard เพื่อผ่านบัญชีเงินจริง
3. ใช้ symbol/M5/UTC offset/model hashes ที่ทดสอบแล้ว ไม่เริ่มพร้อม manual position
   หรือ pending order บน symbol เดียวกัน
4. เปิด Service บน loopback เดียวกับ MT5 และตรวจ `/health`, approval และ request จริงจาก Shadow
5. ตั้ง `EmergencyStop=false` แล้วผู้ใช้จึงเปลี่ยน `AUTO_TRADING=true`
6. อนุญาตการซื้อขายของ EA ใน Properties และเปิดปุ่ม Algo Trading ของ MT5
   ให้ตรวจทั้งสิทธิ์ terminal, EA และ account ไม่ใช่ดู Input ตัวเดียว

การเริ่มด้วย `AUTO_TRADING=true` อาจมี log `demo_execution_configured`
ไม่ได้หมายความว่าจะมีออร์เดอร์ทันที ยังต้องรอ candidate และผ่าน ML/guards ทุกตัว
ระบบไม่ใช้ martingale, grid หรือ averaging down และยังคงต้องมี broker-side SL/TP

### 7.2 ตรวจ BUY/SELL ที่เปิด

ดู Toolbox → Trade ตรวจ symbol, ทิศทาง, volume, ราคา fill และ SL/TP ที่มีอยู่จริง
ดู History หลังปิดสถานะ และดู event `order` กับ retcode ใน Experts/Journal
คำว่า `_sent` ใน log หมายถึงผล `OrderSend` ระดับ request ไม่ได้ยืนยันว่าสถานะเปิดครบ
ต้องตรวจ retcode และ positions/orders/history โดยเฉพาะ `PLACED` หรือ partial fills

เทียบ `signal_id` กับ candidate/Service log และทิศทางที่ EA วางแผน
ไม่มีหน้าจอ dashboard หรือปุ่มจัดการออร์เดอร์เฉพาะของโปรเจกต์ ต้องตรวจผ่าน MT5 และ logs
การเลื่อน SL, time exit และ recovery ต้องเก็บหลักฐานแยก ไม่อนุมานจากการเห็นเทรดแรกสำเร็จ

### 7.3 หยุด EA อย่างปลอดภัย

**หากต้องการหยุดเข้าใหม่แต่ให้ EA จัดการสถานะเดิมต่อ:** ตั้ง `EmergencyStop=true`
หรือ `AUTO_TRADING=false` โดยคง terminal เปิด เชื่อมต่อ และมีสิทธิ์ส่งคำสั่ง
EA จะยังพยายามจัดการ BE/Trailing/Time Exit และเก็บ broker SL/TP
ทั้งสอง Input ไม่ได้สั่งปิดสถานะทั้งหมดทันที

**หากปิดปุ่ม Algo Trading, ถอน EA, ปิด MT5, ปิดเครื่อง หรือขาดการเชื่อมต่อ:**
EA ไม่สามารถส่งคำสั่งเลื่อน SL หรือ time exit ได้ broker-side SL/TP ที่ฝากไว้จะยังอยู่
แต่อาจเกิด slippage/gap จึงไม่ควรปิดโปรแกรมแล้วเข้าใจว่า Hybrid Exit ยังทำงานครบ
เมื่อต้องการหยุดทั้งหมด ให้ตรวจสถานะและ pending orders จริงก่อน
หากผู้ใช้เลือกปิดสถานะด้วยมือ ให้ยืนยันผลใน Trade/History ไม่ใช่ดูเพียงว่าถอน EA แล้ว

อย่าลบ Global Variables หรือ journal เพื่อปลด uncertainty/mutex lock
หาก order response ไม่ชัดเจน ต้องตรวจ broker history, positions, orders และ logs ให้ครบก่อน
ไม่มีปุ่ม reset locks อัตโนมัติที่ปลอดภัยให้ใช้แทนการตรวจสอบนี้

## 8. การแก้ปัญหาที่พบบ่อย

| อาการ | จุดที่ควรตรวจ |
|---|---|
| EA ไม่เปิดออร์เดอร์ | เริ่มจาก Demo enum, symbol/M5, `AUTO_TRADING`, `EmergencyStop`, สิทธิ์ Algo Trading, candidate/regime, model approval และ guards; ไม่มีสัญญาณไม่ใช่ connection error เสมอไป |
| EA เริ่มต้นไม่สำเร็จ | symbol ต้องเริ่มด้วย `XAUUSD`, ชื่อกราฟต้องตรง, timeframe M5, Input ต้องอยู่ในช่วงที่ยอมรับ และใช้ Demo |
| `data` / `not_ready` | โหลดประวัติ M5/M15/H1 ให้ครบและ synchronized รอ indicator และแท่งที่ปิดแล้ว โดยเฉพาะหลังเปิดตลาดหรือเพิ่งติดตั้ง |
| ML Service ต่อไม่ได้ | Service ต้องรันอยู่บน loopback เดียวกัน ตรวจ `/health`, port 8000, WebRequest allowlist, `InferenceURL` ต้องมี `/score` และ model pins ต้องไม่ว่าง |
| Service อยู่บน Mac แต่ MT5 อยู่ Windows VM | `127.0.0.1` คนละสภาพแวดล้อม ให้รัน Service ภายใน VM เดียวกับ MT5; EA ไม่รองรับ URL เป็น IP ข้ามเครื่องในรุ่นนี้ |
| `http_timeout_or_error` | ตรวจ Service log/status, allowlist และโหลดเครื่อง; timeout สูงสุดที่ EA ยอมรับคือ 2000 ms ห้ามคิดว่าขอเวลานานขึ้นแล้วปัญหาความถูกต้องหาย |
| Compile Error | ใช้ MetaEditor ของ MT5, เปิดไฟล์ `.mq5` จริง, วาง `.mqh` สองไฟล์ข้าง EA และตรวจบรรทัดจาก Errors; ยังไม่มีผลคอมไพล์ยืนยัน จึงอาจต้องแก้ native code และทดสอบใหม่ |
| Invalid Stops / modification ถูกปฏิเสธ | ตรวจ Bid/Ask, tick size, stops level, freeze level และราคา TP/SL หลัง rounding; ดู `check`, `stop_update` และ retcode ไม่ถอด SL/TP เพื่อฝืนส่งคำสั่ง |
| Spread สูง | ตรวจ spread เป็น points ของ symbol ปัจจุบันและเทียบ `MaxSpreadPoints`; อย่าเพิ่มค่าจนผ่านโดยไม่ปรับสมมติฐานต้นทุนและประเมินใหม่ |
| โมเดลไม่พร้อม | ตรวจ `SG_ARTIFACT` ว่ามีทั้ง `model.joblib` และ `manifest.json`; `/health` ที่ตอบ HTTP ได้อย่างเดียวไม่พิสูจน์ว่าโหลดโมเดลแล้ว |
| `model_unapproved` | โหลดโมเดลแล้วแต่ยังไม่ผ่าน approval จึง abstain ตามปกติสำหรับ Shadow ไม่ใช่บั๊กที่ต้องแก้โดยปิด guard |
| `artifact_invalid` | ตรวจไฟล์ ความเข้ากันได้ dependencies, feature metadata, model SHA256 และลำดับเวลา; Service อาจโหลดไม่ได้ อย่าแก้ hash เพียงให้ตรงกับไฟล์ที่ไม่ทราบที่มา |
| `model_mismatch` | EA pin version/hash คนละชุดกับ Service เช่นเลือก Logistic แต่ใช้ manifest ของ LightGBM |
| `stale_request` / `model_from_future` | ตรวจเวลา UTC/server offset, เวลาเครื่องที่เปิด Service, ข้อมูลเก่าหรือช่วงทดสอบอยู่ก่อน `threshold_through` |
| `abstain_or_reject` | เป็นเหตุผลรวมฝั่ง EA ต้องดู `reason` จาก Service เพื่อแยก model approval, threshold, เวลา และปัญหาอื่น |
| Replay ไม่เปิดออร์เดอร์ | Tester ไม่ใช้ HTTP; ตรวจ `ReplayFile`, file sandbox/`tester_file`, model pins, symbol suffix, OOS IDs และ expiry รวมทั้งว่า Replay ไม่ได้มีแต่ ABSTAIN |
| Train ไม่ได้ | ตรวจข้อมูลครบ warmup, มี candidate/labels, ครบสามคลาสใน fit/calibration และข้อมูลพอหลัง purge; อย่าปลอม labels เพื่อให้ train ผ่าน |
| `missing_daily_equity_with_exposure` | ไม่มี baseline ที่เชื่อถือได้ตอนเริ่มพร้อม exposure จึงล็อกวันนั้น ตรวจเหตุผลและสถานะ ไม่ลบ lock เพื่อฝืน |
| `missing_immutable_state` | journal/Global Variables หายหรือ actual entry ไม่ตรง state; ตรวจ broker protection และ history ห้ามใช้ trailed SL มาสร้าง initial R ใหม่ |
| มี `entry_blocked` แต่ไม่รู้ guard ไหน | log บางจุดเป็นเหตุผลรวม และบาง execution checks คืนค่าโดยไม่มีเหตุผลเฉพาะ ต้องตรวจเงื่อนไขใน `Execute()`/`DailyGuard()`; ยังไม่มีหน้าจออธิบาย guard ครบทุกตัว |

ตรวจ **Experts / Journal ของกราฟปกติ** แยกจาก **Journal ของ Strategy Tester**
และ log ของ Python Service ซึ่งเป็นคนละ process
หากต้องรายงานปัญหา ให้แนบ commit, build MT5, Input ที่ไม่ใช่ความลับ,
symbol properties, เวลา UTC และ error/retcode ห้ามแนบรหัสผ่านบัญชี

## 9. โครงสร้างโปรเจกต์

```text
scalping-gold/
├── README.md
├── pyproject.toml
├── .gitignore
├── .github/workflows/tests.yml
├── mql5/
│   ├── ScalpingGold.mq5
│   ├── GoldCore.mqh
│   ├── GoldJson.mqh
│   ├── GoldCoreTests.mq5
│   └── ExportBars.mq5
├── src/scalping_gold/
│   ├── __init__.py
│   ├── core.py
│   ├── data.py
│   ├── replay.py
│   ├── safety.py
│   ├── protocol.py
│   ├── train.py
│   ├── service.py
│   └── cli.py
├── scripts/
│   ├── serve.py
│   ├── verify_parity.py
│   ├── compare_exports.py
│   └── evaluate_matrix.py
├── config/
│   ├── demo-shadow.set
│   ├── service.env.example
│   ├── approval.example.json
│   └── tester.example.ini
├── tests/
│   ├── test_core.py
│   ├── test_data_replay.py
│   ├── test_protocol_service.py
│   ├── test_training.py
│   ├── test_safety.py
│   ├── test_http_integration.py
│   └── test_source_contract.py
└── docs/
    ├── IMPLEMENTATION.md
    ├── VALIDATION.md
    ├── test-results.txt
    └── python-tested.txt
```

| ไฟล์/กลุ่ม | หน้าที่ |
|---|---|
| `mql5/ScalpingGold.mq5` | EA หลัก อ่านแท่ง ส่ง ML/Replay ตรวจ guards ส่งคำสั่ง จัดการ exits/recovery และเขียน logs |
| `mql5/GoldCore.mqh` | กฎ regime, candidate, arbitration และลำดับ features |
| `mql5/GoldJson.mqh` | parser สำหรับ flat JSON response ที่ตรวจ duplicate keys และรูปแบบ scalar |
| `mql5/GoldCoreTests.mq5` | native fixture test และ export CSV; ไม่ส่งออร์เดอร์ |
| `mql5/ExportBars.mq5` | สคริปต์อ่าน historical M5 และ export CSV เป็น UTC |
| `src/scalping_gold/__init__.py` | ประกาศ Python package |
| `src/scalping_gold/core.py` | reference ของกลยุทธ์ features, risk และ Hybrid Exit ที่ทดสอบใน Python |
| `src/scalping_gold/data.py` | ตรวจ CSV, สร้าง indicators และรวมข้อมูลตามเวลาที่ทราบได้จริง |
| `src/scalping_gold/replay.py` | label ผลเทรด จำลอง costs/exits และสถิติพอร์ต |
| `src/scalping_gold/safety.py` | reference guard ledger ด้วย SQLite สำหรับทดสอบ policy ไม่เชื่อม broker และไม่ใช่ที่เก็บ state ของ EA |
| `src/scalping_gold/protocol.py` | schema request/response, feature/model contracts และการตรวจเวลา |
| `src/scalping_gold/train.py` | train LR/LightGBM, calibration, purge/embargo, validation และ artifacts |
| `src/scalping_gold/service.py` | API `/health`, `/score`, โหลด frozen model และตรวจ approval |
| `src/scalping_gold/cli.py` | คำสั่ง `prepare` และ `replay` |
| `scripts/serve.py` | เปิด Service loopback พร้อม INFO scoring logs |
| `scripts/verify_parity.py` | เทียบ CSV จาก native fixture กับ Python หกกรณี |
| `scripts/compare_exports.py` | เทียบ IDs/features ของ EA export กับ Python candidates |
| `scripts/evaluate_matrix.py` | เปรียบเทียบโมเดลกับ exit modes บน common OOS IDs |
| `config/demo-shadow.set` | Inputs ตัวอย่างที่ปิดการเปิดออร์เดอร์ใหม่ |
| `config/service.env.example` | ตัวอย่าง environment variables ไม่ใช่ไฟล์ที่โหลดให้อัตโนมัติ |
| `config/approval.example.json` | โครงไฟล์อนุมัติ เริ่มต้น `approved=false` |
| `config/tester.example.ini` | template Tester ที่ยังต้องตรวจ path/วันที่/inputs |
| `tests/test_core.py` | กลยุทธ์ทั้งสองทิศ regime, arbitration, risk, exits และ persistence reference |
| `tests/test_data_replay.py` | closed-bar availability, future leakage, costs, ambiguity, gaps และ portfolio reference |
| `tests/test_protocol_service.py` | schema, inference failure, stale/mismatched response และ timeout |
| `tests/test_training.py` | ฝึกจริงบน synthetic fixtures, calibration, walk-forward และ artifact/approval checks |
| `tests/test_safety.py` | policy locks, duplicates, partial/uncertain submissions และ reference-ledger restart |
| `tests/test_http_integration.py` | เปิด Uvicorn process บน loopback จริงเพื่อตรวจ health/schema; ไม่เชื่อม MT5 |
| `tests/test_source_contract.py` | ตรวจ source wiring ของ MQL5/feature/API; ไม่ใช่ MQL5 compiler หรือ runtime test |
| `docs/IMPLEMENTATION.md` | สมมติฐานและบันทึกแต่ละ phase |
| `docs/VALIDATION.md` | หลักฐาน ข้อจำกัด และ native acceptance matrix |
| `docs/test-results.txt` | output ของชุดทดสอบที่บันทึกไว้ |
| `docs/python-tested.txt` | เวอร์ชัน dependencies ของ environment ที่ใช้ทดสอบเดิม |
| `pyproject.toml` | package metadata, dependencies และการตั้งค่า pytest/Ruff |
| `.github/workflows/tests.yml` | Python tests, Ruff และ dependency checks บน Python 3.11/3.12 ไม่ได้คอมไพล์ MQL5 |
| `.gitignore` | ไม่ติดตาม virtual environment, data, artifacts, `.ex5`, logs และไฟล์ approval ส่วนตัวตามกฎที่กำหนด |

`data/`, `artifacts/` และ `.venv/` สร้างภายหลังบนเครื่องผู้ใช้ ไม่ได้มีข้อมูลตลาดหรือโมเดลพร้อมใช้
รวมอยู่ใน repository การติดตั้งแบบ editable อาจสร้าง `.egg-info/` ซึ่งไม่ใช่ซอร์สที่ต้องแก้

### Logs และ state ตอนใช้งาน

ใน **Data Folder ของ MT5**:

| ตำแหน่ง | เนื้อหา |
|---|---|
| `MQL5/Files/scalping-gold-events.jsonl` | event/reason, server time, state และ signal ID |
| `MQL5/Files/scalping-gold-candidates.jsonl` | request schema พร้อม features สำหรับเทียบ parity |
| `MQL5/Files/scalping-gold-plans.jsonl` | entry/SL/TP ที่วางแผนและ request เต็มชุด |
| `MQL5/Files/GoldCoreTests.csv` | ผล native fixture หลังรันสคริปต์ |
| `MQL5/Files/gold-m5.csv` | ผล historical export หลังรันสคริปต์ |

ใน Tester ต้องดู sandbox ของ agent ที่ใช้งาน ไม่สมมติว่าเป็นโฟลเดอร์เดียวกับกราฟปกติ
EA ใช้ **Terminal Global Variables** เก็บ initial R/entry/strategy, daily baseline/locks,
last submitted signal, pending journal และ uncertainty ตาม keys ที่ hash login/server/symbol
ไม่ได้เก็บ state นี้ในไฟล์ SQLite ของ `safety.py`
mutex ป้องกันการส่งพร้อมกันอยู่ใน terminal เดียวกัน ไม่ประสานหลายเครื่องหรือหลาย terminal

## 10. ข้อจำกัดและสถานะการทดสอบ

### พัฒนาไว้แล้วและมี Python checks รองรับ

- ซอร์สกลยุทธ์ BUY/SELL ทั้งสามแบบ, regime hysteresis, arbitration และ features ที่มีเวอร์ชัน/hash
- ซอร์ส EA แบบ Demo-only พร้อม guards, SL/TP, BE/Trailing/Time Exit และ journal/recovery
  แต่พฤติกรรม native ยังต้องพิสูจน์แยก
- historical preparation, conservative OHLC labels, LR/LightGBM, calibration,
  purged validation, embargo, walk-forward, model/exit comparison และ frozen inference
- fail-closed เมื่อ inference ไม่พร้อม และ Offline Decision Replay สำหรับ Tester
- configuration examples, logging, Python tests และ CI

หลักฐานที่บันทึกไว้ใน [docs/test-results.txt](docs/test-results.txt):
**59 tests passed** บน Linux/Python 3.12.14 พร้อม dependency deprecation warning หนึ่งรายการ
Ruff และ `pip check` ผ่าน และ CI ของ implementation commit `5df6e08` ผ่าน Python 3.11/3.12
ดูเวอร์ชันที่ใช้จริงใน [docs/python-tested.txt](docs/python-tested.txt)
ตัวเลขนี้เป็นผลของ implementation ชุดที่บันทึก ไม่ใช่ผลการทดสอบ MT5 บนเครื่องของผู้อ่าน

การ train และ scoring ที่ทดสอบอัตโนมัติใช้ synthetic fixtures
การทดสอบ reference ledger ไม่ใช่การส่งคำสั่งผ่าน MT5 และ source assertions ไม่ใช่การคอมไพล์ MQL5

### ยังไม่ได้ยืนยันผลการทดสอบ

- Compile EA/สคริปต์ด้วย MetaEditor และตรวจ compiler warnings/errors จริง
- รัน `GoldCoreTests` ใน MT5 และเทียบ native historical indicators/features กับ Python
- Strategy Tester บน real ticks, Replay file transfer/expiry และรายงานผล Backtest
- broker-specific digits/tick size/stops/freeze/margin/spread, slippage, gaps และ partial fills
- actual-fill R/TP, monotonic SL, recovery/restart, missing protection และ daily floating-equity locks ใน MT5
- ผล OOS บนข้อมูลตลาดจริง, model approval และ latency distribution ของเครื่องที่จะใช้
- การใช้งาน macOS/Wine, Apple Silicon และ Windows VM/Windows ARM แต่ละรูปแบบ

รายการตรวจรับอย่างละเอียดอยู่ใน [docs/VALIDATION.md](docs/VALIDATION.md)
ยังไม่มีหลักฐานผลกำไร ผลว่าระบบ ML ดีกว่ากฎล้วน หรือผลว่าทดลองเทรด Demo ผ่านแล้ว

### สิ่งที่ยังไม่ได้ทำหรือไม่ได้มีให้ใช้งานใน V1

- ไม่มี pretrained/approved model, historical dataset หรือ `.ex5` ที่พร้อมใช้งาน
- ไม่มี auto-deployment, auto-enable Algo Trading หรือ auto-approval จากการ train สำเร็จ
- ไม่มี UI/dashboard ของโปรเจกต์ ไม่มีฟังก์ชัน reset risk locks สำหรับผู้เริ่มต้น
- ไม่มี Inputs ปรับ risk %, exit multipliers, timeframe หรือเลือกเปิด/ปิดแต่ละกลยุทธ์
- ไม่มี online self-training หรือ AI early-exit execution
- ไม่มี Python tick-level execution simulator หรือการจำลอง broker costs/event ordering ครบทุกกรณี
- ไม่มีระบบตรวจ UTC/DST อัตโนมัติ ส่ง Replay ไป test agents อัตโนมัติ หรือประสาน state ข้าม terminal
- ไม่มีการเชื่อม ML ผ่าน IP ของอีกเครื่องใน EA รุ่นปัจจุบัน
- ไม่รองรับเงินจริงหรือ Contest และไม่ควรแก้ guard เพื่อใช้งานนอกขอบเขต Demo

### ข้อจำกัดของ Demo, Backtest และการป้องกันความเสี่ยง

ผล Demo ไม่รับรอง execution บัญชีจริง และระบบนี้ไม่ได้รองรับเงินจริงอยู่แล้ว
Backtest ขึ้นกับคุณภาพ tick/spread, ช่วงข้อมูล, costs และการป้องกัน future leakage
OHLC replay สมมติ stop-first อย่างระมัดระวังแต่ยังแทนลำดับ tick และสภาพคล่องจริงไม่ได้
อย่าสรุปความสามารถทำกำไรจาก synthetic tests หรือการปรับ threshold ให้เข้ากับ test set

risk 0.5% เป็นการคำนวณ SL loss ก่อนต้นทุนที่ไม่ทราบและ market gaps จึงไม่ใช่เพดานขาดทุนรับประกัน
BE ไม่รับประกัน zero loss; SL/TP จริงยังขึ้นกับการรับและประมวลผลของโบรกเกอร์
บัญชีที่มี cash flows หรือ exposure อื่นอาจกระทบ equity locks
baseline วันแรกที่ flat อิงการย้อนยอดเงินจาก history ส่วน rollover ต่อเนื่องอิง equity
ที่ quote แรกที่สังเกตได้ ไม่ใช่ tick เที่ยงคืนที่ไม่มีข้อมูล

broker-side SL/TP คือส่วนที่ฝากไว้กับโบรกเกอร์ ส่วน BE/Trailing/Time Exit และ emergency close
ต้องอาศัย terminal ที่ทำงาน เชื่อมต่อ มีราคา และมีสิทธิ์ซื้อขาย
HTTP เป็น synchronous และอาจหน่วงการจัดการได้ถึง timeout ที่กำหนด
history scans ที่เรียบง่ายอาจช้าเมื่อบัญชีมีประวัติมาก ต้องวัดบน terminal จริงก่อนทดลอง

guards ใน EA ไม่สามารถห้ามคำสั่งที่ผู้ใช้หรือโปรแกรมอื่นส่งนอก EA หรือจากเครื่องอื่น
state อยู่ใน Data Folder ของ terminal นั้น ต้องรักษาไว้เมื่อ restart
หากสถานะ order ไม่ชัดเจนหรือ state หาย ให้หยุดเปิดใหม่และตรวจหลักฐาน
ไม่ควรลบ locks หรือถอด broker protection เพื่อทำให้ระบบกลับมาเทรดเร็วขึ้น
