"""
PlateAgent Mock Backend - SQLite 版，零外部依赖
"""
import sqlite3, os, json
from datetime import date, datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

DB_PATH = os.path.join(os.path.dirname(__file__), "plate_records.db")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    conn.execute('''CREATE TABLE IF NOT EXISTS plate_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT NOT NULL,
        image_path TEXT,
        plate_color TEXT,
        avg_confidence REAL,
        blacklist_hit INTEGER DEFAULT 0,
        blacklist_type TEXT,
        recognize_method TEXT,
        process_time_ms INTEGER,
        status TEXT,
        error_message TEXT,
        raw_result TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    cur = conn.execute("SELECT COUNT(*) FROM plate_records")
    if cur.fetchone()[0] == 0:
        records = [
            ("粤A12345", "/uploads/img001.jpg", "蓝色", 0.98, 0, None, "SVM+LLM", 245, "success", "{}"),
            ("京B67890", "/uploads/img002.jpg", "绿色", 0.85, 1, "套牌", "SVM", 180, "success", "{}"),
            ("沪C11111", "/uploads/img003.jpg", "蓝色", 0.62, 0, None, "SVM+LLM", 320, "partial", "{}"),
            ("粤D22222", "/uploads/img004.jpg", "黄色", 0.0, 0, None, "SVM", 500, "failed", '{"error":"无法识别"}'),
            ("粤E33333", "/uploads/img005.jpg", "蓝色", 0.95, 1, "违章", "SVM+LLM", 210, "success", "{}"),
            ("粤F56789", "/uploads/img006.jpg", "蓝色", 0.91, 0, None, "SVM+LLM", 198, "success", "{}"),
            ("京A11111", "/uploads/img007.jpg", "绿色", 0.73, 0, None, "SVM", 156, "partial", "{}"),
            ("沪B22222", "/uploads/img008.jpg", "蓝色", 0.88, 1, "盗抢", "SVM+LLM", 230, "success", "{}"),
        ]
        conn.executemany(
            "INSERT INTO plate_records (plate_number,image_path,plate_color,avg_confidence,blacklist_hit,blacklist_type,recognize_method,process_time_ms,status,raw_result) VALUES (?,?,?,?,?,?,?,?,?,?)",
            records
        )
        conn.commit()
    conn.close()

init_db()

class LoginRequest(BaseModel):
    username: str
    password: str

def row_to_camel(row):
    if row is None: return None
    d = {}
    for k in row.keys():
        ck = ''.join(p if i == 0 else p.capitalize() for i, p in enumerate(k.split('_')))
        d[ck] = row[k]
    return d

@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.username == "admin" and req.password == "password":
        return {"token": "mock-jwt-token-demo-2024", "username": "admin"}
    raise HTTPException(401, detail="用户名或密码错误")

@app.get("/api/records")
def list_records(plate: str = None, status: str = None, page: int = 0, size: int = 20):
    conn = get_conn()
    try:
        where = []
        params = []
        if plate:
            where.append("plate_number LIKE ?")
            params.append(f"%{plate}%")
        if status:
            where.append("status = ?")
            params.append(status)
        wc = ("WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute(f"SELECT COUNT(*) FROM plate_records {wc}", params).fetchone()[0]
        rows = [row_to_camel(r) for r in conn.execute(
            f"SELECT * FROM plate_records {wc} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [size, page * size]
        ).fetchall()]
        return {"content": rows, "totalElements": total, "totalPages": max(1, (total + size - 1) // size), "number": page, "size": size}
    finally:
        conn.close()

@app.get("/api/records/blacklist")
def blacklist(page: int = 0, size: int = 20):
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM plate_records WHERE blacklist_hit = 1").fetchone()[0]
        rows = [row_to_camel(r) for r in conn.execute(
            "SELECT * FROM plate_records WHERE blacklist_hit = 1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [size, page * size]
        ).fetchall()]
        return {"content": rows, "totalElements": total, "totalPages": max(1, (total + size - 1) // size), "number": page, "size": size}
    finally:
        conn.close()

@app.get("/api/records/stats/today")
def today_stats():
    conn = get_conn()
    try:
        today_str = date.today().isoformat()
        total = conn.execute("SELECT COUNT(*) FROM plate_records WHERE date(created_at) = ?", [today_str]).fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM plate_records WHERE status='success' AND date(created_at) = ?", [today_str]).fetchone()[0]
        partial = conn.execute("SELECT COUNT(*) FROM plate_records WHERE status='partial' AND date(created_at) = ?", [today_str]).fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM plate_records WHERE status='failed' AND date(created_at) = ?", [today_str]).fetchone()[0]
        bl = conn.execute("SELECT COUNT(*) FROM plate_records WHERE blacklist_hit=1 AND date(created_at) = ?", [today_str]).fetchone()[0]
        avg_row = conn.execute("SELECT AVG(avg_confidence) FROM plate_records WHERE date(created_at) = ? AND avg_confidence IS NOT NULL", [today_str]).fetchone()
        avgc = float(avg_row[0]) if avg_row and avg_row[0] else 0.0
        return {"totalRecognitions": total, "successCount": success, "partialCount": partial, "failedCount": failed, "blacklistHits": bl, "avgConfidence": avgc, "avgProcessTimeMs": 250}
    finally:
        conn.close()

@app.get("/api/records/stats/hourly")
def hourly_stats():
    conn = get_conn()
    try:
        today_str = date.today().isoformat()
        rows = conn.execute(
            "SELECT cast(strftime('%H', created_at) as integer) as hour, COUNT(*) as count FROM plate_records WHERE date(created_at) = ? GROUP BY hour ORDER BY hour",
            [today_str]
        ).fetchall()
        return [{"hour": r["hour"], "count": r["count"]} for r in rows]
    finally:
        conn.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
