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
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_futures_data():
    check_date = datetime.now()
    found_data = False
    max_tries = 15 # 增加回溯天數防止過年連假
    
    while not found_data and max_tries > 0:
        date_str = check_date.strftime("%Y/%m/%d")
        print(f"🔍 嘗試抓取日期: {date_str}...")
        
        try:
            # 1. 下載三大法人 CSV
            inst_url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
            r1 = requests.post(inst_url, data={'queryDate': date_str, 'commodityId': ''}, headers=HEADERS)
            
            # 2. 下載大額交易人 CSV
            large_url = "https://www.taifex.com.tw/cht/3/largeTradersFutDown"
            r2 = requests.post(large_url, data={'queryDate': date_str}, headers=HEADERS)

            # 檢查檔案是否有效 (CSV 檔頭通常包含日期)
            if "日期" in r1.text and "日期" in r2.text:
                # 讀取 CSV
                df_inst = pd.read_csv(io.StringIO(r1.text))
                df_large = pd.read_csv(io.StringIO(r2.text))
                found_data = True
                print(f"✅ 成功找到 {date_str} 的 CSV 數據")
                break
        except Exception as e:
            print(f"抓取發生異常: {e}")
        
        check_date -= timedelta(days=1)
        max_tries -= 1

    if not found_data:
        return None, None

    results = []
    # 標的設定
    targets = [
        {"name": "台指期", "inst_code": "臺股期貨", "large_code": "臺股期貨"},
        {"name": "那指期", "inst_code": "美國那斯達克100期貨", "large_code": "美國那斯達克100"}
    ]

    for t in targets:
        try:
            # --- 三大法人計算 ---
            # 篩選標的
            target_inst = df_inst[df_inst['商品名稱'].str.strip() == t['inst_code']]
            # 外資 (身份別為外資及陸資)
            foreign_net = int(target_inst[target_inst['身份別'].str.contains("外資")]['未平倉持有工口數-淨額'].values[0])
            # 投信
            trust_net = int(target_inst[target_inst['身份別'].str.contains("投信")]['未平倉持有工口數-淨額'].values[0])

            # --- 大額交易人計算 ---
            # 篩選標的，且合約月份為「所有月份」
            target_large = df_large[(df_large['商品名稱'].str.strip() == t['large_code']) & (df_large['合約月份'] == '所有月份')]
            # 抓取「前五大特定法人」的多空部位 (CSV 欄位名稱請見官網說明)
            # 在 CSV 中，前五大特定法人多方/空方通常是第 10, 11 欄 (索引 9, 10)
            top5_buy = int(target_large.iloc[0, 9])
            top5_sell = int(target_large.iloc[0, 10])
            top5_net = top5_buy - top5_sell

            # --- 小外資公式 ---
            big_f = top5_net - trust_net
            small_f = foreign_net - big_f
            
            results.append({
                "標的": t['name'],
                "外資": foreign_net,
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
        send_tg_msg("❌ 系統錯誤：回溯 15 天仍查無 CSV 資料，請確認期交所官網是否維護中。")
        return

    # 存檔 CSV (維持不變)
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
