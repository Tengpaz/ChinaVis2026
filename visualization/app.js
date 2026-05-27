const data = window.CHINAVIS_DATA;

const topicById = new Map(data.topics.map((topic) => [topic.id, topic]));
const collectionById = new Map(data.collections.map((collection) => [collection.id, collection]));

const state = {
  search: "",
  collectionId: "all",
  topicId: "all",
  focusTopicId: data.meta.strongestTopicId,
};

const els = {
  metricGrid: document.querySelector("#metricGrid"),
  searchInput: document.querySelector("#searchInput"),
  collectionSelect: document.querySelector("#collectionSelect"),
  topicSelect: document.querySelector("#topicSelect"),
  resetButton: document.querySelector("#resetButton"),
  topicBars: document.querySelector("#topicBars"),
  networkChart: document.querySelector("#networkChart"),
  heatmap: document.querySelector("#heatmap"),
  playList: document.querySelector("#playList"),
  playCountText: document.querySelector("#playCountText"),
  snippetPanel: document.querySelector("#snippetPanel"),
  selectionStatus: document.querySelector("#selectionStatus"),
  tooltip: document.querySelector("#tooltip"),
};

function formatNumber(value, digits = 0) {
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function percentage(value) {
  return `${formatNumber(value * 100, 1)}%`;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  return node;
}

function colorForTopic(topicId) {
  return topicById.get(Number(topicId))?.color || "#6f7682";
}

function activeTopicId() {
  return state.topicId === "all" ? state.focusTopicId : Number(state.topicId);
}

function topicLabel(topicId) {
  return topicById.get(Number(topicId))?.label || "全部主题";
}

function mixHex(hex, amount) {
  const safe = hex.replace("#", "");
  const r = parseInt(safe.slice(0, 2), 16);
  const g = parseInt(safe.slice(2, 4), 16);
  const b = parseInt(safe.slice(4, 6), 16);
  const mix = (channel) => Math.round(255 - (255 - channel) * amount);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}

function attachTooltip(node, text) {
  node.addEventListener("pointerenter", (event) => showTooltip(event, text));
  node.addEventListener("pointermove", moveTooltip);
  node.addEventListener("pointerleave", hideTooltip);
}

function showTooltip(event, text) {
  els.tooltip.textContent = text;
  els.tooltip.style.opacity = "1";
  moveTooltip(event);
}

function moveTooltip(event) {
  els.tooltip.style.left = `${event.clientX}px`;
  els.tooltip.style.top = `${event.clientY}px`;
}

function hideTooltip() {
  els.tooltip.style.opacity = "0";
}

function syncControls() {
  els.searchInput.value = state.search;
  els.collectionSelect.value = state.collectionId;
  els.topicSelect.value = state.topicId;
}

function initControls() {
  const allCollection = document.createElement("option");
  allCollection.value = "all";
  allCollection.textContent = "全部集合";
  els.collectionSelect.appendChild(allCollection);

  data.collections.forEach((collection) => {
    const option = document.createElement("option");
    option.value = collection.id;
    option.textContent = `${collection.id} ${collection.name} (${collection.playCount})`;
    els.collectionSelect.appendChild(option);
  });

  const allTopic = document.createElement("option");
  allTopic.value = "all";
  allTopic.textContent = "全部主题";
  els.topicSelect.appendChild(allTopic);

  data.topics.forEach((topic) => {
    const option = document.createElement("option");
    option.value = String(topic.id);
    option.textContent = topic.label;
    els.topicSelect.appendChild(option);
  });

  els.searchInput.addEventListener("input", () => {
    state.search = els.searchInput.value.trim();
    renderPlayList();
  });

  els.collectionSelect.addEventListener("change", () => {
    state.collectionId = els.collectionSelect.value;
    renderAll();
  });

  els.topicSelect.addEventListener("change", () => {
    state.topicId = els.topicSelect.value;
    if (state.topicId !== "all") state.focusTopicId = Number(state.topicId);
    renderAll();
  });

  els.resetButton.addEventListener("click", () => {
    state.search = "";
    state.collectionId = "all";
    state.topicId = "all";
    state.focusTopicId = data.meta.strongestTopicId;
    syncControls();
    renderAll();
  });
}

function renderMetrics() {
  clear(els.metricGrid);
  const metrics = [
    ["剧目数", formatNumber(data.meta.playCount), "完成主题权重归一化"],
    ["数据集合", formatNumber(data.meta.collectionCount), "跨来源、跨流派比较"],
    ["主题类别", formatNumber(data.meta.topicCount), "含历史、家庭、公案等"],
    ["最强主题", data.meta.strongestTopicLabel, "按总权重累计"],
    ["最强组合", data.meta.strongestPairLabel, "按主题共现权重"],
    ["平均活跃主题", formatNumber(data.meta.averageActiveTopics, 2), "每部剧约含多个主题"],
  ];
  metrics.forEach(([label, value, note]) => {
    const item = el("div", "metric");
    item.appendChild(el("span", "", label));
    item.appendChild(el("strong", "", value));
    item.appendChild(el("span", "", note));
    els.metricGrid.appendChild(item);
  });
}

function setTopicFilter(topicId) {
  state.topicId = String(topicId);
  state.focusTopicId = Number(topicId);
  syncControls();
  renderAll();
}

function setCollectionTopic(collectionId, topicId) {
  state.collectionId = collectionId;
  state.topicId = String(topicId);
  state.focusTopicId = Number(topicId);
  syncControls();
  renderAll();
}

function renderTopicBars() {
  clear(els.topicBars);
  const width = 760;
  const rowHeight = 34;
  const margin = { top: 22, right: 130, bottom: 34, left: 116 };
  const height = margin.top + margin.bottom + rowHeight * data.topics.length;
  const maxTotal = Math.max(...Object.values(data.topicTotals));
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  const chartWidth = width - margin.left - margin.right;

  data.topics.forEach((topic, index) => {
    const y = margin.top + index * rowHeight;
    const total = data.topicTotals[String(topic.id)];
    const count = data.dominantTopicCounts[String(topic.id)] || 0;
    const barWidth = (total / maxTotal) * chartWidth;
    const isActive = activeTopicId() === topic.id;
    const group = svgEl("g", { class: `clickable ${isActive ? "" : "is-dimmed"}` });
    group.addEventListener("click", () => setTopicFilter(topic.id));
    attachTooltip(group, `${topic.label}：总权重 ${formatNumber(total, 1)}，主导 ${count} 部剧`);

    group.appendChild(svgEl("text", {
      x: margin.left - 12,
      y: y + 20,
      "text-anchor": "end",
      class: "svg-label",
    })).textContent = topic.label;

    group.appendChild(svgEl("rect", {
      x: margin.left,
      y,
      width: chartWidth,
      height: 22,
      rx: 4,
      fill: "#e8edf2",
    }));
    group.appendChild(svgEl("rect", {
      x: margin.left,
      y,
      width: Math.max(barWidth, 2),
      height: 22,
      rx: 4,
      fill: topic.color,
    }));
    group.appendChild(svgEl("text", {
      x: margin.left + Math.min(barWidth + 8, chartWidth + 8),
      y: y + 16,
      class: "svg-muted",
    })).textContent = `${formatNumber(total, 1)} / ${count} 部`;
    svg.appendChild(group);
  });

  svg.appendChild(svgEl("text", {
    x: margin.left,
    y: height - 8,
    class: "svg-muted",
  })).textContent = "点击主题可筛选剧目并查看代表片段";

  els.topicBars.appendChild(svg);
}

function renderNetwork() {
  clear(els.networkChart);
  const width = 540;
  const height = 430;
  const cx = width / 2;
  const cy = height / 2 + 4;
  const radius = 154;
  const maxTotal = Math.max(...Object.values(data.topicTotals));
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  const positions = new Map();

  data.topics.forEach((topic, index) => {
    const angle = -Math.PI / 2 + (index / data.topics.length) * Math.PI * 2;
    positions.set(topic.id, {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      angle,
    });
  });

  data.cooccurrences.slice().reverse().forEach((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    const active = activeTopicId();
    const highlighted = edge.source === active || edge.target === active;
    const line = svgEl("line", {
      x1: source.x,
      y1: source.y,
      x2: target.x,
      y2: target.y,
      stroke: highlighted ? colorForTopic(active) : "#9f9689",
      "stroke-width": 1 + edge.normalizedWeight * 8,
      "stroke-opacity": highlighted ? 0.62 : 0.2 + edge.normalizedWeight * 0.25,
      "stroke-linecap": "round",
    });
    attachTooltip(line, `${topicLabel(edge.source)} - ${topicLabel(edge.target)}：共现权重 ${formatNumber(edge.weight, 2)}`);
    svg.appendChild(line);
  });

  data.cooccurrences.slice(0, 4).forEach((edge, index) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    const text = svgEl("text", {
      x: (source.x + target.x) / 2,
      y: (source.y + target.y) / 2 - 8 - index * 3,
      "text-anchor": "middle",
      class: "svg-muted",
    });
    text.textContent = `${topicLabel(edge.source)}-${topicLabel(edge.target)}`;
    svg.appendChild(text);
  });

  data.topics.forEach((topic) => {
    const pos = positions.get(topic.id);
    const nodeRadius = 12 + (data.topicTotals[String(topic.id)] / maxTotal) * 20;
    const active = activeTopicId() === topic.id;
    const group = svgEl("g", { class: "clickable" });
    group.addEventListener("click", () => setTopicFilter(topic.id));
    attachTooltip(group, `${topic.label}：关键词 ${topic.keywords.slice(0, 8).join("、") || "无"}`);

    group.appendChild(svgEl("circle", {
      cx: pos.x,
      cy: pos.y,
      r: nodeRadius,
      fill: topic.color,
      "fill-opacity": active ? 0.95 : 0.72,
      stroke: active ? "#252629" : "#fbfcfd",
      "stroke-width": active ? 2.4 : 1.4,
    }));

    const labelX = pos.x + Math.cos(pos.angle) * (nodeRadius + 16);
    const labelY = pos.y + Math.sin(pos.angle) * (nodeRadius + 16) + 4;
    const anchor = Math.cos(pos.angle) > 0.25 ? "start" : Math.cos(pos.angle) < -0.25 ? "end" : "middle";
    group.appendChild(svgEl("text", {
      x: labelX,
      y: labelY,
      "text-anchor": anchor,
      class: "svg-label",
    })).textContent = topic.label;
    svg.appendChild(group);
  });

  els.networkChart.appendChild(svg);
}

function renderHeatmap() {
  clear(els.heatmap);
  const left = 218;
  const top = 60;
  const colWidth = 88;
  const rowHeight = 28;
  const width = left + colWidth * data.topics.length + 28;
  const height = top + rowHeight * data.collections.length + 26;
  const maxMean = Math.max(
    ...data.collections.flatMap((collection) => Object.values(collection.meanWeights)),
  );
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  svg.style.minWidth = `${width}px`;

  data.topics.forEach((topic, index) => {
    const x = left + index * colWidth + colWidth / 2;
    const text = svgEl("text", {
      x,
      y: 28,
      "text-anchor": "middle",
      class: "svg-label",
    });
    text.textContent = topic.label;
    svg.appendChild(text);
  });

  data.collections.forEach((collection, rowIndex) => {
    const y = top + rowIndex * rowHeight;
    const rowActive = state.collectionId === collection.id;
    const label = svgEl("text", {
      x: left - 12,
      y: y + 18,
      "text-anchor": "end",
      class: `svg-label clickable ${state.collectionId !== "all" && !rowActive ? "is-dimmed" : ""}`,
    });
    label.textContent = `${collection.id} ${collection.name}`;
    label.addEventListener("click", () => {
      state.collectionId = collection.id;
      syncControls();
      renderAll();
    });
    attachTooltip(label, `${collection.name}：${collection.playCount} 部剧`);
    svg.appendChild(label);

    data.topics.forEach((topic, colIndex) => {
      const x = left + colIndex * colWidth;
      const mean = collection.meanWeights[String(topic.id)];
      const active = rowActive && activeTopicId() === topic.id;
      const amount = 0.14 + (mean / maxMean) * 0.86;
      const rect = svgEl("rect", {
        x: x + 3,
        y: y + 3,
        width: colWidth - 6,
        height: rowHeight - 6,
        rx: 4,
        fill: mixHex(topic.color, amount),
        stroke: active ? "#252629" : "#fbfcfd",
        "stroke-width": active ? 2 : 1,
        class: "clickable",
      });
      rect.addEventListener("click", () => setCollectionTopic(collection.id, topic.id));
      attachTooltip(rect, `${collection.name} / ${topic.label}：均值 ${percentage(mean)}`);
      svg.appendChild(rect);

      if (mean >= 0.45) {
        const value = svgEl("text", {
          x: x + colWidth / 2,
          y: y + 18,
          "text-anchor": "middle",
          class: "svg-muted",
        });
        value.textContent = percentage(mean);
        svg.appendChild(value);
      }
    });
  });

  els.heatmap.appendChild(svg);
}

function filteredPlays() {
  const keyword = state.search.toLowerCase();
  return data.plays
    .filter((play) => {
      if (state.collectionId !== "all" && play.collectionId !== state.collectionId) return false;
      if (state.topicId !== "all" && (play.weights[state.topicId] || 0) <= 0) return false;
      if (!keyword) return true;
      return `${play.title} ${play.collectionName} ${play.comboLabel}`.toLowerCase().includes(keyword);
    })
    .sort((a, b) => {
      if (state.topicId !== "all") {
        return (b.weights[state.topicId] || 0) - (a.weights[state.topicId] || 0);
      }
      const aPrimary = a.weights[String(a.primaryTopicId)] || 0;
      const bPrimary = b.weights[String(b.primaryTopicId)] || 0;
      return bPrimary - aPrimary || a.title.localeCompare(b.title, "zh-CN");
    });
}

function renderPlayList() {
  clear(els.playList);
  const plays = filteredPlays();
  const visible = plays.slice(0, 80);
  const topicId = state.topicId === "all" ? null : state.topicId;
  els.playCountText.textContent = `匹配 ${formatNumber(plays.length)} 部剧，列表显示前 ${formatNumber(visible.length)} 部。`;

  if (!visible.length) {
    els.playList.appendChild(el("div", "empty-state", "没有匹配的剧目，请调整检索词或筛选条件。"));
    return;
  }

  const fragment = document.createDocumentFragment();
  visible.forEach((play) => {
    const item = el("article", "play-item");
    const head = el("div", "play-head");
    head.appendChild(el("div", "play-title", play.title));
    const scoreText = topicId
      ? `${topicLabel(topicId)} ${percentage(play.weights[topicId] || 0)}`
      : `${topicLabel(play.primaryTopicId)} ${percentage(play.weights[String(play.primaryTopicId)] || 0)}`;
    head.appendChild(el("div", "play-score", scoreText));
    item.appendChild(head);

    item.appendChild(el("div", "play-meta", `${play.collectionId} ${play.collectionName}`));

    const bar = el("div", "weight-bar");
    data.topics.forEach((topic) => {
      const weight = play.weights[String(topic.id)] || 0;
      if (weight <= 0) return;
      const segment = el("div", "weight-segment");
      segment.style.width = `${weight * 100}%`;
      segment.style.background = topic.color;
      segment.title = `${topic.label} ${percentage(weight)}`;
      bar.appendChild(segment);
    });
    item.appendChild(bar);
    item.appendChild(el("div", "combo-label", play.comboLabel));
    attachTooltip(item, `${play.title}：${play.comboLabel}`);
    fragment.appendChild(item);
  });

  els.playList.appendChild(fragment);
}

function renderSnippets() {
  clear(els.snippetPanel);
  const topicId = activeTopicId();
  const topic = topicById.get(topicId);
  const title = el("h3", "", topic.label);
  title.style.color = topic.color;
  els.snippetPanel.appendChild(title);

  const keywords = el("ul", "keyword-strip");
  topic.keywords.slice(0, 16).forEach((word) => {
    keywords.appendChild(el("li", "", word));
  });
  if (!topic.keywords.length) {
    keywords.appendChild(el("li", "", "无关键词"));
  }
  els.snippetPanel.appendChild(keywords);

  const topicSnippets = data.snippets.filter((snippet) => snippet.topicId === topicId).slice(0, 3);
  if (!topicSnippets.length) {
    els.snippetPanel.appendChild(el("div", "empty-state", "该主题暂无代表片段。"));
    return;
  }

  topicSnippets.forEach((snippet) => {
    const block = el("div", "snippet");
    block.style.borderLeftColor = topic.color;
    block.appendChild(el("p", "", snippet.snippetShort));
    block.appendChild(el("div", "snippet-meta", `${snippet.title} · 片段得分 ${formatNumber(snippet.score, 1)}`));
    els.snippetPanel.appendChild(block);
  });
}

function renderStatus() {
  const collectionText = state.collectionId === "all" ? "全部集合" : collectionById.get(state.collectionId)?.name;
  const topicText = state.topicId === "all" ? `聚焦：${topicLabel(state.focusTopicId)}` : `筛选：${topicLabel(state.topicId)}`;
  els.selectionStatus.textContent = `${collectionText} · ${topicText}`;
}

function renderAll() {
  renderStatus();
  renderTopicBars();
  renderNetwork();
  renderHeatmap();
  renderPlayList();
  renderSnippets();
}

initControls();
syncControls();
renderMetrics();
renderAll();
