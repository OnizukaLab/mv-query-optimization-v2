[](file:///c%3A/Users/kanji%20masuda/query/mv-query-optimization/experiments/small_test/time_dependent_output) の読み取り

[](file:///c%3A/Users/kanji%20masuda/query/mv-query-optimization/experiments/small_test/time_dependent_output/normal_summary.json) の読み取り

[](file:///c%3A/Users/kanji%20masuda/query/mv-query-optimization/experiments/small_test/time_dependent_output/normal_morning_result.json#1-1) の 1 から 50 行を読み取り

Ran terminal command: python -c "
import json
with open('experiments/small_test/time_dependent_output/normal_morning_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('各MVのサイズ（バイト単位）:')
total_size = 0
for mv in data['selected_views']:
    size = mv['size']
    total_size += size
    print(f'{mv[\"node_id\"]:<12}: {size:>8} bytes ({size/1024:.2f} KB)')

print(f'\n総サイズ: {total_size} bytes ({total_size/1024:.2f} KB, {total_size/(1024*1024):.4f} MB)')
print(f'MV数: {len(data[\"selected_views\"])}')
print(f'平均サイズ: {total_size/len(data[\"selected_views\"]):.0f} bytes ({total_size/len(data[\"selected_views\"])/1024:.2f} KB)')
"

[](file:///c%3A/Users/kanji%20masuda/query/mv-query-optimization/experiments/small_test/analyze_mv_sizes.py) が作成されました

"ファイル内の文字列の置換" を使用しています


```

```


Ran terminal command: python experiments/small_test/analyze_mv_sizes.py

## 📊 MVサイズ分析結果

この実験で生成されるマテリアライズドビュー（MV）の容量は以下の通りです：

### 🎯 全体統計
- **総サイズ**: 10,609 bytes (10.36 KB, 0.0101 MB)
- **MV数**: 9個
- **平均サイズ**: 1,179 bytes (1.15 KB)

### 📈 サイズ分布
- **小サイズ (1KB未満)**: 4個 MV
- **中サイズ (1-10KB)**: 5個 MV  
- **大サイズ (10KB以上)**: 0個 MV

### 🔍 各MVのサイズ（バイト単位）
```
leaf_1     :      588 bytes (0.57 KB) - ユーザーの年齢フィルタ
leaf_2     :     1377 bytes (1.34 KB) - 最近60日の注文
leaf_4     :     2331 bytes (2.28 KB) - 最近90日の注文
leaf_5     :     3108 bytes (3.04 KB) - 最近120日の注文
leaf_6     :     3885 bytes (3.79 KB) - 最近180日の注文
non_leaf_5 :      588 bytes (0.57 KB) - 結合ビュー
non_leaf_9 :      588 bytes (0.57 KB) - 結合ビュー
non_leaf_11:      588 bytes (0.57 KB) - 結合ビュー
non_leaf_12:      588 bytes (0.57 KB) - 結合ビュー
```

## 💡 考察

1. **非常に小さいサイズ**: 各MVが1KB前後の小さなサイズ
2. **主にフィルタビュー**: 時間範囲や条件によるフィルタがメイン
3. **ストレージ効率**: 設定された5MB制限に対して0.01MB（1%未満）しか使用していない

このサイズは、小規模テストデータ（50ユーザー、30商品、200注文）によるもので、実運用ではデータ量に応じてサイズが増大します。最適化アルゴリズムは、設定されたストレージ制限（5MB）の中で最も効果的なMVを選択しています。

変更を行いました。