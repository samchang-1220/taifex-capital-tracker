import requests
import pandas as pd
import io
import os
import time
from datetime import datetime, timedelta, timezone

# --- 環境變數 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    requests.post(url, data=payload)

def get_taiwan_time():
    # 強制使用台灣時區 (UTC+8)
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

def download_data(date_str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://www.taifex.com.tw'
    }
    
    # 1. 下載大額交易人
    large_url = "https://www.taifex.com.tw/cht/3/dlLargeTraderFutDown"
    large_payload = {'queryStartDate': date_str, 'queryEndDate': date_str}
    
    # 2. 下載三大法人 (TXF)
    inst_url = "https://www.taifex.com.tw/cht/3/dlFutContractsDateDown"
    inst_payload = {'queryStartDate': date_str, 'queryEndDate': date_str, 'commodityId': 'TXF'}

    session = requests.Session()
    # 必須先訪問 View 頁面拿 Session
    session.get("https://www.taifex.com.tw/cht/3/dlLargeTraderFutView", headers=headers)
    
    r_large = session.post(large_url, data=large_payload, headers=headers)
    r_inst = session.post(inst_url, data=inst_payload, headers=headers)
    
    return r_large, r_inst

def main():
    now = get_taiwan_time()
    date_str = now.strftime("%Y/%m/%d")
    
    try:
        r_large, r_inst = download_data(date_str)
        
        # 檢查是否真的有資料 (排除 HTML 或過短的內容)
        if b"DOCTYPE" in r_large.content[:100] or len(r_large.content) < 500:
            raise ValueError("期交所尚未更新資料")

        # --- A. 解析大額交易人 ---
        df_large = pd.read_csv(io.StringIO(r_large.content.decode('cp950')), skipinitialspace=True)
        df_large.columns = [c.strip() for c in df_large.columns]
        
        # 篩選 TX, 999999, 類別 1
        df_large['code'] = df_large.iloc[:, 1].astype(str).str.strip()
        df_large['month'] = df_large.iloc[:, 3].astype(str).str.strip().str.replace('.0', '', regex=False)
        df_large['type'] = df_large.iloc[:, 4].astype(str).str.strip().str.replace('.0', '', regex=False)
        
        l_row = df_large[(df_large['code'] == "TX") & (df_large['month'] == "999999") & (df_large['type'] == "1")].iloc[0]
        top5_buy = int(float(l_row['前五大交易人買方']))
        top5_sell = int(float(l_row['前五大交易人賣方']))
        top5_spec_net = top5_buy - top5_sell

        # --- B. 解析三大法人 ---
        df_inst = pd.read_csv(io.StringIO(r_inst.content.decode('cp950')), skipinitialspace=True)
        df_inst.columns = [c.strip() for c in df_inst.columns]
        
        trust_net = int(df_inst[df_inst['身份別'].str.contains("投信")]['多空未平倉口數淨額'].values[0])
        foreign_net = int(df_inst[df_inst['身份別'].str.contains("外資")]['多空未平倉口數淨額'].values[0])

        # --- C. 公式計算 ---
        big_foreign = top5_spec_net - trust_net
        small_foreign = foreign_net - big_foreign

        # --- D. 組合成訊息 ---
        msg = (
            f"🏆 *{date_str} 台指期小外資計算結果*\n"
            f"=============================\n"
            f"特定五大買方： `{top5_buy:>10,}`\n"
            f"特定五大賣方： `{top5_sell:>10,}`\n"
            f"特定五大淨額： `{top5_spec_net:>10,}`\n"
            f"-----------------------------\n"
            f"外資總淨額：   `{foreign_net:>10,}`\n"
            f"投信總淨額：   `{trust_net:>10,}`\n"
            f"-----------------------------\n"
            f"🔥 *大外資 (Big F):* `{big_foreign:>10,}`\n"
            f"🌟 *小外資 (Small F):* `{small_foreign:>10,}`\n"
            f"============================="
        )
        send_telegram(msg)
        print("✅ 數據已成功發送至 TG")

    except Exception as e:
        error_msg = f"⚠️ {date_str} 無資料，可能為國定假日或程式壞掉\n(錯誤訊息: {str(e)})"
        send_telegram(error_msg)
        print(f"❌ {error_msg}")

if __name__ == "__main__":
    main()
