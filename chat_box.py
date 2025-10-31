import streamlit as st
import google.generativeai as genai
import pandas as pd


def init_gemini():
    """Khởi tạo Gemini bằng API key trong secrets.toml"""
    if "gemini_api_key" not in st.secrets:
        st.error("❌ Thiếu gemini_api_key trong secrets.toml.")
        st.stop()
    genai.configure(api_key=st.secrets["gemini_api_key"])


def render_chat_box(score_df: pd.DataFrame):
    """Hiển thị khung chat cho phép Gemini truy cập dữ liệu bảng điểm thực tế"""
    st.markdown("Hãy hỏi về tình hình học tập, vi phạm, điểm trung bình... 👇")

    # --- Chuẩn hóa dữ liệu ---
    df = score_df.copy()
    df["Tổng điểm"] = pd.to_numeric(df["Tổng điểm"], errors="coerce").fillna(0)
    df = df.head(300)
    data_text = df.to_json(orient="records", force_ascii=False)

    # === TẠCH CHAT RIÊNG CHO TỪNG NGƯỜI / LỚP ===
    username = st.session_state.get("username", "guest")
    role = st.session_state.get("role", "user").lower()
    class_name = st.session_state.get("class_name", "all")

    user_key = f"chat_history_{username}_{class_name}"

    # --- Định nghĩa giọng nói AI ---
    if role == "admin":
        personality = (
            "Bạn là Trợ lý Ban Giám Đốc. "
            "Hãy phân tích dữ liệu học tập, nề nếp của toàn trường một cách tổng quan, "
            "với giọng trang trọng, chuyên nghiệp. "
            "Nếu có số liệu cụ thể, hãy đưa ra nhận xét theo tuần hoặc theo lớp."
        )
    else:
        personality = (
            f"Bạn là Trợ lý Giáo viên chủ nhiệm của lớp {class_name}. "
            "Hãy nói với giọng thân thiện, gần gũi, nhẹ nhàng. "
            "Trả lời dựa trên dữ liệu thật của lớp, đưa ra nhận xét cụ thể từng tuần, "
            "và có thể động viên học viên nếu phù hợp."
        )

    # --- Tạo hội thoại khởi tạo nếu chưa có ---
    if user_key not in st.session_state:
        st.session_state[user_key] = [
            {
                "role": "user",
                "parts": [{"text": personality}],
            },
            {
                "role": "user",
                "parts": [{
                    "text": f"Dưới đây là dữ liệu bảng điểm (JSON):\n{data_text}\n"
                            "Hãy ghi nhớ và sử dụng khi trả lời các câu hỏi."
                }]
            }
        ]

    chat_history = st.session_state[user_key]

    # --- Hiển thị lịch sử chat ---
    for msg in chat_history:
        text = msg["parts"][0]["text"]
        if "Dưới đây là dữ liệu bảng điểm" in text or "Trợ lý" in text:
            continue
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(text)

    # --- Ô nhập chat ---
    prompt = st.chat_input("Nhập câu hỏi của bạn về dữ liệu...")
    if prompt:
        user_msg = {"role": "user", "parts": [{"text": prompt}]}
        chat_history.append(user_msg)

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("🤖 Trợ lý đang suy nghĩ..."):
                try:
                    model = genai.GenerativeModel("gemini-2.5-pro")
                    response = model.generate_content(chat_history)
                    ai_text = response.text.strip() if response.text else "Không có phản hồi."
                except Exception as e:
                    ai_text = f"❌ Lỗi khi gọi Gemini: {e}"

                st.markdown(ai_text)

        chat_history.append({"role": "model", "parts": [{"text": ai_text}]})
