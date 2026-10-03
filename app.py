#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 28 15:13:00 2026

@author: Allen
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
CORS(app) 

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': 'Al040310100410', 
    'database': 'credit_card_app',
    'charset': 'utf8mb4'
}

# ==========================================
# 🌟 自動初始化資料庫與建立 Users 表格
# ==========================================
def init_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 建立 users 表格的 SQL 語法 (如果不存在的話)
        create_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(100) NOT NULL,
            birthday DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        
        cursor.execute(create_users_table)
        conn.commit()
        print("✅ 資料庫初始化成功：已確保 users 資料表存在！")
        
    except Exception as e:
        print(f"❌ 初始化資料庫失敗：{e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

@app.route('/api/register', methods=['POST'])
def register_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    full_name = data.get('full_name')
    birthday = data.get('birthday')

    if not all([email, password, full_name, birthday]):
        return jsonify({"error": "所有欄位都是必填的！"}), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        insert_query = """
        INSERT INTO users (email, password_hash, full_name, birthday) 
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (email, hashed_password, full_name, birthday))
        conn.commit()
        
        return jsonify({"message": "🎉 註冊成功！歡迎加入！"}), 201
        
    except mysql.connector.IntegrityError:
        return jsonify({"error": "這個 Email 已經被註冊過囉！"}), 409
    except Exception as e:
        return jsonify({"error": f"伺服器錯誤：{e}"}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

@app.route('/api/login', methods=['POST'])
def login_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "請輸入帳號與密碼！"}), 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True) 
        
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            return jsonify({
                "message": "登入成功！", 
                "user_name": user['full_name'],
                "birthday": str(user['birthday'])
            }), 200
        else:
            return jsonify({"error": "帳號或密碼錯誤！"}), 401
            
    except Exception as e:
        return jsonify({"error": f"伺服器錯誤：{e}"}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

# ==========================================
# 🌟 搜尋最高回饋的無狀態 API
# ==========================================
@app.route('/api/search_rewards', methods=['POST'])
def search_rewards():
    data = request.json
    keyword = data.get('keyword', '')
    user_cards = data.get('user_cards', [])
    birthday_str = data.get('birthday', '') 
    
    if not keyword or not user_cards:
        return jsonify([]), 200
        
    current_month = datetime.now().month
    birth_month = None
    if birthday_str:
        try:
            birth_date = datetime.strptime(birthday_str[:10], '%Y-%m-%d')
            birth_month = birth_date.month
        except ValueError:
            pass

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        card_conditions = []
        query_params = [f"%{keyword}%"] 
        
        for card in user_cards:
            c_name = card.get('card_name')
            
            if c_name == 'CUBE卡':
                c_level = card.get('card_level', 'Level 1')
            elif c_name == 'Unicard':
                c_level = card.get('card_level', '簡單選') 
            else:
                c_level = 'Standard'
                
            card_conditions.append("(card_name = %s AND card_level = %s)")
            query_params.extend([c_name, c_level])
            
        cards_clause = " OR ".join(card_conditions)
        
        query = f"""
            SELECT bank_name, card_name, card_level, scheme_name, merchant_name, reward_rate 
            FROM card_rewards 
            WHERE merchant_name LIKE %s AND ({cards_clause})
        """
        
        cursor.execute(query, tuple(query_params))
        db_results = cursor.fetchall()
        
        # 🌟 新增：使用字典來過濾同一張卡的最高回饋結果
        best_results = {}
        
        for row in db_results:
            card_name = row['card_name']
            scheme_name = row.get('scheme_name') 
            
            user_card_state = next((c for c in user_cards if c['card_name'] == card_name), None)
            if not user_card_state:
                continue
                
            is_valid = True
            
            if scheme_name == '新戶' and not user_card_state.get('is_new_user'):
                is_valid = False
            elif scheme_name == '童樂匯' and not user_card_state.get('has_kids_club'):
                is_valid = False
            elif scheme_name == '慶生月':
                if birth_month != current_month:
                    is_valid = False
                    
            if card_name == 'Unicard' and scheme_name == '百大特店':
                unicard_scheme = user_card_state.get('card_level') 
                chosen_merchants = user_card_state.get('chosen_merchants', [])
                
                if unicard_scheme == '任意選' and row['merchant_name'] not in chosen_merchants:
                    is_valid = False
                
            if is_valid:
                current_rate = float(row['reward_rate'])
                
                if card_name == 'Unicard':
                    has_e_bill = user_card_state.get('has_e_bill', False)
                    has_auto_deduct = user_card_state.get('has_auto_deduct', False)
                    
                    if has_e_bill and has_auto_deduct:
                        current_rate += 1.0
                    elif has_e_bill:
                        current_rate += 0.3
                        
                # 🌟 邏輯修改：檢查目前這張卡是否已經存在 best_results 中
                # 如果不存在，或是目前方案的回饋比較高，就覆蓋儲存
                if card_name not in best_results or current_rate > best_results[card_name]['reward_rate']:
                    best_results[card_name] = {
                        "card_name": card_name,
                        "reward_rate": current_rate,
                        "card_level": row.get('card_level'),
                        "scheme_name": row.get('scheme_name'),
                        "merchant_name": row.get('merchant_name')
                    }
        
        # 🌟 將過濾完成的字典轉換回陣列，並由高到低排序
        final_results = list(best_results.values())
        final_results.sort(key=lambda x: x['reward_rate'], reverse=True)
        
        return jsonify(final_results), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


# ==========================================
# 🌟 搜尋框自動補齊 (模糊搜尋) API
# ==========================================
@app.route('/api/autocomplete', methods=['GET'])
def autocomplete():
    keyword = request.args.get('q', '')
    
    if not keyword:
        return jsonify([]), 200

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT DISTINCT merchant_name 
            FROM card_rewards 
            WHERE merchant_name LIKE %s
            LIMIT 10
        """
        
        cursor.execute(query, (f"%{keyword}%",))
        results = cursor.fetchall()
        
        suggestions = [row['merchant_name'] for row in results]
        
        return jsonify(suggestions), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()
        
# ==========================================
# 🌟 獲取玉山 Unicard 百大特店清單
# ==========================================
@app.route('/api/unicard_merchants', methods=['GET'])
def get_unicard_merchants():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT DISTINCT merchant_name 
            FROM card_rewards 
            WHERE card_name = 'Unicard' AND scheme_name = '百大特店'
            ORDER BY merchant_name
        """)
        results = [row['merchant_name'] for row in cursor.fetchall()]
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

if __name__ == '__main__':
    # 🌟 在伺服器啟動前，先執行資料庫初始化檢查
    init_db()
    print("🚀 後端 API 伺服器啟動中... 正在監聽 Port 5000")
    app.run(host='0.0.0.0', port=5000, debug=True)