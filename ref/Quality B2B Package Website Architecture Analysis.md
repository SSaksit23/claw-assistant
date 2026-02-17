# Quality B2B Package Website Architecture Analysis

## Website Overview
**URL**: https://www.qualityb2bpackage.com/
**Domain**: Goholidaytour.com (Quality B2B Package)
**Purpose**: B2B travel package management and booking system

## Main Navigation Structure

### Left Sidebar Menu
1. **Dashboard** - Main dashboard view
2. **จัดการคำสั่งจอง** (Manage Bookings) - Booking management
3. **คำสั่งจองทั้งหมด** (All Bookings) - View all bookings
4. **รายงานการแจ้งหนี้** (Invoice Reports) - Invoice reporting
5. **รายงานแจ้งจ่ายเงิน** (Payment Reports) - Payment reporting
6. **คำขอยกเลิกคำสั่งจอง** (Cancellation Requests) - Booking cancellations
7. **คำสั่งจองยกเลิกที่ไม่ได้อนุมัติเงิน** (Unapproved Cancellations)
8. **Report(รายงาน)** - Reports section
9. **สมาชิก/เอเจ้นท์** (Members/Agents) - User management
10. **โปรแกรมทัวร์** (Travel Programs) - Travel package management
11. **ข้อมูลบัตร/สถานที่ท่องเที่ยว** (Card/Destination Info)
12. **JR Pass** - Japan Rail Pass management
13. **Cruises(เรือ)** (Cruises) - Cruise management
14. **Group(ข้อมูลคณะทัวร์)** (Group Info) - Group tour information

## Key Modules and URLs

### 1. Charges/Expenses Management
**URL**: `https://www.qualityb2bpackage.com/charges_group`

**Features**:
- List of group tour expenses
- Search functionality
- Add new expense button
- Table columns:
  - โปรแกรมทัวร์ (Travel Program)
  - ทีดีเทียม (Team/Group ID)
  - ประเทศ (Country)
  - สำนักงาน (Office)
  - วันที่จ่าย (Payment Date)
  - จำนวนเงิน (Amount)
  - หลัก (Main)
  - ฉบับ (Version)
  - เพิ่มเติมข้อมูล (Additional Info)
  - Created
  - Edited
  - Action

**Create Expense URL**: `https://www.qualityb2bpackage.com/charges_group/create`

**Create Form Fields**:
- โปรแกรมช่วงวันที่ (Program Date Range) - Date picker
- โปรแกรมทัวร์ (Travel Program) - Dropdown
- รหัสทัวร์ (Tour Code) - Dropdown
- วันที่จ่าย (Payment Date) - Date picker
- เวลา (Time) - Time input
- วันที่ในใบเสร็จ (Receipt Date) - Date picker
- เลขที่ใบเสร็จ/ใบกำกับภาษี (Receipt/Invoice Number) - Text input
- Dynamic rows for expenses:
  - คำอธิบาย (Description) - Text
  - ประเภท (Type) - Dropdown (Flight, Visa, Meal, Taxi, etc.)
  - จำนวนเงิน (Amount) - Numeric
  - Currency - Dropdown (EUR, CNY, IQD, AFN, DZD, etc.)
  - เรท (Exchange Rate) - Numeric (default: 1)

### 2. Booking Management
**URL**: `https://www.qualityb2bpackage.com/booking`

**Features**:
- Manage and view all bookings
- Booking status tracking
- Booking details

### 3. Reports Section
**URL**: `https://www.qualityb2bpackage.com/report/report_seller`

**Report Features**:
- Report type selection:
  - Tour (ทัวร์)
  - Group Tour (กรุ๊ปเหมา)
  - Package (แพ็คเกจ)
  - Famtrip (เว็บไซต์เจ้าของ)
- Website selection dropdown
- Summary vs. Detailed report options
- Report grouping options:
  - By country (ประเทศ)
  - By province (จังหวัด)
  - By continent (ทวีป)
- Data aggregation options
- Filters:
  - Country selection
  - Province selection
  - Continent selection

### 4. Travel Package Management
**URL**: `https://www.qualityb2bpackage.com/travelpackage`

**Features**:
- List of travel packages
- Add new package button
- Filter options:
  - Website selection
  - Country selection
  - City selection
  - Show/Display options
  - Product type (B2B products)
  - Product category
- Search functionality (by program name or tour code)
- Package table columns:
  - # (ID)
  - รหัส (Code)
  - ชื่อโปรแกรมทัวร์ (Program Name)
  - ประเทศ (Country)
  - ประเภทโปรแกรม (Program Type)
  - โปรแกรมทัวร์อื่น (Other Programs)
  - Created
  - Edited
  - Action (Edit, Copy)

**Sample Packages**:
- TAIWAN 2U - Taiwan charter flight package
- VIETNAM - Vietnam central region package
- Shanghai tour package

## Authentication & User Management
- User login system (currently logged in as: ศักดิ์สิทธิ์ (น่อย))
- Logout functionality
- User-specific dashboard

## Technical Architecture Notes
- Left sidebar navigation with expandable menus
- Main content area with data tables
- Date pickers and dropdown selectors
- Search and filter functionality
- CRUD operations (Create, Read, Update, Delete)
- Multi-language support (Thai interface)
- Currency and exchange rate handling
- Dynamic form rows for multiple expense entries

## Data Flow Patterns
1. **Expense Recording**: User inputs expense data → System stores in charges_group
2. **Reporting**: System aggregates data from bookings and charges → Generates reports
3. **Package Management**: Create/Edit travel packages → Display in listings
4. **Booking Management**: Users create bookings → Track status → Generate invoices

## Integration Points
- Dashboard overview
- Real-time data updates
- Report generation
- Multi-currency support
- Date and time handling
- File upload capabilities (implied from form structure)
