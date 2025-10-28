import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, date
import hashlib
import unicodedata
import re

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
def save_score_reordered(ws, df, original_header, core_cols, vesinh_col):
    """
    ✅ Ghi DataFrame về Google Sheet với thứ tự cột cố định & tự tạo header nếu sheet trống.
    """
    # ====== CỘT CỐ ĐỊNH MẶC ĐỊNH ======
    base_headers = ["Ngày nhập", "Tên Tài Khoản", "Tuần", "Lớp"]

    # ====== Danh sách cột theo ITEMS (điểm, vi phạm, thưởng, v.v.) ======
    item_headers = [label for _, label, _, _ in ITEMS]

    # ====== Cột tổng điểm ======
    total_headers = ["Tổng điểm"]

    # ====== Nếu sheet trống hoặc không có header, tạo header mới ======
    if df.empty or len(df.columns) == 0:
        st.warning("⚠️ Sheet 'Score' trống — đang tự tạo tiêu đề chuẩn.")
        all_headers = base_headers + item_headers + total_headers
        ws.clear()
        ws.update([all_headers])
        return

    # ====== Chuẩn hóa tên cột trong df để khớp với header chuẩn ======
    normalized_cols = {N(col): col for col in df.columns}

    def find_col(name):
        nname = N(name)
        return normalized_cols.get(nname, name)

    # ====== Dò cột lõi trong df (nếu thiếu thì thêm vào) ======
    for col in base_headers + item_headers + total_headers:
        if col not in df.columns:
            df[col] = ""

    # ====== Xác định lại thứ tự cột ======
    final_header = [find_col(c) for c in base_headers] + \
                   [find_col(c) for c in item_headers] + \
                   [find_col(c) for c in total_headers]

    # ====== Ghi dữ liệu theo thứ tự chuẩn ======
    ws.clear()
    data = [final_header] + df.reindex(columns=final_header).astype(str).values.tolist()
    ws.update(data, value_input_option="USER_ENTERED")

    st.success("✅ Đã lưu dữ liệu và tự động sắp xếp cột đúng thứ tự.")

# =========================
# UI
# =========================
st.set_page_config(page_title="Tổng Kết Tuần", page_icon="🧮", layout="wide")
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
/* === 🌟 Tiêu đề trung tâm === */
.main-title-container {
    text-align: center !important;
    margin-top: 20px;
    margin-bottom: 35px;
}

/* Dòng TRUNG TÂM GDNN - GDTX THẠNH PHÚ */
.main-title-container h2 {
    color: #FACC15 !important; /* vàng nhạt */
    font-weight: 700;
    margin-bottom: 8px;
    font-size: clamp(16px, 2.5vw, 24px); /* Tự co giãn theo chiều rộng */
}

/* Dòng ỨNG DỤNG TỔNG KẾT TUẦN */
.main-title-container h1 {
    color: #1E3A8A !important; /* xanh dương đậm */
    font-weight: 900;
    margin: 0;
    font-size: clamp(22px, 4vw, 48px); /* co giãn theo màn hình */
    line-height: 1.2em;
}

/* === 📱 Tùy chỉnh thêm cho điện thoại nhỏ hơn 480px === */
@media (max-width: 480px) {
    .main-title-container h1 {
        font-size: 26px !important;
    }
    .main-title-container h2 {
        font-size: 18px !important;
    }
}
</style>
""", unsafe_allow_html=True)

    st.markdown("""
        <style>
        .main-title-container {
            text-align: center !important;
            margin-top: 20px;
            margin-bottom: 35px;
        }
        .main-title-container h2 {
            color: #FFD700;
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .main-title-container h1 {
            color: #1E3A8A;
            font-size: 20px;
            font-weight: 900;
            margin: 0;
        }
        </style>

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
        counts, total = {}, 0
        cols = st.columns(3)
        for i, (key, label, weight, _) in enumerate(ITEMS):
            with cols[i % 3]:
                counts[key] = st.number_input(f"{label} ({weight:+})", min_value=0, step=1, value=0)
                total += counts[key] * weight
        submitted = st.form_submit_button("💾 Lưu / Cập nhật")

    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mask = (score_df[CLASS_COL] == class_name) & (score_df[WEEK_COL].astype(str) == str(week))
        if mask.any():
            idx = score_df[mask].index[0]
            for key, cnt in counts.items():
                score_df.loc[idx, item_colmap[key]] = int(cnt)
            score_df.loc[idx, TOTAL_COL] = int(total)
            score_df.loc[idx, TIME_COL] = now
            st.success(f"✅ Đã cập nhật tuần {week}. Tổng điểm = {total}")
        else:
            new = {c: "" for c in score_df.columns}
            new.update({
                CLASS_COL: class_name,
                WEEK_COL: str(week),
                TIME_COL: now,
                USER_COL: st.session_state.username,
                TOTAL_COL: total
            })
            for key, cnt in counts.items():
                new[item_colmap[key]] = int(cnt)
            score_df = pd.concat([score_df, pd.DataFrame([new])], ignore_index=True)
            st.success(f"✅ Đã thêm bản ghi tuần {week}. Tổng điểm = {total}")

        save_score_reordered(score_ws, score_df, score_header, [TIME_COL, USER_COL, WEEK_COL, CLASS_COL], item_colmap.get("vesinhxaut"))
        st.rerun()

elif role.lower() == "admin":
    st.subheader("📋 Dữ liệu (Admin)")
    edited = st.data_editor(score_df, use_container_width=True, num_rows="dynamic", hide_index=True)
    if st.button("💾 Lưu thay đổi"):
        save_score_reordered(score_ws, edited, score_header, [TIME_COL, USER_COL, WEEK_COL, CLASS_COL], item_colmap.get("vesinhxaut"))
        st.success("✅ Đã lưu thay đổi.")
        st.rerun()

