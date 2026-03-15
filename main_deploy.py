"""
Chợ Đồ Cũ - Backend FastAPI
Deploy: Render.com hoặc VPS Ubuntu
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import sqlite3, os, shutil, uvicorn, secrets
from datetime import datetime
from typing import Optional

app = FastAPI(title="Chợ Đồ Cũ")

# ══════════════════════════════════════════
#  ⚙️  CẤU HÌNH — đọc từ biến môi trường
#      (đặt trong Render Dashboard hoặc .env)
# ══════════════════════════════════════════
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "chodocus123")
PORT           = int(os.environ.get("PORT", 8000))

# ── Đường dẫn lưu trữ ──
# Render.com dùng /data (persistent disk)
# VPS / local dùng thư mục hiện tại
IS_RENDER = os.environ.get("RENDER", False)
DATA_DIR  = "/data" if IS_RENDER else os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(DATA_DIR, "shop.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("static", exist_ok=True)

active_tokens: set = set()

def check_token(request: Request) -> bool:
    return request.cookies.get("admin_token", "") in active_tokens

def require_auth(request: Request):
    if not check_token(request):
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ── Khởi tạo SQLite ──
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            price       INTEGER NOT NULL,
            orig_price  INTEGER DEFAULT 0,
            category    TEXT    DEFAULT '',
            condition   TEXT    DEFAULT '',
            location    TEXT    DEFAULT '',
            description TEXT    DEFAULT '',
            phone       TEXT    DEFAULT '',
            image       TEXT    DEFAULT '',
            views       INTEGER DEFAULT 0,
            sold        INTEGER DEFAULT 0,
            created_at  TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ═══════════════════════════════════════════
#  TRANG WEB
# ═══════════════════════════════════════════

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/admin")
def admin_page(request: Request):
    if not check_token(request):
        return FileResponse("static/login.html")
    return FileResponse("static/admin.html")

@app.get("/login")
def login_page():
    return FileResponse("static/login.html")

# ═══════════════════════════════════════════
#  AUTH API
# ═══════════════════════════════════════════

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    if data.get("username") == ADMIN_USERNAME and data.get("password") == ADMIN_PASSWORD:
        token = secrets.token_hex(32)
        active_tokens.add(token)
        response = JSONResponse({"ok": True, "message": "Đăng nhập thành công!"})
        response.set_cookie(
            key="admin_token", value=token,
            httponly=True, max_age=86400 * 7, samesite="lax"
        )
        return response
    return JSONResponse(
        {"ok": False, "message": "Sai tên đăng nhập hoặc mật khẩu!"},
        status_code=401
    )

@app.post("/api/logout")
def logout(request: Request):
    active_tokens.discard(request.cookies.get("admin_token", ""))
    res = JSONResponse({"ok": True})
    res.delete_cookie("admin_token")
    return res

@app.get("/api/check-auth")
def check_auth(request: Request):
    return {"ok": check_token(request)}

# ═══════════════════════════════════════════
#  API SẢN PHẨM (public)
# ═══════════════════════════════════════════

@app.get("/api/products")
def list_products(
    cat: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    sold: Optional[int] = None
):
    conn = get_db()
    q = "SELECT * FROM products WHERE 1=1"
    params = []
    if cat and cat != "Tất cả":
        q += " AND category=?"; params.append(cat)
    if search:
        q += " AND (name LIKE ? OR description LIKE ?)"; params += [f"%{search}%"]*2
    if sold is not None:
        q += " AND sold=?"; params.append(sold)
    q += {
        "price_asc":  " ORDER BY price ASC",
        "price_desc": " ORDER BY price DESC",
        "discount":   " ORDER BY (orig_price-price) DESC",
        "views":      " ORDER BY views DESC",
    }.get(sort, " ORDER BY created_at DESC")
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/products/{pid}")
def get_product(pid: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404, "Không tìm thấy")
    return dict(row)

@app.post("/api/products/{pid}/view")
def add_view(pid: int):
    conn = get_db()
    conn.execute("UPDATE products SET views=views+1 WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return {"ok": True}

@app.get("/api/stats")
def stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM products WHERE sold=0").fetchone()[0]
    sold  = conn.execute("SELECT COUNT(*) FROM products WHERE sold=1").fetchone()[0]
    views = conn.execute("SELECT SUM(views) FROM products").fetchone()[0] or 0
    cats  = conn.execute("SELECT COUNT(DISTINCT category) FROM products").fetchone()[0]
    conn.close()
    return {"total": total, "sold": sold, "views": views, "cats": cats}

# ═══════════════════════════════════════════
#  API ADMIN (yêu cầu đăng nhập)
# ═══════════════════════════════════════════

@app.post("/api/admin/products")
async def add_product(
    request: Request,
    name: str=Form(...), price: int=Form(...), orig_price: int=Form(0),
    category: str=Form(""), condition: str=Form(""), location: str=Form(""),
    description: str=Form(""), phone: str=Form(""),
    image: UploadFile=File(None)
):
    require_auth(request)
    img_path = ""
    if image and image.filename:
        ext = image.filename.rsplit(".",1)[-1].lower()
        if ext not in ("jpg","jpeg","png","webp","gif"):
            raise HTTPException(400, "Chỉ chấp nhận ảnh jpg/png/webp")
        fname = f"{int(datetime.now().timestamp()*1000)}.{ext}"
        with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
            shutil.copyfileobj(image.file, f)
        img_path = f"/uploads/{fname}"
    conn = get_db()
    conn.execute("""
        INSERT INTO products
          (name,price,orig_price,category,condition,location,description,phone,image,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (name,price,orig_price,category,condition,location,
          description,phone,img_path,datetime.now().isoformat()))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Đăng bán thành công!"}

@app.put("/api/admin/products/{pid}")
async def update_product(
    pid: int, request: Request,
    name: str=Form(...), price: int=Form(...), orig_price: int=Form(0),
    category: str=Form(""), condition: str=Form(""), location: str=Form(""),
    description: str=Form(""), phone: str=Form(""), sold: int=Form(0),
    image: UploadFile=File(None)
):
    require_auth(request)
    conn = get_db()
    row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not row: raise HTTPException(404, "Không tìm thấy")
    img_path = row["image"]
    if image and image.filename:
        ext = image.filename.rsplit(".",1)[-1].lower()
        fname = f"{int(datetime.now().timestamp()*1000)}.{ext}"
        with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
            shutil.copyfileobj(image.file, f)
        img_path = f"/uploads/{fname}"
    conn.execute("""
        UPDATE products SET
          name=?,price=?,orig_price=?,category=?,condition=?,
          location=?,description=?,phone=?,image=?,sold=?
        WHERE id=?
    """, (name,price,orig_price,category,condition,
          location,description,phone,img_path,sold,pid))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Cập nhật thành công!"}

@app.delete("/api/admin/products/{pid}")
def delete_product(pid: int, request: Request):
    require_auth(request)
    conn = get_db()
    row = conn.execute("SELECT image FROM products WHERE id=?", (pid,)).fetchone()
    if row and row["image"]:
        fpath = os.path.join(UPLOAD_DIR, os.path.basename(row["image"]))
        try: os.remove(fpath)
        except: pass
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Đã xóa sản phẩm"}


@app.get("/sitemap.xml")
def sitemap():
    return FileResponse("static/sitemap.xml", media_type="application/xml")

@app.get("/robots.txt")
def robots():
    return FileResponse("static/robots.txt", media_type="text/plain")

# ═══════════════════════════════════════════
#  KHỞI CHẠY
# ═══════════════════════════════════════════
if __name__ == "__main__":
    print("="*50)
    print("🏪  Chợ Đồ Cũ đang chạy!")
    print(f"👤  Tài khoản : {ADMIN_USERNAME}")
    print(f"📁  Database  : {DB_PATH}")
    print(f"🖼️   Uploads   : {UPLOAD_DIR}")
    print(f"🌐  Port      : {PORT}")
    print("="*50)
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
