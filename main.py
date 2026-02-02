import requests
import pandas as pd
import io
import os
from datetime import datetime, timedelta, timezone

# --- 環境變數 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

# 商品清單配置：(大額交易人代號, 顯示名稱, 資料庫檔名)
CONFIG = {
    'TXF': ('TX', '台指期', 'history_data_txf.csv'),
    'UNF': ('UNF', '那斯達克', 'history_data_unf.csv')
}

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        print(f"--- Telegram Message ---\n{message}")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"TG 發送失敗: {e}")

def download_taifex(url, payload):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.taifex.com.tw/cht/3/dlLargeTraderFutView'
    }
    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=20)
        if b"DOCTYPE" in resp.content[:100] or len(resp.content) < 500:
            return None
        return resp.content
    except:
        return None

def update_database(db_file, date_str, data):
    if os.path.exists(db_file):
        df_history = pd.read_csv(db_file)
    else:
        df_history = pd.DataFrame(columns=['日期', '特定五大買', '特定五大賣', '特定五大淨', '外資淨額', '投信淨額', '大外資', '小外資'])
    
    df_history['日期'] = df_history['日期'].astype(str)
    df_history = df_history[df_history['日期'] != date_str]
    new_df = pd.DataFrame([data])
    df_history = pd.concat([df_history, new_df], ignore_index=True).sort_values('日期')
    df_history.to_csv(db_file, index=False, encoding='utf-8-sig')

def get_net_value(df, identity):
    """安全獲取『未平倉淨額』欄位數值"""
    try:
        # 篩選身份 (如: 外資、投信)
        row = df[df['身份別'].str.contains(identity, na=False)]
        if row.empty:
            return 0
            
        # 尋找包含『未平倉』且包含『淨額』的欄位 (通常是倒數第二欄)
        target_cols = [c for c in df.columns if '未平倉' in c and '淨額' in c]
        if target_cols:
            return int(row[target_cols[0]].values[0])
        return 0
    except:
        return 0

def main():
    date_str = get_taiwan_time().strftime("%Y/%m/%d")
    
    # 1. 下載大額交易人原始檔
    large_url = "https://www.taifex.com.tw/cht/3/dlLargeTraderFutDown"
    large_content = download_taifex(large_url, {'queryStartDate': date_str, 'queryEndDate': date_str})
    
    if not large_content:
        send_telegram(f"⚠️ {date_str} 期交所資料尚未更新，或今日為非交易日。")
        return

    # 解析大額交易人
    df_large = pd.read_csv(io.StringIO(large_content.decode('cp950', errors='ignore')), skipinitialspace=True)
    df_large.columns = [c.strip() for c in df_large.columns]
    
    # 建立清洗後的欄位方便比對
    df_large['code_clean'] = df_large.iloc[:, 1].astype(str).str.strip()
    df_large['month_clean'] = df_large.iloc[:, 3].astype(str).str.strip().str.replace('.0', '', regex=False)
    df_large['type_clean'] = df_large.iloc[:, 4].astype(str).str.strip().str.replace('.0', '', regex=False)

    for cmd_id, (large_code, display_name, db_file) in CONFIG.items():
        try:
            # --- 步驟 A: 提取大額數據 ---
            mask = (df_large['code_clean'] == large_code) & \
                   (df_large['month_clean'] == "999999") & \
                   (df_large['type_clean'] == "1")
            l_rows = df_large[mask]
            
            if l_rows.empty:
                send_telegram(f"⚠️ {date_str} {display_name} 找不到特定法人數據，跳過計算。")
                continue
                
            l_row = l_rows.iloc[0]
            top5_buy = int(float(l_row['前五大交易人買方']))
            top5_sell = int(float(l_row['前五大交易人賣方']))
            top5_spec_net = top5_buy - top5_sell

            # --- 步驟 B: 下載法人數據 ---
            inst_url = "https://www.taifex.com.tw/cht/3/dlFutContractsDateDown"
            inst_content = download_taifex(inst_url, {'queryStartDate': date_str, 'queryEndDate': date_str, 'commodityId': cmd_id})
            
            if not inst_content:
                send_telegram(f"⚠️ {date_str} {display_name} 法人資料下載失敗。")
                continue
                
            df_inst = pd.read_csv(io.StringIO(inst_content.decode('cp950', errors='ignore')), skipinitialspace=True)
            df_inst.columns = [c.strip() for c in df_inst.columns]
            
            foreign_net = get_net_value(df_inst, "外資")
            trust_net = get_net_value(df_inst, "投信")

            # --- 步驟 C: 執行公式 ---
            big_f = top5_spec_net - trust_net
            small_f = foreign_net - big_f

            # --- 步驟 D: 存入資料庫 ---
            update_database(db_file, date_str, {
                '日期': date_str, '特定五大買': top5_buy, '特定五大賣': top5_sell, 
                '特定五大淨': top5_spec_net, '外資淨額': foreign_net, '投信淨額': trust_net, 
                '大外資': big_f, '小外資': small_f
            })

            # --- 步驟 E: 發送 Telegram ---
            msg = (
                f"🏆 *{date_str} {display_name}小外資報告*\n"
                f"```\n"
                f"特定五大買方： {top5_buy:>10,}\n"
                f"特定五大賣方： {top5_sell:>10,}\n"
                f"特定五大淨額： {top5_spec_net:>10,}\n"
                f"-----------------------------\n"
                f"外資總淨額：   {foreign_net:>10,}\n"
                f"投信總淨額：   {trust_net:>10,}\n"
                f"-----------------------------\n"
                f"🔥 大外資留倉: {big_f:>10,}\n"
                f"🌟 小外資留倉: {small_f:>10,}\n"
                f"```\n"
                f"📂 小外資留倉對隔日台股多空有預測力。"
            )
            send_telegram(msg)

        except Exception as e:
            send_telegram(f"❌ {display_name} 計算出錯: {str(e)}")

if __name__ == "__main__":
    main()
