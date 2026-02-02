import requests
import pandas as pd
import io
import os
from datetime import datetime, timedelta, timezone

# --- 環境變數 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')
DB_FILE = "history_data.csv" # 你的回測資料庫檔名

def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("TG 資訊不完整，僅在終端機輸出。")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    requests.post(url, data=payload)

def get_taiwan_time():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

def download_data(date_str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.taifex.com.tw/cht/3/dlLargeTraderFutView',
        'Origin': 'https://www.taifex.com.tw'
    }
    # 1. 大額交易人下載引擎 (dl 版)
    large_url = "https://www.taifex.com.tw/cht/3/dlLargeTraderFutDown"
    large_payload = {'queryStartDate': date_str, 'queryEndDate': date_str}
    
    # 2. 三大法人下載引擎 (dl 版)
    inst_url = "https://www.taifex.com.tw/cht/3/dlFutContractsDateDown"
    inst_payload = {'queryStartDate': date_str, 'queryEndDate': date_str, 'commodityId': 'TXF'}

    session = requests.Session()
    session.get("https://www.taifex.com.tw/cht/3/dlLargeTraderFutView", headers=headers)
    
    r_large = session.post(large_url, data=large_payload, headers=headers)
    r_inst = session.post(inst_url, data=inst_payload, headers=headers)
    return r_large, r_inst

def update_database(date_str, data_row):
    """將當日數據存入 CSV 資料庫，若日期重複則覆蓋"""
    if os.path.exists(DB_FILE):
        df_history = pd.read_csv(DB_FILE)
    else:
        # 建立全新的 DataFrame
        df_history = pd.DataFrame(columns=['日期', '特定五大買', '特定五大賣', '特定五大淨', '外資淨額', '投信淨額', '大外資', '小外資'])

    # 確保日期欄位為字串，方便比對
    df_history['日期'] = df_history['日期'].astype(str)
    
    # 如果日期已存在，先刪除舊的那一筆
    df_history = df_history[df_history['日期'] != date_str]
    
    # 加入新數據
    new_df = pd.DataFrame([data_row])
    df_history = pd.concat([df_history, new_df], ignore_index=True)
    
    # 按照日期排序
    df_history = df_history.sort_values('日期')
    
    # 存回 CSV
    df_history.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
    print(f"✅ 資料庫已更新: {date_str}")

def main():
    now = get_taiwan_time()
    date_str = now.strftime("%Y/%m/%d")
    
    try:
        r_large, r_inst = download_data(date_str)
        
        if b"DOCTYPE" in r_large.content[:100] or len(r_large.content) < 500:
            raise ValueError("期交所尚未更新資料")

        # --- A. 解析大額交易人 ---
        df_large = pd.read_csv(io.StringIO(r_large.content.decode('cp950')), skipinitialspace=True)
        df_large.columns = [c.strip() for c in df_large.columns]
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

        # --- D. 更新資料庫 ---
        data_row = {
            '日期': date_str,
            '特定五大買': top5_buy,
            '特定五大賣': top5_sell,
            '特定五大淨': top5_spec_net,
            '外資淨額': foreign_net,
            '投信淨額': trust_net,
            '大外資': big_foreign,
            '小外資': small_foreign
        }
        update_database(date_str, data_row)

        # --- E. 發送訊息 ---
        msg = (
            f"🏆 *{date_str} 台指期小外資結果*\n"
            f"=============================\n"
            f"特定五大淨額： `{top5_spec_net:>10,}`\n"
            f"外資總淨額：   `{foreign_net:>10,}`\n"
            f"投信總淨額：   `{trust_net:>10,}`\n"
            f"-----------------------------\n"
            f"🔥 *大外資 (Big F):* `{big_foreign:>10,}`\n"
            f"🌟 *小外資 (Small F):* `{small_foreign:>10,}`\n"
            f"=============================\n"
            f"📂 歷史數據已存入資料庫。"
        )
        send_telegram(msg)

    except Exception as e:
        error_msg = f"⚠️ {date_str} 無資料，可能為國定假日或程式壞掉\n(錯誤訊息: {str(e)})"
        send_telegram(error_msg)
        print(error_msg)

if __name__ == "__main__":
    main()
