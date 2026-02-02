import requests
import pandas as pd
import io
import os
from datetime import datetime, timedelta, timezone

# --- 環境變數 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

# 商品清單配置：(代號, 法人檔名關鍵字, 顯示名稱, 資料庫檔名)
CONFIG = {
    'TXF': ('TX', '臺股期貨', '台指期', 'history_data_txf.csv'),
    'UNF': ('UNF', '美國那斯達克100期貨', '那斯達克', 'history_data_unf.csv')
}

def get_taiwan_time():
    return datetime.now(timezone(timedelta(hours=8)))

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    requests.post(url, data=payload)

def download_file(url, payload, headers):
    session = requests.Session()
    session.get("https://www.taifex.com.tw/cht/3/dlLargeTraderFutView", headers=headers)
    resp = session.post(url, data=payload, headers=headers, timeout=20)
    if b"DOCTYPE" in resp.content[:100] or len(resp.content) < 500:
        return None
    return resp.content

def update_db(db_file, date_str, data):
    if os.path.exists(db_file):
        df_history = pd.read_csv(db_file)
    else:
        df_history = pd.DataFrame(columns=['日期', '特定五大買', '特定五大賣', '特定五大淨', '外資淨額', '投信淨額', '大外資', '小外資'])
    
    df_history['日期'] = df_history['日期'].astype(str)
    df_history = df_history[df_history['日期'] != date_str] # 覆蓋舊數據
    new_df = pd.DataFrame([data])
    df_history = pd.concat([df_history, new_df], ignore_index=True).sort_values('日期')
    df_history.to_csv(db_file, index=False, encoding='utf-8-sig')

def process_product(symbol, large_df, date_str):
    conf = CONFIG[symbol]
    large_code, inst_name, display_name, db_file = conf
    
    # 1. 抓取該商品的三大法人資料
    inst_url = "https://www.taifex.com.tw/cht/3/dlFutContractsDateDown"
    payload = {'queryStartDate': date_str, 'queryEndDate': date_str, 'commodityId': symbol}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    inst_content = download_file(inst_url, payload, headers)
    if inst_content is None:
        return f"⚠️ {display_name} 法人資料尚未更新。"

    # 2. 解析數據
    try:
        # 大額交易人數據提取
        mask = (large_df.iloc[:, 1].astype(str).str.strip() == large_code) & \
               (large_df.iloc[:, 3].astype(str).str.strip().str.contains("999999")) & \
               (large_df.iloc[:, 4].astype(str).str.strip() == "1")
        l_row = large_df[mask].iloc[0]
        top5_buy = int(float(l_row['前五大交易人買方']))
        top5_sell = int(float(l_row['前五大交易人賣方']))
        top5_spec_net = top5_buy - top5_sell

        # 三大法人數據提取
        df_inst = pd.read_csv(io.StringIO(inst_content.decode('cp950', errors='ignore')), skipinitialspace=True)
        df_inst.columns = [c.strip() for c in df_inst.columns]
        trust_net = int(df_inst[df_inst['身份別'].str.contains("投信")]['多空未平倉口數淨額'].values[0])
        foreign_net = int(df_inst[df_inst['身份別'].str.contains("外資")]['多空未平倉口數淨額'].values[0])

        # 公式計算
        big_f = top5_spec_net - trust_net
        small_f = foreign_net - big_f

        # 儲存到資料庫
        db_data = {'日期': date_str, '特定五大買': top5_buy, '特定五大賣': top5_sell, 
                   '特定五大淨': top5_spec_net, '外資淨額': foreign_net, '投信淨額': trust_net, 
                   '大外資': big_f, '小外資': small_f}
        update_db(db_file, date_str, db_data)

        # 格式化訊息
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
            f"🔥 大外資 (Big F): {big_f:>10,}\n"
            f"🌟 小外資 (Small F): {small_f:>10,}\n"
            f"```\n"
            f"📂 小外資留倉對隔日台股多空有預測力。"
        )
        return msg
    except Exception as e:
        return f"❌ {display_name} 解析失敗: {str(e)}"

def main():
    date_str = get_taiwan_time().strftime("%Y/%m/%d")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 下載大額交易人總表
    large_url = "https://www.taifex.com.tw/cht/3/dlLargeTraderFutDown"
    large_payload = {'queryStartDate': date_str, 'queryEndDate': date_str}
    large_content = download_file(large_url, large_payload, headers)

    if large_content is None:
        send_telegram(f"⚠️ {date_str} 無資料，可能為國定假日或程式壞掉")
        return

    df_large = pd.read_csv(io.StringIO(large_content.decode('cp950', errors='ignore')), skipinitialspace=True)
    df_large.columns = [c.strip() for c in df_large.columns]

    # 分別處理台指與那指
    for symbol in CONFIG.keys():
        report = process_product(symbol, df_large, date_str)
        send_telegram(report)

if __name__ == "__main__":
    main()
