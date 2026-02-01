import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import io

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def fetch_csv(url, params):
    """嘗試用不同方式抓取 CSV"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.taifex.com.tw/cht/3/futContractsDate'
    }
    session = requests.Session()
    try:
        # 優先用 POST
        r = session.post(url, data=params, headers=headers, timeout=15)
        # 如果 POST 失敗或被擋，嘗試用 GET
        if r.status_code != 200 or len(r.content) < 500:
            r = session.get(url, params=params, headers=headers, timeout=15)
        
        # 強制轉碼
        r.encoding = 'cp950'
        text = r.text
        
        if "日期" in text:
            return text
        else:
            print(f"⚠️ 資料格式不符。狀態碼: {r.status_code}, 內容開頭: {text[:100].strip()}")
            return None
    except Exception as e:
        print(f"❌ 連線異常: {e}")
        return None

def get_futures_data():
    check_date = datetime.now()
    max_tries = 6
    
    while max_tries > 0:
        date_str = check_date.strftime("%Y/%m/%d")
        print(f"🔍 檢查日期: {date_str}...")
        
        # 1. 三大法人
        c1 = fetch_csv("https://www.taifex.com.tw/cht/3/futContractsDateDown", {'queryDate': date_str, 'commodityId': ''})
        # 2. 大額交易人
        c2 = fetch_csv("https://www.taifex.com.tw/cht/3/largeTradersFutDown", {'queryDate': date_str})

        if c1 and c2:
            print(f"✅ 成功獲取 {date_str} 數據")
            df_inst = pd.read_csv(io.StringIO(c1))
            df_large = pd.read_csv(io.StringIO(c2))
            
            # --- 解析數據 ---
            results = []
            targets = [
                {"name": "台指期", "inst": "臺股期貨", "large": "臺股期貨"},
                {"name": "那指期", "inst": "美國那斯達克100期貨", "large": "美國那斯達克100"}
            ]

            for t in targets:
                try:
                    # 三大法人：外資(Index 13)與投信(Index 13)
                    inst_sub = df_inst[df_inst['商品名稱'].str.strip() == t['inst']]
                    foreign_net = int(inst_sub[inst_sub['身份別'].str.contains("外資")]['未平倉持有工口數-淨額'].values[0])
                    trust_net = int(inst_sub[inst_sub['身份別'].str.contains("投信")]['未平倉持有工口數-淨額'].values[0])

                    # 大額交易人：前五大特定法人買/賣 (Index 5, 9)
                    large_sub = df_large[(df_large['商品名稱'].str.strip() == t['large']) & (df_large['合約月份'].str.strip() == '所有月份')]
                    spec_buy = int(large_sub.iloc[0, 5])
                    spec_sell = int(large_sub.iloc[0, 9])
                    top5_spec_net = spec_buy - spec_sell

                    # 公式計算
                    big_f = top5_spec_net - trust_net
                    small_f = foreign_net - big_f
                    
                    results.append({"標的": t['name'], "外資": foreign_net, "大外資": big_f, "小外資": small_f})
                except Exception as e:
                    print(f"⚠️ {t['name']} 計算失敗: {e}")
            
            if results: return date_str, results

        check_date -= timedelta(days=1)
        max_tries -= 1

    return None, None

def main():
    date_str, data = get_futures_data()
    if not data:
        send_tg_msg("❌ 失敗：GitHub IP 可能遭期交所封鎖，請查看 Actions Log 中的內容片段。")
        return

    # 存檔與推送 (略，同前版本)
    msg = f"📊 *小外資籌碼報告* ({date_str})\n"
    for item in data:
        signal = "🟢 偏多" if item['小外資'] > 0 else "🔴 偏空"
        msg += f"【{item['標的']}】\n▫️ 大外資: {item['大外資']:,}\n▫️ *小外資: {item['小外資']:,}*\n💡 預測: {signal}\n\n"
    send_tg_msg(msg)

if __name__ == "__main__":
    main()
