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
    """Hiển thị Chat Box cho phép Gemini truy cập dữ liệu bảng điểm"""
    st.subheader("💬 Trò chuyện cùng Trợ lý AI (Gemini)")
    st.markdown("Hãy hỏi về tình hình các lớp 👇")

    # --- Chuẩn hóa dữ liệu ---
    df = score_df.copy()
    df["Tổng điểm"] = pd.to_numeric(df["Tổng điểm"], errors="coerce").fillna(0)
    df = df.head(300)  # tránh gửi quá nhiều dòng
    data_text = df.to_json(orient="records", force_ascii=False)

    # --- Khởi tạo lịch sử hội thoại nếu chưa có ---
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "user",
                "parts": [{
                    "text": (
                        "Bạn là trợ lý ảo của Ban Giám Hiệu, giúp giáo viên phân tích dữ liệu học tập "
                        "và nề nếp học sinh. Hãy đọc dữ liệu bảng điểm sau đây và ghi nhớ nó để trả lời "
                        "các câu hỏi tiếp theo dựa trên dữ liệu thật của trường."
                    )
                }]
            },
            {
                "role": "user",
                "parts": [{
                    "text": f"Dưới đây là dữ liệu bảng điểm (JSON):\n{data_text}\n"
                            "Hãy ghi nhớ và sử dụng khi trả lời các câu hỏi."
                }]
            }
        ]

    # --- Hiển thị lịch sử chat (ẩn phần khởi tạo dữ liệu) ---
    for msg in st.session_state.chat_history:
        text = msg["parts"][0]["text"]

        # Bỏ qua tin nhắn khởi tạo ban đầu
        if "Dưới đây là dữ liệu bảng điểm" in text or "Bạn là trợ lý ảo của Ban Giám Hiệu" in text:
            continue

        # Hiển thị phần chat thật sự
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(text)

    # --- Ô nhập chat ---
    prompt = st.chat_input("Nhập câu hỏi của bạn về dữ liệu...")
    if prompt:
        # Thêm tin nhắn người dùng
        user_msg = {"role": "user", "parts": [{"text": prompt}]}
        st.session_state.chat_history.append(user_msg)

        with st.chat_message("user"):
            st.markdown(prompt)

        # Gọi AI Gemini
        with st.chat_message("assistant"):
            with st.spinner("🤖 Đang phân tích dữ liệu..."):
                try:
                    model = genai.GenerativeModel("gemini-2.5-pro")
                    response = model.generate_content(st.session_state.chat_history)
                    ai_text = response.text.strip() if response.text else "Không có phản hồi."
                except Exception as e:
                    ai_text = f"❌ Lỗi khi gọi Gemini: {e}"

                st.markdown(ai_text)

        # Lưu phản hồi (vai trò 'model' thay vì 'assistant' để phù hợp API)
        st.session_state.chat_history.append(
            {"role": "model", "parts": [{"text": ai_text}]}
        )
