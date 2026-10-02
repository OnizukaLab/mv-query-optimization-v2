import os
import psycopg2
import json

# PostgreSQLに接続
conn = psycopg2.connect("dbname=imdbload user=postgres")
cur = conn.cursor()

# SQLファイルが格納されているフォルダのパス
sql_folder_path = 'dataset/RED_SQL'
#sql_folder_path = 'dataset/RED_SQL/job'

# 出力フォルダのパス
output_folder_path = os.path.join("dataset/", 'RED_JSON')
#output_folder_path = os.path.join("dataset/", 'RED_JSON/job')

# 出力フォルダが存在しない場合は作成
if not os.path.exists(output_folder_path):
    os.makedirs(output_folder_path)

sql_dirs = [p for p, s, f in os.walk(sql_folder_path) if len(f) > 0]

for dir in sql_dirs:
    for sql_file in os.listdir(dir):
        output_path = output_folder_path + dir.replace(sql_folder_path,"")
        input_path = sql_folder_path + dir.replace(sql_folder_path,"")
        # make dirs for jsons
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            #print(output_path)
        
        sql_file_path = os.path.join(input_path, sql_file)
        #print(sql_file_path)
        # SQLファイルを読み込む
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_query = file.read()
        
        cur.execute(f"SET enable_bitmapscan = off")

        # EXPLAIN結果を取得
        cur.execute(f"EXPLAIN (FORMAT JSON) {sql_query}")
        explain_result = cur.fetchone()
        
        # 結果をJSON形式でファイルに保存
        output_file_path = os.path.join(output_path, f"{os.path.splitext(sql_file)[0]}.json")
        #print(output_file_path)
        with open(output_file_path, "w+", encoding='utf-8') as f:
            json.dump(explain_result[0], f, indent=4)

cur.close()
conn.close()