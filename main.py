import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import io

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("未設定 TG Token 或 Chat ID，跳過發送。")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_futures_data():
    # 從今天開始往回找，直到抓到資料
    check_date = datetime.now()
    found_data = False
    max_tries = 10
    
    while not found_data and max_tries > 0:
        date_str = check_date.strftime("%Y/%m/%d")
        print(f"嘗試抓取日期: {date_str}...")
        
        # 抓取資料
        inst_url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        r1 = requests.post(inst_url, data={'queryDate': date_str})
        large_url = "https://www.taifex.com.tw/cht/3/largeTradersFutQry"
        r2 = requests.post(large_url, data={'queryDate': date_str})

        try:
            df_inst_list = pd.read_html(io.StringIO(r1.text))
            df_large_list = pd.read_html(io.StringIO(r2.text))
            
            # 如果表格數量不足，代表當天沒開盤
            if len(df_inst_list) < 3 or len(df_large_list) < 3:
                check_date -= timedelta(days=1)
                max_tries -= 1
                continue
                
            df_inst = df_inst_list[2]
            df_large = df_large_list[2]
            found_data = True # 找到資料了！
        except:
            check_date -= timedelta(days=1)
            max_tries -= 1

    if not found_data:
        return None, None

    results = []
    targets = [
        {"name": "台指期", "code": "臺股期貨"}, 
        {"name": "那指期", "code": "美國那斯達克100期貨"} 
    ]

    for target in targets:
        try:
            target_inst = df_inst[df_inst.iloc[:, 1].str.contains(target['code'], na=False)]
            # 外資通常在第1列，投信在第2列。抓取第13欄 (未平倉淨額)
            foreign_net = int(target_inst.iloc[0, 13]) 
            trust_net = int(target_inst.iloc[1, 13])   

            target_large = df_large[df_large.iloc[:, 1].str.contains(target['code'], na=False)]
            top5_net = int(target_large.iloc[0, 5]) - int(target_large.iloc[0, 6]) # 前五大特定法人多-空

            big_foreign = top5_net - trust_net
            small_foreign = foreign_net - big_foreign
            
            signal = "🔴 偏空" if small_foreign < 0 else "🟢 偏多"

            results.append({
                "標的": target['name'],
                "外資": foreign_net,
                "大外資": big_foreign,
                "小外資": small_foreign,
                "預測": signal
            })
        except:
            continue

    return date_str, results

def main():
    date_str, data = get_futures_data()
    if not data:
        print("完全找不到近期交易數據。")
        return

    # 存檔至 CSV (每日一筆，重複則覆蓋)
    file_path = 'data/futures_history.csv'
    os.makedirs('data', exist_ok=True)
    df_new = pd.DataFrame(data)
    df_new['Data_Date'] = date_str # 標註資料原始日期
    df_new['Update_Time'] = datetime.now().strftime("%Y/%m/%d %H:%M")
    
    if os.path.exists(file_path):
        df_old = pd.read_csv(file_path)
        # 根據資料日期與標的做覆蓋
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Data_Date', '標的'], keep='last')
    else:
        df_final = df_new
    df_final.to_csv(file_path, index=False, encoding='utf-8-sig')

    # Telegram 推送
    msg = f"📊 *每日小外資籌碼報告*\n"
    msg += f"📅 資料日期：{date_str} (最新交易日)\n\n"
    for item in data:
        msg += f"【{item['標的']}】\n"
        msg += f"▫️ 外資留倉: {item['外資']:,}\n"
        msg += f"▫️ 大外資: {item['大外資']:,}\n"
        msg += f"▫️ *小外資: {item['小外資']:,}* \n"
        msg += f"💡 隔日預測: {item['預測']}\n\n"
    
    send_tg_msg(msg)

if __name__ == "__main__":
    main()
