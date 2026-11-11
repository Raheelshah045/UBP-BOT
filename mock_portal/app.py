"""Mock OTC Banking Portal for local development and testing.

Simulates authentic portal behavior: login with CAPTCHA and OTP,
session tracking, BPS -> Check Bill Status navigation, multi-bank search,
pagination, and comprehensive transaction status scenarios.
"""

from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.secret_key = "dummy-otc-portal-secret-key-for-local-testing"

# Synthetic database of transactions for realistic mock responses
SAMPLE_DATA: List[Dict[str, Any]] = [
    # Consumer 10012345678901 on 2026-11-10 (HBL) - Multiple records (Approved + Rejected qualifying)
    {
        "consumer_number": "10012345678901",
        "bank_service": "HBL",
        "date": "2026-11-10",
        "time": "09:15:22",
        "rrn": "RRN100101",
        "auth_id": "AUTH991",
        "amount": "12,500.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved or completed successfully",
    },
    {
        "consumer_number": "10012345678901",
        "bank_service": "HBL",
        "date": "2026-11-10",
        "time": "14:22:10",
        "rrn": "RRN100102",
        "auth_id": "AUTH992",
        "amount": "12,500.00",
        "status": "Rejected",
        "response_code": "51",
        "response_desc": "Insufficient funds",
    },
    # Consumer 10012345678901 on 2026-10-10 - Rejected with Code 95 (Excluded)
    {
        "consumer_number": "10012345678901",
        "bank_service": "HBL",
        "date": "2026-10-10",
        "time": "11:05:40",
        "rrn": "RRN100103",
        "auth_id": "AUTH993",
        "amount": "5,000.00",
        "status": "Rejected",
        "response_code": "95",
        "response_desc": "Customer cancellation / Timeout",
    },
    # Consumer 10012345678901 on 2026-09-12 - Rejected with Code 98 (Excluded)
    {
        "consumer_number": "10012345678901",
        "bank_service": "HBL",
        "date": "2026-09-12",
        "time": "16:45:11",
        "rrn": "RRN100104",
        "auth_id": "AUTH994",
        "amount": "8,200.00",
        "status": "Rejected",
        "response_code": "98",
        "response_desc": "System cutoff or duplicate reversal",
    },
    # Consumer 10012345678901 on 2026-11-08 - Rejected with Code 05 (Qualifying Rejection)
    {
        "consumer_number": "10012345678901",
        "bank_service": "HBL",
        "date": "2026-11-08",
        "time": "10:11:00",
        "rrn": "RRN100105",
        "auth_id": "AUTH995",
        "amount": "3,400.00",
        "status": "Rejected",
        "response_code": "05",
        "response_desc": "Do not honor",
    },
    # Consumer 10012345678901 on 2026-11-11 - Pending transaction
    {
        "consumer_number": "10012345678901",
        "bank_service": "HBL",
        "date": "2026-11-11",
        "time": "18:00:00",
        "rrn": "RRN100106",
        "auth_id": "AUTH996",
        "amount": "2,000.00",
        "status": "Pending",
        "response_code": "01",
        "response_desc": "Refer to card issuer",
    },
    # Consumer 20098765432109 on 2026-11-05 (MEEZAN) - Rejected qualifying (code 14)
    {
        "consumer_number": "20098765432109",
        "bank_service": "MEEZAN",
        "date": "2026-11-05",
        "time": "12:30:15",
        "rrn": "RRN200201",
        "auth_id": "AUTH881",
        "amount": "45,000.00",
        "status": "Rejected",
        "response_code": "14",
        "response_desc": "Invalid card or account number",
    },
    # Consumer 20098765432109 on 2026-10-05 (MEEZAN) - Unknown status / Manual review
    {
        "consumer_number": "20098765432109",
        "bank_service": "MEEZAN",
        "date": "2026-10-05",
        "time": "15:20:00",
        "rrn": "RRN200202",
        "auth_id": "AUTH882",
        "amount": "14,000.00",
        "status": "InReview",
        "response_code": "99",
        "response_desc": "Undefined core response",
    },
    # Consumer 20098765432109 on 2026-09-06 (MEEZAN) - Pagination demo: 4 records (page size 2)
    {
        "consumer_number": "20098765432109",
        "bank_service": "MEEZAN",
        "date": "2026-09-06",
        "time": "08:10:00",
        "rrn": "RRN200203",
        "auth_id": "AUTH883",
        "amount": "1,000.00",
        "status": "Rejected",
        "response_code": "54",
        "response_desc": "Expired card",
    },
    {
        "consumer_number": "20098765432109",
        "bank_service": "MEEZAN",
        "date": "2026-09-06",
        "time": "09:20:00",
        "rrn": "RRN200204",
        "auth_id": "AUTH884",
        "amount": "1,500.00",
        "status": "Successful",
        "response_code": "00",
        "response_desc": "Approved",
    },
    {
        "consumer_number": "20098765432109",
        "bank_service": "MEEZAN",
        "date": "2026-09-06",
        "time": "11:30:00",
        "rrn": "RRN200205",
        "auth_id": "AUTH885",
        "amount": "2,000.00",
        "status": "Rejected",
        "response_code": "61",
        "response_desc": "Exceeds withdrawal amount limit",
    },
    # Consumer 30011223344556 on 2026-11-02 (MCB) - Approved
    {
        "consumer_number": "30011223344556",
        "bank_service": "MCB",
        "date": "2026-11-02",
        "time": "13:00:00",
        "rrn": "RRN300301",
        "auth_id": "AUTH771",
        "amount": "9,800.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved",
    },
    # Consumer 40055667788990 on 2026-11-11 (ALFALAH) - Rejected qualifying (code 57)
    {
        "consumer_number": "40055667788990",
        "bank_service": "ALFALAH",
        "date": "2026-11-11",
        "time": "17:40:00",
        "rrn": "RRN400401",
        "auth_id": "AUTH661",
        "amount": "31,000.00",
        "status": "Rejected",
        "response_code": "57",
        "response_desc": "Transaction not permitted to issuer",
    },
    # Consumer 50099887766554 on 2026-11-07 (NBP) - Rejected code 95 (Excluded)
    {
        "consumer_number": "50099887766554",
        "bank_service": "NBP",
        "date": "2026-11-07",
        "time": "14:15:00",
        "rrn": "RRN500501",
        "auth_id": "AUTH551",
        "amount": "6,500.00",
        "status": "Rejected",
        "response_code": "95",
        "response_desc": "Timeout",
    },
    # Consumer 60012398745612 on 2026-11-11 (ABL) - Rejected code 98 (Excluded)
    {
        "consumer_number": "60012398745612",
        "bank_service": "ABL",
        "date": "2026-11-11",
        "time": "19:25:00",
        "rrn": "RRN600601",
        "auth_id": "AUTH441",
        "amount": "18,900.00",
        "status": "Rejected",
        "response_code": "98",
        "response_desc": "Reversal",
    },
    # 20 UBL Datasets (with both Approved and Rejected transactions)
    {
        "consumer_number": "70085296314001",
        "bank_service": "UBL",
        "date": "2026-11-10",
        "time": "09:14:22",
        "rrn": "RRN701001",
        "auth_id": "AUTH701",
        "amount": "15,400.00",
        "status": "Rejected",
        "response_code": "51",
        "response_desc": "Insufficient funds",
    },
    {
        "consumer_number": "70085296314002",
        "bank_service": "UBL",
        "date": "2026-11-10",
        "time": "10:22:15",
        "rrn": "RRN701002",
        "auth_id": "AUTH702",
        "amount": "8,200.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved or completed successfully",
    },
    {
        "consumer_number": "70085296314003",
        "bank_service": "UBL",
        "date": "2026-11-09",
        "time": "11:05:40",
        "rrn": "RRN701003",
        "auth_id": "AUTH703",
        "amount": "23,100.00",
        "status": "Rejected",
        "response_code": "05",
        "response_desc": "Do not honor",
    },
    {
        "consumer_number": "70085296314004",
        "bank_service": "UBL",
        "date": "2026-11-09",
        "time": "12:15:30",
        "rrn": "RRN701004",
        "auth_id": "AUTH704",
        "amount": "5,600.00",
        "status": "Rejected",
        "response_code": "54",
        "response_desc": "Expired card",
    },
    {
        "consumer_number": "70085296314005",
        "bank_service": "UBL",
        "date": "2026-11-08",
        "time": "14:30:10",
        "rrn": "RRN701005",
        "auth_id": "AUTH705",
        "amount": "12,000.00",
        "status": "Rejected",
        "response_code": "61",
        "response_desc": "Exceeds withdrawal limit",
    },
    {
        "consumer_number": "70085296314006",
        "bank_service": "UBL",
        "date": "2026-11-08",
        "time": "15:45:00",
        "rrn": "RRN701006",
        "auth_id": "AUTH706",
        "amount": "3,400.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved",
    },
    {
        "consumer_number": "70085296314007",
        "bank_service": "UBL",
        "date": "2026-11-07",
        "time": "09:30:00",
        "rrn": "RRN701007",
        "auth_id": "AUTH707",
        "amount": "45,000.00",
        "status": "Rejected",
        "response_code": "14",
        "response_desc": "Invalid card or account number",
    },
    {
        "consumer_number": "70085296314008",
        "bank_service": "UBL",
        "date": "2026-11-07",
        "time": "10:45:15",
        "rrn": "RRN701008",
        "auth_id": "AUTH708",
        "amount": "7,800.00",
        "status": "Rejected",
        "response_code": "57",
        "response_desc": "Transaction not permitted to issuer",
    },
    {
        "consumer_number": "70085296314009",
        "bank_service": "UBL",
        "date": "2026-11-06",
        "time": "13:20:00",
        "rrn": "RRN701009",
        "auth_id": "AUTH709",
        "amount": "9,900.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved",
    },
    {
        "consumer_number": "70085296314010",
        "bank_service": "UBL",
        "date": "2026-11-06",
        "time": "16:10:40",
        "rrn": "RRN701010",
        "auth_id": "AUTH710",
        "amount": "18,500.00",
        "status": "Rejected",
        "response_code": "51",
        "response_desc": "Insufficient funds",
    },
    {
        "consumer_number": "70085296314011",
        "bank_service": "UBL",
        "date": "2026-11-05",
        "time": "11:22:00",
        "rrn": "RRN701011",
        "auth_id": "AUTH711",
        "amount": "31,000.00",
        "status": "Rejected",
        "response_code": "05",
        "response_desc": "Do not honor",
    },
    {
        "consumer_number": "70085296314012",
        "bank_service": "UBL",
        "date": "2026-11-05",
        "time": "14:15:30",
        "rrn": "RRN701012",
        "auth_id": "AUTH712",
        "amount": "4,200.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved",
    },
    {
        "consumer_number": "70085296314013",
        "bank_service": "UBL",
        "date": "2026-11-04",
        "time": "10:05:00",
        "rrn": "RRN701013",
        "auth_id": "AUTH713",
        "amount": "2,700.00",
        "status": "Rejected",
        "response_code": "54",
        "response_desc": "Expired card",
    },
    {
        "consumer_number": "70085296314014",
        "bank_service": "UBL",
        "date": "2026-11-04",
        "time": "12:50:20",
        "rrn": "RRN701014",
        "auth_id": "AUTH714",
        "amount": "16,000.00",
        "status": "Rejected",
        "response_code": "61",
        "response_desc": "Exceeds withdrawal limit",
    },
    {
        "consumer_number": "70085296314015",
        "bank_service": "UBL",
        "date": "2026-11-03",
        "time": "09:40:10",
        "rrn": "RRN701015",
        "auth_id": "AUTH715",
        "amount": "11,800.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved",
    },
    {
        "consumer_number": "70085296314016",
        "bank_service": "UBL",
        "date": "2026-11-03",
        "time": "15:35:45",
        "rrn": "RRN701016",
        "auth_id": "AUTH716",
        "amount": "22,000.00",
        "status": "Rejected",
        "response_code": "51",
        "response_desc": "Insufficient funds",
    },
    {
        "consumer_number": "70085296314017",
        "bank_service": "UBL",
        "date": "2026-11-02",
        "time": "11:15:00",
        "rrn": "RRN701017",
        "auth_id": "AUTH717",
        "amount": "6,300.00",
        "status": "Rejected",
        "response_code": "14",
        "response_desc": "Invalid card or account number",
    },
    {
        "consumer_number": "70085296314018",
        "bank_service": "UBL",
        "date": "2026-11-02",
        "time": "13:40:00",
        "rrn": "RRN701018",
        "auth_id": "AUTH718",
        "amount": "19,400.00",
        "status": "Rejected",
        "response_code": "57",
        "response_desc": "Transaction not permitted",
    },
    {
        "consumer_number": "70085296314019",
        "bank_service": "UBL",
        "date": "2026-11-01",
        "time": "08:55:10",
        "rrn": "RRN701019",
        "auth_id": "AUTH719",
        "amount": "14,000.00",
        "status": "Approved",
        "response_code": "00",
        "response_desc": "Approved",
    },
    {
        "consumer_number": "70085296314020",
        "bank_service": "UBL",
        "date": "2026-11-01",
        "time": "17:20:00",
        "rrn": "RRN701020",
        "auth_id": "AUTH720",
        "amount": "27,500.00",
        "status": "Rejected",
        "response_code": "51",
        "response_desc": "Insufficient funds",
    },
    # Consumer 70085296314725 has no records (returns No Records Found)
]

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>OTC Banking Portal - Secure Login</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f0f4f8; margin: 0; padding: 40px; display: flex; justify-content: center; }
    .card { background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.1); width: 420px; border-top: 5px solid #1B365D; }
    h2 { color: #1B365D; margin-top: 0; }
    .form-group { margin-bottom: 16px; }
    label { display: block; font-weight: 600; margin-bottom: 6px; font-size: 13px; color: #333; }
    input { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
    .captcha-box { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
    .captcha-badge { background: #2A4D69; color: #fff; font-weight: bold; letter-spacing: 4px; padding: 8px 16px; border-radius: 4px; user-select: none; }
    button { width: 100%; background: #1B365D; color: #fff; border: none; padding: 12px; font-size: 15px; font-weight: bold; border-radius: 4px; cursor: pointer; }
    button:hover { background: #132742; }
    .note { font-size: 12px; color: #666; margin-top: 16px; line-height: 1.4; background: #e8f0fe; padding: 10px; border-radius: 4px; }
    .error { color: #d32f2f; font-size: 13px; margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="card" id="loginContainer">
    <h2>OTC Portal Login</h2>
    {% if error %}
      <div class="error" id="loginError">{{ error }}</div>
    {% endif %}
    <form method="POST" action="/login">
      <div class="form-group">
        <label for="username">Username</label>
        <input type="text" id="username" name="username" value="bank_operator" required />
      </div>
      <div class="form-group">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" value="Password@123" required />
      </div>
      <div class="form-group">
        <label>Security CAPTCHA</label>
        <div class="captcha-box">
          <div class="captcha-badge" id="captchaDisplay">7X9K2</div>
          <input type="text" id="captcha" name="captcha" placeholder="Enter CAPTCHA" value="7X9K2" required />
        </div>
      </div>
      <div class="form-group">
        <label for="otp">One-Time Password (OTP)</label>
        <input type="text" id="otp" name="otp" placeholder="Enter 6-digit OTP" value="123456" required />
      </div>
      <button type="submit" id="btnLogin">Log In to OTC Portal</button>
    </form>
    <div class="note">
      <strong>Human-in-the-Loop Simulation:</strong><br>
      Pre-filled with valid test credentials. Click <em>Log In</em> to authenticate your browser session.
    </div>
  </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>OTC Portal - Dashboard</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #f8fafc; }
    .header { background: #1B365D; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
    .brand { font-size: 20px; font-weight: bold; }
    .user-info { display: flex; align-items: center; gap: 12px; }
    .nav { background: #2A4D69; padding: 10px 24px; display: flex; gap: 20px; }
    .nav a { color: white; text-decoration: none; font-weight: 500; font-size: 14px; padding: 6px 12px; border-radius: 4px; }
    .nav a:hover, .nav a.active { background: #4B86B4; }
    .content { padding: 40px; }
    .card { background: white; padding: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
    .btn-action { display: inline-block; background: #1B365D; color: white; padding: 10px 18px; border-radius: 4px; text-decoration: none; font-weight: 600; margin-top: 15px; }
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">OTC Banking Network Portal</div>
    <div class="user-info" id="userProfile" data-authenticated="true">
      <span class="user-logged-in">Logged in as: <strong>Operator (OP-4491)</strong></span>
      <a href="/logout" style="color: #ffcdd2; text-decoration: none; margin-left: 10px;">Log out</a>
    </div>
  </div>
  <div class="nav">
    <a href="/dashboard">Home</a>
    <a href="/bps/check-bill-status" id="navBps">BPS</a>
    <a href="/bps/check-bill-status" id="navCheckBillStatus">Check Bill Status</a>
    <a href="/reports">Reports</a>
  </div>
  <div class="content">
    <div class="card">
      <h2>Welcome to Bill Payment System (BPS) Gateway</h2>
      <p>Select <strong>Check Bill Status</strong> from the navigation menu to query consumer transactions.</p>
      <a class="btn-action" href="/bps/check-bill-status">Go to Check Bill Status &rarr;</a>
    </div>
  </div>
</body>
</html>
"""

CHECK_BILL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>BPS - Check Bill Status</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; background: #f8fafc; }
    .header { background: #1B365D; color: white; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }
    .brand { font-size: 18px; font-weight: bold; }
    .nav { background: #2A4D69; padding: 8px 24px; display: flex; gap: 16px; }
    .nav a { color: white; text-decoration: none; font-size: 14px; padding: 6px 12px; border-radius: 4px; }
    .nav a.active { background: #4B86B4; }
    .container { padding: 24px 32px; max-width: 1200px; margin: 0 auto; }
    .filter-panel { background: white; padding: 20px; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); margin-bottom: 24px; }
    .filter-grid { display: grid; grid-template-columns: repeat(4, 1fr) auto; gap: 16px; align-items: end; }
    .form-group { display: flex; flex-direction: column; }
    label { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 6px; }
    input, select { padding: 9px 12px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; }
    button.search-btn { background: #1B365D; color: white; border: none; padding: 10px 24px; font-weight: bold; border-radius: 4px; cursor: pointer; }
    button.search-btn:hover { background: #132742; }
    .spinner { display: none; text-align: center; padding: 20px; font-weight: bold; color: #1B365D; }
    .results-card { background: white; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); padding: 20px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
    th { background: #1B365D; color: white; padding: 10px; text-align: left; }
    td { padding: 9px 10px; border-bottom: 1px solid #e2e8f0; }
    tr:hover { background: #f1f5f9; }
    .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
    .status-approved { background: #dcfce7; color: #166534; }
    .status-rejected { background: #fee2e2; color: #991b1b; }
    .status-pending { background: #fef3c7; color: #92400e; }
    .alert-box { padding: 14px; border-radius: 4px; margin-top: 12px; display: none; }
    .alert-empty { background: #fef9c3; color: #854d0e; border: 1px solid #fde047; }
    .pagination { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; }
    .page-btn { padding: 6px 14px; border: 1px solid #cbd5e1; background: white; cursor: pointer; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">OTC Portal - Check Bill Status</div>
    <div id="userProfile" data-authenticated="true">Operator: OP-4491 | <a href="/simulate-expire" style="color: #ffcdd2;">Simulate Session Expiry</a></div>
  </div>
  <div class="nav">
    <a href="/dashboard">Home</a>
    <a href="/bps/check-bill-status" id="navBps" class="active">BPS</a>
    <a href="/bps/check-bill-status" id="navCheckBillStatus" class="active">Check Bill Status</a>
  </div>

  <div class="container">
    <div class="filter-panel">
      <div class="filter-grid">
        <div class="form-group">
          <label for="bankSelect">Bank / Service</label>
          <select id="bankSelect">
            <option value="">-- Select Bank --</option>
            <option value="HBL">Habib Bank Limited (HBL)</option>
            <option value="MEEZAN">Meezan Bank Limited</option>
            <option value="MCB">MCB Bank Limited</option>
            <option value="ALFALAH">Bank Alfalah</option>
            <option value="NBP">National Bank of Pakistan (NBP)</option>
            <option value="ABL">Allied Bank Limited (ABL)</option>
            <option value="UBL">United Bank Limited (UBL)</option>
          </select>
        </div>

        <div class="form-group">
          <label for="consumerNumberInput">Consumer Number</label>
          <input type="text" id="consumerNumberInput" placeholder="Enter Consumer #" />
        </div>

        <div class="form-group">
          <label for="fromDateInput">From Date</label>
          <input type="date" id="fromDateInput" />
        </div>

        <div class="form-group">
          <label for="toDateInput">To Date</label>
          <input type="date" id="toDateInput" />
        </div>

        <div>
          <button type="button" id="btnSearch" class="search-btn" onclick="executeSearch(1)">Search</button>
        </div>
      </div>
    </div>

    <div id="loadingSpinner" class="spinner">Searching OTC Gateway records, please wait...</div>
    <div id="noRecordsAlert" class="alert-box alert-empty">No transaction records found matching the given criteria.</div>

    <div id="resultsContainer" class="results-card" style="display: none;">
      <table id="transactionsTable">
        <thead>
          <tr>
            <th>Consumer Number</th>
            <th>Bank / Service</th>
            <th>Transaction Date</th>
            <th>Time</th>
            <th>RRN</th>
            <th>Auth ID</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Response Code</th>
            <th>Response Description</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>

      <div class="pagination">
        <button id="btnPrevPage" class="page-btn" onclick="changePage(-1)">Previous</button>
        <span id="pageInfo">Page 1 of 1</span>
        <button id="btnNextPage" class="page-btn" onclick="changePage(1)">Next</button>
      </div>
    </div>
  </div>

  <script>
    let currentPage = 1;
    let totalPages = 1;

    document.getElementById('consumerNumberInput').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        executeSearch(1);
      }
    });

    async function executeSearch(page) {
      const bank = document.getElementById('bankSelect').value;
      const consumer = document.getElementById('consumerNumberInput').value.trim();
      const fromDate = document.getElementById('fromDateInput').value;
      const toDate = document.getElementById('toDateInput').value;

      document.getElementById('loadingSpinner').style.display = 'block';
      document.getElementById('noRecordsAlert').style.display = 'none';
      document.getElementById('resultsContainer').style.display = 'none';

      try {
        const resp = await fetch(`/api/search?bank=${encodeURIComponent(bank)}&consumer=${encodeURIComponent(consumer)}&from=${encodeURIComponent(fromDate)}&to=${encodeURIComponent(toDate)}&page=${page}`);
        if (resp.status === 401) {
          window.location.href = '/login?expired=1';
          return;
        }
        const data = await resp.json();
        document.getElementById('loadingSpinner').style.display = 'none';

        if (!data.records || data.records.length === 0) {
          document.getElementById('noRecordsAlert').style.display = 'block';
          return;
        }

        currentPage = data.page;
        totalPages = data.total_pages;
        document.getElementById('pageInfo').innerText = `Page ${data.page} of ${data.total_pages}`;
        document.getElementById('btnPrevPage').disabled = (currentPage <= 1);
        document.getElementById('btnNextPage').disabled = (currentPage >= totalPages);

        const tbody = document.getElementById('tableBody');
        tbody.innerHTML = '';
        data.records.forEach(row => {
          const tr = document.createElement('tr');
          const statusClass = row.status.toLowerCase().includes('approved') || row.status.toLowerCase().includes('successful')
            ? 'status-approved' : (row.status.toLowerCase().includes('pending') ? 'status-pending' : 'status-rejected');
          tr.innerHTML = `
            <td>${row.consumer_number}</td>
            <td>${row.bank_service}</td>
            <td>${row.date}</td>
            <td>${row.time}</td>
            <td>${row.rrn}</td>
            <td>${row.auth_id}</td>
            <td>${row.amount}</td>
            <td><span class="status-badge ${statusClass}">${row.status}</span></td>
            <td>${row.response_code}</td>
            <td>${row.response_desc}</td>
          `;
          tbody.appendChild(tr);
        });

        document.getElementById('resultsContainer').style.display = 'block';
      } catch (err) {
        document.getElementById('loadingSpinner').style.display = 'none';
        alert('Search error: ' + err.message);
      }
    }

    function changePage(delta) {
      const target = currentPage + delta;
      if (target >= 1 && target <= totalPages) {
        executeSearch(target);
      }
    }
  </script>
</body>
</html>
"""

SESSION_EXPIRED_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Session Expired - OTC Portal</title>
  <style>
    body { font-family: sans-serif; background: #f8fafc; padding: 50px; text-align: center; }
    .box { background: #fff; padding: 30px; display: inline-block; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    h2 { color: #d32f2f; }
  </style>
</head>
<body>
  <div class="box" id="sessionExpiredAlert">
    <h2>Your Session Has Expired</h2>
    <p>Please log in again to continue transaction operations.</p>
    <a href="/login">Return to Login Screen</a>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        captcha = request.form.get("captcha", "").strip()
        otp = request.form.get("otp", "").strip()

        if username and password and captcha and otp:
            session["user"] = username
            session["auth_time"] = datetime.now().isoformat()
            return redirect(url_for("dashboard"))
        error = "Please complete all authentication fields."

    return render_template_string(LOGIN_HTML, error=error)


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template_string(DASHBOARD_HTML)


@app.route("/bps/check-bill-status")
def check_bill_status():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template_string(CHECK_BILL_HTML)


@app.route("/simulate-expire")
def simulate_expire():
    session.clear()
    return render_template_string(SESSION_EXPIRED_HTML)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/search")
def api_search():
    if "user" not in session:
        return jsonify({"error": "Unauthorized session"}), 401

    bank = request.args.get("bank", "").strip().upper()
    consumer = request.args.get("consumer", "").strip()
    date_val = request.args.get("from", "").strip()
    page = int(request.args.get("page", 1))
    page_size = 2

    matching: List[Dict[str, Any]] = []
    for item in SAMPLE_DATA:
        bank_matches = not bank or bank in item["bank_service"].upper()
        consumer_matches = not consumer or consumer == item["consumer_number"]
        date_matches = not date_val or date_val == item["date"]

        if bank_matches and consumer_matches and date_matches:
            matching.append(item)

    total_records = len(matching)
    total_pages = max(1, (total_records + page_size - 1) // page_size)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_records = matching[start_idx:end_idx]

    return jsonify(
        {
            "records": page_records,
            "page": page,
            "total_pages": total_pages,
            "total_records": total_records,
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
