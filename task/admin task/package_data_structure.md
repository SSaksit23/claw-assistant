# Tour Package Data Structure Analysis

## Package List Page: /travelpackage

The tour package list page displays packages in a table format with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| # | Package ID | 14973 |
| รหัส (Code) | Internal ID | 14973 |
| ชื่อโปรแกรมทัวร์ (Program Name) | Full tour name with airline | บินตรงเจิ้งโจว ซีอาน ลั่วหยาง... |
| รูปแบบโปรแกรมทัวร์ (Format) | Tour type | - |
| ประเภทโปรแกรมทัวร์ (Category) | Tour category | จอยทัวร์ |
| โปรแกรมหมดอายุ (Expiry) | Expiration date | 24/06/2026 |
| Created | Creation date | 2026-01-16 17:03:51 |
| Edited | Last edit date | 2026-01-16 17:29:09 |
| Action | Edit/Copy buttons | Edit, Copy |

## Package Detail Page: /travelpackage/manage/{id}

The detail page contains comprehensive package information:

### Basic Information
- **ประเทศ (Country)**: e.g., China
- **จังหวัด (Province)**: e.g., Luoyang, Xian, Zhengzhou
- **พื้นที่/เขต (Area)**: Optional
- **เลือกเมืองหลัก (Main City)**: e.g., ซีอาน
- **โค้ดโปรแกรมทัวร์ (Program Code)**: e.g., 2UCGO-SL001
- **ชื่อโปรแกรมทัวร์ (Program Name)**: Full tour name
- **รายละเอียดสั้นๆ (Short Description)**: Brief description

### Tour Type Configuration
- **ชื่อประเภทโปรแกรมทัวร์ (Tour Type)**: Options include:
  - จอยทัวร์ (Join Tour)
  - กรุ๊ปเหมา (Private Group)
  - แพ็คเกจ (Package)
  - famtrip

### Display Settings
- **จำนวนกำหนดการ (Number of Schedules)**: e.g., 16
- **การแสดงหน้าเว็บ (Web Display)**: On/Off
- **เจ้าของโปรแกรม (Program Owner)**: e.g., QeBooking.com by 2uCenter
- **พนักงานรับผิดชอบ (Responsible Staff)**: e.g., ศักดิ์สิทธิ์ (น่อย)
- **Product By**: e.g., Qebooking-2U

### Pricing Configuration (ประเภทของราคา)
Multiple price types can be defined:
1. ผู้ใหญ่ 2 ท่านพัก 1 ห้อง (2 adults per room)
2. ผู้ใหญ่ 3 ท่านพัก 1 ห้อง (3 adults per room)
3. ผู้ใหญ่ 1 ท่าน พักเดี่ยว (Single room)

### Images
- **ภาพแบนเนอร์หลัก (Main Banner)**: Tour banner image
- **ภาพโฆษณา (Advertisement Image)**: For promoted tours

## API/Data Access Points

Based on the URL structure, the following endpoints are available:

| Endpoint | Purpose |
|----------|---------|
| /travelpackage | List all packages |
| /travelpackage/manage/{id} | View/Edit package details |
| /charges_group/create | Create expense record |
| /booking | Booking management |

## Key Observations for Scraping

1. The website uses Bootstrap selectpicker for dropdowns
2. jQuery is available on the page
3. Package data can be extracted from the table on /travelpackage
4. Detailed package info requires visiting individual package pages
5. The program code format varies (e.g., 2UCGO-SL001, 2UKMG-MU002, CIG-CVZTFU9)
