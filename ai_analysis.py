# ai_analysis.py
import pandas as pd
import google.generativeai as genai
import streamlit as st

def init_gemini():
    """Khởi tạo Gemini với API key từ secrets"""
    if "gemini_api_key" not in st.secrets:
        st.error("❌ Không tìm thấy gemini_api_key trong secrets.toml.")
        st.stop()
    genai.configure(api_key=st.secrets["gemini_api_key"])

def summarize_scores(df: pd.DataFrame) -> str:
    """Sinh nhận xét AI từ dữ liệu điểm bằng Gemini Pro 2.5"""
    if df.empty:
        return "⚠️ Không có dữ liệu để phân tích."

    if "Tổng điểm" not in df.columns:
        return "⚠️ Không tìm thấy cột 'Tổng điểm'."

    df["Tổng điểm"] = pd.to_numeric(df["Tổng điểm"], errors="coerce").fillna(0)
    avg = df["Tổng điểm"].mean()
    min_score = df["Tổng điểm"].min()
    max_score = df["Tổng điểm"].max()

    prompt = f"""
Bạn là **trợ lý ảo của Ban Giám Đốc Trung tâm**, có nhiệm vụ giúp tổng hợp báo cáo học tập
và nề nếp toàn Trung tâm dựa trên dữ liệu điểm của tất cả các lớp trong tuần.

Dưới đây là dữ liệu thống kê tổng hợp:
- Điểm trung bình toàn Trung tâm: {avg:.1f}
- Điểm cao nhất trong toàn Trung tâm: {max_score:.1f}
- Điểm thấp nhất trong toàn Trung tâm: {min_score:.1f}
- Tổng số lớp được ghi nhận: {len(df['Lớp'].unique()) if 'Lớp' in df.columns else 'N/A'}

Hãy viết **một đoạn nhận xét 8–10 câu** bằng tiếng Việt, có cấu trúc sau:
1️⃣ Mở đầu: Chào chung toàn thể giáo viên và học sinh, nêu tổng quan về tuần học.  
2️⃣ Phần chính:  
   - Đánh giá chung về tinh thần học tập, kỷ luật, phong trào  
   - Nêu điểm sáng (lớp hoặc nhóm học sinh nổi bật)  
   - Nêu hạn chế còn tồn tại  
3️⃣ Kết thúc: Lời động viên, định hướng tuần tới  

Giọng văn nên chuyên nghiệp, khách quan, ấm áp — thể hiện vai trò **trợ lý AI** đang viết
thay Ban Giám Đốc gửi đến toàn Trung tâm.  
Không xưng "tôi", chỉ dùng "nhà Trung tâm", "Ban Giám Đốc", hoặc "thầy cô".
"""


    model = genai.GenerativeModel("gemini-2.5-pro")  # 💪 dùng model mới nhất
    response = model.generate_content(prompt)
    return response.text.strip()
