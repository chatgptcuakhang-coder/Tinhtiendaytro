import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

# =========================================================
# 1. CẤU HÌNH ỨNG DỤNG
# =========================================================

st.set_page_config(
    page_title="Quản lý tiền phòng trọ",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 PHẦN MỀM QUẢN LÝ THU TIỀN DÃY TRỌ - VŨ ĐỨC BÌNH")

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "quan_ly_tien_tro.db",
)

TRANG_THAI = ["Chưa thanh toán", "Đã thanh toán"]


# =========================================================
# 2. KẾT NỐI VÀ KHỞI TẠO SQLITE
# =========================================================

def ket_noi_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def khoi_tao_database():
    with ket_noi_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                room_no INTEGER NOT NULL,
                rent_price INTEGER NOT NULL DEFAULT 2500000,
                tenant_info TEXT NOT NULL DEFAULT '',
                electric_old INTEGER NOT NULL DEFAULT 0,
                electric_new INTEGER NOT NULL DEFAULT 0,
                water_old INTEGER NOT NULL DEFAULT 0,
                water_new INTEGER NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'Chưa thanh toán',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (year, month, room_no)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
        """)

        # Các cấu hình mặc định, chỉ thêm nếu chưa tồn tại.
        defaults = {
            "gia_dien": "3500",
            "gia_nuoc": "15000",
            "phi_khac": "150000",
            "so_phong": "10",
        }

        for key, value in defaults.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings
                (setting_key, setting_value)
                VALUES (?, ?)
                """,
                (key, value),
            )


def doc_cau_hinh(key, default):
    with ket_noi_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return default

    try:
        return int(row["setting_value"])
    except (TypeError, ValueError):
        return default


def luu_cau_hinh(key, value):
    with ket_noi_db() as conn:
        conn.execute(
            """
            INSERT INTO settings (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value = excluded.setting_value
            """,
            (key, str(value)),
        )


def doc_phong(nam, thang, phong):
    with ket_noi_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM bills
            WHERE year = ? AND month = ? AND room_no = ?
            """,
            (nam, thang, phong),
        ).fetchone()

    return dict(row) if row else None


def luu_phong(nam, thang, phong, data):
    with ket_noi_db() as conn:
        conn.execute(
            """
            INSERT INTO bills (
                year, month, room_no, rent_price, tenant_info,
                electric_old, electric_new, water_old, water_new,
                payment_status, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(year, month, room_no)
            DO UPDATE SET
                rent_price = excluded.rent_price,
                tenant_info = excluded.tenant_info,
                electric_old = excluded.electric_old,
                electric_new = excluded.electric_new,
                water_old = excluded.water_old,
                water_new = excluded.water_new,
                payment_status = excluded.payment_status,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                nam,
                thang,
                phong,
                data["rent_price"],
                data["tenant_info"],
                data["electric_old"],
                data["electric_new"],
                data["water_old"],
                data["water_new"],
                data["payment_status"],
            ),
        )


def khoi_tao_du_lieu_thang(nam, thang, so_phong):
    """
    Tạo dữ liệu cho những phòng chưa có trong tháng đang chọn.
    Chỉ số cũ lấy từ chỉ số mới của tháng trước nếu có.
    Không ghi đè dữ liệu đã lưu.
    """
    if thang == 1:
        nam_truoc = nam - 1
        thang_truoc = 12
    else:
        nam_truoc = nam
        thang_truoc = thang - 1

    with ket_noi_db() as conn:
        for phong in range(1, so_phong + 1):
            da_co = conn.execute(
                """
                SELECT 1 FROM bills
                WHERE year = ? AND month = ? AND room_no = ?
                """,
                (nam, thang, phong),
            ).fetchone()

            if da_co:
                continue

            thang_truoc_data = conn.execute(
                """
                SELECT electric_new, water_new
                FROM bills
                WHERE year = ? AND month = ? AND room_no = ?
                """,
                (nam_truoc, thang_truoc, phong),
            ).fetchone()

            dien_cu = (
                thang_truoc_data["electric_new"]
                if thang_truoc_data else 0
            )
            nuoc_cu = (
                thang_truoc_data["water_new"]
                if thang_truoc_data else 0
            )

            conn.execute(
                """
                INSERT INTO bills (
                    year, month, room_no, rent_price, tenant_info,
                    electric_old, electric_new, water_old, water_new,
                    payment_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nam,
                    thang,
                    phong,
                    2500000,
                    "",
                    dien_cu,
                    dien_cu,
                    nuoc_cu,
                    nuoc_cu,
                    "Chưa thanh toán",
                ),
            )


def dong_bo_thang_sau(nam, thang, phong, dien_moi, nuoc_moi):
    """
    Nếu tháng sau đã có dữ liệu, cập nhật chỉ số cũ của tháng sau.
    """
    if thang == 12:
        nam_sau = nam + 1
        thang_sau = 1
    else:
        nam_sau = nam
        thang_sau = thang + 1

    with ket_noi_db() as conn:
        conn.execute(
            """
            UPDATE bills
            SET electric_old = ?,
                water_old = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE year = ? AND month = ? AND room_no = ?
            """,
            (dien_moi, nuoc_moi, nam_sau, thang_sau, phong),
        )


khoi_tao_database()


# =========================================================
# 3. SIDEBAR - CẤU HÌNH GIÁ VÀ SỐ PHÒNG
# =========================================================

st.sidebar.header("⚙️ ĐƠN GIÁ ĐIỆN NƯỚC")

gia_dien = st.sidebar.number_input(
    "⚡ Giá điện (đ/kWh)",
    min_value=0,
    value=doc_cau_hinh("gia_dien", 3500),
    step=100,
    key="setting_gia_dien",
)

gia_nuoc = st.sidebar.number_input(
    "💧 Giá nước (đ/m³)",
    min_value=0,
    value=doc_cau_hinh("gia_nuoc", 15000),
    step=500,
    key="setting_gia_nuoc",
)

phi_khac = st.sidebar.number_input(
    "📦 Phí khác (wifi, vệ sinh...)",
    min_value=0,
    value=doc_cau_hinh("phi_khac", 150000),
    step=10000,
    key="setting_phi_khac",
)

so_phong = st.sidebar.slider(
    "Số lượng phòng",
    min_value=1,
    max_value=100,
    value=max(1, min(100, doc_cau_hinh("so_phong", 10))),
    step=1,
    key="setting_so_phong",
)

luu_cau_hinh("gia_dien", gia_dien)
luu_cau_hinh("gia_nuoc", gia_nuoc)
luu_cau_hinh("phi_khac", phi_khac)
luu_cau_hinh("so_phong", so_phong)


# =========================================================
# 4. CHỌN THÁNG VÀ NĂM
# =========================================================

col_nam, col_thang = st.sidebar.columns(2)

nam_hien_tai = datetime.now().year
danh_sach_nam = list(range(nam_hien_tai - 1, nam_hien_tai + 6))

with col_nam:
    nam_chon = st.selectbox(
        "Chọn năm:",
        danh_sach_nam,
        index=danh_sach_nam.index(nam_hien_tai),
    )

with col_thang:
    thang_chon_so = st.selectbox(
        "Chọn tháng:",
        list(range(1, 13)),
        index=datetime.now().month - 1,
        format_func=lambda x: f"Tháng {x}",
    )

thang_chon = f"Tháng {thang_chon_so}/{nam_chon}"

khoi_tao_du_lieu_thang(nam_chon, thang_chon_so, so_phong)


# =========================================================
# 5. NHẬP VÀ CẬP NHẬT THÔNG TIN PHÒNG
# =========================================================

st.header(f"📋 Nhập số liệu - {thang_chon}")

phong = st.selectbox(
    "Chọn phòng cần cập nhật:",
    range(1, so_phong + 1),
    format_func=lambda x: f"Phòng {x}",
    key=f"chon_phong_{nam_chon}_{thang_chon_so}",
)

data = doc_phong(nam_chon, thang_chon_so, phong)

st.subheader(f"🏠 Cập nhật: Phòng {phong} ({thang_chon})")

# Thông tin người ở được đặt cạnh giá phòng.
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    gia_phong = st.number_input(
        "Giá phòng (VNĐ)",
        min_value=0,
        value=int(data["rent_price"]),
        step=50000,
        key=f"gia_{nam_chon}_{thang_chon_so}_{phong}",
    )

with c2:
    thong_tin_nguoi_o = st.text_input(
        "Thông tin người ở",
        value=data["tenant_info"],
        placeholder="Tên, SĐT, số người...",
        key=f"nguoi_o_{nam_chon}_{thang_chon_so}_{phong}",
    )

with c3:
    dien_cu = st.number_input(
        "Số điện CŨ",
        min_value=0,
        value=int(data["electric_old"]),
        key=f"dien_cu_{nam_chon}_{thang_chon_so}_{phong}",
    )

with c4:
    dien_moi = st.number_input(
        "Số điện MỚI",
        min_value=0,
        value=int(data["electric_new"]),
        key=f"dien_moi_{nam_chon}_{thang_chon_so}_{phong}",
    )

with c5:
    nuoc_cu = st.number_input(
        "Số nước CŨ",
        min_value=0,
        value=int(data["water_old"]),
        key=f"nuoc_cu_{nam_chon}_{thang_chon_so}_{phong}",
    )

with c6:
    nuoc_moi = st.number_input(
        "Số nước MỚI",
        min_value=0,
        value=int(data["water_new"]),
        key=f"nuoc_moi_{nam_chon}_{thang_chon_so}_{phong}",
    )

trang_thai = st.selectbox(
    "💳 Trạng thái thanh toán",
    TRANG_THAI,
    index=TRANG_THAI.index(data["payment_status"])
    if data["payment_status"] in TRANG_THAI else 0,
    key=f"trang_thai_{nam_chon}_{thang_chon_so}_{phong}",
)

if dien_moi < dien_cu:
    st.warning("Chỉ số điện mới nhỏ hơn chỉ số cũ. Tiền điện sẽ được tính bằng 0.")

if nuoc_moi < nuoc_cu:
    st.warning("Chỉ số nước mới nhỏ hơn chỉ số cũ. Tiền nước sẽ được tính bằng 0.")

data_cap_nhat = {
    "rent_price": int(gia_phong),
    "tenant_info": thong_tin_nguoi_o.strip(),
    "electric_old": int(dien_cu),
    "electric_new": int(dien_moi),
    "water_old": int(nuoc_cu),
    "water_new": int(nuoc_moi),
    "payment_status": trang_thai,
}

# Tự động lưu mỗi khi dữ liệu thay đổi.
luu_phong(nam_chon, thang_chon_so, phong, data_cap_nhat)

# Đồng bộ chỉ số sang tháng sau nếu tháng sau đã có bản ghi.
dong_bo_thang_sau(
    nam_chon,
    thang_chon_so,
    phong,
    int(dien_moi),
    int(nuoc_moi),
)

st.caption("Dữ liệu phòng được tự động lưu vào SQLite khi bạn cập nhật.")


# =========================================================
# 6. TÍNH TIỀN VÀ LẬP BẢNG TỔNG HỢP
# =========================================================

ket_qua = []
tong_doanh_thu = 0
tong_da_thu = 0
tong_chua_thu = 0

with ket_noi_db() as conn:
    danh_sach_phong = conn.execute(
        """
        SELECT * FROM bills
        WHERE year = ? AND month = ? AND room_no BETWEEN 1 AND ?
        ORDER BY room_no
        """,
        (nam_chon, thang_chon_so, so_phong),
    ).fetchall()

for row in danh_sach_phong:
    d = dict(row)

    so_dien = max(d["electric_new"] - d["electric_old"], 0)
    so_nuoc = max(d["water_new"] - d["water_old"], 0)

    tien_dien = so_dien * gia_dien
    tien_nuoc = so_nuoc * gia_nuoc

    tong_tien = (
        d["rent_price"]
        + tien_dien
        + tien_nuoc
        + phi_khac
    )

    tong_doanh_thu += tong_tien

    if d["payment_status"] == "Đã thanh toán":
        tong_da_thu += tong_tien
    else:
        tong_chua_thu += tong_tien

    ket_qua.append({
        "Phòng": f"Phòng {d['room_no']}",
        "Thông tin người ở": d["tenant_info"],
        "Giá phòng": d["rent_price"],
        "Số điện cũ": d["electric_old"],
        "Số điện mới": d["electric_new"],
        "Tiền điện": tien_dien,
        "Số nước cũ": d["water_old"],
        "Số nước mới": d["water_new"],
        "Tiền nước": tien_nuoc,
        "Phí khác": phi_khac,
        "Tổng tiền": tong_tien,
        "Trạng thái thanh toán": d["payment_status"],
    })


# =========================================================
# 7. HIỂN THỊ BẢNG, DOANH THU VÀ XUẤT CSV
# =========================================================

st.divider()
st.header(f"📊 Bảng tổng hợp tiền trọ - {thang_chon}")


def dinh_dang_tien(so_tien):
    return f"{so_tien:,.0f}".replace(",", ".") + " VNĐ"


if ket_qua:
    df = pd.DataFrame(ket_qua)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Giá phòng": st.column_config.NumberColumn(format="%d"),
            "Tiền điện": st.column_config.NumberColumn(format="%d"),
            "Tiền nước": st.column_config.NumberColumn(format="%d"),
            "Phí khác": st.column_config.NumberColumn(format="%d"),
            "Tổng tiền": st.column_config.NumberColumn(format="%d"),
        },
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        f"Tổng tiền phải thu ({thang_chon})",
        dinh_dang_tien(tong_doanh_thu),
    )

    m2.metric(
        "Đã thu",
        dinh_dang_tien(tong_da_thu),
    )

    m3.metric(
        "Chưa thu",
        dinh_dang_tien(tong_chua_thu),
    )

    csv = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label=f"📥 Xuất báo cáo CSV - {thang_chon}",
        data=csv,
        file_name=f"Bang_Tien_Phong_Thang_{thang_chon_so}_{nam_chon}.csv",
        mime="text/csv",
    )

else:
    st.info("Chưa có dữ liệu phòng cho tháng này.")


# =========================================================
# 8. TẠO PDF PHIẾU TIỀN TRỌ THEO TỪNG PHÒNG
# =========================================================

def dang_ky_font_tieng_viet():
    """
    Tìm font TrueType có hỗ trợ tiếng Việt.
    Nếu không tìm được, dùng Helvetica dự phòng.
    """
    if "TroFont" in pdfmetrics.getRegisteredFontNames():
        return "TroFont", "TroFontBold"

    font_paths = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ),
        (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ),
    ]

    for regular_path, bold_path in font_paths:
        if os.path.exists(regular_path):
            try:
                pdfmetrics.registerFont(
                    TTFont("TroFont", regular_path)
                )

                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(
                        TTFont("TroFontBold", bold_path)
                    )
                else:
                    pdfmetrics.registerFont(
                        TTFont("TroFontBold", regular_path)
                    )

                return "TroFont", "TroFontBold"

            except Exception:
                continue

    return "Helvetica", "Helvetica-Bold"


def tao_pdf_phieu_tien_tro(
    nam,
    thang,
    phong,
    data,
    gia_dien_pdf,
    gia_nuoc_pdf,
    phi_khac_pdf,
):
    buffer = io.BytesIO()

    font_regular, font_bold = dang_ky_font_tieng_viet()

    so_dien = max(data["electric_new"] - data["electric_old"], 0)
    so_nuoc = max(data["water_new"] - data["water_old"], 0)

    tien_dien = so_dien * gia_dien_pdf
    tien_nuoc = so_nuoc * gia_nuoc_pdf

    tong_tien = (
        data["rent_price"]
        + tien_dien
        + tien_nuoc
        + phi_khac_pdf
    )

    def tien(value):
        return f"{value:,.0f}".replace(",", ".") + " VNĐ"

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Phieu tien tro phong {phong} thang {thang}-{nam}",
        author="Phần mềm quản lý tiền trọ",
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="TieuDeTro",
        fontName=font_bold,
        fontSize=17,
        leading=23,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#314E3B"),
        spaceAfter=8,
    ))

    styles.add(ParagraphStyle(
        name="PhuDeTro",
        fontName=font_regular,
        fontSize=11,
        leading=17,
        alignment=TA_CENTER,
        spaceAfter=12,
    ))

    styles.add(ParagraphStyle(
        name="NoiDungTro",
        fontName=font_regular,
        fontSize=10,
        leading=16,
    ))

    styles.add(ParagraphStyle(
        name="TongTienTro",
        fontName=font_bold,
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#314E3B"),
    ))

    story = []

    story.append(Paragraph(
        "PHIẾU TIỀN PHÒNG TRỌ",
        styles["TieuDeTro"],
    ))

    story.append(Paragraph(
        f"Phòng {phong} - Tháng {thang}/{nam}",
        styles["PhuDeTro"],
    ))

    ten_nguoi_o = escape(data["tenant_info"] or "Chưa cập nhật")

    story.append(Paragraph(
        f"<b>Thông tin người ở:</b> {ten_nguoi_o}",
        styles["NoiDungTro"],
    ))

    story.append(Paragraph(
        f"<b>Trạng thái thanh toán:</b> "
        f"{escape(data['payment_status'])}",
        styles["NoiDungTro"],
    ))

    story.append(Spacer(1, 8 * mm))

    rows = [
        ["Nội dung", "Cách tính", "Thành tiền"],
        ["Tiền phòng", "Theo giá phòng", tien(data["rent_price"])],
        [
            "Tiền điện",
            f"{data['electric_old']} → {data['electric_new']} "
            f"({so_dien} kWh × {tien(gia_dien_pdf)}/kWh)",
            tien(tien_dien),
        ],
        [
            "Tiền nước",
            f"{data['water_old']} → {data['water_new']} "
            f"({so_nuoc} m³ × {tien(gia_nuoc_pdf)}/m³)",
            tien(tien_nuoc),
        ],
        ["Phí khác", "Wifi, vệ sinh...", tien(phi_khac_pdf)],
        ["TỔNG CỘNG", "", tien(tong_tien)],
    ]

    table = Table(
        rows,
        colWidths=[35 * mm, 78 * mm, 55 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_regular),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, -1), (-1, -1), font_bold),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#314E3B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8EFE8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C8D2C8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))

    story.append(table)
    story.append(Spacer(1, 10 * mm))

    story.append(Paragraph(
        f"<b>TỔNG TIỀN CẦN THANH TOÁN: {tien(tong_tien)}</b>",
        styles["TongTienTro"],
    ))

    story.append(Spacer(1, 16 * mm))

    story.append(Paragraph(
        "Người thuê phòng ký xác nhận: ____________________",
        styles["NoiDungTro"],
    ))

    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(
        "Người thu tiền: ____________________",
        styles["NoiDungTro"],
    ))

    story.append(Spacer(1, 12 * mm))

    story.append(Paragraph(
        f"Ngày lập phiếu: {datetime.now().strftime('%d/%m/%Y')}",
        styles["NoiDungTro"],
    ))

    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()


st.divider()
st.header("🧾 Xuất phiếu tiền trọ PDF theo từng phòng")

st.write(
    "Chọn phòng để tạo phiếu tiền trọ riêng, bao gồm thông tin người ở, "
    "chỉ số điện nước, chi tiết chi phí và trạng thái thanh toán."
)

phong_pdf = st.selectbox(
    "Chọn phòng cần xuất PDF:",
    range(1, so_phong + 1),
    format_func=lambda x: f"Phòng {x}",
    key=f"phong_pdf_{nam_chon}_{thang_chon_so}",
)

if st.button("📄 Tạo phiếu tiền trọ PDF", type="primary"):
    data_pdf = doc_phong(nam_chon, thang_chon_so, phong_pdf)

    if data_pdf is None:
        st.error("Không tìm thấy dữ liệu của phòng này.")
    else:
        pdf_bytes = tao_pdf_phieu_tien_tro(
            nam=nam_chon,
            thang=thang_chon_so,
            phong=phong_pdf,
            data=data_pdf,
            gia_dien_pdf=gia_dien,
            gia_nuoc_pdf=gia_nuoc,
            phi_khac_pdf=phi_khac,
        )

        st.download_button(
            label=f"⬇️ Tải phiếu PDF phòng {phong_pdf}",
            data=pdf_bytes,
            file_name=(
                f"Phieu_Tien_Tro_Phong_{phong_pdf}_"
                f"Thang_{thang_chon_so}_{nam_chon}.pdf"
            ),
            mime="application/pdf",
            key=f"download_pdf_{nam_chon}_{thang_chon_so}_{phong_pdf}",
        )

st.caption(
    "Lưu ý: Hãy sao lưu file quan_ly_tien_tro.db định kỳ để tránh mất dữ liệu."
)
