// グローバル状態
let currentQuerySet = null;
let currentResultFile = null;
let optimizationData = null;
let staticOptimizationData = null; // 静的最適化データ保持用
let benchmarkData = null; // ベンチマークデータ保持用
let comparisonSelectedFiles = []; // 比較用選択ファイル [{folder: path, file: filename, label: displayName}, ...]
let selectedMVs = [];
let rootNodesMap = null; // クエリ名 -> ルートノードID
let mvSizesMap = null; // MV名 -> サイズ(bytes)
let subqueryCostsMap = null; // MV名 -> cost（作成コスト表示用）
let mvUtilitiesMap = null; // MV名 -> utility（利得表示用）

// ルートMV化率更新
function updateRootMVStats() {
    const el = document.getElementById('root-mv-stats');
    if (!el || !rootNodesMap || !selectedMVs) {
        if (el) el.textContent = 'ルートMV化率: - / -';
        return;
    }

    // クエリ数ベースのカウント
    const total = Object.keys(rootNodesMap).length;
    const covered = Object.values(rootNodesMap).filter(id => selectedMVs.includes(id)).length;
    const percent = total > 0 ? (covered / total * 100).toFixed(1) : 0;

    // サイズベースの計算（mvSizesMapが利用可能な場合）
    let sizeInfo = '';
    if (mvSizesMap) {
        let totalSize = 0;
        let coveredSize = 0;
        for (const [queryName, rootNodeId] of Object.entries(rootNodesMap)) {
            const nodeSize = mvSizesMap[rootNodeId] || 0;
            totalSize += nodeSize;
            if (selectedMVs.includes(rootNodeId)) {
                coveredSize += nodeSize;
            }
        }
        const sizePercent = totalSize > 0 ? (coveredSize / totalSize * 100).toFixed(1) : 0;
        sizeInfo = ` | サイズ: ${formatBytes(coveredSize)} / ${formatBytes(totalSize)} (${sizePercent}%)`;
    }

    el.textContent = `ルートMV化率: ${covered} / ${total} クエリ (${percent}%)${sizeInfo}`;
}

// 自然数ソート
function naturalSort(arr) {
    return arr.sort((a, b) => {
        const ax = [], bx = [];
        a.replace(/(\d+)|(\D+)/g, (_, $1, $2) => { ax.push([$1 || Infinity, $2 || ""]) });
        b.replace(/(\d+)|(\D+)/g, (_, $1, $2) => { bx.push([$1 || Infinity, $2 || ""]) });
        while (ax.length && bx.length) {
            const an = ax.shift(), bn = bx.shift();
            const nn = (an[0] - bn[0]) || an[1].localeCompare(bn[1]);
            if (nn) return nn;
        }
        return ax.length - bx.length;
    });
}


// バイトを人間が読める形式に変換
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// API呼び出しヘルパー
async function fetchAPI(endpoint) {
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
}

// 初期化
async function init() {
    // クエリセット読み込み
    const querySets = await fetchAPI('/api/query-sets');
    const querySetSelect = document.getElementById('query-set-select');
    querySets.forEach(qs => {
        const opt = document.createElement('option');
        opt.value = qs;
        opt.textContent = qs;
        querySetSelect.appendChild(opt);
    });

    // デフォルト選択
    if (querySets.includes('job')) {
        querySetSelect.value = 'job';
    }

    querySetSelect.addEventListener('change', onQuerySetChange);
    await onQuerySetChange();

    // タブ切り替え
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');

            // クエリツリータブに切り替えたときは再描画
            if (tab.dataset.tab === 'query-tree') {
                setTimeout(() => updateQueryTree(), 100);
            }
            // 比較タブ切り替え時
            if (tab.dataset.tab === 'comparison') {
                setupComparisonTab();
            }
            // 頻度タブ切り替え時
            if (tab.dataset.tab === 'frequency') {
                loadFrequencyFiles();
            }
        });
    });

    // 比較更新ボタン
    document.getElementById('update-comparison-btn').addEventListener('click', updateComparisonCharts);
    document.getElementById('clear-comparison-btn').addEventListener('click', () => {
        comparisonSelectedFiles = [];
        renderComparisonFileList();
    });

    // 頻度タブのイベントハンドラ設定
    setupFrequencyTab();

    // スライダー初期化
    setupSlider('timestep-slider', 'timestep-value', '', onTimestepChange);
    setupSlider('table-height', 'table-height-value', 'px', v => {
        document.getElementById('mv-table-container').style.height = v + 'px';
    });
}

function setupSlider(sliderId, valueId, suffix, onChange) {
    const slider = document.getElementById(sliderId);
    const valueEl = document.getElementById(valueId);
    slider.addEventListener('input', () => {
        valueEl.textContent = slider.value + suffix;
        onChange(parseInt(slider.value));
    });
}

// クエリセット変更
async function onQuerySetChange() {
    currentQuerySet = document.getElementById('query-set-select').value;

    // サブフォルダ読み込み（動的ナビゲーション）
    await loadSubfolders('');
}

// 現在のフォルダパス
let currentFolderPath = '(root)';

// サブフォルダ読み込み
async function loadSubfolders(path) {
    const subfolderData = await fetchAPI(`/api/subfolders/${currentQuerySet}?path=${encodeURIComponent(path)}`);
    const subfolderSelect = document.getElementById('subfolder-select');
    subfolderSelect.innerHTML = '';

    currentFolderPath = subfolderData.current_path;

    // 戻るボタン（ルート以外の場合）
    if (subfolderData.parent_path !== '') {
        const backOpt = document.createElement('option');
        backOpt.value = `__BACK__:${subfolderData.parent_path}`;
        backOpt.textContent = '⬆️ 上のフォルダへ戻る';
        subfolderSelect.appendChild(backOpt);
    }

    // 現在のフォルダに結果がある場合、そのオプションを追加
    if (subfolderData.has_results) {
        const currentOpt = document.createElement('option');
        currentOpt.value = subfolderData.current_path;
        currentOpt.textContent = `📁 [現在] ${subfolderData.current_path}`;
        currentOpt.selected = true;
        subfolderSelect.appendChild(currentOpt);
    }

    // サブフォルダ一覧
    subfolderData.folders.forEach(folder => {
        const opt = document.createElement('option');
        if (folder.has_children) {
            // サブフォルダを持つ → ナビゲーション用
            opt.value = `__NAV__:${folder.path}`;
            opt.textContent = `📂 ${folder.name} ▶`;
        } else if (folder.has_results) {
            // 結果のみ → 選択可能
            opt.value = folder.path;
            opt.textContent = `📁 ${folder.name}`;
        } else {
            // 結果もサブフォルダもなし → スキップ
            return;
        }
        subfolderSelect.appendChild(opt);
    });

    // フォルダがない場合
    if (!subfolderData.has_results && subfolderData.folders.length === 0 && subfolderData.parent_path === '') {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '(なし)';
        subfolderSelect.appendChild(opt);
    }

    // イベントリスナー設定（重複防止のためonを使用）
    subfolderSelect.onchange = async function () {
        const val = subfolderSelect.value;
        if (val.startsWith('__BACK__:')) {
            // 戻る
            const parentPath = val.replace('__BACK__:', '');
            await loadSubfolders(parentPath === '(root)' ? '' : parentPath);
        } else if (val.startsWith('__NAV__:')) {
            // サブフォルダへナビゲート
            const navPath = val.replace('__NAV__:', '');
            await loadSubfolders(navPath);
        } else {
            // 結果フォルダを選択
            currentFolderPath = val;
            await onSubfolderChange();
        }
    };

    // 結果がある場合は読み込み
    if (subfolderData.has_results) {
        await onSubfolderChange();
    }

    // クエリ一覧読み込み
    const queries = await fetchAPI(`/api/queries/${currentQuerySet}`);
    const querySelect = document.getElementById('query-select');
    querySelect.innerHTML = '';
    queries.forEach(q => {
        const opt = document.createElement('option');
        opt.value = q;
        opt.textContent = q;
        querySelect.appendChild(opt);
    });
    querySelect.addEventListener('change', (e) => scrollToQuery(e.target.value));
    initQueryGallery(queries);

    // Root Nodes取得
    try {
        rootNodesMap = await fetchAPI(`/api/root-nodes/${currentQuerySet}`);
    } catch (e) { console.warn("Root nodes fetch failed", e); }

    // MVサイズ取得
    try {
        mvSizesMap = await fetchAPI(`/api/mv-sizes/${currentQuerySet}`);
    } catch (e) { console.warn("MV sizes fetch failed", e); }

    // subquery_costs取得（コスト表示用）
    try {
        subqueryCostsMap = await fetchAPI(`/api/subquery-costs/${currentQuerySet}`);
    } catch (e) { console.warn("subquery costs fetch failed", e); }

    // mv_utilities取得（利得表示用）
    try {
        mvUtilitiesMap = await fetchAPI(`/api/mv-utilities/${currentQuerySet}`);
    } catch (e) { console.warn("mv utilities fetch failed", e); }

    // 全データ取得後にルートMV化率を更新
    updateRootMVStats();

    // 頻度ファイル一覧も更新
    loadFrequencyFiles();
}

// サブフォルダ変更
async function onSubfolderChange() {
    // currentFolderPath を使用（loadSubfoldersで設定済み）
    const subfolder = currentFolderPath === '(root)' ? '' : currentFolderPath;

    // 結果ファイル読み込み
    const files = await fetchAPI(`/api/result-files/${currentQuerySet}?subfolder=${encodeURIComponent(subfolder)}`);
    const resultSelect = document.getElementById('result-file-select');
    resultSelect.innerHTML = '';

    // 動的最適化ファイル
    files.optimization.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = `[動的] ${f}`;
        opt.dataset.type = 'dynamic';
        resultSelect.appendChild(opt);
    });

    // 適応的最適化ファイル
    if (files.adaptive_optimization) {
        files.adaptive_optimization.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.textContent = `[適応的] ${f}`;
            opt.dataset.type = 'adaptive';
            resultSelect.appendChild(opt);
        });
    }

    // 静的最適化ファイル
    files.static.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = `[静的] ${f}`;
        opt.dataset.type = 'static';
        resultSelect.appendChild(opt);
    });

    resultSelect.addEventListener('change', onResultFileChange);

    await onResultFileChange();
}

// 結果ファイル変更
async function onResultFileChange() {
    const resultSelect = document.getElementById('result-file-select');
    currentResultFile = resultSelect.value;
    if (!currentResultFile) return;

    const subfolder = currentFolderPath === '(root)' ? '' : currentFolderPath;
    const selectedOption = resultSelect.options[resultSelect.selectedIndex];
    const fileType = selectedOption?.dataset?.type || 'dynamic';

    // スライダーコンテナを取得
    const sliderContainer = document.querySelector('.slider-container');

    // 時系列分析パネルのID
    const timeSeriesPanels = ['panel-changes-summary', 'panel-storage-chart', 'panel-mv-timeline'];

    if (fileType === 'static') {
        // 静的最適化結果を取得
        const staticData = await fetchAPI(`/api/static-result/${currentQuerySet}/${currentResultFile}?subfolder=${encodeURIComponent(subfolder)}`);

        // タイムステップスライダーを非表示
        sliderContainer.style.display = 'none';

        // 時系列パネルを非表示
        timeSeriesPanels.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });

        // メトリクス更新
        document.getElementById('mv-count').textContent = staticData.mv_count;
        document.getElementById('total-size').textContent = formatBytes(staticData.total_size);
        document.getElementById('total-cost').textContent = staticData.objective_value.toFixed(2);
        document.getElementById('utilization').textContent = staticData.utilization_percent.toFixed(1) + '%';

        // 選択されたMVを更新
        selectedMVs = staticData.selected_mvs;
        updateRootMVStats();

        // テーブル更新
        const tbody = document.getElementById('mv-table-body');
        tbody.innerHTML = '';
        staticData.mv_details.forEach(mv => {
            const tr = document.createElement('tr');
            const utilityValue = (mvUtilitiesMap && mvUtilitiesMap[mv.mv]) ? mvUtilitiesMap[mv.mv] : 0;
            const costValue = (subqueryCostsMap && subqueryCostsMap[mv.mv]) ? subqueryCostsMap[mv.mv] : (mv.cost || 0);
            tr.innerHTML = `
                <td>${mv.mv}</td>
                <td>${formatBytes(mv.size || 0)}</td>
                <td>${utilityValue.toFixed(2)}</td>
                <td>${costValue.toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });

        // グローバル変数に保存
        staticOptimizationData = staticData;
        optimizationData = null; // 動的データはクリア

        // クエリツリーのタイムステップ選択を非表示
        document.getElementById('tree-timestep-select').parentElement.style.display = 'none';

    } else {
        // 動的最適化結果を取得（従来の処理）
        // 動的最適化結果を取得（従来の処理）
        optimizationData = await fetchAPI(`/api/optimization-result/${currentQuerySet}/${currentResultFile}?subfolder=${encodeURIComponent(subfolder)}`);
        staticOptimizationData = null;

        // タイムステップスライダーを表示
        sliderContainer.style.display = 'flex';

        // 時系列パネルを表示
        timeSeriesPanels.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'block';
        });

        // クエリツリーのタイムステップ選択を表示
        document.getElementById('tree-timestep-select').parentElement.style.display = 'inline-block';

        // スライダー更新
        const slider = document.getElementById('timestep-slider');
        slider.max = optimizationData.timesteps.length - 1;
        slider.value = 0;
        document.getElementById('timestep-value').textContent = '0';

        // タイムステップセレクト更新
        const tsSelect = document.getElementById('tree-timestep-select');
        tsSelect.innerHTML = '';
        optimizationData.timesteps.forEach((t, i) => {
            const opt = document.createElement('option');
            opt.value = i;
            opt.textContent = `T${t}`;
            tsSelect.appendChild(opt);
        });
        tsSelect.addEventListener('change', updateAllLoadedQueries);

        // 各ビュー更新
        onTimestepChange(0);
        updateTimelineChart();
        updateStorageChart();
        updateChangesTable();
    }

    // ベンチマーク結果取得 & 更新
    try {
        benchmarkData = await fetchAPI(`/api/benchmark-result/${currentQuerySet}/${currentResultFile}?subfolder=${encodeURIComponent(subfolder)}`);
        updateBenchmarkChart();
    } catch (e) {
        console.warn("Benchmark data fetch failed:", e);
        benchmarkData = null;
        updateBenchmarkChart(); // クリア表示
    }

    updateAllLoadedQueries();
}

// タイムステップ変更
function onTimestepChange(timestep) {
    if (!optimizationData) return;

    const tsData = optimizationData.timestep_data[timestep];
    if (!tsData) return;

    selectedMVs = tsData.mvs.map(m => m.mv);
    updateRootMVStats();

    // メトリクス更新
    document.getElementById('mv-count').textContent = tsData.mv_count;
    document.getElementById('total-size').textContent = formatBytes(tsData.total_size);
    const totalCost = tsData.mvs.reduce((sum, m) => sum + (m.cost || 0), 0);
    document.getElementById('total-cost').textContent = totalCost.toFixed(2);
    document.getElementById('utilization').textContent = tsData.utilization_percent.toFixed(1) + '%';

    // テーブル更新
    const tbody = document.getElementById('mv-table-body');
    tbody.innerHTML = '';
    tsData.mvs.forEach(mv => {
        const tr = document.createElement('tr');
        const utilityValue = (mvUtilitiesMap && mvUtilitiesMap[mv.mv]) ? mvUtilitiesMap[mv.mv] : 0;
        const costValue = (subqueryCostsMap && subqueryCostsMap[mv.mv]) ? subqueryCostsMap[mv.mv] : (mv.cost || 0);
        tr.innerHTML = `
            <td>${mv.mv}</td>
            <td>${formatBytes(mv.size || 0)}</td>
            <td>${utilityValue.toFixed(2)}</td>
            <td>${costValue.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// タイムラインチャート更新
function updateTimelineChart() {
    if (!optimizationData) return;

    // MVごとの選択状態をマトリクス化
    const allMVs = new Set();
    optimizationData.timestep_data.forEach(ts => {
        ts.mvs.forEach(m => allMVs.add(m.mv));
    });
    const mvList = naturalSort([...allMVs]);

    // MV数に応じてチャート高さを計算（各MV行に25px、最小400px）
    const chartHeight = Math.max(400, mvList.length * 25 + 80);
    document.getElementById('timeline-chart').style.height = chartHeight + 'px';

    const z = mvList.map(mv =>
        optimizationData.timestep_data.map(ts =>
            ts.mvs.some(m => m.mv === mv) ? 1 : 0
        )
    );

    const data = [{
        z: z,
        x: optimizationData.timesteps.map(t => 'T' + t),
        y: mvList,
        type: 'heatmap',
        colorscale: [[0, '#313244'], [1, '#a6e3a1']],
        showscale: false,
        xgap: 1,  // セル間の水平ギャップ
        ygap: 1   // セル間の垂直ギャップ（MV間の境界線）
    }];

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 120, r: 20, t: 20, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: '', autorange: 'reversed' },
        height: chartHeight
    };

    Plotly.newPlot('timeline-chart', data, layout, { responsive: true });
}

// ストレージチャート更新
function updateStorageChart() {
    if (!optimizationData) return;

    const data = [{
        x: optimizationData.timesteps.map(t => parseInt(t)),
        y: optimizationData.timestep_data.map(ts => ts.total_size / (1024 * 1024)),
        type: 'scatter',
        mode: 'lines+markers',
        fill: 'tozeroy',
        fillcolor: 'rgba(137, 180, 250, 0.2)',
        line: { color: '#89b4fa', width: 2 },
        marker: { size: 6 }
    }];

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 20, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: 'ストレージ (MB)' }
    };

    Plotly.newPlot('storage-chart', data, layout, { responsive: true });
}

// 変更テーブル更新
function updateChangesTable() {
    if (!optimizationData) return;

    const tbody = document.getElementById('changes-table-body');
    tbody.innerHTML = '';

    let prevMVs = new Set();
    optimizationData.timestep_data.forEach(ts => {
        const currentMVs = new Set(ts.mvs.map(m => m.mv));
        const added = [...currentMVs].filter(m => !prevMVs.has(m));
        const removed = [...prevMVs].filter(m => !currentMVs.has(m));

        if (added.length > 0 || removed.length > 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>T${ts.timestep}</td>
                <td style="color: var(--accent-green)">+${added.length}</td>
                <td style="color: var(--accent-red)">-${removed.length}</td>
            `;
            tbody.appendChild(tr);
        }
        prevMVs = currentMVs;
    });
}

// クエリギャラリー初期化
function initQueryGallery(queries) {
    const gallery = document.getElementById('query-gallery');
    gallery.innerHTML = ''; // Clear existing

    queries.forEach(q => {
        const card = document.createElement('div');
        card.className = 'query-card';
        card.dataset.queryName = q;
        card.innerHTML = `
            <div class="query-card-header">
                <h3>Query: ${q}</h3>
                <button onclick="scrollToQuery('${q}')" style="padding:4px 8px; cursor:pointer;">Focus</button>
            </div>
            <div class="query-card-svg-container" style="height: 100%; min-height: 400px;">
                <svg width="100%" height="100%"></svg>
            </div>
        `;
        gallery.appendChild(card);
    });

    setupLazyLoading();
}

// Lazy Loading設定
function setupLazyLoading() {
    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const card = entry.target;
                if (!card.classList.contains('loaded')) {
                    loadQueryCard(card);
                    obs.unobserve(card); // 一度ロードしたら監視解除
                }
            }
        });
    }, { root: document.getElementById('query-gallery'), threshold: 0.1 });

    document.querySelectorAll('.query-card').forEach(card => observer.observe(card));
}

// 個別クエリカードのロード
async function loadQueryCard(card) {
    const queryName = card.dataset.queryName;
    const svgContainer = card.querySelector('.query-card-svg-container');
    card.classList.add('loaded'); // ロード済みフラグ

    try {
        // EXPLAIN取得
        const explain = await fetchAPI(`/api/explain/${currentQuerySet}/${queryName}`);

        // ハイライト用MV算出
        let highlightMVs = [];
        const timestep = parseInt(document.getElementById('tree-timestep-select').value || 0);

        // 選択MVリスト
        let allSelectedMVs = [];
        if (staticOptimizationData) {
            allSelectedMVs = staticOptimizationData.selected_mvs || [];
        } else if (optimizationData && optimizationData.timestep_data[timestep]) {
            allSelectedMVs = optimizationData.timestep_data[timestep].mvs.map(m => m.mv);
        }

        // 使用MVフィルタリング
        try {
            const mvUsage = await fetchAPI(
                `/api/query-mv-usage/${currentQuerySet}/${queryName}?selected_mvs=${allSelectedMVs.join(',')}`
            );
            highlightMVs = mvUsage.usable_mvs;
        } catch (e) {
            highlightMVs = allSelectedMVs;
        }

        renderTree(explain, svgContainer, highlightMVs);

    } catch (e) {
        console.error(`Failed to load ${queryName}:`, e);
        svgContainer.innerHTML = `<div style="color:red; padding:20px;">Error loading query</div>`;
    }
}

// 指定クエリへスクロール
function scrollToQuery(queryName) {
    const card = document.querySelector(`.query-card[data-query-name="${queryName}"]`);
    if (card) {
        card.scrollIntoView({ behavior: 'smooth', inline: 'center' });
    }
}

// ロード済み全カード更新（最適化結果などが変わった場合）
async function updateAllLoadedQueries() {
    const loadedCards = document.querySelectorAll('.query-card.loaded');
    for (const card of loadedCards) {
        await loadQueryCard(card);
    }
}

// D3.jsでツリー描画（縦方向: 上から下）
function renderTree(planData, container, highlightMVs = []) {
    const svg = d3.select(container).select('svg');
    svg.selectAll('*').remove();

    const width = container.clientWidth - 40;
    const height = container.clientHeight - 40;

    // ツリーデータ構築
    function buildHierarchy(node) {
        const result = {
            name: node['Node Type'],
            nodeId: node.node_id || '',
            relation: node['Relation Name'] || '',
            alias: node['Alias'] || '',
            rows: node['Plan Rows'] || 0,
            width: node['Plan Width'] || 0,
            cost: node['Total Cost'] || 0,
            children: []
        };
        if (node.Plans) {
            result.children = node.Plans.map(buildHierarchy);
        }
        return result;
    }

    const plan = planData.Plan || planData;
    const root = d3.hierarchy(buildHierarchy(plan));

    // ツリーの深さとリーフ数を計算
    const depth = root.height;

    // 木の深さに基づいてSVG高さを計算（各レベル間に十分な間隔を確保）
    const nodeSpacing = 60;  // ノード間の垂直間隔
    const treeHeight = Math.max(400, (depth + 1) * nodeSpacing);

    // 幅はコンテナに収める
    const treeWidth = Math.max(width - 60, 300); // 最小幅確保

    // 縦方向ツリーレイアウト
    const treeLayout = d3.tree()
        .size([treeWidth, treeHeight])
        .separation((a, b) => (a.parent === b.parent ? 1 : 1.5));
    treeLayout(root);

    // SVGサイズを木のサイズに合わせる
    svg.attr('width', Math.max(width, treeWidth + 60)).attr('height', treeHeight + 60);

    const g = svg.append('g').attr('transform', 'translate(30, 30)');

    // リンク描画（直角カギ型）
    g.selectAll('.link')
        .data(root.links())
        .join('path')
        .attr('class', 'link')
        .attr('fill', 'none')
        .attr('d', d => {
            const sx = d.source.x, sy = d.source.y;
            const tx = d.target.x, ty = d.target.y;
            const midY = (sy + ty) / 2;
            return `M${sx},${sy}V${midY}H${tx}V${ty}`;
        });

    // ノード描画
    const node = g.selectAll('.node')
        .data(root.descendants())
        .join('g')
        .attr('class', 'node')
        .attr('transform', d => `translate(${d.x},${d.y})`);

    node.append('rect')
        .attr('x', -45)
        .attr('y', -18)
        .attr('width', 90)
        .attr('height', 36)
        .attr('rx', 4)
        .attr('fill', d => {
            if (highlightMVs.includes(d.data.nodeId)) return '#a6e3a1';
            if (d.data.nodeId.startsWith('leaf_')) return '#fab387';
            if (d.data.nodeId.startsWith('non_leaf_')) return '#89b4fa';
            return '#cdd6f4';
        })
        .attr('stroke', d => highlightMVs.includes(d.data.nodeId) ? '#fff' : 'none')
        .attr('stroke-width', 2);

    // ノードタイプ（1行目）
    node.append('text')
        .attr('dy', -5)
        .attr('text-anchor', 'middle')
        .attr('fill', '#1e1e2e')
        .attr('font-size', '7px')
        .attr('font-weight', '600')
        .text(d => d.data.name);

    // テーブル名またはノードID（2行目）
    node.append('text')
        .attr('dy', 5)
        .attr('text-anchor', 'middle')
        .attr('fill', '#1e1e2e')
        .attr('font-size', '6px')
        .text(d => {
            // リーフノードの場合はテーブル名とノードIDを表示
            if (d.data.nodeId.startsWith('leaf_') && d.data.relation) {
                return `${d.data.relation} (${d.data.nodeId})`;
            }
            return d.data.relation ? d.data.relation : d.data.nodeId;
        });

    // ツールチップ要素（シングルトン）
    let tooltip = d3.select('body').select('.custom-tooltip');
    if (tooltip.empty()) {
        tooltip = d3.select('body').append('div')
            .attr('class', 'custom-tooltip')
            .style('opacity', 0);
    }

    // イベントリスナー追加
    node.on('mouseover', (event, d) => {
        let sizeStr = '';
        if (mvSizesMap && mvSizesMap[d.data.nodeId]) {
            sizeStr = formatBytes(mvSizesMap[d.data.nodeId]);
        } else {
            sizeStr = formatBytes((d.data.rows * d.data.width) || 0) + ' (est)';
        }

        // コスト（作成コスト）を取得
        let costValue = 0;
        if (subqueryCostsMap && subqueryCostsMap[d.data.nodeId]) {
            costValue = subqueryCostsMap[d.data.nodeId];
        } else {
            costValue = d.data.cost || 0;
        }

        // 利得(utility)を取得
        let utilityValue = 0;
        if (mvUtilitiesMap && mvUtilitiesMap[d.data.nodeId]) {
            utilityValue = mvUtilitiesMap[d.data.nodeId];
        }

        tooltip.transition().duration(200).style('opacity', 1);
        tooltip.html(
            `<strong>${d.data.name}</strong><br>` +
            `${d.data.relation || d.data.nodeId}<br>` +
            `<small style="color:#888">${d.data.nodeId}</small><br>` +
            `<hr style="margin:4px 0; border:0; border-top:1px solid #555">` +
            `Size: ${sizeStr}<br>` +
            `Cost: ${costValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}<br>` +
            `Utility: ${utilityValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
        )
            .style('left', (event.clientX + 12) + 'px')
            .style('top', (event.clientY + 12) + 'px');
    })
        .on('mousemove', (event) => {
            tooltip
                .style('left', (event.clientX + 12) + 'px')
                .style('top', (event.clientY + 12) + 'px');
        })
        .on('mouseout', () => {
            tooltip.transition().duration(200).style('opacity', 0);
        });
}

// ベンチマークチャート更新
function updateBenchmarkChart() {
    if (!benchmarkData || !benchmarkData.found) {
        document.getElementById('benchmark-chart').innerHTML = '<div class="loading">No benchmark data</div>';
        document.getElementById('benchmark-line-chart').innerHTML = '';
        ['total-exec-time', 'total-query-time', 'total-migration-time'].forEach(id => {
            document.getElementById(id).textContent = '-';
        });
        return;
    }

    // サマリー更新
    document.getElementById('total-exec-time').textContent = benchmarkData.total_execution_time.toFixed(2);
    document.getElementById('total-query-time').textContent = benchmarkData.total_query_time.toFixed(2);
    document.getElementById('total-migration-time').textContent = benchmarkData.total_migration_time.toFixed(2);

    // チャートデータ作成
    const timesteps = benchmarkData.timesteps.map(t => 'T' + t.timestep);
    const queryTimes = benchmarkData.timesteps.map(t => t.query_time);
    const migrationTimes = benchmarkData.timesteps.map(t => t.migration_time);

    // 1. 積み上げ棒グラフ (Query vs Migration)
    const trace1 = {
        x: timesteps,
        y: queryTimes,
        name: 'クエリ実行時間',
        type: 'bar',
        marker: { color: '#89b4fa' },
        text: queryTimes.map(t => t > 0 ? t.toFixed(2) : ''),
        textposition: 'auto',
        textfont: { color: '#1e1e2e' }
    };

    const trace2 = {
        x: timesteps,
        y: migrationTimes,
        name: 'マイグレーション時間',
        type: 'bar',
        marker: { color: '#f38ba8' },
        text: migrationTimes.map(t => t > 0 ? t.toFixed(2) : ''),
        textposition: 'auto',
        textfont: { color: '#1e1e2e' }
    };

    const barLayout = {
        barmode: 'stack',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: '時間 (秒)' },
        legend: { orientation: 'h', y: 1.1 }
    };

    Plotly.newPlot('benchmark-chart', [trace1, trace2], barLayout, { responsive: true });

    // 2. 折れ線グラフ (Query Time Trend)
    const traceLine = {
        x: timesteps,
        y: queryTimes,
        name: 'クエリ時間推移',
        type: 'scatter',
        mode: 'lines+markers+text',
        line: { color: '#a6e3a1', width: 2 },
        marker: { size: 6, color: '#a6e3a1' },
        text: queryTimes.map(t => t > 0 ? t.toFixed(2) : ''),
        textposition: 'top center',
        textfont: { color: '#a6e3a1' } // テキスト色をラインに合わせる
    };

    const lineLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: 'クエリ実行時間 (秒)' },
        showlegend: false
    };

    Plotly.newPlot('benchmark-line-chart', [traceLine], lineLayout, { responsive: true });
}

// 比較タブセットアップ（フォルダ選択など）
async function setupComparisonTab() {
    const folderSelect = document.getElementById('comparison-folder-select');
    const fileSelect = document.getElementById('comparison-add-file-select');
    const addBtn = document.getElementById('add-comparison-file-btn');

    // フォルダ一覧を読み込み（フラットなリストとして取得）
    await loadComparisonFolders();

    // フォルダ変更時にファイル一覧を更新
    folderSelect.onchange = () => loadComparisonFiles();

    // 追加ボタン
    addBtn.onclick = () => {
        const folder = folderSelect.value;
        const file = fileSelect.value;
        if (!file) return;

        // 重複チェック
        const exists = comparisonSelectedFiles.some(f => f.folder === folder && f.file === file);
        if (exists) {
            alert('このファイルはすでに追加されています');
            return;
        }

        const folderDisplay = folder === '(root)' ? '(root)' : folder.split('/').pop();
        comparisonSelectedFiles.push({
            folder: folder,
            file: file,
            label: `${folderDisplay}/${file.replace('.json', '')}`
        });
        renderComparisonFileList();
    };

    // 初期ファイル一覧読み込み
    await loadComparisonFiles();
    renderComparisonFileList();
}

// 比較用フォルダ一覧を読み込み
async function loadComparisonFolders() {
    const folderSelect = document.getElementById('comparison-folder-select');
    folderSelect.innerHTML = '';

    // APIから再帰的にフォルダを取得する関数
    async function collectFolders(path, depth = 0) {
        const data = await fetchAPI(`/api/subfolders/${currentQuerySet}?path=${encodeURIComponent(path)}`);
        const folders = [];

        // 結果があるフォルダを追加
        if (data.has_results) {
            const indent = '　'.repeat(depth);
            folders.push({
                value: data.current_path,
                label: indent + data.current_path
            });
        }

        // サブフォルダを再帰処理
        for (const folder of data.folders) {
            if (folder.has_results || folder.has_children) {
                const subFolders = await collectFolders(folder.path, depth + 1);
                folders.push(...subFolders);
            }
        }

        return folders;
    }

    const allFolders = await collectFolders('');

    allFolders.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.value;
        opt.textContent = f.label;
        folderSelect.appendChild(opt);
    });
}

// 比較用ファイル一覧を読み込み（ベンチマーク結果ファイルを表示）
async function loadComparisonFiles() {
    const folderSelect = document.getElementById('comparison-folder-select');
    const fileSelect = document.getElementById('comparison-add-file-select');
    fileSelect.innerHTML = '';

    const folder = folderSelect.value || '(root)';
    const subfolder = folder === '(root)' ? '' : folder;

    try {
        const files = await fetchAPI(`/api/result-files/${currentQuerySet}?subfolder=${encodeURIComponent(subfolder)}`);

        // 動的ベンチマークファイル
        if (files.benchmark) {
            files.benchmark.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.textContent = `[動的] ${f}`;
                fileSelect.appendChild(opt);
            });
        }

        // 適応的ベンチマークファイル
        if (files.adaptive_benchmark) {
            files.adaptive_benchmark.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.textContent = `[適応的] ${f}`;
                fileSelect.appendChild(opt);
            });
        }

        // 静的ベンチマークファイル
        if (files.static_benchmark) {
            files.static_benchmark.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.textContent = `[静的] ${f}`;
                fileSelect.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Failed to load comparison files:', e);
    }
}

// 比較用ファイルリスト描画（選択済みファイル）
function renderComparisonFileList() {
    const container = document.getElementById('comparison-file-list');
    container.innerHTML = '';

    if (comparisonSelectedFiles.length === 0) {
        container.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.9em;">比較対象が選択されていません。<br>上のコントロールからファイルを追加してください。</span>';
        return;
    }

    comparisonSelectedFiles.forEach((item, index) => {
        const div = document.createElement('div');
        div.style.display = 'flex';
        div.style.alignItems = 'center';
        div.style.marginBottom = '6px';
        div.style.padding = '4px 8px';
        div.style.background = 'var(--bg-tertiary)';
        div.style.borderRadius = '4px';

        const label = document.createElement('span');
        label.style.flex = '1';
        label.style.fontSize = '0.85em';
        label.style.wordBreak = 'break-all';
        label.textContent = item.label;

        const removeBtn = document.createElement('button');
        removeBtn.textContent = '✕';
        removeBtn.style.marginLeft = '8px';
        removeBtn.style.padding = '2px 6px';
        removeBtn.style.background = 'var(--accent-red)';
        removeBtn.style.color = '#fff';
        removeBtn.style.border = 'none';
        removeBtn.style.borderRadius = '3px';
        removeBtn.style.cursor = 'pointer';
        removeBtn.onclick = () => {
            comparisonSelectedFiles.splice(index, 1);
            renderComparisonFileList();
        };

        div.appendChild(label);
        div.appendChild(removeBtn);
        container.appendChild(div);
    });
}

// 比較チャート更新
async function updateComparisonCharts() {
    if (comparisonSelectedFiles.length === 0) {
        alert('比較するファイルを選択してください');
        return;
    }

    // データ並列取得（各ファイルのフォルダを使用）
    const results = await Promise.all(comparisonSelectedFiles.map(async item => {
        try {
            const subfolder = item.folder === '(root)' ? '' : item.folder;
            const data = await fetchAPI(`/api/benchmark-result/${currentQuerySet}/${item.file}?subfolder=${encodeURIComponent(subfolder)}`);
            return { file: item.file, label: item.label, folder: item.folder, data };
        } catch (e) {
            console.error(`Failed to fetch ${item.file}:`, e);
            return { file: item.file, label: item.label, folder: item.folder, data: null };
        }
    }));

    const validResults = results.filter(r => r.data && r.data.found);
    if (validResults.length === 0) {
        alert('有効な結果が見つかりませんでした');
        return;
    }

    // カラーパレット
    const colors = [
        '#89b4fa', '#f38ba8', '#a6e3a1', '#fab387', '#cba6f7',
        '#f5c2e7', '#94e2d5', '#f9e2af', '#74c7ec', '#b4befe'
    ];

    // ファイル名短縮ヘルパー（ラベルを使用）
    const shortenName = (result) => result.label || result.file.replace(/benchmark_results_|_opt\.json/g, '').replace(/^dynamic_/, '');

    // 0. サマリーテーブル更新
    const summaryBody = document.querySelector('#comparison-summary-table tbody');
    summaryBody.innerHTML = '';
    validResults.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-weight: bold;">${shortenName(r)}</td>
            <td>${r.data.total_execution_time.toFixed(2)}</td>
            <td>${r.data.total_query_time.toFixed(2)}</td>
            <td>${r.data.total_migration_time.toFixed(2)}</td>
        `;
        summaryBody.appendChild(row);
    });

    // 1. 棒グラフ (Grouped by Method, Stacked Query+Migration)
    const allTimesteps = new Set();
    validResults.forEach(r => r.data.timesteps.forEach(t => allTimesteps.add(t.timestep)));
    const sortedTimesteps = Array.from(allTimesteps).sort((a, b) => a - b);
    const xLabels = sortedTimesteps.map(ts => 'T' + ts);

    // 各ファイルごとにトレースを作成
    const barTraces = [];
    validResults.forEach((r, i) => {
        const color = colors[i % colors.length];
        const name = shortenName(r);

        const queryTimes = sortedTimesteps.map(ts => {
            const tsData = r.data.timesteps.find(d => d.timestep === ts);
            return tsData ? tsData.query_time : 0;
        });

        const migrationTimes = sortedTimesteps.map(ts => {
            const tsData = r.data.timesteps.find(d => d.timestep === ts);
            return tsData ? tsData.migration_time : 0;
        });

        // クエリ時間（濃い色）
        barTraces.push({
            x: xLabels,
            y: queryTimes,
            name: name,
            type: 'bar',
            marker: { color: color },
            offsetgroup: i,  // 同じファイルは同じオフセットグループ
            legendgroup: name,
            showlegend: true,
            hovertemplate: `${name}<br>クエリ: %{y:.2f}秒<extra></extra>`
        });

        // マイグレーション時間（薄い色、積み上げ）
        barTraces.push({
            x: xLabels,
            y: migrationTimes,
            name: name + ' (Migration)',
            type: 'bar',
            marker: { color: color, opacity: 0.4 },
            offsetgroup: i,  // 同じファイルは同じオフセットグループ
            base: queryTimes,  // クエリ時間の上に積み上げ
            legendgroup: name,
            showlegend: false,
            hovertemplate: `${name}<br>マイグレーション: %{y:.2f}秒<extra></extra>`
        });
    });

    const barLayout = {
        barmode: 'group',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 40, b: 50 },
        xaxis: {
            title: 'タイムステップ',
            tickangle: 0
        },
        yaxis: { title: '実行時間 (秒)' },
        showlegend: true,
        legend: { orientation: 'h', y: 1.05, x: 0.5, xanchor: 'center' }
    };

    Plotly.newPlot('comparison-bar-chart', barTraces, barLayout, { responsive: true });

    // 2. 折れ線グラフ (Query Time Trend)
    const lineTraces = validResults.map((r, i) => {
        const timesteps = r.data.timesteps.map(t => 'T' + t.timestep);
        const queryTimes = r.data.timesteps.map(t => t.query_time);

        return {
            x: timesteps,
            y: queryTimes,
            name: shortenName(r),
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: colors[i % colors.length], width: 2 },
            marker: { size: 6 }
        };
    });

    const lineLayout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 30, b: 40 },
        xaxis: { title: 'タイムステップ' },
        yaxis: { title: 'クエリ実行時間 (秒)' },
        showlegend: true,
        legend: { orientation: 'h', y: 1.1 }
    };

    Plotly.newPlot('comparison-line-chart', lineTraces, lineLayout, { responsive: true });

    // 3. 比較MVタイムライン
    // 全MVセット取得
    const allMVs = new Set();
    validResults.forEach(r => {
        r.data.timesteps.forEach(t => {
            if (t.selected_mvs) {
                t.selected_mvs.forEach(mv => allMVs.add(mv.name));
            }
        });
    });
    const sortedMVs = naturalSort([...allMVs]); // MV1, MV2...

    // 手法数に応じたバーの配置計算
    const numMethods = validResults.length;
    const groupHeight = 0.8; // 1つのMV領域(高さ1.0)のうち0.8を使う
    const barHeight = groupHeight / Math.max(numMethods, 1);

    // カスタム凡例の生成 (スクロール外に出すため)
    const legendContainer = document.getElementById('comparison-timeline-legend');
    if (legendContainer) {
        legendContainer.innerHTML = '';
        validResults.forEach((r, i) => {
            const methodName = shortenName(r);
            const color = colors[i % colors.length];

            const item = document.createElement('div');
            item.style.display = 'flex';
            item.style.alignItems = 'center';
            item.style.gap = '6px';
            item.style.fontSize = '0.9em';
            item.style.backgroundColor = 'var(--bg-tertiary)';
            item.style.padding = '4px 8px';
            item.style.borderRadius = '4px';

            const box = document.createElement('div');
            box.style.width = '12px';
            box.style.height = '12px';
            box.style.backgroundColor = color;
            box.style.borderRadius = '2px';

            const text = document.createElement('span');
            text.textContent = methodName;
            text.style.color = 'var(--text-primary)';

            item.appendChild(box);
            item.appendChild(text);
            legendContainer.appendChild(item);
        });
    }

    // Trace作成
    const timelineTraces = validResults.map((r, i) => {
        const methodName = shortenName(r);
        const color = colors[i % colors.length];

        // 中心(0)からのオフセット計算
        // i=0 が一番上に来るように計算 (y軸reversed前提)
        // 領域: [-0.4, 0.4]
        const yOffset = - (groupHeight / 2) + (i * barHeight) + (barHeight / 2);

        const yData = [];
        const baseData = [];
        const xData = []; // duration
        const textData = [];

        r.data.timesteps.forEach(t => {
            if (t.selected_mvs) {
                t.selected_mvs.forEach(mv => {
                    const mvIdx = sortedMVs.indexOf(mv.name);
                    if (mvIdx === -1) return;

                    yData.push(mvIdx + yOffset);
                    baseData.push(t.timestep);
                    xData.push(1); // 1 timestep width
                    textData.push(`T${t.timestep}: ${mv.name} [${methodName}]`);
                });
            }
        });

        return {
            type: 'bar',
            orientation: 'h',
            name: methodName,
            y: yData,
            base: baseData, // Start position (timestep)
            x: xData,       // Width (duration)
            width: barHeight * 0.9, // 隙間を空ける
            marker: { color: color },
            hovertext: textData,
            hoverinfo: 'text',
            showlegend: false // カスタム凡例を使うので非表示
        };
    });

    // 最大タイムステップ数
    let maxTimestep = 15;
    validResults.forEach(r => {
        if (r.data.timesteps.length > 0) {
            const lastTs = r.data.timesteps[r.data.timesteps.length - 1].timestep;
            if (lastTs > maxTimestep) maxTimestep = lastTs;
        }
    });

    // 境界線 (Shapes) - MVごとの区切り線
    const shapes = [];
    for (let i = 0; i < sortedMVs.length - 1; i++) {
        shapes.push({
            type: 'line',
            x0: -0.5,
            x1: maxTimestep + 0.5,
            y0: i + 0.5,
            y1: i + 0.5,
            line: {
                color: '#45475a', // 区切り線色
                width: 1
            }
        });
    }

    // 高さの動的計算 (MV数 * 高さ係数)
    const timelineHeight = Math.max(600, sortedMVs.length * 50 + 100);

    const timelineLayout = {
        height: timelineHeight,
        title: '比較MVタイムライン',
        xaxis: {
            title: 'タイムステップ',
            dtick: 1,
            range: [-0.5, maxTimestep + 0.5],
            zeroline: false
        },
        yaxis: {
            tickvals: sortedMVs.map((_, i) => i),
            ticktext: sortedMVs,
            range: [-0.5, sortedMVs.length - 0.5],
            autorange: 'reversed', // 上から下に表示
            automargin: true,
            tickfont: { size: 12 }
        },
        shapes: shapes,
        barmode: 'overlay', // 独自座標を使用するためOverlay
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 200, r: 20, t: 50, b: 40 }, // タイトル用に上マージン確保
        showlegend: false
    };

    Plotly.newPlot('comparison-mv-timeline', timelineTraces, timelineLayout, { responsive: true });
}

// =====================================
// 頻度変化タブ関連
// =====================================

// 頻度ファイル一覧を取得・表示
async function loadFrequencyFiles() {
    const select = document.getElementById('frequency-file-select');
    if (!select) return;

    // 現在の選択値を保存して再描画後に復元できるようにする
    const previousSelection = select.value;

    try {
        const allFiles = await fetchAPI('/api/all-frequency-files');
        select.innerHTML = '';
        
        let hasPrevious = false;
        
        for (const qs in allFiles) {
            const group = document.createElement('optgroup');
            group.label = `📁 ${qs}`;
            
            allFiles[qs].forEach(f => {
                const opt = document.createElement('option');
                opt.value = `${qs}/${f}`;
                opt.textContent = f;
                
                // 以前の選択状態を復元、または現在のクエリセットのファイルをデフォルト選択
                if (opt.value === previousSelection) {
                    opt.selected = true;
                    hasPrevious = true;
                } else if (!hasPrevious && !previousSelection && qs === currentQuerySet) {
                    opt.selected = true;
                    hasPrevious = true;
                }
                
                group.appendChild(opt);
            });
            select.appendChild(group);
        }
    } catch (e) {
        console.error('Failed to load frequency files:', e);
    }
}

// 頻度データを読み込んでチャート表示
async function loadFrequencyData() {
    const select = document.getElementById('frequency-file-select');
    if (!select || !select.value) return;

    // valueは "query_set/filename" の形式
    const [targetQs, targetFile] = select.value.split('/');
    if (!targetQs || !targetFile) return;

    try {
        // 対象のクエリセットからデータを取得
        const data = await fetchAPI(`/api/frequency-data/${targetQs}/${targetFile}`);

        // 情報表示
        const infoEl = document.getElementById('frequency-info');
        if (infoEl) {
            infoEl.innerHTML = `
                <strong>説明:</strong> ${data.description || 'N/A'}<br>
                <strong>備考:</strong> ${data.note || 'N/A'}<br>
                <strong>総クエリ数:</strong> ${data.total_queries} / <strong>タイムステップ数:</strong> ${data.timesteps}
            `;
        }

        // グループ情報表示
        const oddInfo = document.getElementById('odd-group-info');
        const evenInfo = document.getElementById('even-group-info');

        const oddQueries = Object.keys(data.odd_group);
        const evenQueries = Object.keys(data.even_group);

        if (oddInfo) {
            oddInfo.textContent = `${oddQueries.length}個のクエリ: ${oddQueries.slice(0, 10).join(', ')}${oddQueries.length > 10 ? '...' : ''}`;
        }
        if (evenInfo) {
            evenInfo.textContent = `${evenQueries.length}個のクエリ: ${evenQueries.slice(0, 10).join(', ')}${evenQueries.length > 10 ? '...' : ''}`;
        }

        // チャート描画
        renderFrequencyChart(data);
        renderQueryTimelineChart(data);

    } catch (e) {
        console.error('Failed to load frequency data:', e);
    }
}

// クエリタイムラインを描画
function renderQueryTimelineChart(data) {
    const allQueriesData = { ...data.odd_group, ...data.even_group };
    const queryNames = naturalSort(Object.keys(allQueriesData));
    const timesteps = data.timesteps;

    // X軸ラベル
    const xLabels = Array.from({ length: timesteps }, (_, i) => 'T' + (i + 1));

    // Z値（頻度）データ配列 (y軸がqueryNames, x軸がtimesteps)
    const zData = queryNames.map(q => allQueriesData[q]);
    
    // 表示用テキストデータ。頻度が0の場合は空文字、0より大きい場合は数値を表示
    const textData = zData.map(row => row.map(val => val > 0 ? (Math.round(val * 10) / 10).toString() : ''));

    const chartHeight = Math.max(400, queryNames.length * 25 + 80);
    document.getElementById('query-timeline-chart').style.height = chartHeight + 'px';

    const trace = {
        z: zData,
        x: xLabels,
        y: queryNames,
        type: 'heatmap',
        // 0と1以上を明確に区別し、使い始めを緑にするカラースケール
        colorscale: [
            [0, '#313244'],          // 0: ダークグレー（無）
            [0.001, '#313244'],      // (境界線) 0付近はダークグレーを維持
            [0.001, '#a6e3a1'],      // 0より大きい（使い始め）: 緑
            [0.4, '#f9e2af'],        // 中頻度: 黄色
            [0.7, '#fab387'],        // 高頻度: オレンジ
            [1.0, '#f38ba8']         // 最高頻度: 赤
        ],
        showscale: true,         // カラーバーを表示して目安をわかりやすくする
        text: textData,
        texttemplate: '%{text}', // 枠内に値を表示
        textfont: { color: '#1e1e2e' }, // ダークテーマに合わせて見やすい色
        xgap: 1, 
        ygap: 1,
        hovertemplate: 'クエリ: %{y}<br>タイムステップ: %{x}<br>頻度: %{z}<extra></extra>'
    };

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 80, r: 20, t: 20, b: 40 },
        xaxis: { title: 'タイムステップ', side: 'top' },
        yaxis: { title: '', autorange: 'reversed' },
        height: chartHeight
    };

    Plotly.newPlot('query-timeline-chart', [trace], layout, { responsive: true });
}

// 頻度変化チャートを描画
function renderFrequencyChart(data) {
    const oddGroup = data.odd_group;
    const evenGroup = data.even_group;
    const timesteps = data.timesteps;

    // X軸ラベル
    const xLabels = Array.from({ length: timesteps }, (_, i) => 'T' + (i + 1));

    // 代表クエリを選んで頻度を取得（全クエリは同じパターンのはず）
    const firstOddKey = Object.keys(oddGroup)[0];
    const firstEvenKey = Object.keys(evenGroup)[0];

    const oddFrequencies = firstOddKey ? oddGroup[firstOddKey] : [];
    const evenFrequencies = firstEvenKey ? evenGroup[firstEvenKey] : [];

    const traces = [
        {
            x: xLabels,
            y: oddFrequencies,
            name: '奇数クエリ (1, 3, 5, ...)',
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: '#89b4fa', width: 2 },
            marker: { size: 8 }
        },
        {
            x: xLabels,
            y: evenFrequencies,
            name: '偶数クエリ (2, 4, 6, ...)',
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: '#f38ba8', width: 2 },
            marker: { size: 8 }
        }
    ];

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: '#1e1e2e',
        font: { color: '#cdd6f4' },
        margin: { l: 60, r: 20, t: 40, b: 50 },
        xaxis: {
            title: 'タイムステップ',
            tickangle: -45
        },
        yaxis: {
            title: '頻度',
            rangemode: 'tozero'
        },
        showlegend: true,
        legend: { orientation: 'h', y: 1.1, x: 0.5, xanchor: 'center' }
    };

    Plotly.newPlot('frequency-chart', traces, layout, { responsive: true });
}

// 頻度タブのイベントハンドラを設定
function setupFrequencyTab() {
    const loadBtn = document.getElementById('load-frequency-btn');
    if (loadBtn) {
        loadBtn.addEventListener('click', loadFrequencyData);
    }
}

// 初期化実行
init().catch(console.error);

