# Form Structure Analysis - qualityb2bpackage.com/charges_group/create

## Form Elements Identified

### Main Form Fields
1. **Date Range Filter** (โปรแกรมช่วงวันที่)
   - Start Date: `input[name="start"]` - Default: 09/01/2026
   - End Date: `input[name="end"]` - Default: 16/01/2026

2. **Tour Program Dropdown** (โปรแกรมทัวร์)
   - Type: Bootstrap selectpicker
   - Name: `select[name="package"]`
   - Default: "ทั้งหมด" (All)

3. **Tour Code Dropdown** (รหัสทัวร์)
   - Type: Bootstrap selectpicker
   - Name: `select[name="period"]`
   - Default: "ทั้งหมด" (All)
   - Dependent on Tour Program selection

4. **Payment Date** (วันที่จ่าย)
   - Name: `input[name="payment_date"]`

5. **Time Fields** (เวลา)
   - Two text inputs for hour and minute

6. **Receipt Date** (วันที่ในใบเสร็จ)
   - Date picker input

7. **Receipt Number** (เลขที่ใบเสร็จ/ใบกำกับภาษี)
   - Text input

8. **Description** (คำอธิบาย)
   - Name: `input[name="description[]"]`
   - Can add multiple rows with "เพิ่มแถว+" button

9. **Type Dropdown** (ประเภท)
   - ID: `rate_type`
   - Name: `select[name="rate_type[]"]`
   - Options:
     - เลือกประเภทราคา (Select price type)
     - ค่าตั๋วเครื่องบิน (Flight ticket)
     - ค่าวีซ่า (Visa fee)
     - เบี้ยเลี้ยง (ค่าจ้างมัคคุเทศก์และหัวหน้าทัวร์) (Allowance)
     - ค่าแท็กซี่หัวหน้าทัวร์ (Taxi fee)

10. **Amount** (จำนวนเงิน)
    - Name: `input[name="price[]"]`

11. **Currency**
    - ID: `currency`
    - Options: EUR, CNY, IQD, AFN, DZD, THB, etc.

12. **Exchange Rate** (เรท)
    - Default: 1

13. **Payment Evidence** (หลักฐานการจ่าย)
    - File upload input

14. **Remark** (หมายเหตุ)
    - ID: `remark`
    - Name: `textarea[name="remark"]`

15. **Expense Number** (เลขที่ค่าใช้จ่าย)
    - ID: `charges_no`
    - Placeholder: C2021XX-XXXX
    - Auto-generated after save

### Company Expense Section (เพิ่มในค่าใช้จ่ายบริษัท)
- Toggle link to expand company expense section
- Fields when expanded:
  - Company: `select[name="charges[id_company_charges_agent]"]`
  - Payment Method: `select[name="charges[payment_type]"]`
  - Amount: `input[name="charges[amount]"]`
  - Payment Type: `select[name="charges[id_company_charges_type]"]`
  - Payment Date: `input[name="charges[payment_date]"]`
  - Period: `input[name="charges[period]"]`
  - Remark: `textarea[name="charges[remark]"]`

### Submit Buttons
- **Save**: `input[type="submit"]` with value "Save" (index 38)
- **Reset**: `input[type="reset"]` with value "Reset" (index 39)

## Key Observations
1. The Save button is `input[type="submit"]` not a `button` element
2. Form uses Bootstrap selectpicker for dropdowns (requires jQuery)
3. The expense number (charges_no) is auto-generated after successful submission
4. Company expense section is hidden by default, toggled by clicking "เพิ่มในค่าใช้จ่ายบริษัท"

## Potential Issues with Current Code
1. The code tries to find `button[type="submit"]` but the actual element is `input[type="submit"]`
2. May need to wait for form validation before submission
3. Need to verify if the form requires specific fields to be filled before submission
