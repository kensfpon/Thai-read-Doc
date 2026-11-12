# CLAUDE.md

คู่มือสำหรับ Claude Code เมื่อทำงานใน repository นี้

## โปรเจกต์นี้คืออะไร

ซอฟต์แวร์อ่านค่าจาก transmitter ผ่าน **HART protocol** (ผ่าน HART modem บน serial port) พร้อม web app แสดงค่าสด ประวัติ และ diagnostic

- **สถานะปัจจุบัน: Phase 0–1 เสร็จกับ simulator** (HART core + `hartcli`) — ยังไม่ได้ทดสอบกับ hardware จริง, ยังไม่มี services/API/UI จริง
- อ่าน [`DESIGN.md`](./DESIGN.md) ก่อนเริ่มงานทุกครั้ง — สถาปัตยกรรม, API, data model และแผน phase อยู่ที่นั่น
- ทำงานตามลำดับ phase ใน DESIGN.md §9 อย่าข้ามไปทำ UI ก่อน HART core จะผ่าน acceptance
- ถ้าการ implement ทำให้ต้องเปลี่ยนการออกแบบ ให้แก้ DESIGN.md ใน commit เดียวกัน

## โครงสร้าง

```
backend/app/hart/        HART stack: transport → link → app (ไม่มี dependency กับ web/db)
backend/app/cli.py       hartcli: scan / read / monitor
backend/app/main.py      FastAPI app (ตอนนี้มีแค่ /api/health)
backend/tests/           unit / integration / fixtures/frames
frontend/src/            React + TypeScript + Vite (ตอนนี้เป็น placeholder)
# ตามแผน ยังไม่มี: backend/app/services/, api/, db/
```

## คำสั่ง

```bash
# Backend (ใช้ venv — pytest ของระบบมองไม่เห็น dependency ของโปรเจกต์)
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
pytest                                          # ทั้งหมด
pytest tests/unit/test_frame.py -k checksum     # เฉพาะบางส่วน
ruff check . && ruff format --check . && mypy
uvicorn app.main:app --reload

# hartcli — ไม่ใส่ --port = ใช้ simulator (อุปกรณ์จำลองที่ address 0 และ 3)
hartcli scan
hartcli --frames read 3 --address 0             # --frames แสดง hex ของ frame
hartcli --realtime monitor --address 3          # --realtime จำลองความเร็ว 1200 baud
hartcli --port COM5 scan                        # modem จริง (ยังไม่เคยทดสอบ)

# Frontend
cd frontend && npm install
npm run dev          # proxy /api และ /ws ไป backend :8000
npm test             # Vitest
npm run typecheck
npm run build
```

## กฎที่ห้ามละเมิด

1. **Read-only**: ส่งได้เฉพาะ HART command ใน allowlist (`READ_ONLY_COMMANDS` ใน `hart/tables.py`, DESIGN.md §3.4) ห้ามเพิ่มคำสั่งเขียน (เช่น 6, 17, 18, 35, 40, 45, 46)
   เว้นแต่ผู้ใช้สั่งชัดเจน — คำสั่งเหล่านี้เปลี่ยนพฤติกรรม transmitter ในกระบวนการจริง
2. **Layering**: `hart/` ห้าม import FastAPI, SQLAlchemy หรืออะไรจาก `services/`, `api/`, `db/`
   command class ต้องไม่มี I/O (รับ bytes คืน dataclass)
3. **Bus เดียว transaction เดียว**: ทุกการส่งต้องผ่าน master ใน `hart/link` ซึ่งถือ lock ห้ามเขียน serial port ตรงจากที่อื่น
4. **ห้ามแสดงค่าค้างเป็นค่าสด**: ทุกค่าที่ส่งถึง UI ต้องมี timestamp; NaN จากอุปกรณ์ (`0x7FA00000`) ส่งเป็น `null` ไม่ใช่ 0
5. **ห้ามเดา spec**: ถ้าไม่แน่ใจ layout ของ byte หรือ timing ให้บอกผู้ใช้ว่าไม่แน่ใจและใส่ `# TODO(spec): ...` อย่าเขียนเหมือนรู้แน่

## แนวทางการเขียนโค้ด

- Python 3.12, type hints ครบ, async ทั้งเส้นทาง I/O, format/lint ด้วย ruff
- TypeScript strict; type ของ API สร้างจาก OpenAPI ของ backend ไม่เขียนมือซ้ำ
- ตัวเลขใน HART เป็น big-endian; ใช้ helper ใน `hart/app/codec.py` ไม่ `struct.unpack` กระจายทั่วโค้ด
- decoder ต้องรับ response ที่ **สั้นหรือยาวกว่า** spec ได้ (อุปกรณ์ต่าง revision ส่งไม่เท่ากัน) — ห้าม crash ให้คืน field ที่ขาดเป็น `None`
- ค่าคงที่ของ protocol (delimiter, timeout, unit code) รวมไว้ที่ `hart/tables.py` / `config.py` ไม่ hardcode กลางโค้ด
- เวลาเก็บเป็น UTC เสมอ แปลงเป็นเวลาท้องถิ่นที่ frontend
- ข้อความ UI: ภาษาไทยเป็นหลัก, ศัพท์ HART คงภาษาอังกฤษ (PV, URV, LRV, tag, loop current)
- comment และชื่อในโค้ดเป็นภาษาอังกฤษ; เอกสารเป็นภาษาไทย

## การทดสอบ

- เพิ่ม/แก้ command ใด ต้องมี unit test ด้วย **golden bytes** (hex ของ request และ response) เสมอ
- แก้ `hart/link` ต้องรัน integration test กับ simulator
- frame ที่จับได้จากอุปกรณ์จริงให้เก็บใน `backend/tests/fixtures/frames/` พร้อมระบุรุ่นอุปกรณ์
- ในสภาพแวดล้อมนี้ไม่มี hardware: ใช้ `SimulatorTransport` และ **บอกผู้ใช้ตรง ๆ** ว่าสิ่งใดยังไม่ได้ทดสอบกับอุปกรณ์จริง
- งานฝั่ง UI ต้องเปิดดูใน browser จริง (กับ simulator) ก่อนรายงานว่าเสร็จ

## Git

- commit message ภาษาอังกฤษ รูปแบบ `area: summary` เช่น `hart/link: resync after garbage bytes`
- อย่า commit ไฟล์ฐานข้อมูล (`*.db`), `node_modules/`, `frontend/dist/`, หรือ `.env`
