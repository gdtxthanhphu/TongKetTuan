import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, date
import hashlib
import unicodedata
import re
from ai_analysis import init_gemini, summarize_scores

# === Utils: ép số + tính tổng ===
def ensure_columns(df: pd.DataFrame, columns, fill=0):
    for c in columns:
        if c not in df.columns:
            df[c] = fill
    return df

def coerce_numeric_int(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df.get(c), errors="coerce").fillna(0).astype(int)
    return df

def recompute_total_weighted(df: pd.DataFrame, items, item_colmap: dict, total_col: str):
    """
    items: danh sách ITEMS gốc [(key, label, weight, ...), ...]
    item_colmap: map key -> tên cột trong DataFrame (cmap["ITEMS"])
    total_col: tên cột Tổng điểm
    """
    total = 0
    for key, label, weight, _ in items:
        colname = item_colmap.get(key, label)
        if colname not in df.columns:
            df[colname] = 0
        # đảm bảo cột là số nguyên
        df[colname] = pd.to_numeric(df[colname], errors="coerce").fillna(0).astype(int)
        # cộng có trọng số
        total += df[colname] * int(weight)
    df[total_col] = total.astype(int)
    return df


# =========================
# CONFIG
# =========================
SPREADSHEET_ID = "1Ahv3CNsRvT0N5s-te8o3xkfwATbFuhAENpX0xoqM3Sw"
SERVICE_FILE = "service_account.json"
USE_HASHED_PASSWORDS = False
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ====== Tuần gốc ======
BASE_WEEK_DATE = (2025, 10, 27)
BASE_WEEK_NUMBER = 8

def calc_week(d: date) -> int:
    base = date(*BASE_WEEK_DATE)
    delta = (d - base).days
    week = BASE_WEEK_NUMBER + (delta // 7)
    return max(1, week)

# ====== Chuẩn hóa tên cột ======
def N(x: str) -> str:
    if x is None: return ""
    x = unicodedata.normalize("NFD", x)
    x = "".join(ch for ch in x if unicodedata.category(ch) != "Mn")
    x = x.lower()
    x = re.sub(r"[^a-z0-9]+", " ", x).strip()
    return x

# ====== Danh sách mục và điểm ======
ITEMS = [
    ("vesinhxaut", "Vệ sinh chưa tốt", -5, ["ve sinh chua tot"]),
    ("cobachutthuoc", "Cờ bạc, hút thuốc, uống rượu, bia", -20, ["co bac","hut thuoc","ruou bia"]),
    ("cuptiet", "Cúp tiết, SHDC, SHL", -5, ["cup tiet"]),
    ("nonbh", "Không đội nón bảo hiểm hoặc sai quy cách", -5, ["non bao hiem","sai quy cach"]),
    ("tocdai", "Tóc dài hoặc cắt kiểu không phù hợp", -2, ["toc dai","cat kieu"]),
    ("viphampl", "Vi phạm pháp luật ( ATGT, ANTT,…..)", -20, ["vi pham phap luat"]),
    ("viphamkt", "Vi phạm kiểm tra", -5, ["vi pham kiem tra"]),
    ("phahoaists", "Phá hoại tài sản", -20, ["pha hoai tai san"]),
    ("vole", "Vô lễ, đánh nhau", -20, ["vo le","danh nhau"]),
    ("dtdd", "Sử dụng điện thoại trong giờ học", -3, ["dien thoai"]),
    ("nghikhongphep", "Nghỉ học không phép", -4, ["nghi hoc khong phep"]),
    ("viphamht", "Vi phạm học tập", -3, ["hoc tap"]),
    ("mattrattu", "Mất trật tự", -3, ["mat trat tu"]),
    ("nhuomtoc", "Nhuộm tóc, son môi, sơn móng", -3, ["nhuom toc","son moi"]),
    ("noituc", "Nói tục", -3, ["noi tuc"]),
    ("ditre", "Đi trễ", -2, ["di tre"]),
    ("khongdongphuc", "Không đồng phục, phù hiệu, huy hiệu", -2, ["dong phuc","phu hieu"]),
    ("diconggv", "Đi cổng giáo viên, bỏ ra khỏi Trung tâm", -2, ["di cong giao vien"]),
    ("chayxe", "Chạy xe trong sân, để xe sai quy định", -2, ["chay xe","de xe"]),
    ("deplao", "Mang dép lào", -2, ["dep lao"]),
    ("nghicophep", "Nghỉ học có phép", -1, ["nghi hoc co phep"]),
    ("diem8", "Điểm 8", +3, ["diem 8"]),
    ("diem9", "Điểm 9", +4, ["diem 9"]),
    ("diem10", "Điểm 10", +5, ["diem 10"]),
    ("tiethoctot", "Tiết học tốt  (đạt/tổng đăng ký)", +50, ["tiet hoc tot"]),
    ("khongphongtrao", "Không tham gia các hoạt động phong trào (Mỗi tuần một câu chuyện hay...)", -20, ["khong tham gia phong trao"]),
    ("diemcong", "Điểm cộng", +1, ["diem cong"]),
    ("diemthuong", "Điểm thưởng", +1, ["diem thuong"]),
]


TOTAL_HEADER_CANDIDATES = ["tong diem","tongdiem","tổng điểm"]

# =========================
# =========================
# KẾT NỐI GOOGLE SHEETS (TỰ PHÁT HIỆN LOCAL / CLOUD)
# =========================
import os, json
from google.oauth2.service_account import Credentials

@st.cache_resource(show_spinner=False)
def get_client():
    """
    Tự động xác định môi trường:
      - Nếu chạy local: dùng file service_account.json
      - Nếu chạy trên Streamlit Cloud: đọc từ st.secrets["google_service_account"]
    """
    try:
        if os.path.exists("service_account.json"):
            # chạy local (trên máy tính)
            
            return gspread.service_account(filename="service_account.json", scopes=SCOPES)

        elif "google_service_account" in st.secrets:
            # chạy trên Streamlit Cloud
            st.info("☁️ Dùng Service Account trong st.secrets")
            service_info = st.secrets["google_service_account"]
            credentials = Credentials.from_service_account_info(service_info, scopes=SCOPES)
            return gspread.authorize(credentials)

        else:
            st.error("❌ Không tìm thấy thông tin xác thực Google (service account).")
            st.stop()

    except Exception as e:
        st.error(f"⚠️ Lỗi khi tạo client Google Sheets: {e}")
        st.stop()


def open_sheets(gc):
    """
    Mở Google Sheet và kiểm tra quyền truy cập.
    """
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        acc = sh.worksheet("TaiKhoan")
        score = sh.worksheet("Score")
        return acc, score
    except gspread.exceptions.APIError:
        st.error("🚫 Không thể mở Google Sheet. Hãy kiểm tra quyền chia sẻ:")
        st.info("""
        1️⃣ Mở Google Sheet  
        2️⃣ Nhấn Share → Dán email trong service_account.json (`client_email`)  
        3️⃣ Cấp quyền **Editor (Người chỉnh sửa)**  
        """)
        st.stop()
    except Exception as e:
        st.error(f"⚠️ Lỗi không xác định khi mở Google Sheet: {e}")
        st.stop()


def load_accounts(ws):
    df = pd.DataFrame(ws.get_all_records())
    if df.empty:
        st.warning("⚠️ Sheet 'TaiKhoan' trống. Hãy thêm tài khoản trước.")
    return df


def parse_score(ws):
    vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame(), [], {}
    header = vals[0]
    df = pd.DataFrame(vals[1:], columns=header)
    hnorm = [N(h) for h in header]

    def find_header(cands, default=None):
        for c in cands:
            if c in hnorm:
                return header[hnorm.index(c)]
        return default

    CLASS_COL = find_header(["lop"], "Lớp")
    WEEK_COL  = find_header(["tuan"], "Tuần")
    TIME_COL  = find_header(["ngay nhap","time"], "Ngày nhập")
    USER_COL  = find_header(["username","tai khoan"], "Tên Tài Khoản")
    TOTAL_COL = find_header(TOTAL_HEADER_CANDIDATES, "Tổng điểm")

    colmap = {}
    for key, label, weight, candlist in ITEMS:
        target = None
        for c in candlist:
            if c in hnorm:
                target = header[hnorm.index(c)]
                break
        if not target:
            target = label
            if target not in df.columns:
                df[target] = "0"
        colmap[key] = target

    for col, default in [(CLASS_COL,""), (WEEK_COL,""), (TIME_COL,""), (USER_COL,""), (TOTAL_COL,"0")]:
        if col not in df.columns:
            df[col] = default

    return df, header, {"CLASS": CLASS_COL, "WEEK": WEEK_COL, "TIME": TIME_COL, "USER": USER_COL, "TOTAL": TOTAL_COL, "ITEMS": colmap}


# =========================
# HÀM GHI LẠI SHEET (SẮP CỘT MỚI)
# =========================
def save_score_reordered(ws, df, original_header, core_cols, vesinh_col, chunk_rows=500):
    """
    Ghi DataFrame về Google Sheet theo thứ tự cột chuẩn.
    - Ghi header tại A1
    - Ghi dữ liệu theo từng khối (chunk) để tránh rớt lệnh update lớn.
    - Có log kích thước, số dòng ghi.
    """
    import math

    # ====== Header chuẩn theo ITEMS của app ======
    base_headers  = ["Ngày nhập", "Tên Tài Khoản", "Tuần", "LỚP"]  # <— LƯU Ý: "LỚP" đang đúng theo file của bạn
    item_headers  = [label for _, label, _, _ in ITEMS]
    total_headers = ["Tổng điểm"]

    # Nếu df trống → chỉ ghi header
    if df is None or df.empty:
        ws.clear()
        ws.update("A1", [base_headers + item_headers + total_headers])
        return

    # Đảm bảo đủ cột cho reindex
    for col in base_headers + item_headers + total_headers:
        if col not in df.columns:
            df[col] = ""

    # Thứ tự cột cuối cùng
    final_header = base_headers + item_headers + total_headers

    # Reindex + ép về str (để viết không lỗi)
    df_to_write = df.reindex(columns=final_header).copy()
    # Tránh object lạ gây lỗi cập nhật
    for c in df_to_write.columns:
        # giữ số cho cột mục/tổng điểm để nhìn rõ trong sheet
        if c in item_headers + total_headers:
            df_to_write[c] = pd.to_numeric(df_to_write[c], errors="coerce")
        else:
            df_to_write[c] = df_to_write[c].astype(str)

    rows = df_to_write.values.tolist()

    # ====== Ghi theo khối ======
    ws.clear()
    ws.update("A1", [final_header])  # header

    total = len(rows)
    # Ghi từ A2 trở đi
    for start in range(0, total, chunk_rows):
        end = min(start + chunk_rows, total)
        block = rows[start:end]
        # A{2+start} … theo số cột
        start_row = 2 + start
        # Tính cột cuối (ví dụ có N cột → cột cuối là index N-1)
        last_col_idx = len(final_header) - 1
        # Hàm đổi số → chữ cột (A, B, …, AA…)
        def col_letter(n):
            s = ""
            n += 1
            while n > 0:
                n, r = divmod(n - 1, 26)
                s = chr(65 + r) + s
            return s
        end_col_letter = col_letter(last_col_idx)
        rng = f"A{start_row}:{end_col_letter}{start_row + len(block) - 1}"

        # Ghi khối
        ws.update(rng, block, value_input_option="USER_ENTERED")

    st.success(f"✅ Đã ghi {total} dòng vào sheet '{ws.title}' theo {math.ceil(total/max(1,chunk_rows))} khối.")


# =========================
# UI
# =========================
st.set_page_config(page_title="Tổng Kết Tuần", page_icon="🧮", layout="wide")
st.markdown("""
<style>
/* Giảm kích thước tiêu đề phụ và tiêu đề nhỏ */
h2, .stMarkdown h2, .stSubheader, .st-emotion-cache-10trblm {
    font-size: 22px !important;  /* giảm so với mặc định 26px */
    color: #38BDF8 !important;   /* xanh cyan nhẹ, hài hòa dark mode */
    font-weight: 700 !important;
}

/* Giảm kích thước tiêu đề cấp 3 (###) */
h3, .stMarkdown h3 {
    font-size: 20px !important;
    color: #38BDF8 !important;
    font-weight: 700 !important;
}

/* Khoảng cách nhẹ hơn giữa tiêu đề và nội dung */
h2, h3 {
    margin-bottom: 8px !important;
    margin-top: 12px !important;
}
</style>
<style>
/* 🌙 Bật chế độ Dark Mode toàn ứng dụng */

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], [data-testid="stMain"] {
    background-color: #0F172A !important;  /* xanh đen đậm */
    color: #F8FAFC !important;             /* chữ sáng */
}

/* 🧩 Khối nội dung */
section.main > div.block-container {
    background-color: rgba(255,255,255,0.05) !important;
    border-radius: 16px;
    padding: 1.5rem !important;
}

/* 🧠 Nút bấm */
div.stButton > button {
    background-color: #2563EB !important;  /* xanh dương sáng */
    color: white !important;
    border-radius: 8px;
    border: none;
}
div.stButton > button:hover {
    background-color: #1D4ED8 !important;
    transform: scale(1.03);
}

/* 📋 Ô nhập liệu */
input, textarea, select {
    background-color: #1E293B !important;
    color: white !important;
    border: 1px solid #475569 !important;
}

/* 🔐 Label (Tên đăng nhập, Mật khẩu) */
label, .stTextInput label, .stPasswordInput label {
    color: #F8FAFC !important;
}

/* 🌙 Màu cho tiêu đề */
h1, h2, h3 {
    color: #38BDF8 !important; /* xanh cyan sáng */
}
</style>
""", unsafe_allow_html=True)

# CSS riêng cho từng chế độ (login / main app)
if not st.session_state.get("logged_in", False):
    # ------------------------
    # 🧩 Giao diện đăng nhập
    # ------------------------
    st.markdown("""
        <style>
        section.main > div.block-container {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100vh;
            padding-top: 0 !important;
        }

        .block-container {
            max-width: 600px;
            margin: 0 auto;
        }

        /* 🧮 Tiêu đề ứng dụng */
        .app-title {
            text-align: center !important;
            font-size: 30px !important;
            font-weight: 800 !important;
            margin-bottom: 25px;
            color: white !important;
            display: block;
            width: 100vw;
            white-space: nowrap;
            overflow: hidden;
            position: relative;
            left: calc(50% - 50vw);
        }

        /* 🔐 Tiêu đề phụ */
        h2, h3 {
            text-align: center !important;
            font-size: 22px !important;
            font-weight: 700 !important;
            margin-bottom: 10px;
        }

        /* ✏️ Ô nhập và nhãn */
        label {
            font-size: 22px !important;
            font-weight: 600 !important;
            color: #e6e6e6 !important;
        }

        input, textarea, select {
            font-size: 20px !important;
            border-radius: 8px !important;
            padding: 10px !important;
        }

        /* 🎯 Nút đăng nhập lệch nhẹ */
        div.stButton {
            text-align: center;
            margin-top: 15px;
        }

        div.stButton > button {
            display: inline-block;
            width: 200px;
            font-size: 18px !important;
            border-radius: 8px !important;
            margin-left: 80px;
        }

        div.stButton > button:hover {
            background-color: #4CAF50 !important;
            color: white !important;
            transform: scale(1.05);
        }
        </style>
    """, unsafe_allow_html=True)
else:
    # ------------------------
    # 🌟 Giao diện chính sau đăng nhập
    # ------------------------
    st.markdown("""
        <style>
        /* Cho phép phần nội dung chính hiển thị toàn màn hình */
        .block-container {
            max-width: 95% !important;
            padding-left: 3% !important;
            padding-right: 3% !important;
        }

        /* Tăng kích thước bảng dữ liệu */
        div[data-testid="stDataFrame"] table {
            font-size: 18px !important;
        }

        /* Cố định cột đầu */
        div[data-testid="stDataFrame"] thead tr th:nth-child(-n+4),
        div[data-testid="stDataFrame"] tbody tr td:nth-child(-n+4) {
            position: sticky;
            left: 0;
            background-color: white;
            z-index: 3;
        }

        </style>
    """, unsafe_allow_html=True)

# =========================
# GIAO DIỆN: PHÓNG TO CHỮ & CỐ ĐỊNH CỘT
# =========================
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-size: 18px !important;
    }
    h1, h2, h3, h4 {
        font-weight: 700 !important;
    }
    input, textarea, select, button {
        font-size: 18px !important;
    }
    div[data-testid="stDataFrame"] table {
        font-size: 17px !important;
    }
    /* ======= CỐ ĐỊNH 4 CỘT ĐẦU ======= */
    div[data-testid="stDataFrame"] thead tr th:nth-child(-n+4),
    div[data-testid="stDataFrame"] tbody tr td:nth-child(-n+4) {
        position: sticky;
        left: 0;
        background-color: white;
        z-index: 3;
    }
    div[data-testid="stDataFrame"] table {
        border-collapse: collapse;
    }
    div[data-testid="stDataFrame"] th, 
    div[data-testid="stDataFrame"] td {
        border: 1px solid #ddd !important;
        padding: 6px 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# =======================
# 


gc = get_client()
acc_ws, score_ws = open_sheets(gc)
acc_df = load_accounts(acc_ws)
score_df, score_header, cmap = parse_score(score_ws)
# Lấy tên cột động từ cmap (đúng như trên Sheet)
CLASS_COL = cmap["CLASS"]      # vd "LỚP" hoặc "Lớp"
WEEK_COL  = cmap["WEEK"]       # vd "Tuần"
TIME_COL  = cmap["TIME"]       # vd "Ngày nhập"
USER_COL  = cmap["USER"]       # vd "Tên Tài Khoản"
TOTAL_COL = cmap["TOTAL"]      # vd "Tổng điểm"
item_colmap = cmap["ITEMS"]    # dict: key -> tên cột mục trên Sheet

# Danh sách cột mục (đúng tên cột trên Sheet, theo ITEMS)
ITEM_COLS = [item_colmap.get(k, lbl) for (k, lbl, _, _) in ITEMS]

# Cột lõi (base)
BASE_COLS = [TIME_COL, USER_COL, WEEK_COL, CLASS_COL]

# Thứ tự cột cuối cùng dùng cho ép kiểu & ghi
FINAL_HEADER = BASE_COLS + ITEM_COLS + [TOTAL_COL]

# (tuỳ chọn) kiểm tra nhanh
# st.write({"BASE_COLS": BASE_COLS, "ITEM_COLS": ITEM_COLS, "FINAL_HEADER": FINAL_HEADER})


# ---- LOGIN ----
if "logged_in" not in st.session_state:
    st.session_state.update({
        "logged_in": False,
        "role": None,
        "username": None,
        "class_name": None,
        "teacher_name": None
    })

if not st.session_state.logged_in:
    # ---------------- Giao diện đăng nhập ----------------
    st.subheader("Đăng nhập")
    u = st.text_input("Tên đăng nhập")
    p = st.text_input("Mật khẩu", type="password")

    if st.button("Đăng nhập"):
        if acc_df.empty:
            st.error("Không có dữ liệu tài khoản.")
            st.stop()

        # Kiểm tra thông tin đăng nhập
        row = acc_df[acc_df["Username"] == u] if "Username" in acc_df.columns else acc_df[acc_df.iloc[:, 0] == u]

        if not row.empty:
            stored_pw = str(row.iloc[0].get("Password", ""))
            ok = hashlib.sha256(p.encode()).hexdigest() == stored_pw if USE_HASHED_PASSWORDS else (p == stored_pw)

            if ok:
                st.session_state.update({
                    "logged_in": True,
                    "username": u,
                    "role": str(row.iloc[0].get("Quyen", "User")).strip(),
                    "class_name": str(row.iloc[0].get("LopPhuTrach", "")),
                    "teacher_name": str(row.iloc[0].get("TenGiaoVien", "")),
                })
                st.success(f"Xin chào {st.session_state.teacher_name or u} 👋")
                st.rerun()
            else:
                st.error("Sai mật khẩu.")
        else:
            st.error("Không tìm thấy tài khoản.")
    st.stop()

else:
    # ---------------- Giao diện sau đăng nhập ----------------
  st.markdown("""
<style>
/* ===== 🌟 Tiêu đề trung tâm ===== */
.main-title-container {
    text-align: center !important;
    margin-top: 10px !important;
    margin-bottom: 25px !important;
    animation: fadeInDown 1.2s ease; /* ✨ Hiệu ứng mượt khi load */
}

/* 🌕 Dòng trên: Trung tâm GDNN - GDTX Thạnh Phú */
.main-title-container h2 {
    color: #FACC15 !important;   /* vàng nhạt */
    font-weight: 700;
    margin-bottom: 8px;
    font-size: 30px !important;  /* to rõ trên desktop */
    letter-spacing: 0.5px;
}

/* 💎 Dòng dưới: Ứng dụng tổng kết tuần */
.main-title-container h1 {
    color: #FDE047 !important;   /* vàng sáng hơn */
    font-weight: 900;
    margin: 0;
    font-size: 52px !important;  /* nổi bật trên desktop */
    line-height: 1.2em;
    text-shadow: 2px 2px 10px rgba(0,0,0,0.3); /* đổ bóng nhẹ cho đẹp */
}

/* 📱 Tablet và điện thoại */
@media (max-width: 768px) {
    .main-title-container h2 {
        font-size: 22px !important;
    }
    .main-title-container h1 {
        font-size: 32px !important;
    }
}

/* 📱 Điện thoại nhỏ hơn 480px */
@media (max-width: 480px) {
    .main-title-container h2 {
        font-size: 18px !important;
    }
    .main-title-container h1 {
        font-size: 26px !important;
    }
}

/* 💨 Hiệu ứng hiện dần từ trên xuống */
@keyframes fadeInDown {
  0% { opacity: 0; transform: translateY(-20px); }
  100% { opacity: 1; transform: translateY(0); }
}
</style>
""", unsafe_allow_html=True)

  st.markdown("""
        <div class="main-title-container">
            <h2>TT GDNN - GDTX THẠNH PHÚ</h2>
            <h1>ỨNG DỤNG TỔNG KẾT TUẦN</h1>
        </div>
    """, unsafe_allow_html=True)

# ---- MAIN ----
role = st.session_state.role
class_name = st.session_state.class_name
st.sidebar.write(f"👤 {st.session_state.username}")
st.sidebar.write(f"🔑 Quyền: {role}")
st.sidebar.write(f"📘 Lớp phụ trách: {class_name}")
if st.sidebar.button("Đăng xuất"):
    st.session_state.logged_in = False
    st.rerun()

CLASS_COL, WEEK_COL, TIME_COL, USER_COL, TOTAL_COL = cmap["CLASS"], cmap["WEEK"], cmap["TIME"], cmap["USER"], cmap["TOTAL"]
item_colmap = cmap["ITEMS"]

# ==== GIAO DIỆN ====
if role.lower() == "user":
    st.subheader(f"📋 Dữ liệu lớp {class_name}")
    view = score_df[score_df[CLASS_COL].astype(str) == str(class_name)]
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.write("### ✏️ Nhập mục & tính điểm")

    with st.form("score_form"):
        ngay_nhap = st.date_input("Ngày nhập", value=datetime.now().date())
        week = calc_week(ngay_nhap)
        st.text_input("Tuần (tự tính)", value=str(week), disabled=True)

        counts = {}
        for key, label, weight, _ in ITEMS:
            counts[key] = st.number_input(
                f"{label} ({weight:+})",
                min_value=0,
                step=1,
                value=0,
                key=f"input_{key}"
            )

        submitted = st.form_submit_button("💾 Lưu / Cập nhật")

    # 👇👇👇 ĐƯA KHỐI NÀY VÀO TRONG NHÁNH USER 👇👇👇
    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        week_str = str(week)

        # Update/Append bản ghi
        mask = (score_df[CLASS_COL].astype(str) == str(class_name)) & (score_df[WEEK_COL].astype(str) == week_str)
        if mask.any():
            idx = score_df[mask].index[0]
            for key, cnt in counts.items():
                score_df.loc[idx, item_colmap[key]] = int(cnt)
            score_df.loc[idx, TIME_COL] = now
            score_df.loc[idx, USER_COL] = st.session_state.username
        else:
            new = {c: "" for c in score_df.columns}
            new.update({
                CLASS_COL: str(class_name),
                WEEK_COL: week_str,
                TIME_COL: now,
                USER_COL: st.session_state.username,
            })
            for key, cnt in counts.items():
                new[item_colmap[key]] = int(cnt)
            score_df = pd.concat([score_df, pd.DataFrame([new])], ignore_index=True)

        # ✅ CÁCH 6: Ép số & tính lại Tổng điểm (có trọng số)
        score_df = ensure_columns(score_df, FINAL_HEADER, fill=0)
        score_df = coerce_numeric_int(score_df, ITEM_COLS)
        score_df = recompute_total_weighted(score_df, ITEMS, item_colmap, TOTAL_COL)

        # Hiển thị tổng điểm của dòng vừa thao tác
        try:
            total_now = int(
                score_df[
                    (score_df[CLASS_COL].astype(str) == str(class_name)) &
                    (score_df[WEEK_COL].astype(str) == week_str)
                ][TOTAL_COL].iloc[-1]
            )
        except Exception:
            total_now = 0

        st.success(f"✅ Đã lưu tuần {week}. Tổng điểm = {total_now}")

        # Ghi về Sheet
        save_score_reordered(
            score_ws,
            score_df,
            score_header,
            [TIME_COL, USER_COL, WEEK_COL, CLASS_COL],
            item_colmap.get("vesinhxaut")
        )
        st.rerun()


elif role.lower() == "admin":
    st.subheader("📋 Dữ liệu (Admin)")

    CLASS_COL = cmap["CLASS"]
    WEEK_COL  = cmap["WEEK"]
    TIME_COL  = cmap["TIME"]
    USER_COL  = cmap["USER"]
    TOTAL_COL = cmap["TOTAL"]
    item_colmap = cmap["ITEMS"]

    week_list  = sorted(score_df[WEEK_COL].dropna().astype(str).unique().tolist())
    class_list = sorted(score_df[CLASS_COL].dropna().astype(str).unique().tolist())
    sel_week   = st.selectbox("📅 Chọn tuần:",  ["Tất cả"] + week_list)
    sel_class  = st.selectbox("🏫 Chọn lớp:",   ["Tất cả"] + class_list)

    view_df = score_df.copy()
    if sel_week != "Tất cả":
        view_df = view_df[view_df[WEEK_COL].astype(str) == sel_week]
    if sel_class != "Tất cả":
        view_df = view_df[view_df[CLASS_COL].astype(str) == sel_class]

    # ✅ Bảng + nút submit phải nằm BÊN TRONG form và được thụt lề
    with st.form("admin_form", clear_on_submit=False):
        edited_df = st.data_editor(
            view_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="admin_editor"
        )
        save_admin = st.form_submit_button("💾 Lưu thay đổi")

    # ✅ Xử lý lưu vẫn thuộc NHÁNH ADMIN (cùng cấp với with), KHÔNG đưa ra ngoài
    if save_admin:
        try:
            key_cols = [CLASS_COL, WEEK_COL]

            # 0) Chuẩn hoá edited_df
            work = edited_df.copy()
            work = ensure_columns(work, FINAL_HEADER, fill=0)
            for k in key_cols:
                work[k] = work[k].astype(str).str.strip()

            # 1) Ép số & tính lại Tổng điểm
            work = coerce_numeric_int(work, ITEM_COLS)
            work = recompute_total_weighted(work, ITEMS, item_colmap, TOTAL_COL)

            # 2) Cập nhật thời gian
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            work[TIME_COL] = work.get(TIME_COL, "").replace("", now)

            # 3) Cập nhật in-place theo MultiIndex (giữ vị trí cũ)
            base = score_df.copy()
            for k in key_cols:
                base[k] = base[k].astype(str).str.strip()

            base_idxed = base.set_index(key_cols)
            WRITE_COLS = [c for c in FINAL_HEADER if c not in key_cols]
            work_by_key = work.set_index(key_cols)[WRITE_COLS]

            base_idxed.update(work_by_key)  # ghi đè key đã có
            to_add = work_by_key.loc[~work_by_key.index.isin(base_idxed.index)]
            if not to_add.empty:
                base_idxed = pd.concat([base_idxed, to_add], axis=0)

            base = base_idxed.reset_index()
            base = ensure_columns(base, FINAL_HEADER, fill=0)

            save_score_reordered(
                score_ws,
                base,
                score_header,
                [TIME_COL, USER_COL, WEEK_COL, CLASS_COL],
                item_colmap.get("vesinhxaut")
            )

            score_df = base
            st.success("✅ Đã lưu thay đổi cho phần đang chỉnh!")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Lỗi khi ghi dữ liệu: {e}")


# === PHÂN TÍCH AI BẰNG GEMINI ===
st.markdown("---")
st.subheader("🧠 Phân tích AI (Gemini)")

# Nhập module AI và Chat Box
from ai_analysis import init_gemini, summarize_scores
from chat_box import init_gemini as init_chat_gemini, render_chat_box

# --- Phân tích dữ liệu bằng AI ---
if st.button("✨ Tạo nhận xét tự động bằng AI"):
    init_gemini()
    with st.spinner("🤖 Đang phân tích dữ liệu..."):
        summary = summarize_scores(score_df)
        st.markdown("### 🧾 Nhận xét tổng hợp:")
        st.write(summary)
# ===================== BIỂU ĐỒ TÙY BIẾN =====================
st.markdown("### 📊 Biểu đồ tùy biến theo cột Tuần & Lớp")

# (1) Xác định các cột có thể dùng làm "Tuần"
num_like_cols = []
for c in score_df.columns:
    # ưu tiên cột hiện tại từ cmap
    if c == cmap["WEEK"]:
        num_like_cols.insert(0, c)
        continue
    # các cột khác có khả năng là tuần: toàn số hoặc số kiểu text phần lớn
    ser = pd.to_numeric(score_df[c], errors="coerce")
    if ser.notna().mean() >= 0.7:   # >=70% ép số được
        num_like_cols.append(c)

# fallback
if not num_like_cols:
    num_like_cols = [cmap["WEEK"]]

# (2) Chọn cột Tuần & lớp
col1, col2, col3 = st.columns([1.2, 1.2, 1])
with col1:
    sel_week_col = st.selectbox("🗂️ Chọn cột Tuần", options=num_like_cols, index=0)
with col2:
    # danh sách lớp
    class_col = cmap["CLASS"]
    all_classes = sorted(score_df[class_col].dropna().astype(str).unique().tolist())
    sel_classes = st.multiselect("🏫 Chọn lớp", options=["Tất cả"] + all_classes, default=["Tất cả"])
with col3:
    agg_mode = st.radio("Gộp", ["Mean", "Sum"], horizontal=True, index=0)

# (3) Chuẩn bị dữ liệu
df_chart = score_df.copy()
df_chart[sel_week_col] = pd.to_numeric(df_chart[sel_week_col], errors="coerce")
df_chart = df_chart.dropna(subset=[sel_week_col])
df_chart[sel_week_col] = df_chart[sel_week_col].astype(int)

total_col = cmap["TOTAL"]
df_chart[total_col] = pd.to_numeric(df_chart[total_col], errors="coerce").fillna(0)

# Lọc lớp (nếu không chọn "Tất cả")
if "Tất cả" not in sel_classes:
    df_chart = df_chart[df_chart[class_col].astype(str).isin([str(x) for x in sel_classes])]

# (4) Gộp theo tuần & lớp → có thể vẽ so sánh nhiều lớp
how = "mean" if agg_mode == "Mean" else "sum"
if how == "mean":
    grp = df_chart.groupby([sel_week_col, class_col], as_index=False)[total_col].mean()
else:
    grp = df_chart.groupby([sel_week_col, class_col], as_index=False)[total_col].sum()

# pivot: hàng = tuần, cột = lớp
pivot = grp.pivot(index=sel_week_col, columns=class_col, values=total_col).sort_index()

# (5) Tùy chọn làm mượt (rolling) & loại bỏ cột trống
roll = st.slider("📐 Trung bình trượt (tuần)", 1, 7, 3, help="Chọn 1 để tắt làm mượt")
if roll > 1:
    pivot = pivot.rolling(roll, min_periods=1).mean()

pivot = pivot.dropna(axis=1, how="all")  # bỏ lớp không có dữ liệu

# (6) Vẽ biểu đồ
if pivot.empty:
    st.info("Chưa có dữ liệu phù hợp để vẽ.")
else:
    st.line_chart(pivot, use_container_width=True)
    cap_class = "Tất cả lớp" if "Tất cả" in sel_classes else ", ".join([str(x) for x in sel_classes])
    st.caption(
        f"Trục X: {sel_week_col} • Dữ liệu: {agg_mode} {total_col} • Lớp: {cap_class} • "
        f"Rolling: {roll} tuần."
    )


# --- Chat Box (AI đọc dữ liệu thật theo lớp) ---
st.markdown("---")
st.subheader("💬 Trò chuyện cùng Trợ lý AI (Gemini)")

from chat_box import init_gemini as init_chat_gemini, render_chat_box

# 🔹 Khởi tạo Gemini
init_chat_gemini()

# 🔹 Lọc dữ liệu theo lớp đang đăng nhập
if role.lower() == "user":
    # Giáo viên chỉ xem dữ liệu lớp mình phụ trách
    class_data = score_df[score_df[CLASS_COL].astype(str) == str(class_name)]
else:
    # Admin xem toàn bộ
    class_data = score_df  

# 🔹 Truyền dữ liệu lớp cụ thể vào AI
render_chat_box(class_data)

