import requests
import pandas as pd
from datetime import datetime, timedelta
import os

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')
# 建議去 FinMind 官網註冊免費帳號取得 Token，穩定性會提高很多
FINMIND_TOKEN = os.getenv('FINMIND_TOKEN', "") 

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_finmind_data(dataset, date):
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {
        "dataset": dataset,
        "start_date": date,
        "end_date": date,
        "token": FINMIND_TOKEN,
    }
    try:
        resp = requests.get(url, params=parameter, timeout=15)
        if resp.status_code != 200:
            print(f"❌ API 連線失敗, 狀態碼: {resp.status_code}")
            return pd.DataFrame()
        
        data = resp.json()
        if 'data' in data and len(data['data']) > 0:
            return pd.DataFrame(data['data'])
    except Exception as e:
        print(f"❌ 請求過程發生錯誤: {e}")
    return pd.DataFrame()

def main():
    check_date = datetime.now()
    found = False
    data_date = ""
    
    # 回溯 6 天尋找最近的有開盤日期
    for i in range(7):
        target_date = (check_date - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"🔍 檢查 FinMind 資料日期: {target_date}...")
        
        df_inst = get_finmind_data("TaiwanFuturesInstitutionalEntity", target_date)
        df_large = get_finmind_data("TaiwanFuturesTradersRegion", target_date)
        
        if not df_inst.empty and not df_large.empty:
            found = True
            data_date = target_date
            print(f"✅ 成功獲取 {target_date} 數據！")
            break
            
    if not found:
        print("❌ 搜尋 6 天仍無資料。可能是 FinMind 更新延遲或 Token 被限流。")
        return

    results = []
    targets = [{"name": "台指期", "code": "TX"}, {"name": "那指期", "code": "UNF"}]

    for t in targets:
        try:
            # 三大法人 (ForeignInv: 外資, Trust: 投信)
            inst_sub = df_inst[df_inst['fut_id'] == t['code']]
            f_net = int(inst_sub[inst_sub['institutional_entity'] == 'ForeignInv']['open_interest_net'].values[0])
            i_net = int(inst_sub[inst_sub['institutional_entity'] == 'Trust']['open_interest_net'].values[0])

            # 大額交易人 (特定五大)
            large_sub = df_large[(df_large['fut_id'] == t['code']) & (df_large['contract_month'] == 'all')].iloc[0]
            spec_net = int(large_sub['top_five_specific_long_oi']) - int(large_sub['top_five_specific_short_oi'])

            # 公式計算
            # 1. 大外資 = 特定五大法人 - 投信
            big_f = spec_net - i_net
            # 2. 小外資 = 外資 - 大外資
            small_f = f_net - big_f
            
            results.append({
                "Date": data_date,
                "標的": t['name'],
                "外資淨": f_net,
                "大外資": big_f,
                "小外資": small_f,
                "預測": "🟢 偏多" if small_f > 0 else "🔴 偏空"
            })
        except Exception as e:
            print(f"⚠️ {t['name']} 解析失敗: {e}")

    if results:
        # --- 存檔至 CSV ---
        file_path = 'data/futures_history.csv'
        os.makedirs('data', exist_ok=True)
        df_new = pd.DataFrame(results)
        
        if os.path.exists(file_path):
            df_old = pd.read_csv(file_path)
            df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Date', '標的'], keep='last')
        else:
            df_final = df_new
        
        df_final.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"📁 歷史數據已存入 {file_path}")

        # --- TG 推送 ---
        msg = f"📊 *每日小外資籌碼報告*\n📅 資料日期：{data_date}\n"
        msg += "---" + "\n"
        for item in results:
            msg += f"【{item['標的']}】\n"
            msg += f"▫️ 大外資: {item['大外資']:,}\n"
            msg += f"▫️ *小外資: {item['小外資']:,}*\n"
            msg += f"💡 預測: {item['預測']}\n\n"
        send_tg_msg(msg)

if __name__ == "__main__":
    main()
