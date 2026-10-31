# VoxStudio – VoxCPM2 chạy local

Thư mục này **độc lập hoàn toàn**. Python, thư viện, model và cache đều nằm trong `E:\VoxStudio`. Nó không dùng chung gì với các bản VoxCPM khác trên máy.

## Chạy
- Mở bằng icon **VoxStudio** ngoài Desktop (hoặc bấm đúp `VoxStudio.vbs`). App mở trong cửa sổ riêng, đóng cửa sổ là app tự tắt (trừ khi đang đọc/huấn luyện dở — việc đó vẫn chạy tiếp tới khi xong).
- `run.bat` = chạy kèm cửa sổ đen để xem lỗi. `install.bat` = cài lại / sửa lỗi cài đặt (bước nào xong rồi sẽ bỏ qua).

## 📦 Cài sang máy khác
- Gửi file **VoxStudio-Setup-x.y.z.exe** cho máy kia → bấm đúp → chọn ổ cài (≥15GB trống) → đợi 15–40 phút. Xong có icon ngoài Desktop.
- Windows có thể hiện "Windows protected your PC" vì file chưa ký số → bấm **More info → Run anyway**.
- Giọng không tự sang máy khác: vào *Quản lý giọng → 📤 Chia sẻ giọng* để xuất file `.voxvoice`, máy kia bấm **📥 Nhập giọng**.

## 🔄 Cập nhật
- Người dùng: khi có bản mới, đầu trang hiện **🔔 Có bản cập nhật → Cập nhật ngay**. Bấm là xong, app tự khởi động lại. Giọng, dự án, kết quả không bị đụng tới; bản cũ được sao lưu trong `runtime\backup`.
- Người phát triển (máy gốc): sửa code xong → bấm **publish.bat** → nhập số phiên bản + ghi chú → code được đẩy lên GitHub → mọi máy thấy nút cập nhật.

## 🎤 Tạo giọng
1. Đặt tên, chọn **giọng mẫu nói tiếng gì** và **lưu giọng để đọc tiếng gì**. Hỗ trợ 30 ngôn ngữ của VoxCPM2.
2. Kéo thả các file giọng mẫu. **Nên dùng WAV hoặc MP3**, càng nhiều đoạn sạch càng tốt.
3. Bấm **✨ Tạo giọng**, rồi bấm **Nghe thử**.

Mục "Quản lý giọng (nâng cao)" dùng để:
- thêm đoạn mẫu, bật/tắt đoạn, cắt đoạn dài;
- sửa lời tham chiếu, đổi ngôn ngữ, đổi kiểu clone;
- đổi tên hoặc xoá giọng;
- huấn luyện LoRA.

## 📜 Đọc kịch bản
1. Thả file vào hoặc dán chữ. Nhận các định dạng: txt, srt, vtt, ass, json, csv, docx, pdf, epub, md, html...
2. Chọn **ngôn ngữ đọc**. Danh sách giọng sẽ chỉ hiện các giọng đã lưu cho ngôn ngữ đó. Tích "hiện cả giọng ngôn ngữ khác" nếu muốn đọc chéo ngôn ngữ.
3. Chọn loại video: Short/TikTok, YouTube dài, hoặc Sách nói.
4. Chỉnh phụ đề:
   - **số từ mỗi dòng** (với tiếng Trung, Nhật, Thái... thì tính theo số ký tự);
   - **1 hoặc 2 dòng mỗi khung**;
   - bỏ dấu câu cuối dòng.
5. Bấm **🎬 Tạo audio + phụ đề** để nhận WAV + MP3 + SRT.
   - Thời gian phụ đề được căn theo tiếng nói thật.
   - Muốn đổi kiểu phụ đề thì bấm **Xuất lại phụ đề**, không cần đọc lại.

## 🎭 Cảm xúc giọng đọc
- Chọn cảm xúc cho cả bài: Tự nhiên, Tự động theo nội dung, Kể chuyện đều, Ấm áp, Vui, Hào hứng, Buồn, Tin tức, Hồi hộp, Tức giận, Sợ hãi, Thì thầm, Quảng cáo, hoặc tự viết. Có 3 mức độ: Nhẹ, Vừa, Mạnh.
- **Tự động theo nội dung**: mỗi đoạn tự chọn cảm xúc theo từ ngữ trong đoạn đó (khóc → buồn, wow → hào hứng...). Đoạn trung tính giữ nguyên chất giọng mẫu.
- **Thẻ trong kịch bản**: gõ `[buồn]`, `[vui]`, `[hồi hộp]`, `[thì thầm]`, `[kể chuyện]`, `[bình thường]` hoặc `[style: tired, sleepy voice]`. Thẻ có hiệu lực từ chỗ gõ tới thẻ kế tiếp.
- Khi dùng cảm xúc, app chuyển sang chế độ "lấy âm sắc" để cảm xúc thể hiện được. Đoạn "Tự nhiên" vẫn dùng chế độ giống nhất.

## 🗂️ Dự án
Mọi lần đọc đều được lưu lại. Nếu bị dừng hoặc tắt máy giữa chừng, bấm **Chạy tiếp**. Có thể nghe lại, sửa chữ và đọc lại từng đoạn, sau đó bấm **Ghép & xuất lại**.

## Giới hạn VRAM
Mặc định `"auto"` = tổng VRAM của card trừ 1.5GB. Muốn đặt cố định (VD 10.5), sửa `vram_limit_gb` trong `settings.json`.

## Thư mục
| Thư mục | Nội dung |
|---|---|
| `voices\` | Giọng đã lưu. Giọng bị xoá được chuyển vào `voices\_trash` |
| `projects\` | Dự án đọc, có thể chạy tiếp |
| `outputs\` | File kết quả |
| `models\` | VoxCPM2, Whisper, ZipEnhancer |
| `logs\` | Log cài đặt, log app, log LoRA |
