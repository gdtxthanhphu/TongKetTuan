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
# KẾT NỐI GOOGLE SHEETS
# =========================
@st.cache_resource(show_spinner=False)
def get_client():
    try:
        return gspread.service_account(filename=SERVICE_FILE, scopes=SCOPES)
    except Exception as e:
        st.error(f"Lỗi khi tải service account: {e}")
        st.stop()

def open_sheets(gc):
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        return sh.worksheet("TaiKhoan"), sh.worksheet("Score")
    except Exception as e:
        st.error(f"Không thể mở Google Sheet. Kiểm tra quyền truy cập.\n{e}")
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
    Ghi DataFrame về tab Score theo thứ tự:
    Ngày nhập | Tên Tài Khoản | Tuần | Lớp | Vệ sinh chưa tốt | (các cột trong ITEMS theo thứ tự) | (cột dư nếu có)
    """
    # Cột lõi bắt buộc
    preferred = [c for c in core_cols if c and c in df.columns]

    # Nếu có cột "Vệ sinh chưa tốt", thêm vào sau cột lõi
    if vesinh_col and vesinh_col in df.columns and vesinh_col not in preferred:
        preferred.append(vesinh_col)

    # === Sắp cột theo logic ITEMS (theo thứ tự bạn định nghĩa trong ITEMS list) ===
    item_cols = []
    for key, label, _, _ in ITEMS:
        # Nếu tiêu đề trùng khớp tên cột thực trong sheet
        if label in df.columns:
            item_cols.append(label)
    item_cols = [c for c in item_cols if c not in preferred]

    # Các cột còn lại (phụ / thêm sau)
    extras = [c for c in df.columns if c not in preferred and c not in item_cols]

    # Hợp lại danh sách cột cuối cùng
    final_header = preferred + item_cols + extras

    # === Ghi vào Google Sheet ===
    ws.clear()
    data = [final_header] + df.reindex(columns=final_header).astype(str).values.tolist()
    ws.update(data, value_input_option="USER_ENTERED")


# =========================
# UI
# =========================
st.set_page_config(page_title="Tổng Kết Tuần", page_icon="🧮", layout="wide")

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

st.title("🧮 ỨNG DỤNG TỔNG KẾT TUẦN")

gc = get_client()
acc_ws, score_ws = open_sheets(gc)
acc_df = load_accounts(acc_ws)
score_df, score_header, cmap = parse_score(score_ws)

# ---- LOGIN ----
if "logged_in" not in st.session_state:
    st.session_state.update({"logged_in": False, "role": None, "username": None, "class_name": None, "teacher_name": None})

if not st.session_state.logged_in:
    st.subheader("🔐 Đăng nhập")
    u = st.text_input("Tên đăng nhập")
    p = st.text_input("Mật khẩu", type="password")
    if st.button("Đăng nhập"):
        if acc_df.empty:
            st.error("Không có dữ liệu tài khoản.")
            st.stop()
        row = acc_df[acc_df["Username"] == u] if "Username" in acc_df.columns else acc_df[acc_df.iloc[:,0] == u]
        if not row.empty:
            stored_pw = str(row.iloc[0].get("Password", ""))
            ok = hashlib.sha256(p.encode()).hexdigest() == stored_pw if USE_HASHED_PASSWORDS else (p == stored_pw)
            if ok:
                st.session_state.update({
                    "logged_in": True,
                    "username": u,
                    "role": str(row.iloc[0].get("Quyen","User")).strip(),
                    "class_name": str(row.iloc[0].get("LopPhuTrach", "")),
                    "teacher_name": str(row.iloc[0].get("TenGiaoVien","")),
                })
                st.success(f"Xin chào {st.session_state.teacher_name or u} 👋")
                st.rerun()
            else:
                st.error("Sai mật khẩu.")
        else:
            st.error("Không tìm thấy tài khoản.")
    st.stop()

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
    if st.button("💾 Lưu thay đổi vào Google Sheet"):
        save_score_reordered(score_ws, edited, score_header, [TIME_COL, USER_COL, WEEK_COL, CLASS_COL], item_colmap.get("vesinhxaut"))
        st.success("✅ Đã lưu thay đổi.")
        st.rerun()
