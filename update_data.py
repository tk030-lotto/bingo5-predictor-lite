import os
import sys
import json
import re
import requests
import io
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BINGO5_UPDATER")

BINGO5_CSV_URL = 'https://loto-life.net/csv/bingo5'

def clean_val(val):
    if not isinstance(val, str):
        return val
    s = val.strip()
    match = re.search(r'="(.+?)"', s)
    if match:
        return match.group(1)
    return s.strip('"')

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(clean_val)

def fetch_and_parse_csv():
    logger.info(f"Downloading CSV from {BINGO5_CSV_URL}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(BINGO5_CSV_URL, headers=headers, timeout=15)
    response.raise_for_status()
    
    csv_bytes = response.content
    decoded_text = None
    for enc in ('cp932', 'utf-8', 'utf-8-sig'):
        try:
            decoded_text = csv_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
            
    if not decoded_text:
        raise ValueError("Failed to decode CSV bytes")
        
    df = pd.read_csv(io.StringIO(decoded_text.strip()))
    df.columns = [clean_val(c) if isinstance(c, str) else c for c in df.columns]
    df = clean_data(df)
    
    parsed_history = []
    
    for _, row in df.iterrows():
        try:
            # 1列目: 回号
            round_no = int(row.iloc[0])
            # 2列目: 抽せん日
            date_str = str(row.iloc[1]).strip()
            # 3〜10列目: 当選番号
            numbers = [int(row.iloc[col]) for col in range(2, 10)]
            
            # 基本的なバリデーション
            if len(numbers) != 8:
                continue
            
            # ビンゴ5の数字範囲チェック
            # 各マスの範囲は (i*5+1) から (i*5+5)
            valid = True
            for i, num in enumerate(numbers):
                lo = i * 5 + 1
                hi = i * 5 + 5
                if not (lo <= num <= hi):
                    valid = False
                    break
            
            if not valid:
                continue
                
            parsed_history.append({
                "round": round_no,
                "date": date_str,
                "numbers": numbers
            })
        except Exception as e:
            continue
            
    # 回号の降順でソート
    parsed_history.sort(key=lambda x: x['round'], reverse=True)
    return parsed_history

def main():
    target_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bingo5_data.js")
    
    try:
        history = fetch_and_parse_csv()
        if not history:
            logger.error("No parsed data")
            sys.exit(1)
            
        # JavaScriptファイルとして書き出し
        js_content = f"""// ビンゴ5履歴データ（全件）
// 自動生成・同期機能用
const DEFAULT_BINGO5_DATA = {json.dumps(history, ensure_ascii=False, indent=2)};
"""
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(js_content)
        logger.info(f"Successfully updated bingo5_data.js. Rounds: {len(history)}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error updating bingo5_data.js: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
