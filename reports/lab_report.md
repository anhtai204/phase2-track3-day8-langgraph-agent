# Day 08 Lab Report

## 1. Team / student

- Name: Nguyễn Anh Tài
- Repo/commit: [phase2-track3-day8-langgraph-agent](https://github.com/anhtai204/phase2-track3-day8-langgraph-agent.git)
- Date: 2026-05-11

## 2. Architecture

Hệ thống được thiết kế dưới dạng một **StateGraph** tuần tự và có điều kiện:
- **Nodes**: 
    - `intake`: Chuẩn hóa dữ liệu đầu vào.
    - `classify`: Phân loại yêu cầu dựa trên từ khóa ưu tiên (Risky > Tool > Missing > Error > Simple).
    - `tool` & `evaluate`: Cặp node xử lý công cụ và kiểm tra kết quả để tạo vòng lặp retry.
    - `approval`: Node ngắt (Interrupt) để chờ phê duyệt cho các tác vụ nguy hiểm.
    - `retry` & `dead_letter`: Quản lý việc thử lại có giới hạn.
    - `answer`, `clarify`, `finalize`: Các node đầu ra và kết thúc luồng.
- **Edges**: Sử dụng `conditional_edges` sau các bước `classify`, `evaluate`, `approval` và `retry` để điều hướng linh hoạt.

## 3. State schema

Các trường trạng thái được thiết kế để đảm bảo tính minh bạch (auditability) và khả năng phục hồi.

| Field | Reducer | Why |
|---|---|---|
| messages | append | Lưu trữ lịch sử hội thoại và thông tin các bước |
| tool_results | append | Lưu trữ tất cả kết quả từ công cụ để đối chiếu |
| errors | append | Ghi lại lịch sử các lỗi tạm thời để phân tích |
| events | append | Audit trail chi tiết cho việc trực quan hóa Dashboard |
| route | overwrite | Chỉ lưu lộ trình hiện tại để định tuyến |
| attempt | overwrite | Biến đếm số lần thử lại hiện tại |
| approval | overwrite | Trạng thái phê duyệt mới nhất từ người dùng |

## 4. Scenario results

Dưới đây là kết quả từ file `outputs/metrics.json` sau khi chạy 7 kịch bản:

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | ✅ | 0 | 0 |
| S02_tool | tool | tool | ✅ | 0 | 0 |
| S03_missing | missing_info | missing_info | ✅ | 0 | 0 |
| S04_risky | risky | risky | ✅ | 0 | 1 |
| S05_error | error | error | ✅ | 2 | 0 |
| S06_delete | risky | risky | ✅ | 0 | 1 |
| S07_dead_letter | error | error | ✅ | 1 | 0 |

## 5. Failure analysis

1. **Retry / Tool failure**: Xử lý lỗi tạm thời trong scenario `S05_error`. Hệ thống phát hiện lỗi "ERROR", tăng biến `attempt` và quay lại node `tool`. Sau 2 lần thử, nó thành công.
2. **Exhausted Retries**: Trong `S07_dead_letter`, với `max_attempts=1`, hệ thống nhận diện việc vượt quá giới hạn ngay sau lỗi đầu tiên và chuyển sang node `dead_letter` thay vì lặp vô tận.

## 6. Persistence / recovery evidence

- **Checkpointer**: Sử dụng `SqliteSaver` lưu vào file `outputs/checkpoint.db`.
- **Thread ID**: Mỗi scenario được gán một `thread_id` duy nhất (ví dụ: `thread-S04_risky`), cho phép truy xuất lịch sử cụ thể của phiên làm việc đó.
- **Recovery**: Nhờ SQLite, trạng thái Agent được bảo toàn ngay cả khi tiến trình bị ngắt giữa chừng tại bước `approval`.

## 7. Extension work

Tôi đã hoàn thành 3 phần mở rộng để đạt mức điểm tối đa:
- **SQLite Persistence**: Thay thế MemorySaver bằng cơ sở dữ liệu SQLite thật.
- **Graph Diagram**: Xuất sơ đồ Mermaid để trực quan hóa kiến trúc hệ thống.
- **Streamlit Dashboard**: Xây dựng giao diện UI chuyên nghiệp để theo dõi log, timeline và message thread của Agent.

## 8. Improvement plan

1. **LLM Classifier**: Sử dụng LLM để phân loại yêu cầu thay vì regex/keyword để tăng độ chính xác ngữ nghĩa.
2. **Exponential Backoff**: Áp dụng thời gian chờ tăng dần giữa các lần retry để bảo vệ hệ thống downstream.
