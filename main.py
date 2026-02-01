import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import io

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("❌ 未設定 TG Token 或 Chat ID")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload)
        print(f"TG 發送狀態: {r.status_code}, 回應: {r.text}")
    except Exception as e:
        print(f"TG 發送異常: {e}")

def get_taifex_table(url, date_str, match_text):
    """通用抓取期交所表格函數"""
    try:
        resp = requests.post(url, data={'queryDate': date_str}, headers=HEADERS, timeout=15)
        if "查無資料" in resp.text or not resp.text.strip():
            return None
        
        # 抓取所有表格
        dfs = pd.read_html(io.StringIO(resp.text))
        for df in dfs:
            # 只要表格內容包含關鍵字，就是我們要的
            if df.astype(str).apply(lambda x: x.str.contains(match_text)).any().any():
                return df
    except Exception as e:
        print(f"抓取失敗 ({match_text}): {e}")
    return None

def get_futures_data():
    check_date = datetime.now()
    found_data = False
    max_tries = 10 
    
    while not found_data and max_tries > 0:
        date_str = check_date.strftime("%Y/%m/%d")
        print(f"🔍 嘗試抓取日期: {date_str}...")
        
        # 1. 抓取三大法人
        df_inst = get_taifex_table("https://www.taifex.com.tw/cht/3/futContractsDate", date_str, "臺股期貨")
        # 2. 抓取大額交易人
        df_large = get_taifex_table("https://www.taifex.com.tw/cht/3/largeTradersFutQry", date_str, "臺股期貨")

        if df_inst is not None and df_large is not None:
            found_data = True
            print(f"✅ 成功找到 {date_str} 的數據")
            break
        
        check_date -= timedelta(days=1)
        max_tries -= 1

    if not found_data:
        return None, None

    results = []
    # 標的對應 (台指期, 那指期)
    targets = [
        {"name": "台指期", "inst_code": "臺股期貨", "large_code": "臺股期貨"},
        {"name": "那指期", "inst_code": "美國那斯達克100期貨", "large_code": "美國那斯達克100"}
    ]

    for t in targets:
        try:
            # --- 三大法人數據 ---
            # 找到標的所在列
            inst_rows = df_inst[df_inst.iloc[:, 1].str.contains(t['inst_code'], na=False)]
            # 外資通常是該標的的第1列，投信第2列。未平倉淨額在第13欄
            f_net = int(inst_rows.iloc[0, 13])
            i_net = int(inst_rows.iloc[1, 13])

            # --- 大額交易人數據 ---
            large_rows = df_large[df_large.iloc[:, 1].str.contains(t['large_code'], na=False)]
            # 抓取「所有月份」且「前五大」之「特定法人」的多空頭部位 (欄位 5, 6)
            top5_buy = int(large_rows.iloc[0, 5])
            top5_sell = int(large_rows.iloc[0, 6])
            top5_net = top5_buy - top5_sell

            # --- 公式計算 ---
            big_f = top5_net - i_net
            small_f = f_net - big_f
            
            results.append({
                "標的": t['name'],
                "外資": f_net,
                "大外資": big_f,
                "小外資": small_f,
                "預測": "🟢 偏多" if small_f > 0 else "🔴 偏空"
            })
        except Exception as e:
            print(f"⚠️ 解析 {t['name']} 失敗: {e}")

    return date_str, results

def main():
    date_str, data = get_futures_data()
    
    if not data:
        send_tg_msg("❌ 系統錯誤：回溯 10 天仍無法解析期交所數據，請檢查網頁格式。")
        return

    # 存檔 CSV
    file_path = 'data/futures_history.csv'
    os.makedirs('data', exist_ok=True)
    df_new = pd.DataFrame(data)
    df_new['Date'] = date_str
    
    if os.path.exists(file_path):
        df_old = pd.read_csv(file_path)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Date', '標的'], keep='last')
    else:
        df_final = df_new
    df_final.to_csv(file_path, index=False, encoding='utf-8-sig')

    # TG 推送
    msg = f"📊 *每日小外資籌碼報告*\n📅 資料日期：{date_str}\n"
    msg += "---" + "\n"
    for item in data:
        msg += f"【{item['標的']}】\n"
        msg += f"▫️ 外資: {item['外資']:,}\n"
        msg += f"▫️ 大外資: {item['大外資']:,}\n"
        msg += f"▫️ *小外資: {item['小外資']:,}*\n"
        msg += f"💡 預測: {item['預測']}\n\n"
    
    send_tg_msg(msg)

if __name__ == "__main__":
    main()
