# Ứng dụng Tổng Kết Tuần (Python + Google Sheets)

## Thư mục
- `app.py` — phiên bản **khóa theo lớp** (mỗi lớp chỉ sửa lớp mình)
- `app_open_access.py` — phiên bản **mở quyền** (ai đăng nhập cũng cập nhật mọi lớp)
- `requirements.txt` — thư viện cần cài

## Chuẩn bị Google Cloud & Google Sheets
1) Google Cloud Console
   - Tạo Project
   - Enable: Google Sheets API (bắt buộc), Google Drive API (khuyến nghị)
   - Tạo Service Account → tạo **JSON key** (ví dụ `service_account.json`)

2) Google Sheets
   - Tải file Excel của bạn lên Drive → **File → Save as Google Sheets**
   - Đặt tên bảng: **TỔNG KẾT TUẦN 1.2**
   - Tạo (hoặc kiểm tra) 2 tab:
     - `TaiKhoan`: cột `Username, Password, TenGiaoVien, LopPhuTrach, Quyen`
     - `Score`: cột `ThoiGian, Username, Lop, Tuan, HoatDong, SoTiet, GhiChu`
   - **Share** cho `client_email` trong `service_account.json` với quyền **Editor**

## Chạy ứng dụng
```bash
pip install -r requirements.txt
streamlit run app.py            # bản khóa theo lớp
# hoặc
streamlit run app_open_access.py  # bản mở quyền
```

## Bật mật khẩu băm (tuỳ chọn)
- Mở file app, đặt `USE_HASHED_PASSWORDS = True`
- Chuyển cột Password trong tab `TaiKhoan` sang chuỗi băm SHA-256.

## Lưu ý
- Không public `service_account.json`
- Nếu lỗi PERMISSION_DENIED: kiểm tra đã Share sheet đúng email service account chưa
- Nếu lỗi WorksheetNotFound: kiểm tra tên tab & tên file sheet
