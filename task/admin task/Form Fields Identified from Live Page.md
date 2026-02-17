# Form Fields Identified from Live Page

## Page Information
- **URL**: https://www.qualityb2bpackage.com/charges_group/create
- **Title**: เพิ่มค่าใช้จ่ายกรุ๊ปทัวร์!!

## Form Fields Visible

### 1. Date Range Filter (โปรแกรมช่วงวันที่)
- **Start Date**: Text input, default value: "07/01/2026"
- **End Date**: Text input, default value: "14/01/2026"

### 2. Tour Program Dropdown (โปรแกรมทัวร์)
- **Current Display**: "ทั้งหมด" (All)
- **Type**: Dropdown with button interface
- **Note**: This is a searchable dropdown

### 3. Tour Code Dropdown (รหัสทัวร์)
- **Current Display**: "ทั้งหมด" (All)
- **Type**: Dropdown with button interface
- **Note**: Dependent on Tour Program selection

### 4. Payment Date (วันที่จ่าย)
- **Type**: Date picker with calendar icon
- **Field**: Text input

### 5. Time Fields (เวลา)
- **Type**: Two text inputs for time
- **Format**: Hour : Minute

### 6. Receipt Date (วันที่ในใบเสร็จ)
- **Type**: Date picker with calendar icon
- **Field**: Text input

### 7. Receipt Number (เลขที่ใบเสร็จ/ใบกำกับภาษี)
- **Type**: Text input

### 8. Add Row Button (เพิ่มแถว+คำอธิบาย)
- **Type**: Button labeled "เพิ่มแถว+"
- **Purpose**: Add new description row

### 9. Description Field (คำอธิบาย)
- **Type**: Text input
- **Purpose**: Enter charge description

### 10. Type Dropdown (ประเภท)
- **ID**: rate_type
- **Type**: Select dropdown
- **Options**:
  - เลือกประเภทราคา (Select price type)
  - ค่าตั๋วเครื่องบิน (Flight ticket)
  - ค่าวีซ่า (Visa fee)
  - เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์) (Allowance)
  - ค่าแท็กซี่หัวหน้าทัวร์ (Taxi fee for tour leader)

### 11. Amount Field (จำนวนเงิน)
- **Type**: Text input (number)

### 12. Currency Dropdown
- **ID**: currency
- **Type**: Select dropdown
- **Options**: EUR, CNY, IQD, AFN, DZD, etc.

### 13. Exchange Rate (เรท)
- **Type**: Text input
- **Default Value**: 1

## Additional Notes
- The page has more content below (471 pixels below viewport)
- Need to scroll down to see submit button and other fields


## Tour Program Dropdown Details

The Tour Program dropdown is a searchable dropdown (Bootstrap Selectpicker) that shows:
- "ทั้งหมด" (All) as the first option
- List of tour programs with full descriptions including:
  - Tour name
  - Duration
  - Airline information
  - Program code (at the end)

Examples visible:
- ฮ่องกง พระใหญ่นองปิง 3 วัน 2 คืน โดยสายการบิน Emirates Airline (EK) MC-MYSP1-EK
- มหัศจรรย์...เวียดนามกลาง ดานัง ฮอยอัน ชมโชว์สุดอลังการ Hoi an Impression 4 วัน 3 คืน โดยสายการบิน Thai Vietjet Air (VZ) BT-DAD51_VZ
- SINGAPORE SAVER สิงคโปร์ วัดพระเขี้ยวแก้ว คลากคีย์ 3 วัน 2 คืน โดยสายการบิน THAI LION AIR (SL) SPHZ-32

The program code appears at the end of each option (e.g., MC-MYSP1-EK, BT-DAD51_VZ, SPHZ-32)
